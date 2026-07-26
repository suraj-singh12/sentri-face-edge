from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from sentriface.cli import build_dev_engine
from sentriface.config import RuntimeConfig
from sentriface.models import DetectedFace, FaceBox, MatchDecision, QualityStatus


class EngineWorkflowTest(unittest.TestCase):
    def _write_image(self, image: Path) -> None:
        canvas = np.full((160, 160, 3), 128, dtype=np.uint8)
        cv2.rectangle(canvas, (35, 35), (125, 125), (220, 220, 220), -1)
        cv2.circle(canvas, (62, 70), 7, (20, 20, 20), -1)
        cv2.circle(canvas, (98, 70), 7, (20, 20, 20), -1)
        cv2.ellipse(canvas, (80, 100), (28, 12), 0, 0, 180, (20, 20, 20), 2)
        cv2.imwrite(str(image), canvas)

    def test_initialize_creates_missing_runtime_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "missing-data"

            engine = build_dev_engine(data_dir)
            engine.initialize()

            self.assertTrue(data_dir.exists())
            self.assertTrue((data_dir / "sentriface.db").exists())
            self.assertTrue((data_dir / "faces").exists())
            self.assertTrue((data_dir / "index").exists())

    def test_add_and_recognize_same_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            pending = engine.prepare_additions(image)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0].quality.status, QualityStatus.WARN)
            person_id = engine.confirm_new_person(pending[0], "Test Person")

            results = engine.recognize(image)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].decision, MatchDecision.STRONG)
            self.assertEqual(results[0].matches[0].person_id, person_id)

    def test_queue_and_confirm_pending_existing_person(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            prepared = engine.queue_additions(image)
            pending = prepared.accepted
            self.assertEqual(len(pending), 1)
            self.assertEqual(prepared.rejected, [])
            self.assertTrue(Path(pending[0].face.crop_path).exists())
            self.assertEqual(len(engine.list_pending_additions()), 1)

            person_id = engine.confirm_pending_as_new_person(pending[0].pending_id, "Test Person")
            self.assertEqual(engine.list_pending_additions(), [])

            second = engine.queue_additions(image).accepted
            self.assertEqual(second[0].decision, MatchDecision.STRONG)
            embedding_id = engine.confirm_pending_as_existing_person(
                second[0].pending_id,
                person_id,
            )

            self.assertTrue(embedding_id)
            self.assertEqual(engine.list_pending_additions(), [])

    def test_bad_quality_face_is_rejected_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)

            config = RuntimeConfig(
                data_dir=temp_path / "data",
                min_face_size=999,
                min_quality_score=0.8,
            )
            engine = build_dev_engine(temp_path / "data", config)
            engine.initialize()

            prepared = engine.queue_additions(image)

            self.assertEqual(prepared.accepted, [])
            self.assertEqual(len(prepared.rejected), 1)
            self.assertEqual(prepared.rejected[0].quality.status, QualityStatus.BAD)

    def test_bad_quality_face_can_be_forced(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)

            config = RuntimeConfig(
                data_dir=temp_path / "data",
                min_face_size=999,
                min_quality_score=0.8,
            )
            engine = build_dev_engine(temp_path / "data", config)
            engine.initialize()

            prepared = engine.queue_additions(image, allow_bad_quality=True)

            self.assertEqual(len(prepared.accepted), 1)
            self.assertEqual(prepared.accepted[0].quality.status, QualityStatus.BAD)
            self.assertEqual(prepared.rejected, [])

    def test_prepare_face_addition_preserves_selected_detection_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "faces.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            faces = [
                DetectedFace(FaceBox(10, 20, 60, 80, 0.96), 0.9),
                DetectedFace(FaceBox(88, 18, 58, 82, 0.94), 0.88),
            ]
            engine.detector = StaticDetector(faces)

            selected = engine.prepare_face_addition(image, 1, allow_bad_quality=True, expected_box=faces[1].box)

            self.assertIsNotNone(selected)
            self.assertEqual(selected.face.box, faces[1].box)
            self.assertNotEqual(selected.face.box, faces[0].box)

    def test_prepare_face_addition_rejects_stale_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            with self.assertRaisesRegex(KeyError, "Face 2"):
                engine.prepare_face_addition(image, 2)


class StaticDetector:
    def __init__(self, faces):
        self.faces = faces

    def detect(self, image_path):
        return self.faces


if __name__ == "__main__":
    unittest.main()
