from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from sentriface.api_server import _required_capability, _support_package_bytes


class SupportPackageTests(unittest.TestCase):
    def test_package_is_diagnostic_only_and_contains_no_identity_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "people.sqlite3"
            database.write_bytes(b"SQLite format 3\x00")
            config = SimpleNamespace(
                data_dir=root,
                db_path=database,
                hardware_tier="medium",
                max_workers=2,
                onnx_intra_threads=2,
                max_image_edge=1280,
                detector_input_size=640,
                batch_size=4,
                prefer_small_models=False,
                detector_model=root / "models" / "detector.onnx",
                recognizer_model=root / "models" / "recognizer.onnx",
                storage_key=b"secret-key",
            )
            server = SimpleNamespace(
                config=config,
                runtime="onnx",
                hardware_profile=SimpleNamespace(cpu_count=8, memory_gb=16),
                model_usage={"usage_basis": "noncommercial-research", "terms_version": "1"},
                os_network_policy=None,
                engine=SimpleNamespace(index_status={"requested": "flat", "actual": "flat", "degraded_reason": None}),
                events_lock=threading.Lock(),
                events=[{
                    "timestamp": "2026-08-06T10:00:00+00:00",
                    "event": "person-update",
                    "person_id": "private-person-id",
                    "path": "/private/photos/person.jpg",
                }],
                models_available=lambda: True,
                recovery_readiness=lambda: {
                    "ready": True,
                    "configured": True,
                    "destination_available": True,
                    "recovery_kit_present": True,
                    "external_backup_present": True,
                    "acknowledged": True,
                    "acknowledged_by": "private-operator-name",
                },
            )

            payload = _support_package_bytes(server)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                self.assertEqual(set(archive.namelist()), {"README.txt", "diagnostic-report.json"})
                report = json.loads(archive.read("diagnostic-report.json"))
                serialized = json.dumps(report)

            self.assertEqual(report["events"]["history"][0]["event"], "person-update")
            self.assertEqual(report["models"]["detector"], "detector.onnx")
            self.assertNotIn("private-person-id", serialized)
            self.assertNotIn("private-operator-name", serialized)
            self.assertNotIn(str(root), serialized)

    def test_export_requires_technical_capability(self) -> None:
        self.assertEqual(_required_capability("POST", "/api/support-package"), "technical")


if __name__ == "__main__":
    unittest.main()
