from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.storage.sqlite_store import SCHEMA_VERSION, SQLiteIdentityStore, _schema_migrations


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
        store.finalize_observation(
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
            store.set_canonical_person_id(
                source.person_id, survivor.person_id, "canonical-self-map",
            )

            self.assertEqual(graph.get_global_projection().connections, ())
            self.assertEqual(len(graph.get_connection_evidence(
                source.person_id, survivor.person_id, include_inactive=True,
            )), 0)
            self.assertTrue(graph.validate_projection()["valid"])

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


if __name__ == "__main__":
    unittest.main()
