from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from sentriface.cli import build_dev_engine
from sentriface.engine import _assign_groups
from sentriface.models import DetectedFace, FaceBox, InitFace, PersonMatch, QualityReport, QualityStatus


class InitWorkflowTest(unittest.TestCase):
    def test_queue_groups_merge_faces_with_same_strong_known_match(self) -> None:
        faces = [
            self._init_face("face_1", (1.0, 0.0)),
            self._init_face("face_2", (0.0, 1.0)),
        ]

        split_without_known_match = _assign_groups(faces, threshold=0.9)
        grouped_with_known_match = _assign_groups(
            faces,
            threshold=0.9,
            matches_by_face_id={
                face.init_face_id: [
                    PersonMatch(
                        person_id="person-known",
                        score=1.0,
                        embedding_ids=("embedding-known",),
                        embeddings_matched=1,
                    )
                ]
                for face in faces
            },
        )

        self.assertEqual(len({face.group_id for face in split_without_known_match}), 2)
        self.assertEqual(len({face.group_id for face in grouped_with_known_match}), 1)

    def test_init_scan_groups_and_confirms(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_dir = temp_path / "images"
            image_dir.mkdir()
            self._write_image(image_dir / "person_a_1.jpg", shade=120)
            self._write_image(image_dir / "person_a_2.jpg", shade=120)
            self._write_image(image_dir / "person_b_1.jpg", shade=180)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            session = engine.create_init_session(image_dir)
            groups = engine.list_init_groups(session.session_id)

            self.assertGreaterEqual(len(groups), 2)
            self.assertEqual(sum(len(group.faces) for group in groups), 3)
            self.assertTrue(Path(groups[0].faces[0].face.crop_path).exists())

            first_group = groups[0]
            person_id = engine.confirm_init_group(
                session.session_id,
                first_group.group_id,
                "Init Person",
            )

            self.assertTrue(person_id)
            updated = engine.list_init_groups(session.session_id)
            confirmed = [group for group in updated if group.group_id == first_group.group_id][0]
            self.assertEqual(confirmed.status, "confirmed")

    def test_init_reject_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_dir = temp_path / "images"
            image_dir.mkdir()
            self._write_image(image_dir / "person_a.jpg", shade=120)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            session = engine.create_init_session(image_dir)
            group = engine.list_init_groups(session.session_id)[0]
            engine.reject_init_group(session.session_id, group.group_id)

            updated = engine.list_init_groups(session.session_id)[0]
            self.assertEqual(updated.status, "rejected")

    def test_init_confirm_existing_person(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_dir = temp_path / "images"
            image_dir.mkdir()
            seed = temp_path / "seed.jpg"
            self._write_image(seed, shade=120)
            self._write_image(image_dir / "person_a_2.jpg", shade=120)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(seed)[0], "Existing")

            session = engine.create_init_session(image_dir)
            group = engine.list_init_groups(session.session_id)[0]
            added = engine.confirm_init_group_existing(session.session_id, group.group_id, person_id)

            self.assertEqual(added, 1)
            self.assertEqual(len(engine.list_person_embeddings(person_id)), 2)
            updated = engine.list_init_groups(session.session_id)[0]
            self.assertEqual(updated.status, "confirmed")

    def test_init_reset_group_to_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_dir = temp_path / "images"
            image_dir.mkdir()
            self._write_image(image_dir / "person_a.jpg", shade=120)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            session = engine.create_init_session(image_dir)
            group = engine.list_init_groups(session.session_id)[0]
            engine.reject_init_group(session.session_id, group.group_id)
            engine.reset_init_group(session.session_id, group.group_id)

            updated = engine.list_init_groups(session.session_id)[0]
            self.assertEqual(updated.status, "pending")

    def test_queue_selected_faces_leave_remaining_group_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_dir = temp_path / "images"
            image_dir.mkdir()
            self._write_image(image_dir / "person_a_1.jpg", shade=120)
            self._write_image(image_dir / "person_a_2.jpg", shade=120)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            session = engine.create_init_session(image_dir)
            group = max(engine.list_init_groups(session.session_id), key=lambda item: len(item.faces))
            self.assertGreaterEqual(len(group.faces), 2)

            selected = [group.faces[0].init_face_id]
            person_id, embedding_ids = engine.confirm_init_faces(session.session_id, group.group_id, selected, "Queue Person")

            self.assertTrue(person_id)
            self.assertEqual(len(embedding_ids), 1)
            updated = [item for item in engine.list_init_groups(session.session_id) if item.group_id == group.group_id][0]
            self.assertEqual(updated.status, "pending")
            self.assertEqual(len(updated.faces), len(group.faces) - 1)

    def test_queue_discard_selected_faces_removes_only_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_dir = temp_path / "images"
            image_dir.mkdir()
            self._write_image(image_dir / "person_a_1.jpg", shade=120)
            self._write_image(image_dir / "person_a_2.jpg", shade=120)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            session = engine.create_init_session(image_dir)
            group = max(engine.list_init_groups(session.session_id), key=lambda item: len(item.faces))
            self.assertGreaterEqual(len(group.faces), 2)

            engine.discard_init_faces(session.session_id, group.group_id, [group.faces[0].init_face_id])

            updated = [item for item in engine.list_init_groups(session.session_id) if item.group_id == group.group_id][0]
            self.assertEqual(updated.status, "pending")
            self.assertEqual(len(updated.faces), len(group.faces) - 1)

    def _write_image(self, image: Path, shade: int) -> None:
        canvas = np.full((160, 160, 3), shade, dtype=np.uint8)
        cv2.rectangle(canvas, (35, 35), (125, 125), (220, 220, 220), -1)
        cv2.circle(canvas, (62, 70), 7, (20, 20, 20), -1)
        cv2.circle(canvas, (98, 70), 7, (20, 20, 20), -1)
        cv2.ellipse(canvas, (80, 100), (28, 12), 0, 0, 180, (20, 20, 20), 2)
        cv2.imwrite(str(image), canvas)

    def _init_face(self, init_face_id: str, vector: tuple[float, ...]) -> InitFace:
        return InitFace(
            init_face_id=init_face_id,
            session_id="session",
            group_id="unassigned",
            source_image=f"{init_face_id}.jpg",
            face=DetectedFace(
                box=FaceBox(x=0, y=0, width=100, height=100, confidence=1.0),
                quality_score=1.0,
            ),
            vector=vector,
            quality=QualityReport(status=QualityStatus.GOOD, score=1.0),
        )


if __name__ == "__main__":
    unittest.main()
