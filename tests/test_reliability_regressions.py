from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from sentriface.api_server import create_server
from sentriface.cli import build_dev_engine
from sentriface.components.hnsw_index import HnswFaceIndex
from sentriface.models import EmbeddingRecord


class ReliabilityRegressionTest(unittest.TestCase):
    def _write_face(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        image = np.full((160, 160, 3), 128, dtype=np.uint8)
        cv2.rectangle(image, (35, 35), (125, 125), (220, 220, 220), -1)
        cv2.circle(image, (62, 70), 7, (20, 20, 20), -1)
        cv2.circle(image, (98, 70), 7, (20, 20, 20), -1)
        cv2.ellipse(image, (80, 100), (28, 12), 0, 0, 180, (20, 20, 20), 2)
        self.assertTrue(cv2.imwrite(str(path), image))

    def test_soft_deleted_embedding_still_protects_managed_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            source = data_dir / "uploads" / "source.jpg"
            self._write_face(source)
            engine = build_dev_engine(data_dir)
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(source)[0], "Protected")
            embedding = engine.list_person_embeddings(person_id)[0]
            engine.delete_embedding(embedding.embedding_id, str(uuid.uuid4()))

            session = engine.create_queue_session(source, allow_bad_quality=True).session
            engine.discard_init_session(session.session_id)

            self.assertTrue(source.exists())
            self.assertIn(str(source), engine.store.list_all_file_references())

    def test_pending_confirmation_and_followup_retries_do_not_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            source = data_dir / "uploads" / "source.jpg"
            self._write_face(source)
            engine = build_dev_engine(data_dir)
            engine.initialize()
            pending = engine.prepare_additions(source)[0]
            operation_id = str(uuid.uuid4())

            first = engine.confirm_new_person(pending, "Retry Safe", operation_id=operation_id)
            second = engine.confirm_new_person(pending, "Retry Safe", operation_id=operation_id)
            self.assertEqual(first, second)
            embeddings = engine.list_person_embeddings(first)
            self.assertEqual(len(embeddings), 1)
            self.assertEqual(len(engine.list_persons()), 1)
            self.assertEqual(engine.list_pending_additions(), [])

            followup_id = str(uuid.uuid4())
            kwargs = {
                "embedding_id": embeddings[0].embedding_id,
                "person_id": first,
                "image_id": "source.jpg#face-01",
                "name": "Retry Safe",
                "decision": "new",
                "seen_date": "2026-07-27",
                "seen_time": "12:00",
                "place_seen": "Test",
                "individual_count": 1,
                "event_occasion": "Test",
                "image_path": str(source),
                "operation_id": followup_id,
            }
            detail_a = engine.add_recognition_detail(**kwargs)
            detail_b = engine.add_recognition_detail(**kwargs)
            self.assertEqual(detail_a, detail_b)
            self.assertEqual(len(engine.list_recognition_details_for_person(first)), 1)

    def test_queue_confirmation_retry_reuses_atomic_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            source = data_dir / "uploads" / "source.jpg"
            self._write_face(source)
            engine = build_dev_engine(data_dir)
            engine.initialize()
            result = engine.create_queue_session(source, allow_bad_quality=True)
            group = result.groups[0]
            face_ids = [face.init_face_id for face in group.faces]
            operation_id = str(uuid.uuid4())

            first_person, first_accepted = engine.confirm_init_faces(
                result.session.session_id,
                group.group_id,
                face_ids,
                "Queue Retry",
                operation_id,
            )
            second_person, second_accepted = engine.confirm_init_faces(
                result.session.session_id,
                group.group_id,
                face_ids,
                "Queue Retry",
                operation_id,
            )
            self.assertEqual(first_person, second_person)
            self.assertEqual(first_accepted, second_accepted)
            self.assertEqual(len(engine.list_persons()), 1)
            self.assertEqual(len(engine.list_person_embeddings(first_person)), 1)

    def test_hnsw_failed_generation_does_not_publish_partial_state(self) -> None:
        old = EmbeddingRecord("old", "person", (1.0, 0.0), 1.0)
        new = EmbeddingRecord("new", "person", (0.0, 1.0), 1.0)
        index = HnswFaceIndex(2)
        sentinel = object()
        index._records = [old]
        index._index = sentinel
        index._capacity = 64

        with patch.object(index, "_build", side_effect=MemoryError("simulated")):
            with self.assertRaises(MemoryError):
                index.add(new)
        self.assertIs(index._index, sentinel)
        self.assertEqual(index._records, [old])
        self.assertEqual(index._capacity, 64)

    def test_server_rejects_non_loopback_bind(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "loopback"):
                create_server(
                    host="0.0.0.0",
                    port=0,
                    data_dir=Path(temp) / "data",
                    runtime="dev",
                    debug=False,
                )


if __name__ == "__main__":
    unittest.main()
