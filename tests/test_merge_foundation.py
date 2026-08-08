from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace

from sentriface.api_serializers import embedding_record_payload
from sentriface.engine import FaceEngine
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.metrics import MetricsCollector
from sentriface.models import (
    DetectedFace,
    FaceBox,
    InitFace,
    MergeAffectedAction,
    MergeConflictStrategy,
    QualityReport,
    QualityStatus,
)
from sentriface.storage.sqlite_store import (
    SCHEMA_VERSION,
    SQLiteIdentityStore,
    _begin_journal_operation,
    _insert_merge_manifest_in_transaction,
    _set_canonical_person_id_in_transaction,
    _schema_migrations,
    _transition_journal_operation,
)


class MergeFoundationTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def test_connection_scoped_canonical_helper_does_not_commit_or_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            target = store.create_person("Target")
            with sqlite3.connect(store.db_path) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("BEGIN IMMEDIATE")
                _set_canonical_person_id_in_transaction(
                    conn, source.person_id, target.person_id,
                )
                self.assertEqual(
                    conn.execute(
                        "SELECT lifecycle_status FROM persons WHERE person_id = ?",
                        (source.person_id,),
                    ).fetchone()[0],
                    "MERGED",
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM operation_journal").fetchone()[0],
                    0,
                )
                conn.rollback()

            self.assertEqual(store.get_person_lifecycle(source.person_id)["lifecycle_status"], "ACTIVE")

    def test_v24_upgrade_adds_empty_normalized_manifest_without_importing_legacy_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                for migration in _schema_migrations():
                    if migration.to_version > 24:
                        break
                    migration.apply(conn)
                conn.execute(
                    """
                    INSERT INTO person_operations(operation_id, operation_type, result, created_at)
                    VALUES ('legacy-merge', 'merge-persons',
                            '{"source_person_id":"old","target_person_id":"kept"}',
                            '2026-01-01T00:00:00+00:00')
                    """
                )
            store = SQLiteIdentityStore(db_path, embedding_dim=2)
            store.initialize()
            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM merge_operations").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM merge_affected_items").fetchone()[0], 0)

    def test_manifest_is_normalized_immutable_and_linked_to_one_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            target = store.create_person("Target")
            actor = {"user_id": "operator-1", "display_name": "Operator"}
            with store._connect() as conn:
                _begin_journal_operation(
                    conn,
                    "identity.merge",
                    operation_id="merge-foundation-op",
                    actor=actor,
                    source="test",
                )
                manifest = _insert_merge_manifest_in_transaction(
                    conn,
                    merge_operation_id="merge-foundation-op",
                    source_person_id=source.person_id,
                    target_person_id=target.person_id,
                    operation_journal_id="merge-foundation-op",
                    actor=actor,
                    reason="Duplicate identity",
                    context={"review": "operator-confirmed"},
                    affected_items=[
                        {
                            "item_type": item_type,
                            "item_id": f"{item_type.lower()}-1",
                            "previous_person_id": source.person_id,
                            "effective_person_id": target.person_id,
                            "context": {"provenance": "raw-retained"},
                        }
                        for item_type in (
                            "EMBEDDING", "OBSERVATION", "NOTE_MENTION", "PROFILE_FIELD",
                            "GRAPH_EVIDENCE", "OTHER",
                        )
                    ],
                )
                self.assertEqual(manifest.previous_source_lifecycle_status, "ACTIVE")
                _transition_journal_operation(
                    conn, "merge-foundation-op", "COMMITTED", {"manifest_only": True},
                )

            stored = store.get_merge_operation("merge-foundation-op")
            self.assertEqual(stored.actor["user_id"], "operator-1")
            self.assertEqual(stored.reason, "Duplicate identity")
            self.assertEqual(len(stored.affected_items), 6)
            self.assertEqual(store.get_operation("merge-foundation-op")["status"], "COMMITTED")
            with sqlite3.connect(store.db_path) as conn:
                with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                    conn.execute(
                        "UPDATE merge_operations SET reason = 'changed' WHERE merge_operation_id = ?",
                        ("merge-foundation-op",),
                    )

    def test_manifest_canonical_change_and_journal_roll_back_together(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            target = store.create_person("Target")
            with self.assertRaisesRegex(RuntimeError, "validation failure"):
                with store._connect() as conn:
                    _begin_journal_operation(
                        conn, "identity.merge", operation_id="rollback-merge",
                    )
                    _insert_merge_manifest_in_transaction(
                        conn,
                        merge_operation_id="rollback-merge",
                        source_person_id=source.person_id,
                        target_person_id=target.person_id,
                        operation_journal_id="rollback-merge",
                    )
                    _set_canonical_person_id_in_transaction(
                        conn, source.person_id, target.person_id,
                    )
                    raise RuntimeError("validation failure")

            self.assertIsNone(store.get_operation("rollback-merge"))
            self.assertIsNone(store.get_merge_operation("rollback-merge"))
            self.assertEqual(store.resolve_canonical_person_id(source.person_id), source.person_id)

    def test_raw_and_effective_embedding_identity_are_both_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            target = store.create_person("Target")
            embedding = store.add_embedding(source.person_id, (1.0, 0.0), 0.9)
            store._set_canonical_person_id_for_merge(source.person_id, target.person_id, "map-face")

            raw = store.list_raw_embeddings_for_person(source.person_id)
            effective = store.list_embeddings_for_person(target.person_id)

            self.assertEqual(raw[0].person_id, source.person_id)
            self.assertEqual(raw[0].canonical_person_id, target.person_id)
            self.assertEqual(effective[0].embedding_id, embedding.embedding_id)
            self.assertEqual(effective[0].person_id, source.person_id)
            self.assertEqual(effective[0].canonical_person_id, target.person_id)
            self.assertEqual(
                store.current_embedding_person_ids([embedding.embedding_id]),
                {embedding.embedding_id: target.person_id},
            )
            self.assertEqual(store.get_effective_person(source.person_id).person_id, target.person_id)

    def test_merged_historical_mention_can_be_preserved_during_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            owner = store.create_person("Owner")
            mentioned = store.create_person("Mentioned")
            survivor = store.create_person("Survivor")
            note = graph.create_note(
                owner.person_id, "@Mentioned", "mention-create",
                mentioned_person_ids=[mentioned.person_id],
            )
            store._set_canonical_person_id_for_merge(
                mentioned.person_id, survivor.person_id, "map-mentioned",
            )

            updated = graph.update_note(
                note.note_id, "Edited @Mentioned", "mention-edit",
                mentioned_person_ids=[mentioned.person_id],
            )

            self.assertEqual(updated.mentioned_person_ids, (mentioned.person_id,))
            self.assertEqual(updated.effective_mentioned_person_ids, (survivor.person_id,))
            with self.assertRaisesRegex(KeyError, "not active"):
                graph.create_note(
                    owner.person_id, "New raw mention", "new-merged-mention",
                    mentioned_person_ids=[mentioned.person_id],
                )

    def test_observation_raw_and_effective_participants_diverge_after_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            survivor = store.create_person("Survivor")
            other = store.create_person("Other")
            observation = store.create_observation(
                "raw-effective-observation",
                participant_ids=[source.person_id, other.person_id],
            )
            store._set_canonical_person_id_for_merge(
                source.person_id, survivor.person_id, "map-observation-source",
            )

            raw = store.list_raw_observation_participants(observation.observation_id)
            effective = store.list_effective_observation_participants(observation.observation_id)

            self.assertEqual({item.person_id for item in raw}, {source.person_id, other.person_id})
            self.assertEqual(
                {item.person_id for item in effective}, {survivor.person_id, other.person_id},
            )
            self.assertEqual(
                [item.observation_id for item in store.list_raw_observations_for_person(source.person_id)],
                [observation.observation_id],
            )
            self.assertEqual(
                [item.observation_id for item in store.list_observations_for_person(source.person_id)],
                [observation.observation_id],
            )

    def test_observation_correction_resolves_merged_input_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            survivor = store.create_person("Survivor")
            replacement = store.create_person("Replacement")
            observation = store.create_observation(
                "canonical-correction-create", participant_ids=[source.person_id],
            )
            store._finalize_observation_without_graph_evidence(
                observation.observation_id, "canonical-correction-finalize",
            )
            store._set_canonical_person_id_for_merge(
                source.person_id, survivor.person_id, "canonical-correction-map",
            )

            result = store.correct_observation_identity(
                observation.observation_id,
                source.person_id,
                replacement.person_id,
                "canonical-correction",
            )

            self.assertEqual(result["from_person_id"], survivor.person_id)
            self.assertEqual(result["participant_ids"], [replacement.person_id])
            self.assertEqual(
                [item.person_id for item in store.list_raw_observation_participants(
                    observation.observation_id,
                )],
                [source.person_id],
            )
            self.assertEqual(
                [item.person_id for item in store.list_effective_observation_participants(
                    observation.observation_id,
                )],
                [replacement.person_id],
            )

    def test_connection_helper_rejects_cycle_and_dangling_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            with store._connect() as conn:
                with self.assertRaisesRegex(KeyError, "Unknown person"):
                    _set_canonical_person_id_in_transaction(conn, first.person_id, "missing")
                _set_canonical_person_id_in_transaction(conn, first.person_id, second.person_id)
                with self.assertRaisesRegex(ValueError, "cycle"):
                    _set_canonical_person_id_in_transaction(conn, second.person_id, first.person_id)

    def test_merge_after_observation_correction_preserves_corrected_identity(self) -> None:
        cases = (
            ("source-merged", True, False),
            ("target-merged", False, True),
            ("both-canonicalized", True, True),
        )
        for label, merge_source, merge_target in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                store = self._store(Path(temp))
                source = store.create_person("Correction source")
                corrected = store.create_person("Correction target")
                other = store.create_person("Other participant")
                source_survivor = store.create_person("Source survivor")
                target_survivor = store.create_person("Target survivor")
                observation = store.create_observation(
                    f"{label}-create",
                    participant_ids=[source.person_id, other.person_id],
                )
                store._finalize_observation_without_graph_evidence(
                    observation.observation_id, f"{label}-finalize",
                )
                store.record_observation_evidence(
                    observation.observation_id, f"{label}-evidence",
                )
                store.correct_observation_identity(
                    observation.observation_id,
                    source.person_id,
                    corrected.person_id,
                    f"{label}-correct",
                )
                if merge_source:
                    store._set_canonical_person_id_for_merge(
                        source.person_id, source_survivor.person_id, f"{label}-source-map",
                    )
                if merge_target:
                    store._set_canonical_person_id_for_merge(
                        corrected.person_id, target_survivor.person_id, f"{label}-target-map",
                    )

                expected_corrected = (
                    target_survivor.person_id if merge_target else corrected.person_id
                )
                effective = {
                    item.person_id for item in store.list_effective_observation_participants(
                        observation.observation_id,
                    )
                }
                self.assertEqual(effective, {expected_corrected, other.person_id})
                self.assertNotIn(source_survivor.person_id, effective)
                corrections = store.list_corrections_for_observation(
                    observation.observation_id,
                )
                self.assertEqual(corrections[0].from_person_id, source.person_id)
                self.assertEqual(corrections[0].to_person_id, corrected.person_id)
                self.assertEqual(
                    {item.person_id for item in store.list_raw_observation_participants(
                        observation.observation_id,
                    )},
                    {source.person_id, other.person_id},
                )
                store.rebuild_graph_projection(f"{label}-rebuild")
                self.assertTrue(store.validate_graph_projection()["valid"])

    def test_manifest_records_terminal_canonical_survivor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("A")
            intermediate = store.create_person("B")
            survivor = store.create_person("C")
            store._set_canonical_person_id_for_merge(
                intermediate.person_id, survivor.person_id, "map-b-to-c",
            )
            with store._connect() as conn:
                _begin_journal_operation(
                    conn, "identity.merge", operation_id="terminal-survivor",
                )
                manifest = _insert_merge_manifest_in_transaction(
                    conn,
                    merge_operation_id="terminal-survivor",
                    source_person_id=source.person_id,
                    target_person_id=intermediate.person_id,
                    operation_journal_id="terminal-survivor",
                )
                self.assertEqual(manifest.target_person_id, survivor.person_id)
                mapped = _set_canonical_person_id_in_transaction(
                    conn, source.person_id, intermediate.person_id,
                )
                self.assertEqual(mapped["canonical_person_id"], survivor.person_id)

    def test_manifest_rejects_inactive_survivor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            inactive = store.create_person("Inactive")
            store.archive_person(inactive.person_id, "archive-survivor")
            with self.assertRaisesRegex(ValueError, "terminal active"):
                with store._connect() as conn:
                    _begin_journal_operation(
                        conn, "identity.merge", operation_id="inactive-survivor",
                    )
                    _insert_merge_manifest_in_transaction(
                        conn,
                        merge_operation_id="inactive-survivor",
                        source_person_id=source.person_id,
                        target_person_id=inactive.person_id,
                        operation_journal_id="inactive-survivor",
                    )

    def test_conflict_model_is_typed_invertible_and_manifest_closes_on_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            target = store.create_person("Target")
            actor = {"user_id": "operator"}
            strategies = (
                ("name", "Source", "Target", "KEEP_SOURCE", "Source"),
                ("rank", "One", "Two", "KEEP_TARGET", "Two"),
                ("tags", ["a"], ["b"], "COMBINE", ["a", "b"]),
                ("country", "A", "B", "USER_SELECTED", "C"),
            )
            with store._connect() as conn:
                _begin_journal_operation(
                    conn, "identity.merge", operation_id="conflict-op", actor=actor,
                )
                manifest = _insert_merge_manifest_in_transaction(
                    conn,
                    merge_operation_id="conflict-op",
                    source_person_id=source.person_id,
                    target_person_id=target.person_id,
                    operation_journal_id="conflict-op",
                    actor=actor,
                    affected_items=[{
                        "item_type": "EMBEDDING",
                        "item_id": "face-1",
                        "raw_owner_person_id": source.person_id,
                        "effective_owner_person_id": target.person_id,
                        "before_state": {"owner_person_id": source.person_id},
                        "after_state": {"canonical_person_id": target.person_id},
                    }],
                    conflicts=[{
                        "category": "PROFILE",
                        "field_name": field,
                        "source_value": source_value,
                        "target_value": target_value,
                        "strategy": strategy,
                        "selected_value": selected,
                    } for field, source_value, target_value, strategy, selected in strategies],
                )
                self.assertEqual(
                    manifest.affected_items[0].action,
                    MergeAffectedAction.UNION_IN_CURRENT_VIEW,
                )
                self.assertEqual(
                    {item.strategy for item in manifest.conflicts},
                    set(MergeConflictStrategy),
                )
                self.assertTrue(all(
                    set(item.inverse_data) == {"source_value", "target_value"}
                    for item in manifest.conflicts
                ))
                _transition_journal_operation(conn, "conflict-op", "COMMITTED")

            with sqlite3.connect(store.db_path) as conn:
                with self.assertRaisesRegex(sqlite3.IntegrityError, "closed"):
                    conn.execute(
                        """
                        INSERT INTO merge_affected_items(
                            merge_operation_id, item_type, item_id, context
                        ) VALUES (?, 'NOTE', 'late-note', '{}')
                        """,
                        ("conflict-op",),
                    )

    def test_manifest_actor_must_match_journal_actor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            target = store.create_person("Target")
            with self.assertRaisesRegex(ValueError, "actor"):
                with store._connect() as conn:
                    _begin_journal_operation(
                        conn, "identity.merge", operation_id="actor-op",
                        actor={"user_id": "one"},
                    )
                    _insert_merge_manifest_in_transaction(
                        conn,
                        merge_operation_id="actor-op",
                        source_person_id=source.person_id,
                        target_person_id=target.person_id,
                        operation_journal_id="actor-op",
                        actor={"user_id": "two"},
                    )

    def test_failed_merge_attempt_keeps_failure_journal_without_partial_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            target = store.create_person("Target")
            with self.assertRaisesRegex(RuntimeError, "merge failed"):
                with store._connect() as conn:
                    _begin_journal_operation(
                        conn, "identity.merge", operation_id="failed-merge",
                    )
                    _insert_merge_manifest_in_transaction(
                        conn,
                        merge_operation_id="failed-merge",
                        source_person_id=source.person_id,
                        target_person_id=target.person_id,
                        operation_journal_id="failed-merge",
                    )
                    _set_canonical_person_id_in_transaction(
                        conn, source.person_id, target.person_id,
                    )
                    raise RuntimeError("merge failed")

            failure = store.record_merge_attempt_failed(
                "failed-merge", details={"error": "merge failed"},
            )
            self.assertEqual(failure["status"], "FAILED")
            self.assertEqual(
                [item["to_status"] for item in failure["status_history"]],
                ["STARTED", "FAILED"],
            )
            self.assertIsNone(store.get_merge_operation("failed-merge"))
            self.assertEqual(
                store.resolve_canonical_person_id(source.person_id), source.person_id,
            )

    def test_effective_profile_aggregates_source_history_while_raw_views_preserve_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            source = store.create_person("Source", notes="Source profile note")
            survivor = store.create_person("Survivor")
            embedding = store.add_embedding(source.person_id, (1.0, 0.0), 0.9)
            detail = store.add_recognition_detail(
                embedding.embedding_id, source.person_id, "image-1", source.name,
                "existing", "2026-01-01", "10:00:00", "HQ", 1, "Review",
            )
            observation = store.create_observation(
                "profile-observation", participant_ids=[source.person_id],
            )
            graph.create_note(source.person_id, "Source history", "source-note")
            store.update_person_profile(
                source.person_id, "Source Updated", "R1", "IN", "High", "Operator",
                operation_id="source-profile-change",
            )
            store._set_canonical_person_id_for_merge(
                source.person_id, survivor.person_id, "effective-profile-map",
            )

            self.assertEqual(
                {item.embedding_id for item in store.list_embeddings_for_person(survivor.person_id)},
                {embedding.embedding_id},
            )
            self.assertEqual(
                {item.detail_id for item in store.list_recognition_details_for_person(survivor.person_id)},
                {detail.detail_id},
            )
            self.assertIn(
                observation.observation_id,
                {item.observation_id for item in store.list_observations_for_person(survivor.person_id)},
            )
            self.assertEqual(len(store.list_person_notes(survivor.person_id)), 2)
            self.assertEqual(len(store.list_person_changes(survivor.person_id)), 1)
            summary = next(
                item for item in store.list_persons()
                if item.person.person_id == survivor.person_id
            )
            self.assertEqual((summary.embedding_count, summary.sighting_count), (1, 1))

            self.assertEqual(
                store.list_raw_embeddings_for_person(source.person_id)[0].person_id,
                source.person_id,
            )
            self.assertEqual(
                {item.owner_person_id for item in store.list_person_notes(source.person_id, raw=True)},
                {source.person_id},
            )
            self.assertEqual(
                store.list_raw_observations_for_person(source.person_id)[0].observation_id,
                observation.observation_id,
            )
            self.assertEqual(
                store.list_raw_recognition_details_for_person(source.person_id)[0].person_id,
                source.person_id,
            )

    def test_browse_groups_embeddings_and_exclusions_by_canonical_person(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            survivor = store.create_person("Survivor")
            embedding = store.add_embedding(source.person_id, (1.0, 0.0), 0.9)
            session = store.create_init_session("test")
            face = InitFace(
                init_face_id="face-1",
                session_id=session.session_id,
                group_id="group-1",
                source_image="image.jpg",
                face=DetectedFace(FaceBox(0, 0, 10, 10, 1.0), 1.0),
                vector=(1.0, 0.0),
                quality=QualityReport(QualityStatus.GOOD, 1.0),
            )
            store.save_init_faces([face])
            store.add_init_face_person_exclusions(
                session.session_id, [face.init_face_id], source.person_id,
            )
            store._set_canonical_person_id_for_merge(
                source.person_id, survivor.person_id, "browse-map",
            )

            engine = object.__new__(FaceEngine)
            engine.store = store
            engine._metrics_context = ContextVar(
                "merge_foundation_metrics", default=MetricsCollector(),
            )
            engine.config = SimpleNamespace(top_k=5)
            candidates = engine._rank_people_for_vector((1.0, 0.0))
            survivor_candidate = next(
                item for item in candidates
                if item.summary.person.person_id == survivor.person_id
            )
            self.assertEqual(survivor_candidate.match.person_id, survivor.person_id)
            self.assertEqual(survivor_candidate.match.embedding_ids, (embedding.embedding_id,))
            self.assertEqual(survivor_candidate.embeddings[0].person_id, source.person_id)
            exclusions = store.list_init_face_person_exclusions(
                session.session_id, [face.init_face_id],
            )
            self.assertEqual(exclusions[face.init_face_id], {survivor.person_id})
            excluded_candidates = engine._rank_people_for_vector(
                (1.0, 0.0), exclusions[face.init_face_id],
            )
            self.assertNotIn(
                survivor.person_id,
                {item.summary.person.person_id for item in excluded_candidates},
            )

    def test_embedding_api_exposes_raw_and_effective_owners(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            survivor = store.create_person("Survivor")
            embedding = store.add_embedding(source.person_id, (1.0, 0.0), 0.9)
            store._set_canonical_person_id_for_merge(
                source.person_id, survivor.person_id, "api-map",
            )
            payload = embedding_record_payload(
                store.list_embeddings_for_person(survivor.person_id)[0],
            )
            self.assertEqual(payload["raw_person_id"], source.person_id)
            self.assertEqual(payload["canonical_person_id"], survivor.person_id)
            self.assertEqual(payload["embedding_id"], embedding.embedding_id)


if __name__ == "__main__":
    unittest.main()
