from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from sentriface.cli import build_dev_engine
from sentriface.ui import _pending, _person_summary, _recognition


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

    def _write_image(self, image: Path) -> None:
        canvas = np.full((160, 160, 3), 128, dtype=np.uint8)
        cv2.rectangle(canvas, (35, 35), (125, 125), (220, 220, 220), -1)
        cv2.circle(canvas, (62, 70), 7, (20, 20, 20), -1)
        cv2.circle(canvas, (98, 70), 7, (20, 20, 20), -1)
        cv2.ellipse(canvas, (80, 100), (28, 12), 0, 0, 180, (20, 20, 20), 2)
        cv2.imwrite(str(image), canvas)


if __name__ == "__main__":
    unittest.main()
