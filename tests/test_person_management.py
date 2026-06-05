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

    def test_move_embedding_reassigns_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_a = temp_path / "face-a.jpg"
            image_b = temp_path / "face-b.jpg"
            self._write_image(image_a, shade=128)
            self._write_image(image_b, shade=145)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_a = engine.confirm_new_person(engine.prepare_additions(image_a)[0], "Person A")
            person_b = engine.confirm_new_person(engine.prepare_additions(image_b)[0], "Person B")
            embedding = engine.list_person_embeddings(person_a)[0]

            engine.move_embedding(embedding.embedding_id, person_b)

            self.assertEqual(engine.list_person_embeddings(person_a), [])
            self.assertEqual(len(engine.list_person_embeddings(person_b)), 2)
            self.assertEqual(engine.recognize(image_a)[0].matches[0].person_id, person_b)

    def test_merge_persons_moves_embeddings_and_deletes_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_a = temp_path / "face-a.jpg"
            image_b = temp_path / "face-b.jpg"
            self._write_image(image_a, shade=128)
            self._write_image(image_b, shade=145)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            source = engine.confirm_new_person(engine.prepare_additions(image_a)[0], "Source")
            target = engine.confirm_new_person(engine.prepare_additions(image_b)[0], "Target")

            moved = engine.merge_persons(source, target)

            self.assertEqual(moved, 1)
            self.assertIsNone(engine.get_person(source))
            self.assertEqual(len(engine.list_person_embeddings(target)), 2)
            self.assertEqual(engine.recognize(image_a)[0].matches[0].person_id, target)

    def test_merge_persons_rejects_same_person(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "Person A")

            with self.assertRaises(KeyError):
                engine.merge_persons(person_id, person_id)

    def test_move_embedding_rejects_unknown_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "Person A")
            embedding = engine.list_person_embeddings(person_id)[0]

            with self.assertRaises(KeyError):
                engine.move_embedding(embedding.embedding_id, "missing-person")

    def _write_image(self, image: Path, shade: int = 128) -> None:
        canvas = np.full((160, 160, 3), shade, dtype=np.uint8)
        cv2.rectangle(canvas, (35, 35), (125, 125), (220, 220, 220), -1)
        cv2.circle(canvas, (62, 70), 7, (20, 20, 20), -1)
        cv2.circle(canvas, (98, 70), 7, (20, 20, 20), -1)
        cv2.ellipse(canvas, (80, 100), (28, 12), 0, 0, 180, (20, 20, 20), 2)
        cv2.imwrite(str(image), canvas)


if __name__ == "__main__":
    unittest.main()
