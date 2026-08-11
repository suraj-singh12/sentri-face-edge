from __future__ import annotations

import sqlite3
import tempfile
import time
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.errors import GraphProjectionRebuildRefused
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.merge_service import IdentityMergeService
from sentriface.models import utc_now
from sentriface.storage.sqlite_store import (
    SQLiteIdentityStore,
    _expected_graph_connections,
    _insert_relationship_evidence,
    _replace_graph_projection,
)


class GraphProjectionRebuildTest(unittest.TestCase):
    AUTHORITATIVE_TABLES = (
        "persons",
        "embeddings",
        "biometric_enrollment_history",
        "observations",
        "observation_media",
        "observation_participants",
        "observation_face_assignments",
        "photo_reviews",
        "photo_review_faces",
        "recognition_details",
        "identity_corrections",
        "relationship_evidence",
        "notes",
        "note_revisions",
        "note_revision_mentions",
        "note_mentions",
        "merge_operations",
        "merge_affected_items",
        "merge_conflict_resolutions",
        "person_change_history",
    )

    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _pair(self, store: SQLiteIdentityStore, prefix: str = "pair"):
        graph = GlobalIdentityGraphService(store)
        first = store.create_person(f"{prefix} A")
        second = store.create_person(f"{prefix} B")
        observation = store.create_observation(
            f"{prefix}-create", participant_ids=[first.person_id, second.person_id],
        )
        store._finalize_observation_without_graph_evidence(
            observation.observation_id, f"{prefix}-finalize",
        )
        evidence = graph.record_observation_evidence(
            observation.observation_id, f"{prefix}-evidence",
        )[0]
        return graph, first, second, observation.observation_id, evidence

    @staticmethod
    def _revision(store: SQLiteIdentityStore) -> str:
        with store._connect() as conn:
            return f"g{conn.execute('SELECT revision FROM graph_state').fetchone()[0]}"

    @staticmethod
    def _rows(store: SQLiteIdentityStore, table: str) -> tuple[tuple, ...]:
        with store._connect() as conn:
            return tuple(tuple(row) for row in conn.execute(
                f'SELECT * FROM "{table}" ORDER BY rowid'
            ))

    @staticmethod
    def _corrupt(store: SQLiteIdentityStore, *statements: tuple[str, tuple]) -> None:
        with sqlite3.connect(store.db_path) as conn:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("PRAGMA ignore_check_constraints=ON")
            for statement, parameters in statements:
                conn.execute(statement, parameters)
            conn.commit()

    def test_healthy_rebuild_is_idempotent_noop_without_revision_churn(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph, *_ = self._pair(store, "noop")
            before_revision = self._revision(store)

            result = graph.rebuild_projection(
                "rebuild-noop", reason="operator verification", context={"request": "test"},
            )
            retry = graph.rebuild_projection("rebuild-noop")

            self.assertEqual(result, retry)
            self.assertFalse(result["changed"])
            self.assertEqual(result["revision_before"], before_revision)
            self.assertEqual(result["revision_after"], before_revision)
            self.assertEqual(result["preflight_status"], "PASS")
            self.assertEqual(result["postcheck_status"], "PASS")
            with store._connect() as conn:
                row = conn.execute(
                    "SELECT status FROM operation_journal WHERE operation_id='rebuild-noop'"
                ).fetchone()
                self.assertEqual(row[0], "COMMITTED")

    def test_rebuild_repairs_missing_extra_direction_and_support_drift(self) -> None:
        cases = {
            "missing": ("DELETE FROM graph_connections", ()),
            "extra": (
                """INSERT INTO graph_connections VALUES
                   (?, ?, 'KNOWS', 'DIRECTED', 1, '[\"MANUAL_ASSOCIATION\"]', ?)""",
                None,
            ),
            "direction": (
                "UPDATE graph_connections SET directionality='DIRECTED'",
                (),
            ),
            "support": (
                "UPDATE graph_connections SET evidence_count=19, evidence_types='[\"NOTE_REFERENCE\"]'",
                (),
            ),
        }
        for name, (statement, parameters) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                store = self._store(Path(temp))
                graph, first, second, _, evidence = self._pair(store, name)
                expected = graph.get_global_projection().connections
                if name == "extra":
                    third = store.create_person("Extra endpoint")
                    parameters = (first.person_id, third.person_id, utc_now())
                self._corrupt(store, (statement, parameters or ()))
                before_revision = self._revision(store)

                result = graph.rebuild_projection(f"rebuild-{name}")

                self.assertTrue(result["changed"])
                self.assertEqual(result["preflight_status"], "PROJECTION_DRIFT")
                self.assertNotEqual(result["revision_after"], before_revision)
                self.assertEqual(graph.get_global_projection().connections, expected)
                self.assertEqual(evidence.evidence_id, graph.get_connection_evidence(
                    first.person_id, second.person_id,
                )[0].evidence_id)

    def test_retired_evidence_and_canonical_self_edge_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph, first, second, _, evidence = self._pair(store, "retired")
            graph.deactivate_evidence(evidence.evidence_id, "retire-evidence")
            self._corrupt(store, (
                """INSERT INTO graph_connections VALUES
                   (?, ?, 'ASSOCIATED_WITH', 'UNDIRECTED', 1, '[\"CO_OBSERVED\"]', ?)""",
                tuple(sorted((first.person_id, second.person_id))) + (evidence.created_at,),
            ))
            result = graph.rebuild_projection("rebuild-retired")
            self.assertTrue(result["changed"])
            self.assertEqual(graph.get_global_projection().connections, ())
            self.assertFalse(graph.get_connection_evidence(
                first.person_id, second.person_id, include_inactive=True,
            )[0].active)

        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph, source, survivor, _, evidence = self._pair(store, "self")
            store._set_canonical_person_id_for_merge(
                source.person_id, survivor.person_id, "self-map",
            )
            self._corrupt(store, (
                """INSERT INTO graph_connections VALUES
                   (?, ?, 'ASSOCIATED_WITH', 'UNDIRECTED', 1, '[\"CO_OBSERVED\"]', ?)""",
                (survivor.person_id, survivor.person_id, evidence.created_at),
            ))
            result = graph.rebuild_projection("rebuild-self")
            self.assertTrue(result["changed"])
            self.assertEqual(graph.get_global_projection().connections, ())

    def test_rebuild_preserves_evidence_directionality_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            first, second, third = [store.create_person(name) for name in ("A", "B", "C")]
            graph.create_note(
                first.person_id, "@B", "direction-note", mentioned_person_ids=[second.person_id],
            )
            observation = store.create_observation(
                "direction-observation", participant_ids=[second.person_id, third.person_id],
            )
            store._finalize_observation_without_graph_evidence(
                observation.observation_id, "direction-finalize",
            )
            graph.record_observation_evidence(observation.observation_id, "direction-co")
            store.begin_operation("test.manual", operation_id="direction-manual")
            store.mark_operation_committed("direction-manual")
            with store._connect() as conn:
                _insert_relationship_evidence(
                    conn,
                    evidence_type="MANUAL_ASSOCIATION",
                    source_entity_type="MANUAL_ASSERTION",
                    source_entity_id="manual-direction",
                    source_person_id=first.person_id,
                    target_person_id=third.person_id,
                    relationship_type="FOLLOWS",
                    directionality="DIRECTED",
                    source="test",
                    created_operation_id="direction-manual",
                    created_at=utc_now(),
                )
                _replace_graph_projection(conn)
            expected = graph.get_global_projection().connections
            self._corrupt(store, ("DELETE FROM graph_connections", ()))

            graph.rebuild_projection("rebuild-direction-types")

            rebuilt = graph.get_global_projection().connections
            self.assertEqual(rebuilt, expected)
            self.assertEqual(
                {(item.relationship_type, item.directionality) for item in rebuilt},
                {("REFERENCES", "DIRECTED"), ("ASSOCIATED_WITH", "UNDIRECTED"), ("FOLLOWS", "DIRECTED")},
            )

    def test_correction_before_canonical_resolution_for_both_operation_orders(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            merge = IdentityMergeService(store)
            a, b, c, d, e = [store.create_person(name) for name in ("A", "B", "C", "D", "E")]
            first = store.create_observation("ctm-create", participant_ids=[a.person_id, b.person_id])
            store._finalize_observation_without_graph_evidence(first.observation_id, "ctm-final")
            graph.record_observation_evidence(first.observation_id, "ctm-evidence")
            graph.correct_observation_identity(first.observation_id, a.person_id, c.person_id, "ctm-correct")
            merge.execute(c.person_id, d.person_id, "ctm-merge")

            second = store.create_observation("mtc-create", participant_ids=[a.person_id, e.person_id])
            store._finalize_observation_without_graph_evidence(second.observation_id, "mtc-final")
            graph.record_observation_evidence(second.observation_id, "mtc-evidence")
            merge.execute(a.person_id, b.person_id, "mtc-merge")
            graph.correct_observation_identity(second.observation_id, b.person_id, d.person_id, "mtc-correct")
            expected = graph.get_global_projection().connections
            self._corrupt(store, ("DELETE FROM graph_connections", ()))

            result = graph.rebuild_projection("rebuild-transformations")

            self.assertTrue(result["changed"])
            self.assertEqual(graph.get_global_projection().connections, expected)
            self.assertFalse(any(
                item.source_person_id == item.target_person_id
                for item in graph.get_global_projection().connections
            ))

    def test_authoritative_corruption_refuses_without_graph_or_revision_write(self) -> None:
        cases = ("cycle", "dangling", "correction", "evidence")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                store = self._store(Path(temp))
                graph, first, second, observation_id, evidence = self._pair(store, case)
                if case in {"cycle", "dangling"}:
                    statements = [("DROP TRIGGER persons_canonical_update", ())]
                    if case == "cycle":
                        statements.extend([
                            ("UPDATE persons SET lifecycle_status='MERGED', deleted_at=?, canonical_person_id=? WHERE person_id=?", (utc_now(), second.person_id, first.person_id)),
                            ("UPDATE persons SET lifecycle_status='MERGED', deleted_at=?, canonical_person_id=? WHERE person_id=?", (utc_now(), first.person_id, second.person_id)),
                        ])
                    else:
                        statements.append((
                            "UPDATE persons SET lifecycle_status='MERGED', deleted_at=?, canonical_person_id='missing' WHERE person_id=?",
                            (utc_now(), first.person_id),
                        ))
                elif case == "correction":
                    third = store.create_person("Correction target")
                    store.begin_operation("identity.observation.correct", operation_id="bad-correction-op")
                    store.mark_operation_committed("bad-correction-op")
                    statements = [(
                        """INSERT INTO identity_corrections(
                           correction_id, correction_type, observation_id,
                           from_person_id, to_person_id, operation_id, created_at
                           ) VALUES ('bad-correction', 'OBSERVATION_IDENTITY', ?, ?, ?,
                                     'bad-correction-op', ?)""",
                        (observation_id, third.person_id, first.person_id, utc_now()),
                    )]
                else:
                    statements = [
                        ("DROP TRIGGER relationship_evidence_identity_immutable", ()),
                        ("UPDATE relationship_evidence SET source_entity_id='missing-observation' WHERE evidence_id=?", (evidence.evidence_id,)),
                    ]
                self._corrupt(store, *statements)
                corrupted_graph = self._rows(store, "graph_connections")
                corrupted_revision = self._revision(store)
                corrupted_authority = {
                    table: self._rows(store, table)
                    for table in self.AUTHORITATIVE_TABLES
                }

                with self.assertRaises(GraphProjectionRebuildRefused):
                    graph.rebuild_projection(f"refuse-{case}")

                self.assertEqual(self._rows(store, "graph_connections"), corrupted_graph)
                self.assertEqual(self._revision(store), corrupted_revision)
                self.assertEqual(corrupted_authority, {
                    table: self._rows(store, table)
                    for table in self.AUTHORITATIVE_TABLES
                })
                with store._connect() as conn:
                    row = conn.execute(
                        "SELECT status FROM operation_journal WHERE operation_id=?",
                        (f"refuse-{case}",),
                    ).fetchone()
                    self.assertEqual(row[0], "FAILED")

    def test_write_validation_and_revision_failures_roll_back_projection(self) -> None:
        seams = (
            ("_insert_graph_projection_rows", RuntimeError("insert failed")),
            ("_validate_graph_projection", {"valid": False, "errors": ["injected validation failure"]}),
            ("_advance_graph_revision", RuntimeError("revision failed")),
        )
        for seam, effect in seams:
            with self.subTest(seam=seam), tempfile.TemporaryDirectory() as temp:
                store = self._store(Path(temp))
                graph, _, _, _, _ = self._pair(store, seam)
                self._corrupt(store, ("DELETE FROM graph_connections", ()))
                graph_before = self._rows(store, "graph_connections")
                revision_before = self._revision(store)
                authority_before = {
                    table: self._rows(store, table)
                    for table in self.AUTHORITATIVE_TABLES
                }
                target = f"sentriface.storage.sqlite_store.{seam}"
                patcher = patch(target, return_value=effect) if isinstance(effect, dict) else patch(target, side_effect=effect)

                with patcher, self.assertRaises(RuntimeError):
                    graph.rebuild_projection(f"failure-{seam}")

                self.assertEqual(self._rows(store, "graph_connections"), graph_before)
                self.assertEqual(self._revision(store), revision_before)
                self.assertEqual(authority_before, {
                    table: self._rows(store, table)
                    for table in self.AUTHORITATIVE_TABLES
                })
                with store._connect() as conn:
                    self.assertEqual(conn.execute(
                        "SELECT status FROM operation_journal WHERE operation_id=?",
                        (f"failure-{seam}",),
                    ).fetchone()[0], "FAILED")

    def test_rebuild_changes_only_projection_revision_and_new_journal_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph, *_ = self._pair(store, "authority")
            self._corrupt(store, ("DELETE FROM graph_connections", ()))
            authority_before = {
                table: self._rows(store, table) for table in self.AUTHORITATIVE_TABLES
            }
            journal_before = self._rows(store, "operation_journal")
            history_before = self._rows(store, "operation_journal_status_history")

            result = graph.rebuild_projection("authority-proof")

            self.assertTrue(result["changed"])
            self.assertEqual(authority_before, {
                table: self._rows(store, table) for table in self.AUTHORITATIVE_TABLES
            })
            journal_after = self._rows(store, "operation_journal")
            history_after = self._rows(store, "operation_journal_status_history")
            self.assertEqual(journal_after[:len(journal_before)], journal_before)
            self.assertEqual(history_after[:len(history_before)], history_before)

    def test_expected_projection_has_constant_query_shape_on_large_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            created_at = utc_now()
            count = 400
            with store._connect() as conn:
                conn.execute("BEGIN")
                conn.execute(
                    """INSERT INTO operation_journal(
                       operation_id, operation_type, status, actor, context,
                       affected_entities, details, created_at, completed_at
                       ) VALUES ('bulk-op', 'test.bulk', 'COMMITTED', '{}', '{}',
                                 '[]', '{}', ?, ?)""",
                    (created_at, created_at),
                )
                conn.executemany(
                    """INSERT INTO persons(
                       person_id, name, metadata, created_at, enrollment_status, notes,
                       lifecycle_status, identity_status, biometric_status, lifecycle_changed_at
                       ) VALUES (?, ?, '{}', ?, 'placeholder', '', 'ACTIVE',
                                 'IDENTIFIED', 'NO_FACE', ?)""",
                    [(f"bulk-{index:04d}", f"Bulk {index}", created_at, created_at) for index in range(count + 1)],
                )
                conn.executemany(
                    """INSERT INTO relationship_evidence(
                       evidence_id, evidence_type, source_entity_type, source_entity_id,
                       evidence_revision_id, source_person_id, target_person_id,
                       relationship_type, directionality, active, source,
                       created_operation_id, created_at
                       ) VALUES (?, 'MANUAL_ASSOCIATION', 'MANUAL_ASSERTION', ?, ?, ?, ?,
                                 'ASSOCIATED_WITH', 'UNDIRECTED', 1, 'test', 'bulk-op', ?)""",
                    [
                        (
                            f"bulk-evidence-{index:04d}", f"bulk-assertion-{index:04d}",
                            f"bulk-revision-{index:04d}", f"bulk-{index:04d}",
                            f"bulk-{index + 1:04d}", created_at,
                        )
                        for index in range(count)
                    ],
                )
                conn.commit()

            statements: list[str] = []
            with store._connect() as conn:
                conn.set_trace_callback(statements.append)
                tracemalloc.start()
                started = time.perf_counter()
                expected, errors, evidence_count = _expected_graph_connections(conn)
                elapsed = time.perf_counter() - started
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

            reads = [
                statement for statement in statements
                if statement.lstrip().upper().startswith(("SELECT", "WITH"))
            ]
            self.assertEqual(errors, [])
            self.assertEqual(evidence_count, count)
            self.assertEqual(len(expected), count)
            self.assertLessEqual(len(reads), 8)
            self.assertGreater(elapsed, 0)
            self.assertGreater(peak, 0)


if __name__ == "__main__":
    unittest.main()
