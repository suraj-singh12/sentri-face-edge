from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.integrity import (
    INTEGRITY_INVARIANTS,
    ReadOnlyIntegrityChecker,
)
from sentriface.merge_service import IdentityMergeService
from sentriface.models import utc_now
from sentriface.storage.sqlite_store import SQLiteIdentityStore


class ReadOnlyIntegrityCheckerTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _findings(self, store: SQLiteIdentityStore) -> set[str]:
        return {
            finding.invariant_id
            for finding in ReadOnlyIntegrityChecker(store.db_path).run().findings
        }

    def _finalized(
        self, store: SQLiteIdentityStore, prefix: str, person_ids: list[str],
    ) -> str:
        observation = store.create_observation(
            f"{prefix}-create", participant_ids=person_ids,
        )
        store._finalize_observation_without_graph_evidence(
            observation.observation_id, f"{prefix}-finalize",
        )
        return observation.observation_id

    @staticmethod
    def _corrupt(db_path: Path, statements: list[tuple[str, tuple]]) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("PRAGMA ignore_check_constraints=ON")
            for sql, parameters in statements:
                conn.execute(sql, parameters)
            conn.commit()

    def test_registry_ids_are_fixed_and_unique(self) -> None:
        ids = [item.invariant_id for item in INTEGRITY_INVARIANTS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 23)
        self.assertTrue(all(item.authoritative_source for item in INTEGRITY_INVARIANTS))
        self.assertTrue(all(item.condition for item in INTEGRITY_INVARIANTS))

    def test_person_scan_uses_constant_statement_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))

            def traced_statement_count() -> int:
                statements: list[str] = []

                class TracedChecker(ReadOnlyIntegrityChecker):
                    def _connect_read_only(self):
                        connection = super()._connect_read_only()
                        connection.set_trace_callback(statements.append)
                        return connection

                TracedChecker(store.db_path).run()
                return len([
                    statement for statement in statements
                    if statement.lstrip().upper().startswith(("SELECT", "WITH", "PRAGMA"))
                ])

            empty_count = traced_statement_count()
            created_at = utc_now()
            with sqlite3.connect(store.db_path) as conn:
                conn.executemany(
                    """
                    INSERT INTO persons(
                        person_id, name, metadata, created_at, enrollment_status,
                        notes, lifecycle_status, identity_status, biometric_status,
                        lifecycle_changed_at
                    ) VALUES (?, ?, '{}', ?, 'placeholder', '', 'ACTIVE',
                              'IDENTIFIED', 'NO_FACE', ?)
                    """,
                    [
                        (f"person-{index:04d}", f"Person {index}", created_at, created_at)
                        for index in range(500)
                    ],
                )
                conn.commit()

            populated_count = traced_statement_count()

            self.assertLessEqual(populated_count, empty_count + 5)

    def test_clean_database_passes_and_checker_performs_no_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            observation_id = self._finalized(
                store, "clean", [first.person_id, second.person_id],
            )
            GlobalIdentityGraphService(store).record_observation_evidence(
                observation_id, "clean-evidence",
            )
            before_hash = hashlib.sha256(store.db_path.read_bytes()).hexdigest()
            before_journal = store.db_path.with_name(store.db_path.name + "-wal")
            before_journal_size = before_journal.stat().st_size if before_journal.exists() else 0
            statements: list[str] = []

            class TracedChecker(ReadOnlyIntegrityChecker):
                def _connect_read_only(self):
                    connection = super()._connect_read_only()
                    connection.set_trace_callback(statements.append)
                    return connection

            report = TracedChecker(
                store.db_path, clock=lambda: "2026-08-11T00:00:00+00:00",
            ).run()

            self.assertEqual(report.status, "PASS")
            self.assertEqual(report.findings, ())
            self.assertFalse(report.findings_truncated)
            self.assertEqual(
                hashlib.sha256(store.db_path.read_bytes()).hexdigest(), before_hash,
            )
            # Opening a WAL-mode SQLite database after a clean close may create an
            # empty sidecar. No WAL frames or authoritative bytes may be written.
            self.assertEqual(
                before_journal.stat().st_size if before_journal.exists() else 0,
                before_journal_size,
            )
            forbidden = (
                "INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP",
                "ALTER", "VACUUM", "REINDEX", "ATTACH", "DETACH",
            )
            self.assertFalse([
                statement for statement in statements
                if statement.lstrip().upper().startswith(forbidden)
            ])
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM operation_journal").fetchone()[0],
                    3,
                )

    def test_detects_canonical_cycle_and_dangling_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            third = store.create_person("Third")
            self._corrupt(store.db_path, [
                ("DROP TRIGGER persons_canonical_update", ()),
                ("UPDATE persons SET lifecycle_status='MERGED', deleted_at=?, canonical_person_id=? WHERE person_id=?", (utc_now(), second.person_id, first.person_id)),
                ("UPDATE persons SET lifecycle_status='MERGED', deleted_at=?, canonical_person_id=? WHERE person_id=?", (utc_now(), first.person_id, second.person_id)),
                ("UPDATE persons SET lifecycle_status='MERGED', deleted_at=?, canonical_person_id='missing' WHERE person_id=?", (utc_now(), third.person_id)),
            ])

            findings = self._findings(store)

            self.assertIn("P11-IDENTITY-002", findings)
            self.assertIn("P11-SCHEMA-003", findings)

    def test_detects_invalid_correction_chain_and_interpretation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            people = [store.create_person(name) for name in ("A", "B", "C")]
            embedding = store.add_embedding(people[0].person_id, (1.0, 0.0), 0.9)
            for operation_id in ("move-1", "move-2"):
                store.begin_operation("identity.face.move", operation_id=operation_id)
                store.mark_operation_committed(operation_id)
            self._corrupt(store.db_path, [
                ("INSERT INTO identity_corrections VALUES (?,?,?,?,?,?,?,?,?)", ("correction-1", "FACE_OWNERSHIP", None, None, embedding.embedding_id, people[0].person_id, people[1].person_id, "move-1", "2026-08-11T00:00:00+00:00")),
                ("INSERT INTO identity_corrections VALUES (?,?,?,?,?,?,?,?,?)", ("correction-2", "FACE_OWNERSHIP", None, None, embedding.embedding_id, people[2].person_id, "missing-person", "move-2", "2026-08-11T00:01:00+00:00")),
            ])

            findings = self._findings(store)

            self.assertIn("P11-CORRECTION-001", findings)
            self.assertIn("P11-CORRECTION-002", findings)
            self.assertIn("P11-SCHEMA-003", findings)

    def test_detects_missing_participant_and_inconsistent_finalization(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Person")
            observation_id = self._finalized(store, "broken-event", [person.person_id])
            self._corrupt(store.db_path, [
                ("DROP TRIGGER observation_participants_draft_delete", ()),
                ("DELETE FROM observation_participants WHERE observation_id=?", (observation_id,)),
            ])

            self.assertIn("P11-OBSERVATION-001", self._findings(store))

    def test_detects_participant_whose_person_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Person")
            observation_id = self._finalized(store, "dangling-participant", [person.person_id])
            self._corrupt(store.db_path, [
                ("UPDATE observation_participants SET person_id='missing-person' WHERE observation_id=?", (observation_id,)),
            ])

            findings = self._findings(store)

            self.assertIn("P11-SCHEMA-003", findings)
            self.assertIn("P11-CORRECTION-002", findings)
            self.assertIn("P11-OBSERVATION-001", findings)

    def test_detects_orphan_media_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Person")
            observation = store.create_observation(
                "orphan-media-create", participant_ids=[person.person_id],
            )
            operation_id = "orphan-media-attach"
            store.begin_operation("observation.media.attach", operation_id=operation_id)
            store.mark_operation_committed(operation_id)
            self._corrupt(store.db_path, [
                ("INSERT INTO observation_media VALUES (?,?,?,?,?,?)", (observation.observation_id, "missing-media", "/missing/reference.jpg", "corrupt-fixture", operation_id, utc_now())),
            ])

            self.assertIn("P11-OBSERVATION-003", self._findings(store))

    def test_detects_missing_extra_and_retired_graph_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            people = [store.create_person(name) for name in ("A", "B", "C")]
            graph = GlobalIdentityGraphService(store)
            observation_id = self._finalized(
                store, "graph-drift", [people[0].person_id, people[1].person_id],
            )
            evidence = graph.record_observation_evidence(
                observation_id, "graph-drift-evidence",
            )[0]
            graph.deactivate_evidence(evidence.evidence_id, "graph-retire")
            active_observation_id = self._finalized(
                store, "graph-active", [people[0].person_id, people[2].person_id],
            )
            graph.record_observation_evidence(
                active_observation_id, "graph-active-evidence",
            )
            missing_low, missing_high = sorted(
                (people[0].person_id, people[2].person_id)
            )
            extra_low, extra_high = sorted((people[1].person_id, people[2].person_id))
            self._corrupt(store.db_path, [
                ("DELETE FROM graph_connections WHERE source_person_id=? AND target_person_id=?", (missing_low, missing_high)),
                ("INSERT INTO graph_connections VALUES (?,?,?,?,?,?,?)", (extra_low, extra_high, "ASSOCIATED_WITH", "UNDIRECTED", 1, json.dumps(["CO_OBSERVED"]), utc_now())),
            ])

            report = ReadOnlyIntegrityChecker(store.db_path).run()
            graph_findings = [item for item in report.findings if item.invariant_id == "P11-GRAPH-001"]

            self.assertTrue(any("no active evidence support" in item.message for item in graph_findings))
            self.assertTrue(any("is missing" in item.message for item in graph_findings))
            self.assertNotIn(evidence.evidence_id, {value for item in graph_findings for _, value in item.entity_ids})

    def test_detects_broken_note_mention_and_reference_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            owner = store.create_person("Owner")
            mentioned = store.create_person("Mentioned")
            note = store.create_note(
                owner.person_id, "Known person", "note-create",
                mentioned_person_ids=[mentioned.person_id],
            )
            with sqlite3.connect(store.db_path) as conn:
                mention_id = conn.execute(
                    "SELECT mention_id FROM note_mentions WHERE note_id=?", (note.note_id,),
                ).fetchone()[0]
            self._corrupt(store.db_path, [
                ("DROP TRIGGER note_mentions_identity_immutable", ()),
                ("UPDATE note_mentions SET referenced_person_id='missing-person' WHERE mention_id=?", (mention_id,)),
            ])

            findings = self._findings(store)

            self.assertIn("P11-SCHEMA-003", findings)
            self.assertIn("P11-NOTE-003", findings)

    def test_detects_operation_result_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            store.begin_operation(
                "identity.merge", operation_id="committed-without-manifest",
            )
            store.mark_operation_committed("committed-without-manifest")

            findings = self._findings(store)

            self.assertIn("P11-MERGE-001", findings)
            self.assertIn("P11-JOURNAL-003", findings)

    def test_legitimate_historical_lifecycle_and_retired_evidence_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            archived = store.create_person("Archived")
            deleted = store.create_person("Deleted")
            active = store.create_person("Active")
            store.archive_person(archived.person_id, "archive")
            store.soft_delete_person(deleted.person_id, "delete")
            observation_id = self._finalized(
                store, "historical", [archived.person_id, deleted.person_id],
            )
            graph = GlobalIdentityGraphService(store)
            evidence = graph.record_observation_evidence(
                observation_id, "historical-evidence",
            )[0]
            graph.deactivate_evidence(evidence.evidence_id, "historical-retire")

            report = ReadOnlyIntegrityChecker(store.db_path).run()

            self.assertEqual(report.status, "PASS", report.findings)
            self.assertIsNotNone(active.person_id)

    def test_correction_merge_orderings_and_self_edge_suppression_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            a, b, c, d = [store.create_person(name) for name in ("A", "B", "C", "D")]
            first_observation = self._finalized(
                store, "correct-then-merge", [a.person_id, b.person_id],
            )
            graph.record_observation_evidence(first_observation, "ctm-evidence")
            graph.correct_observation_identity(
                first_observation, a.person_id, c.person_id, "ctm-correction",
            )
            IdentityMergeService(store).execute(
                c.person_id, d.person_id, "ctm-merge",
            )

            second_observation = self._finalized(
                store, "merge-then-correct", [a.person_id, b.person_id],
            )
            graph.record_observation_evidence(second_observation, "mtc-evidence")
            IdentityMergeService(store).execute(
                a.person_id, b.person_id, "mtc-merge",
            )
            graph.correct_observation_identity(
                second_observation, b.person_id, d.person_id, "mtc-correction",
            )

            report = ReadOnlyIntegrityChecker(store.db_path).run()

            self.assertEqual(report.status, "PASS", report.findings)
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) FROM graph_connections WHERE source_person_id=target_person_id"
                    ).fetchone()[0],
                    0,
                )

    def test_legitimate_transitive_merge_chain_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first, second, survivor = [
                store.create_person(name) for name in ("First", "Second", "Survivor")
            ]
            merges = IdentityMergeService(store)
            merges.execute(first.person_id, second.person_id, "merge-chain-one")
            merges.execute(second.person_id, survivor.person_id, "merge-chain-two")

            report = ReadOnlyIntegrityChecker(store.db_path).run()

            self.assertEqual(report.status, "PASS", report.findings)


if __name__ == "__main__":
    unittest.main()
