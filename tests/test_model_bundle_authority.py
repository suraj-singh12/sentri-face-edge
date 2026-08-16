from __future__ import annotations

import hashlib
import json
import shutil
import socket
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sentriface.api_server import (
    _required_capability,
    _validate_model_install_payload,
    _validate_model_operation_payload,
    _validate_model_upload_query,
)
from sentriface.errors import InputValidationError, ModelSetupError
from sentriface.model_bundle import ModelBundleAuthority


class ModelBundleAuthorityTest(unittest.TestCase):
    def test_valid_bundle_is_immutable_bounded_and_does_not_mutate_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "authority.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE authority (value TEXT NOT NULL)")
                connection.execute("INSERT INTO authority VALUES ('unchanged')")
            before = hashlib.sha256(database.read_bytes()).hexdigest()
            authority = ModelBundleAuthority(root / "models")
            detector = self._upload(authority, "detector", "detector.onnx", b"detector")
            recognizer = self._upload(authority, "recognizer", "recognizer.onnx", b"recognizer")

            bundle = authority.create_bundle(
                detector_upload_id=detector.upload_id,
                recognizer_upload_id=recognizer.upload_id,
                calibration_upload_id=None,
                calibration_profile="buffalo-s-research",
                usage_basis="noncommercial-research",
                authorized_by="Owner",
            )

            self.assertEqual(set(bundle.components), {"detector", "recognizer", "calibration", "model_usage"})
            self.assertEqual(len(bundle.bundle_id), 32)
            self.assertEqual(len(bundle.fingerprint), 64)
            self.assertNotIn(str(root), json.dumps(bundle.dto()))
            self.assertEqual(authority.list_bundles(), (bundle,))
            self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before)
            with sqlite3.connect(database) as connection:
                self.assertEqual(connection.execute("SELECT value FROM authority").fetchone()[0], "unchanged")

    def test_malformed_and_missing_bundle_components_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            authority = ModelBundleAuthority(Path(temporary) / "models")
            detector = self._upload(authority, "detector", "detector.onnx", b"detector")
            with self.assertRaisesRegex(ModelSetupError, "unknown|consumed"):
                authority.create_bundle(
                    detector_upload_id=detector.upload_id,
                    recognizer_upload_id="0" * 32,
                    calibration_upload_id=None,
                    calibration_profile=None,
                    usage_basis="noncommercial-research",
                    authorized_by="Owner",
                )

            recognizer = self._upload(authority, "recognizer", "recognizer.onnx", b"recognizer")
            bundle = authority.create_bundle(
                detector_upload_id=detector.upload_id,
                recognizer_upload_id=recognizer.upload_id,
                calibration_upload_id=None,
                calibration_profile=None,
                usage_basis="noncommercial-research",
                authorized_by="Owner",
            )
            bundle.directory.chmod(0o755)
            (bundle.directory / "calibration.json").chmod(0o644)
            (bundle.directory / "calibration.json").unlink()
            with self.assertRaisesRegex(ModelSetupError, "missing|verification"):
                authority.read_bundle(bundle.bundle_id)

    def test_unknown_manifest_fields_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            authority = ModelBundleAuthority(Path(temporary) / "models")
            bundle = self._bundle(authority)
            manifest = bundle.directory / "manifest.json"
            bundle.directory.chmod(0o755)
            manifest.chmod(0o644)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["local_path"] = "/operator/chosen/path"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ModelSetupError, "fields"):
                authority.read_bundle(bundle.bundle_id)

    def test_path_traversal_and_symlink_escape_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authority = ModelBundleAuthority(root / "models")
            with self.assertRaisesRegex(ModelSetupError, "metadata"):
                authority.begin_upload("detector", "../detector.onnx")
            with self.assertRaisesRegex(ModelSetupError, "ID"):
                authority.read_bundle("../bundle")

            outside = root / "outside"
            outside.mkdir()
            authority.root.parent.mkdir(parents=True, exist_ok=True)
            authority.root.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ModelSetupError, "symbolic"):
                authority.begin_upload("detector", "detector.onnx")

    def test_symlinked_upload_content_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authority = ModelBundleAuthority(root / "models")
            detector = self._upload(authority, "detector", "detector.onnx", b"detector")
            recognizer = self._upload(authority, "recognizer", "recognizer.onnx", b"recognizer")
            content = authority.uploads_dir / detector.upload_id / "content"
            content.unlink()
            outside = root / "outside.onnx"
            outside.write_bytes(b"detector")
            content.symlink_to(outside)
            with self.assertRaisesRegex(ModelSetupError, "regular|escaped"):
                authority.create_bundle(
                    detector_upload_id=detector.upload_id,
                    recognizer_upload_id=recognizer.upload_id,
                    calibration_upload_id=None,
                    calibration_profile=None,
                    usage_basis="noncommercial-research",
                    authorized_by="Owner",
                )

    def test_oversized_upload_is_refused_before_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            authority = ModelBundleAuthority(Path(temporary) / "models")
            target = authority.begin_upload("calibration", "calibration.json")
            target.path.write_bytes(b"{}")
            with self.assertRaisesRegex(ModelSetupError, "size"):
                authority.complete_upload(
                    target,
                    sha256=hashlib.sha256(b"{}").hexdigest(),
                    size=1_000_001,
                )

    def test_duplicate_and_ambiguous_bundle_authority_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            authority = ModelBundleAuthority(Path(temporary) / "models")
            first = self._bundle(authority)
            detector = self._upload(authority, "detector", "detector.onnx", b"detector")
            recognizer = self._upload(authority, "recognizer", "recognizer.onnx", b"recognizer")
            with self.assertRaisesRegex(ModelSetupError, "identical"):
                authority.create_bundle(
                    detector_upload_id=detector.upload_id,
                    recognizer_upload_id=recognizer.upload_id,
                    calibration_upload_id=None,
                    calibration_profile="buffalo-s-research",
                    usage_basis="noncommercial-research",
                    authorized_by="Owner",
                )

            cloned_id = "f" * 32
            cloned = authority.bundles_dir / cloned_id
            shutil.copytree(first.directory, cloned)
            cloned.chmod(0o755)
            manifest = cloned / "manifest.json"
            manifest.chmod(0o644)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["bundle_id"] = cloned_id
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            detector = self._upload(authority, "detector", "detector.onnx", b"detector")
            recognizer = self._upload(authority, "recognizer", "recognizer.onnx", b"recognizer")
            with self.assertRaisesRegex(ModelSetupError, "ambiguous"):
                authority.create_bundle(
                    detector_upload_id=detector.upload_id,
                    recognizer_upload_id=recognizer.upload_id,
                    calibration_upload_id=None,
                    calibration_profile="buffalo-s-research",
                    usage_basis="noncommercial-research",
                    authorized_by="Owner",
                )

    def test_expired_and_reused_upload_references_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clock = [datetime(2026, 8, 15, tzinfo=timezone.utc)]
            authority = ModelBundleAuthority(Path(temporary) / "models", now=lambda: clock[0])
            detector = self._upload(authority, "detector", "detector.onnx", b"detector")
            recognizer = self._upload(authority, "recognizer", "recognizer.onnx", b"recognizer")
            clock[0] += timedelta(hours=1)
            with self.assertRaisesRegex(ModelSetupError, "expired"):
                authority.create_bundle(
                    detector_upload_id=detector.upload_id,
                    recognizer_upload_id=recognizer.upload_id,
                    calibration_upload_id=None,
                    calibration_profile=None,
                    usage_basis="noncommercial-research",
                    authorized_by="Owner",
                )

            clock[0] += timedelta(hours=1)
            detector = self._upload(authority, "detector", "detector.onnx", b"detector")
            recognizer = self._upload(authority, "recognizer", "recognizer.onnx", b"recognizer")
            authority.create_bundle(
                detector_upload_id=detector.upload_id,
                recognizer_upload_id=recognizer.upload_id,
                calibration_upload_id=None,
                calibration_profile=None,
                usage_basis="noncommercial-research",
                authorized_by="Owner",
            )
            replacement = self._upload(authority, "recognizer", "recognizer.onnx", b"other")
            with self.assertRaisesRegex(ModelSetupError, "consumed"):
                authority.create_bundle(
                    detector_upload_id=detector.upload_id,
                    recognizer_upload_id=replacement.upload_id,
                    calibration_upload_id=None,
                    calibration_profile=None,
                    usage_basis="noncommercial-research",
                    authorized_by="Owner",
                )

    def test_stale_upload_cleanup_is_bounded_to_authority_uploads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clock = [datetime(2026, 8, 15, tzinfo=timezone.utc)]
            authority = ModelBundleAuthority(Path(temporary) / "models", now=lambda: clock[0])
            upload = self._upload(authority, "detector", "detector.onnx", b"detector")
            keep = authority.root / "do-not-delete.txt"
            keep.write_text("authority metadata", encoding="utf-8")
            clock[0] += timedelta(hours=1)
            self.assertEqual(
                authority.cleanup_stale_uploads(),
                {"uploads": 1, "staging": 0},
            )
            self.assertFalse((authority.uploads_dir / upload.upload_id).exists())
            self.assertTrue(keep.exists())

    def test_model_routes_are_administer_only_and_actor_spoof_is_rejected(self) -> None:
        for endpoint in (
            "/api/models/upload",
            "/api/models/install",
            "/api/models/activation/prepare",
            "/api/models/activation/execute",
            "/api/models/rollback/prepare",
            "/api/models/rollback/execute",
        ):
            self.assertEqual(_required_capability("POST", endpoint), "administer")
        with self.assertRaises(InputValidationError) as raised:
            _validate_model_install_payload({
                "detector_upload_id": "a" * 32,
                "recognizer_upload_id": "b" * 32,
                "actor": "spoofed",
            })
        self.assertEqual(raised.exception.reason, "unsupported_model_install_fields")
        with self.assertRaises(InputValidationError) as query_raised:
            _validate_model_upload_query("kind=detector&filename=detector.onnx&actor=spoofed")
        self.assertEqual(query_raised.exception.reason, "unsupported_model_upload_fields")
        with self.assertRaises(InputValidationError) as operation_raised:
            _validate_model_operation_payload(
                "/api/models/activation/execute",
                {"token": "server-token", "operation_id": str(uuid.uuid4()), "actor": "spoofed"},
            )
        self.assertEqual(operation_raised.exception.reason, "unsupported_model_operation_fields")

    def test_bundle_creation_performs_no_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            authority = ModelBundleAuthority(Path(temporary) / "models")
            detector = self._upload(authority, "detector", "detector.onnx", b"detector")
            recognizer = self._upload(authority, "recognizer", "recognizer.onnx", b"recognizer")
            with patch.object(socket, "socket", side_effect=AssertionError("network access")):
                authority.create_bundle(
                    detector_upload_id=detector.upload_id,
                    recognizer_upload_id=recognizer.upload_id,
                    calibration_upload_id=None,
                    calibration_profile=None,
                    usage_basis="noncommercial-research",
                    authorized_by="Owner",
                )

    def _bundle(self, authority: ModelBundleAuthority):
        detector = self._upload(authority, "detector", "detector.onnx", b"detector")
        recognizer = self._upload(authority, "recognizer", "recognizer.onnx", b"recognizer")
        return authority.create_bundle(
            detector_upload_id=detector.upload_id,
            recognizer_upload_id=recognizer.upload_id,
            calibration_upload_id=None,
            calibration_profile="buffalo-s-research",
            usage_basis="noncommercial-research",
            authorized_by="Owner",
        )

    @staticmethod
    def _upload(authority: ModelBundleAuthority, kind: str, filename: str, data: bytes):
        target = authority.begin_upload(kind, filename)
        target.path.write_bytes(data)
        return authority.complete_upload(
            target,
            sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),
        )


if __name__ == "__main__":
    unittest.main()
