from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from sentriface.cli import build_dev_engine
from sentriface.config import RuntimeConfig
from sentriface.engine import _assign_groups, group_representative_embedding
from sentriface.errors import QueueCancellationError
from sentriface.models import DetectedFace, FaceBox, InitFace, InitGroup, PersonMatch, QualityReport, QualityStatus
from sentriface.storage.sqlite_store import SQLiteIdentityStore


class InitWorkflowTest(unittest.TestCase):
    def test_processing_failure_retains_same_targeted_draft_for_processing_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'data'
            engine = build_dev_engine(root)
            engine.initialize()
            person = engine.store.create_person('Known participant')
            observation = engine.store.create_observation('scan-target-create', participant_ids=[person.person_id])
            engine.store._finalize_observation_without_graph_evidence(observation.observation_id, 'scan-target-finalize')
            source = root / 'uploads' / 'batches' / 'scan' / 'input.jpg'
            source.parent.mkdir(parents=True)
            self._write_image(source, 150)
            revision = engine.store.get_encounter_read(observation.observation_id)['revision']
            with patch.object(engine.detector, 'detect', side_effect=RuntimeError('detector failure')):
                with self.assertRaisesRegex(RuntimeError, 'detector failure'):
                    engine.create_queue_session(source, allow_bad_quality=True, quality_only=False,
                        target_observation_id=observation.observation_id, expected_revision=revision)
            session = engine.store.list_init_sessions()[0]
            self.assertEqual(session.status, 'processing_failed')
            self.assertEqual(session.target_observation_id, observation.observation_id)
            self.assertTrue(source.exists())
            self.assertEqual(len(engine.store.list_init_session_media(session.session_id)), 1)
            engine.store.initialize()
            retry = engine.create_queue_session(source, allow_bad_quality=True,
                target_observation_id=observation.observation_id, expected_revision=revision,
                session_id=session.session_id)
            self.assertEqual(retry.session.session_id, session.session_id)
            self.assertFalse(retry.session.quality_only)
            self.assertEqual(engine.store.get_init_session(session.session_id).status, 'pending')
            self.assertEqual(len(engine.store.list_init_sessions()), 1)
            self.assertEqual(engine.store.get_encounter_read(observation.observation_id)['revision'], revision)

    def test_cancel_targeted_draft_with_restored_source_anchor_cleans_only_owned_media(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'data'
            engine = build_dev_engine(root)
            engine.initialize()
            person = engine.store.create_person('Known participant')
            observation = engine.store.create_observation('target-create', participant_ids=[person.person_id])
            engine.store._finalize_observation_without_graph_evidence(observation.observation_id, 'target-finalize')
            objects = root / 'uploads' / 'objects'
            objects.mkdir(parents=True, exist_ok=True)
            owned, unrelated, shared = [objects / name for name in ('owned.jpg', 'other-upload.jpg', 'shared.jpg')]
            for path in (owned, unrelated, shared):
                path.write_bytes(path.name.encode())
            engine.store.add_embedding(person.person_id, [1.0] * engine.config.embedding_dim,
                quality_score=1.0, source_image=str(shared))
            session = engine.store.create_init_session(str(objects), target_observation_id=observation.observation_id,
                expected_revision=engine.store.get_encounter_read(observation.observation_id)['revision'])
            engine.store.save_init_session_media(session.session_id, [str(owned), str(shared)])
            engine.discard_init_session(session.session_id)
            self.assertFalse(owned.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue(shared.exists())
            self.assertIsNone(engine.store.get_init_session(session.session_id))

    def test_queue_search_policy_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "data" / "sentriface.db"
            store = SQLiteIdentityStore(path, embedding_dim=2)
            store.initialize()
            session = store.create_init_session("/managed/queue", quality_only=False)
            reopened = SQLiteIdentityStore(path, embedding_dim=2)
            reopened.initialize()
            self.assertFalse(reopened.get_init_session(session.session_id).quality_only)
            self.assertFalse(reopened.list_init_sessions()[0].quality_only)

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

    def test_queue_groups_do_not_merge_faces_with_weak_known_match(self) -> None:
        faces = [
            self._init_face("face_1", (1.0, 0.0)),
            self._init_face("face_2", (0.0, 1.0)),
        ]

        grouped = _assign_groups(
            faces,
            threshold=0.9,
            matches_by_face_id={
                face.init_face_id: [
                    PersonMatch(
                        person_id="person-known",
                        score=0.89,
                        embedding_ids=("embedding-known",),
                        embeddings_matched=1,
                    )
                ]
                for face in faces
            },
        )

        self.assertEqual(len({face.group_id for face in grouped}), 2)

    def test_queue_groups_bucket_same_person_by_match_strength(self) -> None:
        faces = [
            self._init_face("strong_1", (1.0, 0.0)),
            self._init_face("strong_2", (0.9, 0.1)),
            self._init_face("likely_1", (0.0, 1.0)),
            self._init_face("likely_2", (0.1, 0.9)),
            self._init_face("possible_1", (-1.0, 0.0)),
            self._init_face("possible_2", (-0.9, 0.1)),
        ]

        grouped = _assign_groups(
            faces,
            threshold=0.8,
            medium_threshold=0.5,
            possible_threshold=0.4,
            matches_by_face_id={
                "strong_1": [self._person_match("person-known", 0.95)],
                "strong_2": [self._person_match("person-known", 0.91)],
                "likely_1": [self._person_match("person-known", 0.70)],
                "likely_2": [self._person_match("person-known", 0.65)],
                "possible_1": [self._person_match("person-known", 0.45)],
                "possible_2": [self._person_match("person-known", 0.43)],
            },
        )

        groups_by_face_id = {face.init_face_id: face.group_id for face in grouped}
        self.assertEqual(groups_by_face_id["strong_1"], groups_by_face_id["strong_2"])
        self.assertEqual(groups_by_face_id["likely_1"], groups_by_face_id["likely_2"])
        self.assertEqual(groups_by_face_id["possible_1"], groups_by_face_id["possible_2"])
        self.assertEqual(len(set(groups_by_face_id.values())), 3)

    def test_group_representative_embedding_is_normalized_centroid(self) -> None:
        group = self._init_group(
            self._init_face("face_1", (1.0, 0.0)),
            self._init_face("face_2", (0.0, 1.0)),
        )

        representative = group_representative_embedding(group)

        self.assertAlmostEqual(representative[0], 0.70710678)
        self.assertAlmostEqual(representative[1], 0.70710678)

    @unittest.skip("obsolete whole-group confirmation API; selected-face atomic review tests replace it")
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

    def test_queue_scan_skips_unreadable_images_and_processes_valid_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_dir = temp_path / "images"
            image_dir.mkdir()
            valid_image = image_dir / "valid.jpg"
            invalid_image = image_dir / "fake.jpg"
            self._write_image(valid_image, shade=120)
            invalid_image.write_bytes(b"not an image")

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            result = engine.create_queue_session(image_dir, allow_bad_quality=True)

            self.assertEqual(result.invalid_images, [str(invalid_image)])
            self.assertEqual(sum(len(group.faces) for group in result.groups), 1)
            self.assertEqual(
                {face.source_image for group in result.groups for face in group.faces},
                {str(valid_image)},
            )

    def test_queue_scan_with_only_unreadable_images_returns_empty_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_dir = temp_path / "images"
            image_dir.mkdir()
            invalid_image = image_dir / "fake.png"
            invalid_image.write_bytes(b"not an image")

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            result = engine.create_queue_session(image_dir, allow_bad_quality=True)

            self.assertEqual(result.invalid_images, [str(invalid_image)])
            self.assertEqual(result.groups, [])
            self.assertEqual(engine.list_init_groups(result.session.session_id), [])

    def test_queue_cancellation_rolls_back_session_crops_and_managed_uploads(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            data_dir = temp_path / "data"
            image_dir = data_dir / "uploads" / "batch"
            image_dir.mkdir(parents=True)
            self._write_image(image_dir / "first.jpg", shade=120)
            self._write_image(image_dir / "second.jpg", shade=180)

            engine = build_dev_engine(data_dir)
            engine.initialize()
            checkpoints = 0

            def cancel_after_first_face() -> bool:
                nonlocal checkpoints
                checkpoints += 1
                return checkpoints >= 9

            with self.assertRaises(QueueCancellationError):
                engine.create_queue_session(
                    image_dir,
                    allow_bad_quality=True,
                    cancel_check=cancel_after_first_face,
                )

            self.assertEqual(engine.list_init_sessions(), [])
            self.assertFalse(image_dir.exists())
            init_dir = data_dir / "faces" / "init"
            self.assertFalse(init_dir.exists() and any(init_dir.rglob("*")))

    def test_queue_failure_rolls_back_partial_session_and_managed_uploads(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            data_dir = temp_path / "data"
            image_dir = data_dir / "uploads" / "failed-batch"
            image_dir.mkdir(parents=True)
            self._write_image(image_dir / "first.jpg", shade=120)
            self._write_image(image_dir / "second.jpg", shade=180)

            engine = build_dev_engine(data_dir)
            engine.initialize()
            detector = engine.detector
            detections = 0

            class FailingDetector:
                def detect(self, image_path: Path):
                    nonlocal detections
                    detections += 1
                    if detections == 2:
                        raise RuntimeError("detector failed")
                    return detector.detect(image_path)

            engine.detector = FailingDetector()
            with self.assertRaisesRegex(RuntimeError, "detector failed"):
                engine.create_queue_session(image_dir, allow_bad_quality=True)

            self.assertEqual(engine.list_init_sessions(), [])
            self.assertFalse(image_dir.exists())
            init_dir = data_dir / "faces" / "init"
            self.assertFalse(init_dir.exists() and any(init_dir.rglob("*")))
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

    @unittest.skip("obsolete pre-P6 confirmation API; selected-face atomic review tests replace it")
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

    def test_queue_skip_and_resume_preserves_group_faces(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_dir = temp_path / "images"
            image_dir.mkdir()
            self._write_image(image_dir / "person_a.jpg", shade=120)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            session = engine.create_init_session(image_dir)
            group = engine.list_init_groups(session.session_id)[0]
            original_face_ids = [face.init_face_id for face in group.faces]

            engine.skip_init_group(session.session_id, group.group_id)
            skipped = engine.list_init_groups(session.session_id)[0]
            self.assertEqual(skipped.status, "skipped")
            self.assertEqual([face.init_face_id for face in skipped.faces], original_face_ids)

            resumed = engine.resume_skipped_init_groups(session.session_id)
            restored = engine.list_init_groups(session.session_id)[0]
            self.assertEqual(resumed, 1)
            self.assertEqual(restored.status, "pending")
            self.assertEqual([face.init_face_id for face in restored.faces], original_face_ids)

    def test_queue_reject_match_excludes_person_from_every_group_face(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            config = RuntimeConfig(data_dir=temp_path / "data", embedding_dim=2)
            engine = build_dev_engine(config.data_dir, config)
            engine.initialize()
            person = engine.store.create_person("Wrong suggestion")
            engine.store.add_embedding(person.person_id, (1.0, 0.0), 1.0)
            engine.index.rebuild(engine.store.list_embeddings())
            session = engine.store.create_init_session("manual")
            faces = [
                self._init_face("face_1", (1.0, 0.0), session.session_id, "group_0001"),
                self._init_face("face_2", (0.99, 0.01), session.session_id, "group_0001"),
            ]
            engine.store.save_init_faces(faces)

            engine.reject_init_group_match(session.session_id, "group_0001", person.person_id)

            exclusions = engine.excluded_person_ids_for_init_faces(
                session.session_id,
                [face.init_face_id for face in faces],
            )
            self.assertTrue(all(person.person_id in exclusions[face.init_face_id] for face in faces))
            for group in engine.list_init_groups(session.session_id):
                self.assertNotIn(person.person_id, [match.person_id for match in engine.matches_for_init_group(group)])

    def test_queue_selected_faces_leave_remaining_group_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_dir = temp_path / "images"
            image_dir.mkdir()
            self._write_image(image_dir / "person_a_1.jpg", shade=120)
            self._write_image(image_dir / "person_a_2.jpg", shade=120)
            with (image_dir / "person_a_2.jpg").open("ab") as stream:
                stream.write(b"distinct photo fixture")

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            session = engine.create_init_session(image_dir)
            staged_faces = [face for item in engine.list_init_groups(session.session_id) for face in item.faces]
            engine.store.update_init_face_groups({face.init_face_id: "selected-fixture" for face in staged_faces})
            engine.store.mark_init_group_status(session.session_id, "selected-fixture", "pending")
            group = max(engine.list_init_groups(session.session_id), key=lambda item: len(item.faces))
            self.assertGreaterEqual(len(group.faces), 2)

            selected = [group.faces[0].init_face_id]
            person_id, embedding_ids = engine.confirm_init_faces(
                session.session_id, group.group_id, selected, "Queue Person", "queue-selected",
                actor={"username": "operator"},
            )

            self.assertTrue(person_id)
            self.assertEqual(len(embedding_ids), 1)
            updated = [item for item in engine.list_init_groups(session.session_id) if item.group_id == group.group_id][0]
            self.assertEqual(updated.status, "pending")
            self.assertEqual(len(updated.faces), len(group.faces) - 1)

    def test_queue_subset_accept_regroups_remaining_faces(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            config = RuntimeConfig(data_dir=temp_path / "data", embedding_dim=2)
            engine = build_dev_engine(temp_path / "data", config)
            engine.initialize()
            session = engine.store.create_init_session("manual")
            faces = [
                self._init_face("face_1", (1.0, 0.0), session.session_id, "group_0001"),
                self._init_face("face_2", (0.0, 1.0), session.session_id, "group_0001"),
                self._init_face("face_3", (-1.0, 0.0), session.session_id, "group_0001"),
            ]
            engine.store.save_init_faces(faces)

            person_id, accepted = engine.confirm_init_faces(
                session.session_id,
                "group_0001",
                ["face_1"],
                "Subset Person",
                "queue-subset",
                recognition_detail={
                    "rank": "Captain", "country": "India", "importance": "High",
                    "added_by": "Operator", "date": "2026-09-27", "time": "09:30",
                    "place_seen": "Lobby", "event_occasion": "Visit",
                },
                actor={"username": "operator"},
            )

            self.assertTrue(person_id)
            self.assertEqual(len(accepted), 1)
            saved = engine.get_person(person_id)
            self.assertEqual(saved.metadata["rank"], "Captain")
            self.assertEqual(saved.metadata["country"], "India")
            self.assertEqual(saved.metadata["importance"], "High")
            self.assertEqual(saved.metadata["added_by"], "Operator")
            encounter = engine.list_observations_for_person(person_id)[0]
            self.assertEqual(encounter.location, "Lobby")
            self.assertEqual(encounter.context["occasion"], "Visit")
            groups = engine.list_init_groups(session.session_id)
            pending_groups = [group for group in groups if group.status == "pending"]
            self.assertEqual(len(pending_groups), 2)
            self.assertEqual(sum(len(group.faces) for group in pending_groups), 2)
            self.assertNotIn("face_1", {face.init_face_id for group in pending_groups for face in group.faces})

    def test_subset_accept_excludes_accepted_person_from_leftover_suggestions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            config = RuntimeConfig(
                data_dir=temp_path / "data",
                embedding_dim=2,
                high_confidence=0.9,
                medium_confidence=0.48,
            )
            engine = build_dev_engine(config.data_dir, config)
            engine.initialize()
            person_p = engine.store.create_person("Person P")
            person_q = engine.store.create_person("Person Q")
            engine.store.add_embedding(person_p.person_id, (1.0, 0.0), 1.0)
            engine.store.add_embedding(person_q.person_id, (0.0, 1.0), 1.0)
            engine.index.rebuild(engine.store.list_embeddings())
            session = engine.store.create_init_session("manual")
            faces = [
                self._init_face("face_1", (1.0, 0.0), session.session_id, "group_0001"),
                self._init_face("face_2", (0.0, 1.0), session.session_id, "group_0001"),
                self._init_face("face_3", (1.0, 0.0), session.session_id, "group_0001"),
            ]
            engine.store.save_init_faces(faces)

            accepted = engine.confirm_init_faces_existing(
                session.session_id,
                "group_0001",
                ["face_1", "face_3"],
                person_p.person_id,
                "queue-existing-subset",
                actor={"username": "operator"},
            )

            self.assertEqual(len(accepted), 2)
            pending_groups = engine.list_init_groups(session.session_id)
            pending_faces = [face for group in pending_groups for face in group.faces]
            self.assertEqual([face.init_face_id for face in pending_faces], ["face_2"])
            exclusions = engine.excluded_person_ids_for_init_faces(session.session_id, ["face_2"])
            self.assertIn(person_p.person_id, exclusions["face_2"])
            matches = engine.matches_for_init_group(pending_groups[0])
            self.assertEqual(matches[0].person_id, person_q.person_id)
            self.assertNotIn(person_p.person_id, [match.person_id for match in matches])

    def test_queue_discard_selected_faces_removes_only_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_dir = temp_path / "images"
            image_dir.mkdir()
            self._write_image(image_dir / "person_a_1.jpg", shade=120)
            self._write_image(image_dir / "person_a_2.jpg", shade=120)
            with (image_dir / "person_a_2.jpg").open("ab") as stream:
                stream.write(b"distinct photo fixture")

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            session = engine.create_init_session(image_dir)
            staged_faces = [face for item in engine.list_init_groups(session.session_id) for face in item.faces]
            engine.store.update_init_face_groups({face.init_face_id: "selected-fixture" for face in staged_faces})
            engine.store.mark_init_group_status(session.session_id, "selected-fixture", "pending")
            group = max(engine.list_init_groups(session.session_id), key=lambda item: len(item.faces))
            self.assertGreaterEqual(len(group.faces), 2)

            engine.discard_init_faces(session.session_id, group.group_id, [group.faces[0].init_face_id])

            updated = [item for item in engine.list_init_groups(session.session_id) if item.group_id == group.group_id][0]
            self.assertEqual(updated.status, "pending")
            self.assertEqual(len(updated.faces), len(group.faces) - 1)

    def test_discard_queue_session_removes_records_and_unreferenced_managed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            engine = build_dev_engine(data_dir)
            engine.initialize()
            source = data_dir / "uploads" / "batch" / "incoming.jpg"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"incoming")
            session = engine.store.create_init_session(str(source.parent))
            crop = engine.config.face_dir / "init" / session.session_id / "face.jpg"
            crop.parent.mkdir(parents=True)
            crop.write_bytes(b"crop")

            engine.discard_init_session(session.session_id)

            self.assertIsNone(engine.store.get_init_session(session.session_id))
            self.assertFalse(source.exists())
            self.assertFalse(crop.exists())

    def test_discard_queue_session_preserves_files_used_by_embeddings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            engine = build_dev_engine(data_dir)
            engine.initialize()
            source = data_dir / "uploads" / "batch" / "accepted.jpg"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"accepted")
            session = engine.store.create_init_session(str(source.parent))
            crop = engine.config.face_dir / "init" / session.session_id / "accepted-crop.jpg"
            crop.parent.mkdir(parents=True)
            crop.write_bytes(b"crop")
            person = engine.store.create_person("Accepted Person")
            engine.store.add_embedding(
                person.person_id,
                [0.0] * engine.config.embedding_dim,
                quality_score=1.0,
                source_image=str(source),
                crop_path=str(crop),
            )

            engine.discard_init_session(session.session_id)

            self.assertIsNone(engine.store.get_init_session(session.session_id))
            self.assertTrue(source.exists())
            self.assertTrue(crop.exists())

    def _write_image(self, image: Path, shade: int) -> None:
        canvas = np.full((160, 160, 3), shade, dtype=np.uint8)
        cv2.rectangle(canvas, (35, 35), (125, 125), (220, 220, 220), -1)
        cv2.circle(canvas, (62, 70), 7, (20, 20, 20), -1)
        cv2.circle(canvas, (98, 70), 7, (20, 20, 20), -1)
        cv2.ellipse(canvas, (80, 100), (28, 12), 0, 0, 180, (20, 20, 20), 2)
        cv2.imwrite(str(image), canvas)

    def _init_face(
        self,
        init_face_id: str,
        vector: tuple[float, ...],
        session_id: str = "session",
        group_id: str = "unassigned",
    ) -> InitFace:
        return InitFace(
            init_face_id=init_face_id,
            session_id=session_id,
            group_id=group_id,
            source_image=f"{init_face_id}.jpg",
            face=DetectedFace(
                box=FaceBox(x=0, y=0, width=100, height=100, confidence=1.0),
                quality_score=1.0,
            ),
            vector=vector,
            quality=QualityReport(status=QualityStatus.GOOD, score=1.0),
        )

    def _init_group(self, *faces: InitFace):
        return InitGroup(
            group_id="group_0001",
            session_id="session",
            faces=list(faces),
        )

    def _person_match(self, person_id: str, score: float) -> PersonMatch:
        return PersonMatch(
            person_id=person_id,
            score=score,
            embedding_ids=("embedding-known",),
            embeddings_matched=1,
        )


if __name__ == "__main__":
    unittest.main()
