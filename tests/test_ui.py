from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from sentriface.cli import build_dev_engine
from sentriface.ui import (
    UPLOAD_RESIZE_LIMIT_BYTES,
    _pending,
    _person_summary,
    _recognition,
    _save_upload,
    _save_upload_batch,
)


class UiSerializationTest(unittest.TestCase):
    def test_recognition_payload_contains_debuggable_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            pending = engine.prepare_additions(image)[0]
            person_id = engine.confirm_new_person(pending, "UI Person")

            result = engine.recognize(image)[0]
            payload = _recognition(engine, result, 1)

            self.assertEqual(payload["decision"], "strong")
            self.assertEqual(payload["matches"][0]["person_id"], person_id)
            self.assertIn("box", payload)
            self.assertIn("quality", payload)

    def test_pending_and_person_payloads_are_ui_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            prepared = engine.queue_additions(image)
            pending_payload = _pending(engine, prepared.accepted[0])
            person_id = engine.confirm_pending_as_new_person(pending_payload["pending_id"], "Queued Person")
            person_payload = _person_summary(engine.list_persons()[0])

            self.assertEqual(person_payload["person_id"], person_id)
            self.assertEqual(person_payload["embedding_count"], 1)
            self.assertIn("crop_path", pending_payload)
            self.assertIn("quality", pending_payload)

    def test_upload_save_writes_image_inside_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            encoded = base64.b64encode(b"fake image bytes").decode("ascii")

            saved = _save_upload(data_dir, "face.jpg", f"data:image/jpeg;base64,{encoded}")

            self.assertTrue(saved.exists())
            self.assertEqual(saved.parent, data_dir / "uploads")
            self.assertEqual(saved.read_bytes(), b"fake image bytes")

    def test_upload_save_reduces_large_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            rng = np.random.default_rng(123)
            image = rng.integers(0, 255, (1800, 1800, 3), dtype=np.uint8)
            ok, encoded_image = cv2.imencode(".png", image)
            self.assertTrue(ok)
            original = encoded_image.tobytes()
            self.assertGreater(len(original), UPLOAD_RESIZE_LIMIT_BYTES)
            encoded = base64.b64encode(original).decode("ascii")

            saved = _save_upload(data_dir, "large.png", f"data:image/png;base64,{encoded}")

            self.assertTrue(saved.exists())
            self.assertEqual(saved.suffix, ".jpg")
            self.assertLessEqual(saved.stat().st_size, UPLOAD_RESIZE_LIMIT_BYTES)

    def test_upload_save_rejects_unsupported_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(KeyError):
                _save_upload(Path(temp), "note.txt", "bm90IGFuIGltYWdl")

    def test_upload_batch_writes_supported_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            first = base64.b64encode(b"first image").decode("ascii")
            second = base64.b64encode(b"second image").decode("ascii")

            batch_dir, count = _save_upload_batch(
                data_dir,
                [
                    {
                        "filename": "a.jpg",
                        "relative_path": "folder/a.jpg",
                        "data": f"data:image/jpeg;base64,{first}",
                    },
                    {
                        "filename": "b.png",
                        "relative_path": "folder/nested/b.png",
                        "data": f"data:image/png;base64,{second}",
                    },
                    {
                        "filename": "skip.txt",
                        "relative_path": "folder/skip.txt",
                        "data": "c2tpcA==",
                    },
                ],
            )

            self.assertEqual(count, 2)
            self.assertEqual(len(list((batch_dir / "folder").glob("*.jpg"))), 1)
            self.assertEqual(len(list((batch_dir / "folder" / "nested").glob("*.png"))), 1)
            self.assertFalse((batch_dir / "folder" / "skip.txt").exists())

    def _write_image(self, image: Path) -> None:
        canvas = np.full((160, 160, 3), 128, dtype=np.uint8)
        cv2.rectangle(canvas, (35, 35), (125, 125), (220, 220, 220), -1)
        cv2.circle(canvas, (62, 70), 7, (20, 20, 20), -1)
        cv2.circle(canvas, (98, 70), 7, (20, 20, 20), -1)
        cv2.ellipse(canvas, (80, 100), (28, 12), 0, 0, 180, (20, 20, 20), 2)
        cv2.imwrite(str(image), canvas)


if __name__ == "__main__":
    unittest.main()
