from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from sentriface.cli import build_dev_engine


class PersonManagementTest(unittest.TestCase):
    def test_unique_person_ranking_collapses_embedding_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            pending = engine.prepare_additions(image)[0]
            person_id = engine.confirm_new_person(pending, "Person A")
            engine.confirm_existing_person(engine.prepare_additions(image)[0], person_id)

            results = engine.recognize(image)

            self.assertEqual(len(results[0].matches), 1)
            self.assertEqual(results[0].matches[0].person_id, person_id)
            self.assertEqual(results[0].matches[0].embeddings_matched, 2)

    def test_person_rename_and_soft_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "Old Name")

            engine.rename_person(person_id, "New Name")
            self.assertEqual(engine.get_person(person_id).name, "New Name")

            engine.delete_person(person_id)

            self.assertIsNone(engine.get_person(person_id))
            self.assertEqual(engine.recognize(image)[0].matches, [])

    def test_delete_embedding_removes_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "Person A")
            embedding = engine.list_person_embeddings(person_id)[0]

            engine.delete_embedding(embedding.embedding_id)

            self.assertEqual(engine.list_person_embeddings(person_id), [])
            self.assertEqual(engine.recognize(image)[0].matches, [])

    def _write_image(self, image: Path) -> None:
        canvas = np.full((160, 160, 3), 128, dtype=np.uint8)
        cv2.rectangle(canvas, (35, 35), (125, 125), (220, 220, 220), -1)
        cv2.circle(canvas, (62, 70), 7, (20, 20, 20), -1)
        cv2.circle(canvas, (98, 70), 7, (20, 20, 20), -1)
        cv2.ellipse(canvas, (80, 100), (28, 12), 0, 0, 180, (20, 20, 20), 2)
        cv2.imwrite(str(image), canvas)


if __name__ == "__main__":
    unittest.main()

