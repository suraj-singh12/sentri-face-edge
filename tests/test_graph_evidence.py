from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.models import utc_now
from sentriface.storage.sqlite_store import (
    SCHEMA_VERSION,
    SQLiteIdentityStore,
    _insert_relationship_evidence,
    _replace_graph_projection,
    _schema_migrations,
)


class GlobalGraphEvidenceTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _finalized_observation(
        self,
        store: SQLiteIdentityStore,
        operation_prefix: str,
        person_ids: list[str],
    ) -> str:
        observation = store.create_observation(
            f"{operation_prefix}-create", participant_ids=person_ids,
        )
        store._finalize_observation_without_graph_evidence(
            observation.observation_id, f"{operation_prefix}-finalize",
        )
        return observation.observation_id

    def test_single_person_observation_creates_no_evidence_or_connection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            person = store.create_person("Only Person")
            observation_id = self._finalized_observation(
                store, "single", [person.person_id],
            )

            evidence = graph.record_observation_evidence(
                observation_id, "single-graph-evidence",
            )

            self.assertEqual(evidence, [])
            self.assertEqual(graph.get_person_neighbors(person.person_id), [])
            self.assertEqual(graph.get_global_projection().connections, ())

    def test_two_people_create_one_undirected_explainable_connection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            first = store.create_person("First")
            second = store.create_person("Second")
            observation_id = self._finalized_observation(
                store, "pair", [first.person_id, second.person_id],
            )

            evidence = graph.record_observation_evidence(
                observation_id, "pair-graph-evidence",
            )
            connection = graph.get_person_neighbors(first.person_id)[0]

            self.assertEqual(len(evidence), 1)
            self.assertEqual(evidence[0].evidence_type, "CO_OBSERVED")
            self.assertEqual(evidence[0].source_entity_id, observation_id)
            self.assertEqual(connection.directionality, "UNDIRECTED")
            self.assertEqual(connection.evidence_count, 1)
            self.assertEqual(connection.evidence_types, ("CO_OBSERVED",))
            self.assertEqual(
                [item.evidence_id for item in graph.get_connection_evidence(
                    first.person_id, second.person_id,
                )],
                [evidence[0].evidence_id],
            )

    def test_three_people_create_exactly_three_pairwise_connections(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            people = [store.create_person(name) for name in ("A", "B", "C")]
            observation_id = self._finalized_observation(
                store, "triple", [person.person_id for person in people],
            )

            evidence = graph.record_observation_evidence(
                observation_id, "triple-graph-evidence",
            )

            self.assertEqual(len(evidence), 3)
            self.assertEqual(len(graph.get_global_projection().connections), 3)
            self.assertEqual(
                {len(graph.get_person_neighbors(person.person_id)) for person in people},
                {2},
            )
            deactivated = graph.deactivate_source_evidence(
                "CO_OBSERVED", observation_id, "triple-source-deactivate",
            )
            self.assertEqual(len(deactivated), 3)
            self.assertTrue(all(not item.active for item in deactivated))
            self.assertEqual(graph.get_global_projection().connections, ())

    def test_repeated_observations_add_evidence_not_duplicate_connections(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            first = store.create_person("A")
            second = store.create_person("B")
            person_ids = [first.person_id, second.person_id]
            first_observation = self._finalized_observation(store, "repeat-one", person_ids)
            second_observation = self._finalized_observation(store, "repeat-two", person_ids)

            first_evidence = graph.record_observation_evidence(
                first_observation, "repeat-one-evidence",
            )
            second_evidence = graph.record_observation_evidence(
                second_observation, "repeat-two-evidence",
            )

            self.assertNotEqual(first_evidence[0].evidence_id, second_evidence[0].evidence_id)
            connections = graph.get_global_projection().connections
            self.assertEqual(len(connections), 1)
            self.assertEqual(connections[0].evidence_count, 2)

    def test_record_retry_and_duplicate_invocation_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            first = store.create_person("A")
            second = store.create_person("B")
            observation_id = self._finalized_observation(
                store, "retry", [first.person_id, second.person_id],
            )

            original = graph.record_observation_evidence(observation_id, "retry-evidence")
            same_operation = graph.record_observation_evidence(
                observation_id, "retry-evidence",
            )
            new_operation = graph.record_observation_evidence(
                observation_id, "retry-evidence-new-operation",
            )

            self.assertEqual(original, same_operation)
            self.assertEqual(original, new_operation)
            self.assertEqual(len(graph.get_connection_evidence(first.person_id, second.person_id)), 1)

    def test_canonical_equivalent_participants_never_project_self_edge(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            source = store.create_person("Source")
            survivor = store.create_person("Survivor")
            observation_id = self._finalized_observation(
                store, "canonical-self", [source.person_id, survivor.person_id],
            )
            initial_evidence = graph.record_observation_evidence(
                observation_id, "canonical-self-evidence",
            )
            self.assertEqual(len(initial_evidence), 1)
            self.assertEqual(len(graph.get_global_projection().connections), 1)
            store._set_canonical_person_id_for_merge(
                source.person_id, survivor.person_id, "canonical-self-map",
            )

            self.assertEqual(graph.get_global_projection().connections, ())
            self.assertEqual(len(graph.get_connection_evidence(
                source.person_id, survivor.person_id, include_inactive=True,
            )), 0)
            self.assertTrue(graph.validate_projection()["valid"])

    def test_raw_participant_pairs_survive_canonicalization_before_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            first = store.create_person("A")
            survivor = store.create_person("B")
            third = store.create_person("C")
            observation_id = self._finalized_observation(
                store,
                "raw-provenance",
                [first.person_id, survivor.person_id, third.person_id],
            )
            store._set_canonical_person_id_for_merge(
                first.person_id, survivor.person_id, "raw-provenance-map",
            )

            evidence = graph.record_observation_evidence(
                observation_id, "raw-provenance-evidence",
            )

            self.assertEqual(len(evidence), 3)
            self.assertEqual(
                {
                    tuple(sorted((item.source_person_id, item.target_person_id)))
                    for item in evidence
                },
                {
                    tuple(sorted((first.person_id, survivor.person_id))),
                    tuple(sorted((first.person_id, third.person_id))),
                    tuple(sorted((survivor.person_id, third.person_id))),
                },
            )
            connections = graph.get_global_projection().connections
            self.assertEqual(len(connections), 1)
            self.assertEqual(connections[0].evidence_count, 2)
            expected = connections
            graph.rebuild_projection("raw-provenance-rebuild")
            self.assertEqual(graph.get_global_projection().connections, expected)

    def test_directed_lookup_preserves_direction_and_undirected_insert_normalizes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            first = store.create_person("A")
            second = store.create_person("B")
            operation_id = "evidence-direction-fixture"
            graph.create_note(
                first.person_id,
                "@B",
                "directed-note-a-to-b",
                mentioned_person_ids=[second.person_id],
            )
            graph.create_note(
                second.person_id,
                "@A",
                "directed-note-b-to-a",
                mentioned_person_ids=[first.person_id],
            )
            store.begin_operation("test.evidence-direction", operation_id=operation_id)
            store.mark_operation_committed(operation_id)
            created_at = utc_now()
            with store._connect() as conn:
                first_undirected_id = _insert_relationship_evidence(
                    conn,
                    evidence_type="MANUAL_ASSOCIATION",
                    source_entity_type="MANUAL_ASSERTION",
                    source_entity_id="manual-pair",
                    source_person_id=first.person_id,
                    target_person_id=second.person_id,
                    relationship_type="ASSOCIATED_WITH",
                    directionality="UNDIRECTED",
                    source="test",
                    created_operation_id=operation_id,
                    created_at=created_at,
                )
                reversed_undirected_id = _insert_relationship_evidence(
                    conn,
                    evidence_type="MANUAL_ASSOCIATION",
                    source_entity_type="MANUAL_ASSERTION",
                    source_entity_id="manual-pair",
                    source_person_id=second.person_id,
                    target_person_id=first.person_id,
                    relationship_type="ASSOCIATED_WITH",
                    directionality="UNDIRECTED",
                    source="test",
                    created_operation_id=operation_id,
                    created_at=created_at,
                )
                _replace_graph_projection(conn)

            self.assertEqual(first_undirected_id, reversed_undirected_id)
            forward = graph.get_connection_evidence(first.person_id, second.person_id)
            reverse = graph.get_connection_evidence(second.person_id, first.person_id)
            forward_directed = [item for item in forward if item.directionality == "DIRECTED"]
            reverse_directed = [item for item in reverse if item.directionality == "DIRECTED"]
            self.assertEqual(len(forward_directed), 1)
            self.assertEqual(len(reverse_directed), 1)
            self.assertEqual(
                (forward_directed[0].source_person_id, forward_directed[0].target_person_id),
                (first.person_id, second.person_id),
            )
            self.assertEqual(
                (reverse_directed[0].source_person_id, reverse_directed[0].target_person_id),
                (second.person_id, first.person_id),
            )
            self.assertEqual(
                len([item for item in forward if item.directionality == "UNDIRECTED"]),
                1,
            )

    def test_database_rejects_reversed_undirected_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("A")
            second = store.create_person("B")
            low_person_id, high_person_id = sorted((first.person_id, second.person_id))
            operation_id = "evidence-order-fixture"
            store.begin_operation("test.evidence-order", operation_id=operation_id)
            store.mark_operation_committed(operation_id)

            with self.assertRaisesRegex(sqlite3.IntegrityError, "must be ordered"):
                with store._connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO relationship_evidence(
                            evidence_id, evidence_type, source_entity_type, source_entity_id,
                            source_person_id, target_person_id, relationship_type,
                            directionality, active, created_operation_id, created_at
                        ) VALUES (
                            'reversed-evidence', 'MANUAL_ASSOCIATION', 'MANUAL_ASSERTION',
                            'manual-reversed', ?, ?, 'ASSOCIATED_WITH', 'UNDIRECTED',
                            1, ?, ?
                        )
                        """,
                        (high_person_id, low_person_id, operation_id, utc_now()),
                    )

    def test_archived_and_deleted_people_remain_graph_resolvable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            archived = store.create_person("Archived")
            deleted = store.create_person("Deleted")
            store.archive_person(archived.person_id, "graph-archive-person")
            store.soft_delete_person(deleted.person_id, "graph-delete-person")
            observation_id = self._finalized_observation(
                store, "historical-graph", [archived.person_id, deleted.person_id],
            )

            graph.record_observation_evidence(
                observation_id, "historical-graph-evidence",
            )
            projection = graph.get_global_projection()

            self.assertEqual(len(graph.get_person_neighbors(archived.person_id)), 1)
            node_states = {
                node.person_id: node.lifecycle_status for node in projection.nodes
            }
            self.assertEqual(node_states[archived.person_id], "ARCHIVED")
            self.assertEqual(node_states[deleted.person_id], "DELETED")

    def test_deactivating_evidence_preserves_then_removes_connection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            first = store.create_person("A")
            second = store.create_person("B")
            person_ids = [first.person_id, second.person_id]
            first_observation = self._finalized_observation(store, "deactivate-one", person_ids)
            second_observation = self._finalized_observation(store, "deactivate-two", person_ids)
            first_evidence = graph.record_observation_evidence(
                first_observation, "deactivate-one-record",
            )[0]
            second_evidence = graph.record_observation_evidence(
                second_observation, "deactivate-two-record",
            )[0]

            graph.deactivate_evidence(first_evidence.evidence_id, "deactivate-first")
            self.assertEqual(graph.get_person_neighbors(first.person_id)[0].evidence_count, 1)
            graph.deactivate_evidence(second_evidence.evidence_id, "deactivate-second")

            self.assertEqual(graph.get_person_neighbors(first.person_id), [])
            all_evidence = graph.get_connection_evidence(
                first.person_id, second.person_id, include_inactive=True,
            )
            self.assertEqual(len(all_evidence), 2)
            self.assertTrue(all(not item.active for item in all_evidence))

    def test_projection_validation_and_rebuild_are_deterministic_and_repair_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            first = store.create_person("A")
            second = store.create_person("B")
            observation_id = self._finalized_observation(
                store, "rebuild", [first.person_id, second.person_id],
            )
            graph.record_observation_evidence(observation_id, "rebuild-record")
            expected = graph.get_global_projection().connections

            with sqlite3.connect(store.db_path) as conn:
                conn.execute("DELETE FROM graph_connections")
                conn.commit()
            self.assertFalse(graph.validate_projection()["valid"])
            graph.rebuild_projection("rebuild-projection-one")
            self.assertEqual(graph.get_global_projection().connections, expected)
            graph.rebuild_projection("rebuild-projection-two")
            self.assertEqual(graph.get_global_projection().connections, expected)

            with sqlite3.connect(store.db_path) as conn:
                conn.execute("UPDATE graph_connections SET evidence_count = 99")
                conn.commit()
            self.assertFalse(graph.validate_projection()["valid"])
            graph.rebuild_projection("rebuild-projection-corrupt")
            self.assertEqual(graph.get_global_projection().connections, expected)

    def test_failed_graph_transaction_rolls_back_evidence_projection_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            first = store.create_person("A")
            second = store.create_person("B")
            observation_id = self._finalized_observation(
                store, "rollback-graph", [first.person_id, second.person_id],
            )

            with patch(
                "sentriface.storage.sqlite_store._transition_journal_operation",
                side_effect=RuntimeError("simulated graph journal failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated graph journal failure"):
                    graph.record_observation_evidence(
                        observation_id, "rollback-graph-evidence",
                    )

            self.assertIsNone(store.get_operation("rollback-graph-evidence"))
            self.assertEqual(graph.get_global_projection().connections, ())
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM relationship_evidence").fetchone()[0],
                    0,
                )

    def test_graph_operation_journal_is_committed_with_actor_and_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            first = store.create_person("A")
            second = store.create_person("B")
            observation_id = self._finalized_observation(
                store, "journal-graph", [first.person_id, second.person_id],
            )
            actor = {"user_id": "operator-1", "username": "operator", "roles": ["operator"]}

            graph.record_observation_evidence(
                observation_id,
                "journal-graph-record",
                actor=actor,
                source="test-suite",
            )
            operation = store.get_operation("journal-graph-record")

            self.assertEqual(operation["operation_type"], "graph.observation-evidence.record")
            self.assertEqual(operation["status"], "COMMITTED")
            self.assertEqual(operation["actor"]["user_id"], "operator-1")
            self.assertEqual(operation["source"], "test-suite")

    def test_v19_database_migrates_to_graph_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("BEGIN")
                for migration in _schema_migrations():
                    if migration.to_version > 19:
                        break
                    migration.apply(conn)
                conn.commit()

            store = SQLiteIdentityStore(db_path, embedding_dim=2)
            store.initialize()

            with sqlite3.connect(db_path) as conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertTrue({"relationship_evidence", "graph_connections"} <= tables)

    def test_v20_database_adds_undirected_evidence_order_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("BEGIN")
                for migration in _schema_migrations():
                    if migration.to_version > 20:
                        break
                    migration.apply(conn)
                conn.commit()

            SQLiteIdentityStore(db_path, embedding_dim=2).initialize()

            with sqlite3.connect(db_path) as conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                trigger = conn.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'trigger'
                      AND name = 'relationship_evidence_undirected_order_insert'
                    """
                ).fetchone()
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertEqual(trigger[0], "relationship_evidence_undirected_order_insert")


if __name__ == "__main__":
    unittest.main()
