from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

from sentriface.cli import build_dev_engine


class PersonManagementTest(unittest.TestCase):
    def test_public_merge_and_undo_are_gated_until_p8(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            engine = build_dev_engine(Path(temp) / "data")
            engine.initialize()
            source = engine.store.create_person("Source")
            target = engine.store.create_person("Target")

            with self.assertRaisesRegex(RuntimeError, "temporarily unavailable.*P8"):
                engine.merge_persons(source.person_id, target.person_id, "gated-merge")
            with self.assertRaisesRegex(RuntimeError, "temporarily unavailable.*P8"):
                engine.undo_merge_persons("legacy-merge", "gated-undo")

            self.assertEqual(
                engine.store.get_person(source.person_id).lifecycle_status,
                "ACTIVE",
            )
            self.assertIsNone(
                engine.store.get_person_operation("gated-merge", "merge-persons")
            )

    def test_placeholder_creation_duplicate_names_and_zero_embedding_search(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            engine = build_dev_engine(Path(temp) / "data")
            engine.initialize()

            placeholder = engine.create_placeholder_person(
                "  Alex Morgan  ",
                {"rank": "Visitor", "tags": ["expected"]},
                "Operator",
                "placeholder-create-1",
            )

            self.assertEqual(placeholder.name, "Alex Morgan")
            self.assertEqual(placeholder.enrollment_status, "placeholder")
            self.assertEqual(engine.list_person_embeddings(placeholder.person_id), [])
            summary = next(
                item for item in engine.list_persons()
                if item.person.person_id == placeholder.person_id
            )
            self.assertEqual(summary.embedding_count, 0)
            self.assertEqual(engine.index.search(tuple([0.0] * 512), 5), [])
            with self.assertRaisesRegex(KeyError, "placeholder with this name"):
                engine.create_placeholder_person(
                    "alex morgan",
                    {},
                    "Operator",
                    "placeholder-create-2",
                )

            enrolled_same_name = engine.store.create_person("Alex Morgan")
            self.assertNotEqual(enrolled_same_name.person_id, placeholder.person_id)
            changes = engine.list_person_changes(placeholder.person_id)
            self.assertEqual(changes[0].new_status, "placeholder")
            self.assertEqual(changes[0].editor_name, "Operator")

    def test_placeholder_becomes_enrolled_and_releases_name_after_photo(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            placeholder = engine.create_placeholder_person(
                "Future Visitor",
                {},
                "Operator",
                "placeholder-enroll-1",
            )

            engine.confirm_existing_person(
                engine.prepare_additions(image)[0],
                placeholder.person_id,
            )

            enrolled = engine.get_person(placeholder.person_id)
            self.assertEqual(enrolled.enrollment_status, "enrolled")
            self.assertEqual(len(engine.list_person_embeddings(placeholder.person_id)), 1)
            self.assertEqual(engine.recognize(image)[0].matches[0].person_id, placeholder.person_id)
            changes = engine.list_person_changes(placeholder.person_id)
            self.assertTrue(any(
                change.previous_status == "placeholder" and change.new_status == "enrolled"
                for change in changes
            ))
            replacement = engine.create_placeholder_person(
                "future visitor",
                {},
                "Operator",
                "placeholder-enroll-2",
            )
            self.assertEqual(replacement.enrollment_status, "placeholder")

    def test_placeholder_archive_and_permanent_deletion_use_existing_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            engine = build_dev_engine(Path(temp) / "data")
            engine.initialize()
            placeholder = engine.create_placeholder_person(
                "Temporary Identity",
                {},
                "Operator",
                "placeholder-delete-1",
            )

            archived = engine.archive_person(placeholder.person_id, "placeholder-archive-1")
            self.assertTrue(archived["archived"])
            self.assertIsNone(engine.get_person(placeholder.person_id))
            deleted = engine.permanently_delete_person(
                placeholder.person_id,
                "placeholder-purge-1",
            )
            self.assertTrue(deleted["deleted"])
            self.assertEqual(deleted["deleted_embeddings"], 0)
            self.assertTrue(deleted["tombstoned"])
            historical = engine.get_person(placeholder.person_id, include_archived=True)
            self.assertIsNotNone(historical)
            self.assertEqual(historical.lifecycle_status, "DELETED")

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

            result = engine._legacy_merge_persons_for_compatibility(source, target)

            self.assertEqual(result["moved_embeddings"], 1)
            self.assertIsNone(engine.get_person(source))
            self.assertEqual(len(engine.list_person_embeddings(target)), 2)
            self.assertEqual(engine.recognize(image_a)[0].matches[0].person_id, target)

    def test_archive_restore_and_preferences_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "Person A")
            embedding_id = engine.list_person_embeddings(person_id)[0].embedding_id

            preference_operation = "11111111-1111-4111-8111-111111111111"
            first_preference = engine.update_person_preferences(
                person_id,
                preference_operation,
                favorite=True,
                representative_embedding_id=embedding_id,
            )
            second_preference = engine.update_person_preferences(
                person_id,
                preference_operation,
                favorite=False,
            )
            self.assertEqual(first_preference, second_preference)
            self.assertTrue(engine.get_person(person_id).metadata["favorite"])
            self.assertEqual(
                engine.list_person_operations(person_id)[0]["operation_type"],
                "person-preferences",
            )
            self.assertEqual(
                first_preference["changed_preferences"],
                ["favorite", "representative_photo"],
            )

            archive_operation = "22222222-2222-4222-8222-222222222222"
            self.assertTrue(engine.archive_person(person_id, archive_operation)["archived"])
            self.assertTrue(engine.archive_person(person_id, archive_operation)["archived"])
            self.assertIsNone(engine.get_person(person_id))
            self.assertIsNotNone(engine.get_person(person_id, include_archived=True))
            self.assertEqual(len(engine.list_persons(archived=True)), 1)

            restore_operation = "33333333-3333-4333-8333-333333333333"
            self.assertTrue(engine.restore_person(person_id, restore_operation)["restored"])
            self.assertIsNotNone(engine.get_person(person_id))
            self.assertEqual(engine.recognize(image)[0].matches[0].person_id, person_id)

    def test_profile_update_tags_and_history_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "Person A")
            operation_id = "88888888-8888-4888-8888-888888888888"

            first = engine.update_person_profile(
                person_id=person_id,
                name="Updated Person",
                rank="Operator",
                country="India",
                importance="High",
                editor_name="Reviewer",
                tags=["staff", "Staff", "north"],
                operation_id=operation_id,
            )
            second = engine.update_person_profile(
                person_id=person_id,
                name="Ignored Retry",
                rank="Ignored",
                country="Ignored",
                importance="Low",
                editor_name="Retry",
                tags=[],
                operation_id=operation_id,
            )

            self.assertEqual(first.change_id, second.change_id)
            self.assertEqual(len(engine.list_person_changes(person_id)), 1)
            person = engine.get_person(person_id)
            self.assertEqual(person.name, "Updated Person")
            self.assertEqual(person.metadata["tags"], ["staff", "north"])

    def test_move_embedding_moves_linked_sightings_atomically(self) -> None:
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
            engine.add_recognition_detail(
                embedding_id=embedding.embedding_id,
                person_id=person_a,
                image_id="image-a",
                image_path=str(image_a),
                name="Person A",
                decision="accepted",
                seen_date="2026-07-26",
                seen_time="10:00",
                place_seen="Lobby",
                individual_count=1,
                event_occasion="Arrival",
            )

            operation_id = "44444444-4444-4444-8444-444444444444"
            result = engine.move_embedding(embedding.embedding_id, person_b, operation_id)

            self.assertEqual(result["moved_sightings"], 1)
            self.assertEqual(engine.list_person_embeddings(person_a), [])
            moved_details = engine.list_recognition_details_for_person(person_b)
            self.assertEqual(len(moved_details), 1)
            self.assertEqual(moved_details[0].person_id, person_b)
            self.assertEqual(moved_details[0].name, "Person B")
            self.assertEqual(
                engine.move_embedding(embedding.embedding_id, person_b, operation_id),
                result,
            )

    def test_merge_moves_sightings_and_combines_people_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_a = temp_path / "face-a.jpg"
            image_b = temp_path / "face-b.jpg"
            self._write_image(image_a, shade=128)
            self._write_image(image_b, shade=145)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            source = engine.confirm_new_person(
                engine.prepare_additions(image_a)[0],
                "Source",
                metadata={"favorite": True, "tags": ["staff"]},
            )
            target = engine.confirm_new_person(
                engine.prepare_additions(image_b)[0],
                "Target",
                metadata={"tags": ["vip"]},
            )
            source_embedding = engine.list_person_embeddings(source)[0]
            engine.add_recognition_detail(
                embedding_id=source_embedding.embedding_id,
                person_id=source,
                image_id="source-image",
                image_path=str(image_a),
                name="Source",
                decision="accepted",
                seen_date="2026-07-26",
                seen_time="11:00",
                place_seen="Gate",
                individual_count=1,
                event_occasion="Arrival",
            )

            operation_id = "55555555-5555-4555-8555-555555555555"
            result = engine._legacy_merge_persons_for_compatibility(
                source, target, operation_id,
            )

            self.assertEqual(result["moved_embeddings"], 1)
            self.assertEqual(result["moved_sightings"], 1)
            self.assertEqual(engine.list_recognition_details_for_person(target)[0].name, "Target")
            metadata = engine.get_person(target).metadata
            self.assertTrue(metadata["favorite"])
            self.assertEqual(metadata["tags"], ["vip", "staff"])
            archived_source = engine.get_person(source, include_archived=True)
            self.assertEqual(archived_source.metadata["merged_into"], target)
            self.assertEqual(
                engine._legacy_merge_persons_for_compatibility(
                    source, target, operation_id,
                ),
                result,
            )
            with self.assertRaises(KeyError):
                engine.restore_person(
                    source,
                    "99999999-9999-4999-8999-999999999999",
                )

    def test_undo_merge_restores_both_people_and_their_original_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_a = temp_path / "face-a.jpg"
            image_b = temp_path / "face-b.jpg"
            self._write_image(image_a, shade=128)
            self._write_image(image_b, shade=145)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            source = engine.confirm_new_person(
                engine.prepare_additions(image_a)[0],
                "Source",
                metadata={"favorite": True, "tags": ["source"]},
            )
            target = engine.confirm_new_person(
                engine.prepare_additions(image_b)[0],
                "Target",
                metadata={"tags": ["target"]},
            )
            source_before = engine.get_person(source)
            target_before = engine.get_person(target)
            source_embedding = engine.list_person_embeddings(source)[0]
            target_embedding = engine.list_person_embeddings(target)[0]
            engine.add_recognition_detail(
                embedding_id=source_embedding.embedding_id,
                person_id=source,
                image_id="source-image",
                image_path=str(image_a),
                name="Source",
                decision="accepted",
                seen_date="2026-08-05",
                seen_time="10:30",
                place_seen="Gate",
                individual_count=1,
                event_occasion="Arrival",
            )

            merge_operation_id = "10101010-1010-4010-8010-101010101010"
            undo_operation_id = "20202020-2020-4020-8020-202020202020"
            merge_result = engine._legacy_merge_persons_for_compatibility(
                source, target, merge_operation_id,
            )
            self.assertTrue(merge_result["undo_supported"])

            undo_result = engine._legacy_undo_merge_persons_for_compatibility(
                merge_operation_id, undo_operation_id,
            )

            self.assertTrue(undo_result["undone"])
            self.assertEqual(undo_result["restored_embeddings"], 1)
            self.assertEqual(undo_result["restored_sightings"], 1)
            self.assertEqual(engine.get_person(source).metadata, source_before.metadata)
            self.assertEqual(engine.get_person(target).metadata, target_before.metadata)
            self.assertEqual(
                [item.embedding_id for item in engine.list_person_embeddings(source)],
                [source_embedding.embedding_id],
            )
            self.assertEqual(
                [item.embedding_id for item in engine.list_person_embeddings(target)],
                [target_embedding.embedding_id],
            )
            restored_detail = engine.list_recognition_details_for_person(source)[0]
            self.assertEqual(restored_detail.person_id, source)
            self.assertEqual(restored_detail.name, "Source")
            self.assertEqual(
                engine._legacy_undo_merge_persons_for_compatibility(
                    merge_operation_id, undo_operation_id,
                ),
                undo_result,
            )

    def test_undo_merge_refuses_to_overwrite_changes_made_after_merge(self) -> None:
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
            merge_operation_id = "30303030-3030-4030-8030-303030303030"
            engine._legacy_merge_persons_for_compatibility(
                source, target, merge_operation_id,
            )
            engine.update_person_profile(
                person_id=target,
                name="Edited after merge",
                rank="",
                country="",
                importance="",
                editor_name="Reviewer",
                tags=[],
                operation_id="40404040-4040-4040-8040-404040404040",
            )

            with self.assertRaisesRegex(KeyError, "changed after the merge"):
                engine._legacy_undo_merge_persons_for_compatibility(
                    merge_operation_id,
                    "50505050-5050-4050-8050-505050505050",
                )

            self.assertIsNone(engine.get_person(source))
            self.assertEqual(engine.get_person(target).name, "Edited after merge")

    def test_failed_merge_leaves_both_people_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            source = engine.confirm_new_person(engine.prepare_additions(image)[0], "Source")
            before = engine.list_person_embeddings(source)

            with self.assertRaises(KeyError):
                engine._legacy_merge_persons_for_compatibility(
                    source,
                    "missing-target",
                    "66666666-6666-4666-8666-666666666666",
                )

            self.assertIsNotNone(engine.get_person(source))
            self.assertEqual(engine.list_person_embeddings(source), before)

    def test_delete_restore_and_permanent_purge_preserve_expected_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "Person A")
            embedding = engine.list_person_embeddings(person_id)[0]
            engine.add_recognition_detail(
                embedding_id=embedding.embedding_id,
                person_id=person_id,
                image_id="image-a",
                image_path=str(image),
                name="Person A",
                decision="accepted",
                seen_date="2026-07-26",
                seen_time="12:00",
                place_seen="Lobby",
                individual_count=1,
                event_occasion="Arrival",
            )
            operation_id = "77777777-7777-4777-8777-777777777777"

            result = engine.delete_embedding(embedding.embedding_id, operation_id)

            self.assertEqual(result["retained_sightings"], 1)
            self.assertEqual(engine.list_person_embeddings(person_id), [])
            self.assertEqual(engine.list_recognition_details_for_person(person_id), [])
            self.assertEqual(engine.delete_embedding(embedding.embedding_id, operation_id), result)
            deleted = engine.list_deleted_embeddings()
            self.assertEqual(len(deleted), 1)
            self.assertEqual(deleted[0]["sighting_count"], 1)
            self.assertEqual(deleted[0]["person_id"], person_id)

            restored = engine.restore_deleted_embedding(
                embedding.embedding_id,
                "12121212-1212-4212-8212-121212121212",
            )
            self.assertTrue(restored["restored"])
            self.assertEqual(len(engine.list_person_embeddings(person_id)), 1)
            self.assertEqual(len(engine.list_recognition_details_for_person(person_id)), 1)
            self.assertEqual(engine.recognize(image)[0].matches[0].person_id, person_id)

            with self.assertRaises(KeyError):
                engine.permanently_delete_embedding(
                    embedding.embedding_id,
                    "13131313-1313-4313-8313-131313131313",
                )

            engine.delete_embedding(
                embedding.embedding_id,
                "14141414-1414-4414-8414-141414141414",
            )
            purged = engine.permanently_delete_embedding(
                embedding.embedding_id,
                "15151515-1515-4515-8515-151515151515",
            )
            self.assertTrue(purged["permanent"])
            self.assertEqual(purged["deleted_sightings"], 1)
            self.assertEqual(engine.list_deleted_embeddings(), [])
            self.assertEqual(engine.store.list_recognition_details_for_embedding(embedding.embedding_id), [])
            self.assertEqual(
                engine.permanently_delete_embedding(
                    embedding.embedding_id,
                    "15151515-1515-4515-8515-151515151515",
                ),
                purged,
            )

    def test_deleted_face_cannot_move_or_receive_sightings_and_archived_owner_blocks_restore(self) -> None:
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
            engine.delete_embedding(
                embedding.embedding_id,
                "16161616-1616-4616-8616-161616161616",
            )

            with self.assertRaises(KeyError):
                engine.move_embedding(
                    embedding.embedding_id,
                    person_b,
                    "17171717-1717-4717-8717-171717171717",
                )
            with self.assertRaises(KeyError):
                engine.add_recognition_detail(
                    embedding_id=embedding.embedding_id,
                    person_id=person_a,
                    image_id="deleted-image",
                    name="Person A",
                    decision="accepted",
                    seen_date="2026-07-26",
                    seen_time="12:30",
                    place_seen="Lobby",
                    individual_count=1,
                    event_occasion="Arrival",
                )

            engine.archive_person(
                person_a,
                "18181818-1818-4818-8818-181818181818",
            )
            with self.assertRaises(KeyError):
                engine.restore_deleted_embedding(
                    embedding.embedding_id,
                    "19191919-1919-4919-8919-191919191919",
                )
            engine.restore_person(
                person_a,
                "20202020-2020-4020-8020-202020202020",
            )
            self.assertTrue(
                engine.restore_deleted_embedding(
                    embedding.embedding_id,
                    "21212121-2121-4121-8121-212121212121",
                )["restored"]
            )

    def test_merge_moves_deleted_faces_without_reactivating_them(self) -> None:
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
            deleted_embedding = engine.list_person_embeddings(source)[0]
            engine.delete_embedding(
                deleted_embedding.embedding_id,
                "22222222-2222-4222-8222-222222222221",
            )

            result = engine._legacy_merge_persons_for_compatibility(
                source,
                target,
                "23232323-2323-4323-8323-232323232323",
            )

            self.assertEqual(result["moved_embeddings"], 0)
            self.assertEqual(result["moved_deleted_faces"], 1)
            deleted = engine.list_deleted_embeddings()
            self.assertEqual(deleted[0]["person_id"], target)
            self.assertEqual(len(engine.list_person_embeddings(target)), 1)
            self.assertEqual(engine.recognize(image_a)[0].matches[0].person_id, target)

    def test_representative_photo_is_cleared_on_delete_and_restored_when_needed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "Person A")
            embedding_id = engine.list_person_embeddings(person_id)[0].embedding_id
            engine.update_person_preferences(
                person_id,
                "24242424-2424-4424-8424-242424242424",
                representative_embedding_id=embedding_id,
            )

            engine.delete_embedding(
                embedding_id,
                "25252525-2525-4525-8525-252525252525",
            )
            self.assertNotIn("representative_embedding_id", engine.get_person(person_id).metadata)
            engine.restore_deleted_embedding(
                embedding_id,
                "26262626-2626-4626-8626-262626262626",
            )
            self.assertEqual(
                engine.get_person(person_id).metadata["representative_embedding_id"],
                embedding_id,
            )

    def test_operation_id_cannot_cross_people_operation_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "Person A")
            embedding_id = engine.list_person_embeddings(person_id)[0].embedding_id
            operation_id = "27272727-2727-4727-8727-272727272727"
            engine.delete_embedding(embedding_id, operation_id)

            with self.assertRaises(KeyError):
                engine.restore_deleted_embedding(embedding_id, operation_id)

    def test_concurrent_retry_applies_soft_delete_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "Person A")
            embedding_id = engine.list_person_embeddings(person_id)[0].embedding_id
            operation_id = "28282828-2828-4828-8828-282828282828"

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(
                    lambda _: engine.delete_embedding(embedding_id, operation_id),
                    range(2),
                ))

            self.assertEqual(results[0], results[1])
            self.assertEqual(len(engine.list_deleted_embeddings()), 1)
            matching_events = [
                event
                for event in engine.list_person_operations(person_id)
                if event["operation_id"] == operation_id
            ]
            self.assertEqual(len(matching_events), 1)

    def test_deleted_face_expires_at_thirty_days_not_before(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "Person A")
            embedding_id = engine.list_person_embeddings(person_id)[0].embedding_id
            deleted = engine.delete_embedding(
                embedding_id,
                "29292929-2929-4929-8929-292929292929",
            )
            deleted_at = datetime.fromisoformat(deleted["deleted_at"])
            purge_after = datetime.fromisoformat(deleted["purge_after"])

            self.assertEqual(purge_after - deleted_at, timedelta(days=30))
            self.assertEqual(
                engine.list_expired_deleted_embedding_ids(
                    (purge_after - timedelta(microseconds=1)).isoformat()
                ),
                [],
            )
            self.assertEqual(
                engine.list_expired_deleted_embedding_ids(purge_after.isoformat()),
                [embedding_id],
            )

    def test_merge_persons_rejects_same_person(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "Person A")

            with self.assertRaises(KeyError):
                engine._legacy_merge_persons_for_compatibility(person_id, person_id)

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
