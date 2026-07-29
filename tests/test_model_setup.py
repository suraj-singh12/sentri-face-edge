from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from sentriface.errors import ModelSetupError
from sentriface.model_setup import (
    _extract_verified,
    install_local_models,
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


if __name__ == "__main__":
    unittest.main()
