from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sentriface.components.linear_index import LinearFaceIndex
from sentriface.storage.sqlite_store import SQLiteIdentityStore


class IdentityMergeOrchestrationTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def test_preview_is_read_only_and_basic_merge_preserves_raw_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            target = store.create_person("Target")
            embedding = store.add_embedding(source.person_id, (1.0, 0.0), 0.9)
            detail = store.add_recognition_detail(
                embedding.embedding_id, source.person_id, "image", "Source",
                "accepted", "2026-01-01", "10:00", "HQ", 1, "Review",
            )

            preview = store.preview_identity_merge(source.person_id, target.person_id)
            self.assertFalse(preview["will_mutate"])
            self.assertEqual(store.get_person(source.person_id).lifecycle_status, "ACTIVE")
            self.assertIn("EMBEDDING", {item["item_type"] for item in preview["affected_items"]})
            self.assertIn("RECOGNITION_HISTORY", {item["item_type"] for item in preview["affected_items"]})

            result = store.execute_identity_merge(source.person_id, target.person_id, "basic-merge")
            self.assertEqual(result["target_person_id"], target.person_id)
            raw_source = store.get_person(source.person_id, include_archived=True)
            self.assertEqual(raw_source.lifecycle_status, "MERGED")
            self.assertEqual(raw_source.canonical_person_id, target.person_id)
            self.assertEqual(store.get_effective_person(source.person_id).person_id, target.person_id)
            self.assertEqual(store.list_raw_embeddings_for_person(source.person_id)[0].person_id, source.person_id)
            self.assertEqual(store.list_raw_recognition_details_for_person(source.person_id)[0].detail_id, detail.detail_id)
            self.assertEqual(store.list_embeddings_for_person(target.person_id)[0].embedding_id, embedding.embedding_id)

    def test_profile_conflict_strategies_are_applied_and_invertible(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person(
                "Source", {"rank": "S", "country": "IN", "tags": ["source"]},
            )
            target = store.create_person(
                "Target", {"rank": "T", "country": "US", "tags": ["target"]},
            )
            result = store.execute_identity_merge(
                source.person_id,
                target.person_id,
                "conflict-merge",
                conflict_resolutions={
                    "name": "KEEP_SOURCE",
                    "rank": "KEEP_TARGET",
                    "tags": "COMBINE",
                    "country": {"strategy": "USER_SELECTED", "selected_value": "CA"},
                },
            )
            self.assertTrue(result["merged"])
            survivor = store.get_person(target.person_id)
            self.assertEqual(survivor.name, "Source")
            self.assertEqual(survivor.metadata["rank"], "T")
            self.assertEqual(survivor.metadata["country"], "CA")
            self.assertEqual(survivor.metadata["tags"], ["target", "source"])
            manifest = store.get_merge_operation("conflict-merge")
            strategies = {item.field_name: item.strategy.value for item in manifest.conflicts}
            self.assertEqual(strategies["name"], "KEEP_SOURCE")
            self.assertEqual(strategies["rank"], "KEEP_TARGET")
            self.assertEqual(strategies["tags"], "COMBINE")
            self.assertEqual(strategies["country"], "USER_SELECTED")
            self.assertTrue(all(item.inverse_data for item in manifest.conflicts))

    def test_no_face_and_enrolled_merge_sets_survivor_biometric_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            enrolled_source = store.create_person("Enrolled")
            no_face_target = store.create_person("No face")
            store.add_embedding(enrolled_source.person_id, (1.0, 0.0), 0.9)
            store.execute_identity_merge(enrolled_source.person_id, no_face_target.person_id, "biometric-merge")
            lifecycle = store.get_person_lifecycle(no_face_target.person_id)
            self.assertEqual(lifecycle["biometric_status"], "ENROLLED")

    def test_merged_embedding_keeps_raw_owner_and_moves_by_effective_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            survivor = store.create_person("Survivor")
            destination = store.create_person("Destination")
            embedding = store.add_embedding(source.person_id, (1.0, 0.0), 0.9)
            actor = {"user_id": "operator-1", "username": "operator"}

            store.execute_identity_merge(
                source.person_id, survivor.person_id, "embedding-merge", actor=actor,
            )
            indexed = LinearFaceIndex()
            indexed.rebuild(store.list_embeddings())
            self.assertEqual(
                indexed.search((1.0, 0.0), 1)[0].person_id,
                survivor.person_id,
            )
            store.update_person_preferences(
                survivor.person_id,
                "representative-after-merge",
                representative_embedding_id=embedding.embedding_id,
                actor=actor,
            )
            moved = store.move_face(
                embedding.embedding_id, destination.person_id, "move-after-merge", actor=actor,
            )

            self.assertEqual(moved["source_person_id"], survivor.person_id)
            self.assertEqual(moved["raw_owner_person_id"], source.person_id)
            raw = store.list_raw_embeddings_for_person(source.person_id)
            self.assertEqual([item.embedding_id for item in raw], [embedding.embedding_id])
            self.assertEqual(raw[0].person_id, source.person_id)
            effective = store.list_embeddings_for_person(destination.person_id)
            self.assertEqual(effective[0].canonical_person_id, destination.person_id)
            store.delete_embedding(embedding.embedding_id, "delete-after-move", actor=actor)
            restored = store.restore_deleted_embedding(
                embedding.embedding_id, "restore-after-move", actor=actor,
            )
            self.assertEqual(restored["person_id"], destination.person_id)
            self.assertEqual(restored["raw_person_id"], source.person_id)

    def test_merge_note_resolution_creates_normalized_revision_and_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source", notes="Source history")
            target = store.create_person("Target", notes="Target history")
            target_note_before = store.get_person_note(target.person_id)

            store.execute_identity_merge(
                source.person_id,
                target.person_id,
                "note-merge",
                conflict_resolutions={"notes": "COMBINE"},
                actor={"username": "operator"},
            )

            target_note = store.get_person_note(target.person_id)
            self.assertEqual(target_note.note_id, target_note_before.note_id)
            self.assertEqual(target_note.revision_number, target_note_before.revision_number + 1)
            self.assertEqual(target_note.content, "Target history\n\nSource history")
            self.assertEqual(store.get_person(target.person_id).notes, target_note.content)
            self.assertEqual(
                store.get_person_note(source.person_id).content,
                "Source history",
            )
            revisions = store.list_note_revisions(target_note.note_id)
            self.assertEqual([item.content for item in revisions], [
                "Target history", "Target history\n\nSource history",
            ])

    def test_current_activity_comes_from_operation_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            target = store.create_person("Target")
            corrected = store.create_person("Corrected")
            actor = {"user_id": "operator-1", "display_name": "Operator"}
            store.execute_identity_merge(source.person_id, target.person_id, "activity-merge", actor=actor)
            observation = store.create_observation(
                "activity-observation", participant_ids=[target.person_id], actor=actor,
            )
            store._finalize_observation_without_graph_evidence(
                observation.observation_id, "activity-finalize",
            )
            store.correct_observation_identity(
                observation.observation_id,
                target.person_id,
                corrected.person_id,
                "activity-correction",
                actor=actor,
            )
            store.archive_person(target.person_id, "activity-archive", actor=actor)

            activity = store.list_person_operations(target.person_id)
            self.assertTrue({
                "identity.merge", "identity.observation.correct", "identity.archive",
            }.issubset({item["operation_type"] for item in activity}))
            self.assertTrue(all(item["actor"].get("user_id") == "operator-1" for item in activity))
            with store._connect() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM person_operations").fetchone()[0], 1)

    def test_correction_before_merge_and_participant_collapse_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            original = store.create_person("Original")
            corrected = store.create_person("Corrected")
            survivor = store.create_person("Survivor")
            observation = store.create_observation(
                "create-observation", participant_ids=[original.person_id, survivor.person_id],
            )
            store._finalize_observation_without_graph_evidence(observation.observation_id, "finalize-observation")
            store.correct_observation_identity(
                observation.observation_id, original.person_id, corrected.person_id, "correct-observation",
            )
            store.execute_identity_merge(corrected.person_id, survivor.person_id, "corrected-merge")

            effective = store.list_effective_observation_participants(observation.observation_id)
            self.assertEqual([item.person_id for item in effective], [survivor.person_id])
            raw = store.list_raw_observation_participants(observation.observation_id)
            self.assertEqual({item.person_id for item in raw}, {original.person_id, survivor.person_id})
            correction = store.list_corrections_for_observation(observation.observation_id)[0]
            self.assertEqual(correction.to_person_id, corrected.person_id)

    def test_graph_edges_collapse_self_edges_are_suppressed_and_raw_evidence_remains(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            a = store.create_person("A")
            b = store.create_person("B")
            c = store.create_person("C")
            observations = []
            for index, participants in enumerate((
                [a.person_id, c.person_id],
                [b.person_id, c.person_id],
                [a.person_id, b.person_id],
            )):
                observation = store.create_observation(f"obs-{index}", participant_ids=participants)
                store._finalize_observation_without_graph_evidence(observation.observation_id, f"final-{index}")
                store.record_observation_evidence(observation.observation_id, f"evidence-{index}")
                observations.append(observation)
            with store._connect() as conn:
                raw_before = [tuple(row) for row in conn.execute(
                    "SELECT * FROM relationship_evidence ORDER BY evidence_id"
                ).fetchall()]

            store.execute_identity_merge(a.person_id, b.person_id, "graph-merge")
            projection = store.get_global_graph_projection()
            connections = [item for item in projection.connections if {item.source_person_id, item.target_person_id} == {b.person_id, c.person_id}]
            self.assertEqual(len(connections), 1)
            self.assertEqual(connections[0].evidence_count, 2)
            self.assertFalse(any(item.source_person_id == item.target_person_id for item in projection.connections))
            with store._connect() as conn:
                raw_after = [tuple(row) for row in conn.execute(
                    "SELECT * FROM relationship_evidence ORDER BY evidence_id"
                ).fetchall()]
            self.assertEqual(raw_after, raw_before)
            self.assertTrue(store.validate_graph_projection()["valid"])

    def test_chained_merge_keeps_each_manifest_truthful(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            a = store.create_person("A")
            b = store.create_person("B")
            c = store.create_person("C")
            store.execute_identity_merge(a.person_id, b.person_id, "merge-a-b")
            store.execute_identity_merge(b.person_id, c.person_id, "merge-b-c")
            self.assertEqual(store.resolve_canonical_person_id(a.person_id), c.person_id)
            self.assertEqual(store.resolve_canonical_person_id(b.person_id), c.person_id)
            self.assertEqual(store.get_merge_operation("merge-a-b").target_person_id, b.person_id)
            self.assertEqual(store.get_merge_operation("merge-b-c").target_person_id, c.person_id)

    def test_invalid_deleted_self_and_inactive_target_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            target = store.create_person("Target")
            with self.assertRaisesRegex(ValueError, "different"):
                store.preview_identity_merge(source.person_id, source.person_id)
            store.soft_delete_person(target.person_id, "delete-target")
            with self.assertRaisesRegex(KeyError, "terminal active"):
                store.preview_identity_merge(source.person_id, target.person_id)

    def test_failure_rolls_back_manifest_profile_canonical_and_graph_and_is_durable(self) -> None:
        for stage in ("after_canonical_update", "after_graph_rebuild"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temp:
                store = self._store(Path(temp))
                source = store.create_person("Source")
                target = store.create_person("Target")

                def fail(current: str) -> None:
                    if current == stage:
                        raise RuntimeError(stage)

                with self.assertRaisesRegex(RuntimeError, stage):
                    store.execute_identity_merge(
                        source.person_id, target.person_id, f"failure-{stage}",
                        conflict_resolutions={"name": "KEEP_SOURCE"},
                        failure_injector=fail,
                    )
                self.assertEqual(store.get_person(source.person_id).lifecycle_status, "ACTIVE")
                self.assertEqual(store.get_person(target.person_id).name, "Target")
                self.assertIsNone(store.get_merge_operation(f"failure-{stage}"))
                self.assertEqual(store.get_operation(f"failure-{stage}")["status"], "FAILED")
                self.assertTrue(store.validate_graph_projection()["valid"])

    def test_index_failure_rolls_back_and_success_publishes_survivor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            target = store.create_person("Target")
            store.add_embedding(source.person_id, (1.0, 0.0), 0.9)

            with self.assertRaisesRegex(RuntimeError, "index failed"):
                store.execute_identity_merge(
                    source.person_id, target.person_id, "index-failure",
                    publish_index=lambda records: (_ for _ in ()).throw(RuntimeError("index failed")),
                )
            self.assertEqual(store.get_person(source.person_id).lifecycle_status, "ACTIVE")
            self.assertEqual(store.get_operation("index-failure")["status"], "FAILED")

            index = LinearFaceIndex()
            store.execute_identity_merge(
                source.person_id, target.person_id, "index-success", publish_index=index.rebuild,
            )
            self.assertEqual(index.search((1.0, 0.0), 1)[0].person_id, target.person_id)

    def test_success_retry_is_idempotent_and_failed_id_requires_a_new_retry_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            target = store.create_person("Target")
            first = store.execute_identity_merge(source.person_id, target.person_id, "retry-success")
            second = store.execute_identity_merge(source.person_id, target.person_id, "retry-success")
            self.assertEqual(first, second)
            manifest = store.get_merge_operation("retry-success")
            self.assertEqual(len(manifest.affected_items), len(set(
                (item.item_type, item.item_id) for item in manifest.affected_items
            )))

            another = store.create_person("Another")
            last = store.create_person("Last")
            with self.assertRaises(RuntimeError):
                store.execute_identity_merge(
                    another.person_id, last.person_id, "retry-failed",
                    failure_injector=lambda stage: (_ for _ in ()).throw(RuntimeError("stop")),
                )
            with self.assertRaisesRegex(ValueError, "new operation ID"):
                store.execute_identity_merge(another.person_id, last.person_id, "retry-failed")
            store.execute_identity_merge(another.person_id, last.person_id, "retry-new-id")


if __name__ == "__main__":
    unittest.main()
