from __future__ import annotations

import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from sentriface.errors import GraphProjectionRebuildRefused
from sentriface.integrity import ReadOnlyIntegrityChecker
from sentriface.merge_service import IdentityMergeService
from sentriface.models import utc_now
from sentriface.storage.sqlite_store import (
    SQLiteIdentityStore,
    _begin_journal_operation,
    _insert_relationship_evidence,
    _replace_graph_projection,
    _transition_journal_operation,
)


class NoteEvidenceGraphSemanticAuditTest(unittest.TestCase):
    """P11-C2A history/current consistency and frozen R02 reachability proofs."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteIdentityStore(
            Path(self.temp.name) / "sentriface.db", embedding_dim=2,
        )
        self.store.initialize()
        self.owner = self.store.create_person("Owner")
        self.a = self.store.create_person("A")
        self.b = self.store.create_person("B")
        self.c = self.store.create_person("C")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _report(self):
        return ReadOnlyIntegrityChecker(self.store.db_path).run()

    def _findings(self, invariant_id: str):
        return [
            item for item in self._report().findings
            if item.invariant_id == invariant_id
        ]

    def _assert_p11_clean(self) -> None:
        report = self._report()
        self.assertFalse(report.findings_truncated)
        self.assertEqual(
            [
                (item.invariant_id, item.message)
                for item in report.findings
                if item.severity.value in {"CRITICAL", "ERROR"}
            ],
            [],
        )

    def _graph_revision(self) -> int:
        with self.store._connect() as conn:
            return int(conn.execute(
                "SELECT revision FROM graph_state WHERE singleton_id=1"
            ).fetchone()[0])

    def _active_mention(self, note_id: str) -> sqlite3.Row:
        with self.store._connect() as conn:
            row = conn.execute(
                """
                SELECT m.*, n.owner_person_id
                FROM note_mentions m JOIN notes n USING(note_id)
                WHERE m.note_id=? AND m.active=1
                ORDER BY m.mention_id LIMIT 1
                """,
                (note_id,),
            ).fetchone()
            if row is None:
                raise AssertionError("Expected one active mention")
            return row

    def _replace_note_evidence(self, note_id: str, operation_id: str) -> str:
        with self.store._connect() as conn:
            mention = conn.execute(
                """
                SELECT m.*, n.owner_person_id
                FROM note_mentions m JOIN notes n USING(note_id)
                WHERE m.note_id=? AND m.active=1
                """,
                (note_id,),
            ).fetchone()
            self.assertIsNotNone(mention)
            _begin_journal_operation(
                conn,
                "test.note-reference.replace",
                operation_id=operation_id,
                actor={"display_name": "Integrity test", "roles": []},
                affected_entities=[
                    {"entity_type": "note", "entity_id": note_id},
                    {"entity_type": "note_mention", "entity_id": mention["mention_id"]},
                ],
            )
            changed_at = utc_now()
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=0, deactivated_operation_id=?, deactivated_at=?
                WHERE evidence_type='NOTE_REFERENCE'
                  AND source_entity_id=? AND active=1
                """,
                (operation_id, changed_at, mention["mention_id"]),
            )
            evidence_id = _insert_relationship_evidence(
                conn,
                evidence_type="NOTE_REFERENCE",
                source_entity_type="NOTE",
                source_entity_id=str(mention["mention_id"]),
                evidence_revision_id=operation_id,
                source_person_id=str(mention["owner_person_id"]),
                target_person_id=str(mention["referenced_person_id"]),
                relationship_type="REFERENCES",
                directionality="DIRECTED",
                source="semantic-audit",
                created_operation_id=operation_id,
                created_at=changed_at,
            )
            _replace_graph_projection(conn)
            _transition_journal_operation(
                conn, operation_id, "COMMITTED", {"evidence_id": evidence_id},
            )
            return evidence_id

    def _append_current_occurrence(self, note_id: str, operation_id: str) -> str:
        with self.store._connect() as conn:
            note = conn.execute(
                """
                SELECT n.note_id, n.owner_person_id, r.revision_id
                FROM notes n JOIN note_revisions r USING(note_id)
                WHERE n.note_id=?
                ORDER BY r.revision_number DESC LIMIT 1
                """,
                (note_id,),
            ).fetchone()
            person_id = conn.execute(
                """
                SELECT referenced_person_id FROM note_revision_mentions
                WHERE revision_id=? ORDER BY referenced_person_id LIMIT 1
                """,
                (note["revision_id"],),
            ).fetchone()[0]
            mention_id = str(uuid.uuid4())
            _begin_journal_operation(
                conn,
                "test.note-reference.append-occurrence",
                operation_id=operation_id,
                actor={"display_name": "Integrity test", "roles": []},
            )
            created_at = utc_now()
            conn.execute(
                """
                INSERT INTO note_mentions(
                    mention_id, note_id, referenced_person_id, active,
                    created_revision_id, created_operation_id, created_at
                ) VALUES (?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    mention_id, note_id, person_id, note["revision_id"],
                    operation_id, created_at,
                ),
            )
            _insert_relationship_evidence(
                conn,
                evidence_type="NOTE_REFERENCE",
                source_entity_type="NOTE",
                source_entity_id=mention_id,
                evidence_revision_id=operation_id,
                source_person_id=str(note["owner_person_id"]),
                target_person_id=str(person_id),
                relationship_type="REFERENCES",
                directionality="DIRECTED",
                source="semantic-audit",
                created_operation_id=operation_id,
                created_at=created_at,
            )
            _replace_graph_projection(conn)
            _transition_journal_operation(conn, operation_id, "COMMITTED", {})
            return mention_id

    def test_normal_add_remove_readd_histories_are_fully_clean(self) -> None:
        note = self.store.create_note(
            self.owner.person_id,
            "A and B",
            "history-create",
            mentioned_person_ids=[self.a.person_id, self.b.person_id],
        )
        sequences = (
            ("A", [self.a.person_id]),
            ("none", []),
            ("A and B again", [self.a.person_id, self.b.person_id]),
            ("B only", [self.b.person_id]),
            ("none again", []),
        )
        for index, (content, mentions) in enumerate(sequences):
            self.store.update_note(
                note.note_id,
                content,
                f"history-update-{index}",
                mentioned_person_ids=mentions,
            )
            self._assert_p11_clean()
        self.store.retire_note(note.note_id, "history-retire-note")
        self._assert_p11_clean()
        with self.store._connect() as conn:
            occurrence = conn.execute(
                "SELECT COUNT(*), SUM(active) FROM note_mentions WHERE note_id=?",
                (note.note_id,),
            ).fetchone()
            evidence = conn.execute(
                """
                SELECT COUNT(*), SUM(active) FROM relationship_evidence
                WHERE evidence_type='NOTE_REFERENCE'
                  AND source_entity_id IN (
                    SELECT mention_id FROM note_mentions WHERE note_id=?
                  )
                """,
                (note.note_id,),
            ).fetchone()
        self.assertEqual(tuple(occurrence), (4, 0))
        self.assertEqual(tuple(evidence), (4, 0))

    def test_retired_revisions_on_a_current_occurrence_are_valid_history(self) -> None:
        note = self.store.create_note(
            self.owner.person_id,
            "A",
            "replacement-create",
            mentioned_person_ids=[self.a.person_id],
        )
        revision_before = self._graph_revision()
        for index in range(4):
            self._replace_note_evidence(note.note_id, f"replacement-{index}")
            self._assert_p11_clean()
        with self.store._connect() as conn:
            rows = conn.execute(
                """
                SELECT active, deactivated_operation_id, deactivated_at
                FROM relationship_evidence
                WHERE evidence_type='NOTE_REFERENCE'
                ORDER BY created_at, evidence_id
                """
            ).fetchall()
            revision_count = conn.execute(
                "SELECT COUNT(*) FROM note_revisions WHERE note_id=?",
                (note.note_id,),
            ).fetchone()[0]
            mention_count = conn.execute(
                "SELECT COUNT(*) FROM note_mentions WHERE note_id=?",
                (note.note_id,),
            ).fetchone()[0]
        self.assertEqual(len(rows), 5)
        self.assertEqual(sum(int(row["active"]) for row in rows), 1)
        self.assertTrue(all(
            row["deactivated_operation_id"] and row["deactivated_at"]
            for row in rows if not row["active"]
        ))
        self.assertEqual(revision_count, 1)
        self.assertEqual(mention_count, 1)
        self.assertEqual(self._graph_revision(), revision_before + 4)

    def test_current_evidence_cardinality_is_owned_by_note003(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "cardinality-create",
            mentioned_person_ids=[self.a.person_id],
        )
        mention = self._active_mention(note.note_id)
        with self.store._connect() as conn:
            _begin_journal_operation(
                conn, "test.note-reference.retire-current",
                operation_id="cardinality-retire",
            )
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=0, deactivated_operation_id='cardinality-retire',
                    deactivated_at=?
                WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=?
                """,
                (utc_now(), mention["mention_id"]),
            )
            _transition_journal_operation(conn, "cardinality-retire", "COMMITTED", {})
        self.assertEqual(self._findings("P11-EVIDENCE-001"), [])
        self.assertEqual(len(self._findings("P11-NOTE-003")), 1)
        self.assertEqual(len(self._findings("P11-GRAPH-001")), 1)

        self._replace_note_evidence(note.note_id, "cardinality-replace")
        self._assert_p11_clean()

    def test_generic_deactivation_cannot_leave_an_active_occurrence_unsupported(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "deactivate-guard-create",
            mentioned_person_ids=[self.a.person_id],
        )
        mention = self._active_mention(note.note_id)
        with self.store._connect() as conn:
            evidence_id = conn.execute(
                """
                SELECT evidence_id FROM relationship_evidence
                WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
                """,
                (mention["mention_id"],),
            ).fetchone()[0]
        with self.assertRaisesRegex(
            RuntimeError, "NOTE_REFERENCE current active cardinality disagrees",
        ):
            self.store.deactivate_relationship_evidence(
                evidence_id, "deactivate-guard-attempt",
            )
        with self.store._connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT active FROM relationship_evidence WHERE evidence_id=?",
                (evidence_id,),
            ).fetchone()[0], 1)
            self.assertIsNone(conn.execute(
                "SELECT 1 FROM operation_journal WHERE operation_id=?",
                ("deactivate-guard-attempt",),
            ).fetchone())
        self._assert_p11_clean()

    def test_duplicate_active_evidence_is_current_corruption_not_history_corruption(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "duplicate-create",
            mentioned_person_ids=[self.a.person_id],
        )
        mention = self._active_mention(note.note_id)
        with self.store._connect() as conn:
            _begin_journal_operation(
                conn, "test.note-reference.duplicate", operation_id="duplicate-op",
            )
            _insert_relationship_evidence(
                conn,
                evidence_type="NOTE_REFERENCE",
                source_entity_type="NOTE",
                source_entity_id=str(mention["mention_id"]),
                evidence_revision_id="duplicate-op",
                source_person_id=str(mention["owner_person_id"]),
                target_person_id=str(mention["referenced_person_id"]),
                relationship_type="REFERENCES",
                directionality="DIRECTED",
                source="semantic-audit",
                created_operation_id="duplicate-op",
                created_at=utc_now(),
            )
            _transition_journal_operation(conn, "duplicate-op", "COMMITTED", {})
        self.assertEqual(self._findings("P11-EVIDENCE-001"), [])
        self.assertEqual(len(self._findings("P11-NOTE-003")), 1)
        self.assertEqual(len(self._findings("P11-GRAPH-001")), 1)

        self._replace_note_evidence(note.note_id, "duplicate-reconcile")
        self._assert_p11_clean()

    def test_active_source_compatibility_and_retirement_provenance_stay_strict(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "strict-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self.store.update_note(
            note.note_id, "none", "strict-remove", mentioned_person_ids=[],
        )
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER relationship_evidence_deactivation_only")
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=1, deactivated_operation_id=NULL, deactivated_at=NULL
                WHERE evidence_type='NOTE_REFERENCE'
                """
            )
        self.assertTrue(any(
            "no current active note mention source" in item.message
            for item in self._findings("P11-EVIDENCE-001")
        ))
        self.assertEqual(len(self._findings("P11-NOTE-003")), 1)

        self.tearDown()
        self.setUp()
        note = self.store.create_note(
            self.owner.person_id, "A", "provenance-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self.store.update_note(
            note.note_id, "none", "provenance-remove", mentioned_person_ids=[],
        )
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("PRAGMA ignore_check_constraints=ON")
            conn.execute("DROP TRIGGER relationship_evidence_deactivation_only")
            conn.execute(
                """
                UPDATE relationship_evidence SET deactivated_operation_id=NULL
                WHERE evidence_type='NOTE_REFERENCE'
                """
            )
        self.assertTrue(any(
            "invalid active/deactivation provenance" in item.message
            for item in self._findings("P11-EVIDENCE-001")
        ))

    def test_active_note_reference_on_a_retired_note_is_detected(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "retired-note-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self.store.retire_note(note.note_id, "retired-note-retire")
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER relationship_evidence_deactivation_only")
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=1, deactivated_operation_id=NULL, deactivated_at=NULL
                WHERE evidence_type='NOTE_REFERENCE'
                """
            )
        self.assertTrue(any(
            "no current active note mention source" in item.message
            for item in self._findings("P11-EVIDENCE-001")
        ))
        self.assertEqual(len(self._findings("P11-NOTE-003")), 1)

    def test_retired_row_source_type_direction_and_endpoints_remain_validated(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "malformed-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self._replace_note_evidence(note.note_id, "malformed-replacement")
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER relationship_evidence_identity_immutable")
            retired_id = conn.execute(
                """
                SELECT evidence_id FROM relationship_evidence
                WHERE evidence_type='NOTE_REFERENCE' AND active=0 LIMIT 1
                """
            ).fetchone()[0]
            conn.execute(
                """
                UPDATE relationship_evidence
                SET relationship_type='ASSOCIATED_WITH', directionality='UNDIRECTED',
                    source_entity_id='missing-occurrence'
                WHERE evidence_id=?
                """,
                (retired_id,),
            )
        findings = self._findings("P11-EVIDENCE-001")
        self.assertEqual(len(findings), 1)
        self.assertIn("missing note mention source", findings[0].message)
        self.assertIn("invalid directionality", findings[0].message)
        self.assertEqual(self._findings("P11-NOTE-003"), [])

    def test_p11b_rebuild_accepts_valid_history_and_rejects_malformed_retirement(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "rebuild-history-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self._replace_note_evidence(note.note_id, "rebuild-history-replacement")
        with self.store._connect() as conn:
            evidence_before = tuple(tuple(row) for row in conn.execute(
                "SELECT * FROM relationship_evidence ORDER BY evidence_id"
            ))
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DELETE FROM graph_connections")
        result = self.store.rebuild_graph_projection("rebuild-valid-note-history")
        self.assertTrue(result["changed"])
        self.assertEqual(result["preflight_status"], "PROJECTION_DRIFT")
        self.assertEqual(result["postcheck_status"], "PASS")
        with self.store._connect() as conn:
            evidence_after = tuple(tuple(row) for row in conn.execute(
                "SELECT * FROM relationship_evidence ORDER BY evidence_id"
            ))
        self.assertEqual(evidence_after, evidence_before)
        self._assert_p11_clean()

        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("PRAGMA ignore_check_constraints=ON")
            conn.execute("DROP TRIGGER relationship_evidence_deactivation_only")
            conn.execute(
                """
                UPDATE relationship_evidence SET deactivated_at=NULL
                WHERE evidence_type='NOTE_REFERENCE' AND active=0
                """
            )
        with self.assertRaises(GraphProjectionRebuildRefused):
            self.store.rebuild_graph_projection("rebuild-malformed-note-history")

    def test_other_evidence_types_remain_independent_support(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "support-create",
            mentioned_person_ids=[self.a.person_id],
        )
        observation = self.store.create_observation(
            "support-observation",
            participant_ids=[self.owner.person_id, self.a.person_id],
        )
        self.store._finalize_observation_without_graph_evidence(
            observation.observation_id, "support-finalize",
        )
        self.store.record_observation_evidence(
            observation.observation_id, "support-co-observed",
        )
        with self.store._connect() as conn:
            _begin_journal_operation(
                conn, "test.manual-association", operation_id="support-manual",
            )
            _insert_relationship_evidence(
                conn,
                evidence_type="MANUAL_ASSOCIATION",
                source_entity_type="MANUAL_ASSERTION",
                source_entity_id="support-assertion",
                evidence_revision_id="support-manual",
                source_person_id=self.owner.person_id,
                target_person_id=self.a.person_id,
                relationship_type="ASSOCIATED_WITH",
                directionality="UNDIRECTED",
                source="semantic-audit",
                created_operation_id="support-manual",
                created_at=utc_now(),
            )
            _replace_graph_projection(conn)
            _transition_journal_operation(conn, "support-manual", "COMMITTED", {})
        self.store.update_note(
            note.note_id, "none", "support-remove-note", mentioned_person_ids=[],
        )
        self._assert_p11_clean()
        connections = self.store.get_global_graph_projection().connections
        self.assertEqual(len(connections), 1)
        self.assertEqual(connections[0].evidence_count, 2)
        self.assertEqual(
            set(connections[0].evidence_types),
            {"CO_OBSERVED", "MANUAL_ASSOCIATION"},
        )

    def test_canonical_self_collapse_preserves_note_evidence_history(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "collapse-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self._replace_note_evidence(note.note_id, "collapse-replacement")
        IdentityMergeService(self.store).execute(
            self.owner.person_id, self.a.person_id, "collapse-merge",
        )
        self._assert_p11_clean()
        with self.store._connect() as conn:
            rows = conn.execute(
                """
                SELECT active FROM relationship_evidence
                WHERE evidence_type='NOTE_REFERENCE'
                ORDER BY created_at, evidence_id
                """
            ).fetchall()
        self.assertEqual([int(row["active"]) for row in rows].count(1), 1)
        self.assertEqual(self.store.get_global_graph_projection().connections, ())

    def test_correction_merge_orders_remain_clean_with_retired_note_evidence(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "transform-note-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self._replace_note_evidence(note.note_id, "transform-note-replacement")

        d, e, f = [self.store.create_person(name) for name in ("D", "E", "F")]
        first = self.store.create_observation(
            "transform-first-create",
            participant_ids=[self.owner.person_id, self.b.person_id],
        )
        self.store._finalize_observation_without_graph_evidence(
            first.observation_id, "transform-first-finalize",
        )
        self.store.record_observation_evidence(
            first.observation_id, "transform-first-evidence",
        )
        self.store.correct_observation_identity(
            first.observation_id,
            self.owner.person_id,
            self.c.person_id,
            "transform-correction-then-merge",
        )
        IdentityMergeService(self.store).execute(
            self.c.person_id, self.b.person_id, "transform-first-merge",
        )

        second = self.store.create_observation(
            "transform-second-create", participant_ids=[d.person_id, e.person_id],
        )
        self.store._finalize_observation_without_graph_evidence(
            second.observation_id, "transform-second-finalize",
        )
        self.store.record_observation_evidence(
            second.observation_id, "transform-second-evidence",
        )
        IdentityMergeService(self.store).execute(
            d.person_id, f.person_id, "transform-second-merge",
        )
        self.store.correct_observation_identity(
            second.observation_id,
            f.person_id,
            self.a.person_id,
            "transform-merge-then-correction",
        )
        self._assert_p11_clean()
        self.assertEqual(self._findings("P11-EVIDENCE-002"), [])
        self.assertEqual(self._findings("P11-GRAPH-001"), [])

    def test_existing_group_missing_occurrence_can_reach_clean_state_by_append_only(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "reach-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self.store.update_note(
            note.note_id, "none", "reach-remove", mentioned_person_ids=[],
        )
        self.store.update_note(
            note.note_id, "A again", "reach-readd",
            mentioned_person_ids=[self.a.person_id],
        )
        with self.store._connect() as conn:
            current = conn.execute(
                "SELECT mention_id FROM note_mentions WHERE note_id=? AND active=1",
                (note.note_id,),
            ).fetchone()[0]
            latest = conn.execute(
                """
                SELECT revision_id FROM note_revisions WHERE note_id=?
                ORDER BY revision_number DESC LIMIT 1
                """,
                (note.note_id,),
            ).fetchone()[0]
            _begin_journal_operation(
                conn, "test.remove-current", operation_id="reach-corrupt",
            )
            retired_at = utc_now()
            conn.execute(
                """
                UPDATE note_mentions
                SET active=0, retired_revision_id=?,
                    retired_operation_id='reach-corrupt', retired_at=?
                WHERE mention_id=?
                """,
                (latest, retired_at, current),
            )
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=0, deactivated_operation_id='reach-corrupt',
                    deactivated_at=?
                WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
                """,
                (retired_at, current),
            )
            _replace_graph_projection(conn)
            _transition_journal_operation(conn, "reach-corrupt", "COMMITTED", {})
        self.assertEqual(len(self._findings("P11-NOTE-002")), 1)
        history_before = None
        with self.store._connect() as conn:
            history_before = tuple(tuple(row) for row in conn.execute(
                """
                SELECT mention_id, created_revision_id, created_operation_id, created_at
                FROM note_mentions WHERE note_id=? ORDER BY created_at, mention_id
                """,
                (note.note_id,),
            ))
        self._append_current_occurrence(note.note_id, "reach-reconcile")
        self._assert_p11_clean()
        with self.store._connect() as conn:
            history_after = tuple(tuple(row) for row in conn.execute(
                """
                SELECT mention_id, created_revision_id, created_operation_id, created_at
                FROM note_mentions WHERE note_id=? ORDER BY created_at, mention_id
                """,
                (note.note_id,),
            ))
        self.assertEqual(history_after[: len(history_before)], history_before)
        self.assertEqual(len(history_after), len(history_before) + 1)

    def test_stale_occurrence_and_stale_evidence_can_reach_clean_retired_state(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "stale-reach-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self.store.update_note(
            note.note_id, "none", "stale-reach-remove", mentioned_person_ids=[],
        )
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER note_mentions_deactivation_only")
            conn.execute("DROP TRIGGER relationship_evidence_deactivation_only")
            conn.execute(
                """
                UPDATE note_mentions
                SET active=1, retired_revision_id=NULL,
                    retired_operation_id=NULL, retired_at=NULL
                WHERE note_id=?
                """,
                (note.note_id,),
            )
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=1, deactivated_operation_id=NULL, deactivated_at=NULL
                WHERE evidence_type='NOTE_REFERENCE'
                """
            )
        self.assertEqual(len(self._findings("P11-NOTE-002")), 1)
        with self.store._connect() as conn:
            latest = conn.execute(
                """
                SELECT revision_id FROM note_revisions WHERE note_id=?
                ORDER BY revision_number DESC LIMIT 1
                """,
                (note.note_id,),
            ).fetchone()[0]
            _begin_journal_operation(
                conn, "test.retire-stale-occurrence", operation_id="stale-reconcile",
            )
            retired_at = utc_now()
            conn.execute(
                """
                UPDATE note_mentions
                SET active=0, retired_revision_id=?,
                    retired_operation_id='stale-reconcile', retired_at=?
                WHERE note_id=? AND active=1
                """,
                (latest, retired_at, note.note_id),
            )
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=0, deactivated_operation_id='stale-reconcile',
                    deactivated_at=?
                WHERE evidence_type='NOTE_REFERENCE' AND active=1
                """,
                (retired_at,),
            )
            _replace_graph_projection(conn)
            _transition_journal_operation(conn, "stale-reconcile", "COMMITTED", {})
        self._assert_p11_clean()

        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=1, deactivated_operation_id=NULL, deactivated_at=NULL
                WHERE evidence_type='NOTE_REFERENCE'
                """
            )
        self.assertTrue(self._findings("P11-EVIDENCE-001"))
        self.assertTrue(self._findings("P11-NOTE-003"))
        with self.store._connect() as conn:
            _begin_journal_operation(
                conn, "test.retire-stale-evidence", operation_id="stale-evidence-reconcile",
            )
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=0, deactivated_operation_id='stale-evidence-reconcile',
                    deactivated_at=?
                WHERE evidence_type='NOTE_REFERENCE' AND active=1
                """,
                (utc_now(),),
            )
            _replace_graph_projection(conn)
            _transition_journal_operation(
                conn, "stale-evidence-reconcile", "COMMITTED", {},
            )
        self._assert_p11_clean()

    def test_wholly_missing_occurrence_group_boundary_is_preserved(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "boundary-create",
            mentioned_person_ids=[self.a.person_id],
        )
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER relationship_evidence_no_delete")
            conn.execute("DROP TRIGGER note_mentions_no_delete")
            conn.execute(
                """
                DELETE FROM relationship_evidence
                WHERE source_entity_id IN (
                    SELECT mention_id FROM note_mentions WHERE note_id=?
                )
                """,
                (note.note_id,),
            )
            conn.execute("DELETE FROM note_mentions WHERE note_id=?", (note.note_id,))
            conn.execute("DELETE FROM graph_connections")
        self.assertEqual(self._findings("P11-NOTE-002"), [])
        self.assertEqual(self._findings("P11-NOTE-003"), [])


if __name__ == "__main__":
    unittest.main()
