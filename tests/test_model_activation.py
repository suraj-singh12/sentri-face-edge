from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sentriface.config import RuntimeConfig
from sentriface.engine import RecognitionRuntimeSnapshot
from sentriface.model_activation import (
    ModelActivationRefused,
    ModelActivationService,
    PreparedRecognitionRuntime,
)
from sentriface.model_bundle import ModelBundleAuthority


RUNTIME_FACTS = {
    "runtime": "onnxruntime-cpu",
    "provider": "CPUExecutionProvider",
    "detector_input": [1, 3, 640, 640],
    "detector_outputs": 9,
    "recognizer_input": [1, 3, 112, 112],
    "embedding_dimension": 512,
    "calibration_valid": True,
    "usage_valid": True,
    "compatible": True,
}
ACTOR = {"user_id": "admin-id", "username": "admin"}


class _Engine:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.detector = object()
        self.embedder = object()
        self.quality = object()
        self.model_usage = {"usage_basis": "development"}
        self.authority_marker = object()

    def replace_recognition_runtime(self, *, config, detector, embedder, model_usage):
        snapshot = RecognitionRuntimeSnapshot(
            self.config, self.detector, self.embedder, self.quality, self.model_usage,
        )
        self.config = config
        self.detector = detector
        self.embedder = embedder
        self.model_usage = model_usage
        return snapshot

    def restore_recognition_runtime(self, snapshot: RecognitionRuntimeSnapshot) -> None:
        self.config = snapshot.config
        self.detector = snapshot.detector
        self.embedder = snapshot.embedder
        self.quality = snapshot.quality
        self.model_usage = snapshot.model_usage


class ModelActivationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.clock = [datetime(2026, 8, 16, tzinfo=timezone.utc)]
        self.authority = ModelBundleAuthority(self.root / "models", now=lambda: self.clock[0])
        self.engine = _Engine(RuntimeConfig(data_dir=self.root))
        self.fail_at: str | None = None
        self.service = ModelActivationService(
            self.authority,
            self.engine,  # type: ignore[arg-type]
            self._runtime,
            token_secret=b"0123456789abcdef0123456789abcdef",
            now=lambda: self.clock[0],
            failure_injector=self._inject,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_prepare_does_not_activate_and_execute_is_atomic_and_idempotent(self) -> None:
        bundle = self._bundle(b"one")
        stable_engine = self.engine
        stable_authority = self.engine.authority_marker
        prepared = self.service.prepare_model_activation(bundle.bundle_id)
        self.assertIsNone(self.service.active_state())
        self.assertEqual(prepared["runtime_facts"], RUNTIME_FACTS)
        self.assertNotIn(str(self.root), json.dumps(prepared))

        operation = str(uuid.uuid4())
        result = self.service.execute(prepared["token"], operation, actor=ACTOR)
        self.assertTrue(result["committed"])
        self.assertIs(self.engine, stable_engine)
        self.assertIs(self.engine.authority_marker, stable_authority)
        self.assertEqual(self.service.active_state().active_bundle_id, bundle.bundle_id)
        receipt_text = next(self.service.receipts_dir.glob("*.json")).read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), receipt_text)
        self.assertNotIn(str(prepared["token"]), receipt_text)
        retry = self.service.execute(prepared["token"], operation, actor=ACTOR)
        self.assertTrue(retry["idempotent"])
        other = self._bundle(b"other")
        other_plan = self.service.prepare_model_activation(other.bundle_id)
        with self.assertRaisesRegex(ModelActivationRefused, "conflicting intent"):
            self.service.execute(other_plan["token"], operation, actor=ACTOR)

    def test_stale_expired_and_conflicting_preparations_are_refused(self) -> None:
        first = self._bundle(b"one")
        second = self._bundle(b"two")
        stale = self.service.prepare_model_activation(second.bundle_id)
        current = self.service.prepare_model_activation(first.bundle_id)
        self.service.execute(current["token"], str(uuid.uuid4()), actor=ACTOR)
        with self.assertRaisesRegex(ModelActivationRefused, "stale"):
            self.service.execute(stale["token"], str(uuid.uuid4()), actor=ACTOR)

        expiring = self.service.prepare_model_activation(second.bundle_id)
        self.clock[0] += timedelta(minutes=11)
        with self.assertRaisesRegex(ModelActivationRefused, "expired"):
            self.service.execute(expiring["token"], str(uuid.uuid4()), actor=ACTOR)

    def test_explicit_rollback_retains_known_good_bundle(self) -> None:
        first = self._bundle(b"one")
        second = self._bundle(b"two")
        first_plan = self.service.prepare_model_activation(first.bundle_id)
        self.service.execute(first_plan["token"], str(uuid.uuid4()), actor=ACTOR)
        second_plan = self.service.prepare_model_activation(second.bundle_id)
        self.service.execute(second_plan["token"], str(uuid.uuid4()), actor=ACTOR)
        rollback = self.service.prepare_rollback()
        result = self.service.execute(rollback["token"], str(uuid.uuid4()), actor=ACTOR)
        self.assertEqual(result["action"], "ROLLBACK")
        self.assertEqual(self.service.active_state().active_bundle_id, first.bundle_id)

    def test_failure_after_publication_restores_runtime_and_active_state(self) -> None:
        first = self._bundle(b"one")
        plan = self.service.prepare_model_activation(first.bundle_id)
        detector_before = self.engine.detector
        self.fail_at = "after_runtime_swap"
        operation = str(uuid.uuid4())
        with self.assertRaisesRegex(ModelActivationRefused, "previous runtime remains active"):
            self.service.execute(plan["token"], operation, actor=ACTOR)
        self.assertIsNone(self.service.active_state())
        self.assertIs(self.engine.detector, detector_before)
        retry = self.service.execute(plan["token"], operation, actor=ACTOR)
        self.assertFalse(retry["committed"])
        self.assertTrue(retry["idempotent"])

    def test_corrupted_bundle_and_actor_spoof_are_refused(self) -> None:
        bundle = self._bundle(b"one")
        plan = self.service.prepare_model_activation(bundle.bundle_id)
        with self.assertRaisesRegex(ModelActivationRefused, "actor"):
            self.service.execute(plan["token"], str(uuid.uuid4()), actor={"actor": "spoof"})
        component = bundle.directory / "detector.onnx"
        component.chmod(0o644)
        component.write_bytes(b"tampered")
        with self.assertRaises(Exception):
            self.service.execute(plan["token"], str(uuid.uuid4()), actor=ACTOR)

    def test_execution_requires_the_exact_server_preparation_token(self) -> None:
        bundle = self._bundle(b"one")
        plan = self.service.prepare_model_activation(bundle.bundle_id)
        with self.assertRaisesRegex(ModelActivationRefused, "signature|malformed"):
            self.service.execute(
                str(plan["token"]) + "changed",
                str(uuid.uuid4()),
                actor=ACTOR,
            )
        self.assertIsNone(self.service.active_state())

    def _runtime(self, bundle, base_config):
        usage = json.loads((bundle.directory / "model-usage.json").read_text(encoding="utf-8"))
        return PreparedRecognitionRuntime(
            config=replace(
                base_config,
                detector_model=bundle.directory / "detector.onnx",
                recognizer_model=bundle.directory / "recognizer.onnx",
            ),
            detector=object(),
            embedder=object(),
            usage=usage,
            facts=dict(RUNTIME_FACTS),
        )

    def _inject(self, checkpoint: str) -> None:
        if checkpoint == self.fail_at:
            raise RuntimeError("injected activation failure")

    def _bundle(self, payload: bytes):
        detector = self._upload("detector", "detector.onnx", b"detector-" + payload)
        recognizer = self._upload("recognizer", "recognizer.onnx", b"recognizer-" + payload)
        return self.authority.create_bundle(
            detector_upload_id=detector.upload_id,
            recognizer_upload_id=recognizer.upload_id,
            calibration_upload_id=None,
            calibration_profile="buffalo-s-research",
            usage_basis="noncommercial-research",
            authorized_by="Owner",
        )

    def _upload(self, kind: str, filename: str, data: bytes):
        target = self.authority.begin_upload(kind, filename)
        target.path.write_bytes(data)
        return self.authority.complete_upload(
            target, sha256=hashlib.sha256(data).hexdigest(), size=len(data),
        )


if __name__ == "__main__":
    unittest.main()
