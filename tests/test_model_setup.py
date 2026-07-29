from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from sentriface.errors import ModelSetupError
from sentriface.model_setup import (
    _extract_verified,
    install_local_model_bundle,
    install_local_models,
    load_similarity_calibration,
    install_models,
    require_model_usage_declaration,
    verify_file,
)


class ModelSetupTest(unittest.TestCase):
    def test_verified_model_is_reused_without_download(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            payload = b"verified model"
            target = models / "model.onnx"
            target.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()

            install_models(
                models,
                root / "cache",
                sources={
                    target.name: {
                        "url": "https://invalid.example/model.zip",
                        "member": target.name,
                        "sha256": digest,
                        "size": len(payload),
                    }
                },
            )

            self.assertEqual(target.read_bytes(), payload)

    def test_failed_verification_preserves_existing_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "models.zip"
            target = root / "model.onnx"
            target.write_bytes(b"known good")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr(target.name, b"tampered")

            with self.assertRaisesRegex(ValueError, "verification failed"):
                _extract_verified(
                    archive,
                    target.name,
                    target,
                    hashlib.sha256(b"expected").hexdigest(),
                    len(b"expected"),
                )

            self.assertEqual(target.read_bytes(), b"known good")
            self.assertEqual(list(root.glob(".model.onnx.*.tmp")), [])

    def test_file_verification_checks_size_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "model.onnx"
            path.write_bytes(b"model")
            digest = hashlib.sha256(b"model").hexdigest()

            self.assertTrue(verify_file(path, digest, 5))
            self.assertFalse(verify_file(path, digest, 4))
            self.assertFalse(verify_file(path, "0" * 64, 5))

    def test_research_declaration_is_bound_to_exact_model_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            detector = root / "detector-source.onnx"
            recognizer = root / "recognizer-source.onnx"
            detector.write_bytes(b"detector")
            recognizer.write_bytes(b"recognizer")

            installed = install_local_models(
                models,
                detector_source=detector,
                detector_sha256=hashlib.sha256(b"detector").hexdigest(),
                recognizer_source=recognizer,
                recognizer_sha256=hashlib.sha256(b"recognizer").hexdigest(),
                usage_basis="noncommercial-research",
                authorized_by="Research Operator",
            )

            loaded = require_model_usage_declaration(
                models / "detector.onnx",
                models / "recognizer.onnx",
            )
            self.assertEqual(installed["usage_basis"], "noncommercial-research")
            self.assertEqual(loaded["authorized_by"], "Research Operator")

            (models / "recognizer.onnx").write_bytes(b"changed")
            with self.assertRaisesRegex(ModelSetupError, "changed after model rights"):
                require_model_usage_declaration(
                    models / "detector.onnx",
                    models / "recognizer.onnx",
                )

    def test_commercial_declaration_requires_license_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            detector = root / "detector.onnx"
            recognizer = root / "recognizer.onnx"
            detector.write_bytes(b"detector")
            recognizer.write_bytes(b"recognizer")

            with self.assertRaisesRegex(ValueError, "requires both"):
                install_local_models(
                    root / "models",
                    detector_source=detector,
                    detector_sha256=hashlib.sha256(b"detector").hexdigest(),
                    recognizer_source=recognizer,
                    recognizer_sha256=hashlib.sha256(b"recognizer").hexdigest(),
                    usage_basis="commercial-license",
                    authorized_by="Customer Administrator",
                    licensor="InsightFace",
                )

    def test_permissive_declaration_requires_license_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            detector = root / "detector.onnx"
            recognizer = root / "recognizer.onnx"
            detector.write_bytes(b"detector")
            recognizer.write_bytes(b"recognizer")

            with self.assertRaisesRegex(ValueError, "requires --license-name"):
                install_local_models(
                    root / "models",
                    detector_source=detector,
                    detector_sha256=hashlib.sha256(b"detector").hexdigest(),
                    recognizer_source=recognizer,
                    recognizer_sha256=hashlib.sha256(b"recognizer").hexdigest(),
                    usage_basis="permissive-license",
                    authorized_by="Customer Administrator",
                )

    def test_complete_bundle_installs_hash_bound_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            detector = root / "source-detector.onnx"
            recognizer = root / "source-recognizer.onnx"
            calibration = root / "source-calibration.json"
            detector.write_bytes(b"detector")
            recognizer.write_bytes(b"recognizer")
            recognizer_digest = hashlib.sha256(b"recognizer").hexdigest()
            calibration.write_text(json.dumps({
                "recognizer_sha256": recognizer_digest,
                "representative_dataset": "local validation cohort",
                "target_false_match_rate": 0.0001,
                "thresholds": {"possible": 0.4, "likely": 0.5, "strong": 0.6},
            }), encoding="utf-8")

            declaration = install_local_model_bundle(
                root / "models",
                detector_source=detector,
                detector_sha256=hashlib.sha256(b"detector").hexdigest(),
                recognizer_source=recognizer,
                recognizer_sha256=recognizer_digest,
                calibration_source=calibration,
                calibration_sha256=hashlib.sha256(calibration.read_bytes()).hexdigest(),
                usage_basis="noncommercial-research",
                authorized_by="Research Operator",
            )

            installed = load_similarity_calibration(
                root / "models" / "calibration.json",
                root / "models" / "recognizer.onnx",
            )
            self.assertEqual(declaration["usage_basis"], "noncommercial-research")
            self.assertEqual(installed["thresholds"]["strong"], 0.6)

    def test_bundle_rejects_calibration_for_another_recognizer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            detector = root / "detector.onnx"
            recognizer = root / "recognizer.onnx"
            calibration = root / "calibration.json"
            detector.write_bytes(b"detector")
            recognizer.write_bytes(b"recognizer")
            calibration.write_text(json.dumps({
                "recognizer_sha256": "0" * 64,
                "representative_dataset": "cohort",
                "target_false_match_rate": 0.001,
                "thresholds": {"possible": 0.4, "likely": 0.5, "strong": 0.6},
            }), encoding="utf-8")

            with self.assertRaisesRegex(ModelSetupError, "does not match"):
                install_local_model_bundle(
                    root / "models",
                    detector_source=detector,
                    detector_sha256=hashlib.sha256(detector.read_bytes()).hexdigest(),
                    recognizer_source=recognizer,
                    recognizer_sha256=hashlib.sha256(recognizer.read_bytes()).hexdigest(),
                    calibration_source=calibration,
                    calibration_sha256=hashlib.sha256(calibration.read_bytes()).hexdigest(),
                    usage_basis="noncommercial-research",
                    authorized_by="Research Operator",
                )
            self.assertFalse((root / "models").exists())

if __name__ == "__main__":
    unittest.main()
