from __future__ import annotations

import tempfile
import unittest
import sqlite3
from pathlib import Path

from sentriface.api_server import _person_graph_read_payload, _world_graph_read_payload
from sentriface.graph_read_service import GraphReadService
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.models import GraphReadFilter
from sentriface.storage.sqlite_store import (
    SCHEMA_VERSION,
    SQLiteIdentityStore,
    _schema_migrations,
)


class GraphReadContractsTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _observe(
        self,
        store: SQLiteIdentityStore,
        prefix: str,
        person_ids: list[str],
        *,
        observed_at: str,
        location: str,
    ) -> str:
        observation = store.create_observation(
            f"{prefix}-create",
            participant_ids=person_ids,
            observed_at=observed_at,
            location=location,
        )
        store._finalize_observation_without_graph_evidence(
            observation.observation_id, f"{prefix}-finalize",
        )
        GlobalIdentityGraphService(store).record_observation_evidence(
            observation.observation_id, f"{prefix}-evidence",
        )
        return observation.observation_id

    def test_person_graph_aggregates_multiple_relationships_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            root = store.create_person("Root")
            frequent = store.create_person("Frequent")
            occasional = store.create_person("Occasional")
            self._observe(
                store, "one", [root.person_id, frequent.person_id],
                observed_at="2026-01-10T10:00:00+00:00", location="HQ",
            )
            self._observe(
                store, "two", [root.person_id, frequent.person_id],
                observed_at="2026-02-10T10:00:00+00:00", location="HQ",
            )
            self._observe(
                store, "three", [root.person_id, occasional.person_id],
                observed_at="2026-03-10T10:00:00+00:00", location="Field",
            )
            GlobalIdentityGraphService(store).create_note(
                root.person_id,
                "Known frequent contact",
                "graph-read-note",
                mentioned_person_ids=[frequent.person_id],
            )

            model = GraphReadService(store).person_graph(root.person_id)
            payload = _person_graph_read_payload(model)

            self.assertEqual(payload["contract"], "sentriface.person-graph")
            self.assertEqual(payload["node_count"], 3)
            self.assertEqual(payload["edge_count"], 2)
            by_neighbor = {item["connected_person_id"]: item for item in payload["edges"]}
            self.assertEqual(by_neighbor[frequent.person_id]["relationship_strength"], 3)
            self.assertEqual(
                by_neighbor[frequent.person_id]["provenance_summary"]["evidence_type_counts"],
                {"CO_OBSERVED": 2, "NOTE_REFERENCE": 1},
            )
            summary = by_neighbor[frequent.person_id]["provenance_summary"]
            self.assertEqual(summary["distinct_encounter_count"], 2)
            self.assertEqual(summary["latest_shared_encounter_at"], "2026-02-10T10:00:00+00:00")
            self.assertEqual(summary["note_reference_direction_counts"], {
                f"{root.person_id}->{frequent.person_id}": 1,
            })
            self.assertEqual(by_neighbor[frequent.person_id]["first_occurrence"], "2026-01-10T10:00:00+00:00")
            self.assertTrue(by_neighbor[frequent.person_id]["last_occurrence"])

    def test_world_graph_collapses_merges_and_suppresses_canonical_self_edges(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            survivor = store.create_person("Survivor")
            third = store.create_person("Third")
            self._observe(
                store, "merge-pair", [source.person_id, survivor.person_id],
                observed_at="2026-01-01T10:00:00+00:00", location="HQ",
            )
            self._observe(
                store, "third-pair", [source.person_id, survivor.person_id, third.person_id],
                observed_at="2026-01-02T10:00:00+00:00", location="HQ",
            )
            store.execute_identity_merge(source.person_id, survivor.person_id, "graph-read-merge")

            model = GraphReadService(store).world_graph()
            node_ids = {item.person_id for item in model.nodes}

            self.assertNotIn(source.person_id, node_ids)
            self.assertIn(source.person_id, next(
                item for item in model.nodes if item.person_id == survivor.person_id
            ).historical_person_ids)
            self.assertEqual(len(model.edges), 1)
            self.assertEqual(
                {model.edges[0].source_person_id, model.edges[0].target_person_id},
                {survivor.person_id, third.person_id},
            )
            self.assertEqual(model.edges[0].evidence_count, 2)
            self.assertEqual(model.edges[0].provenance_summary["distinct_encounter_count"], 1)
            merged_request = GraphReadService(store).person_graph(source.person_id)
            self.assertEqual(merged_request.root_person_id, survivor.person_id)
            self.assertEqual(merged_request.root_requested_state, "MERGED")

    def test_correction_moves_current_relationship_and_advances_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            wrong = store.create_person("Wrong")
            corrected = store.create_person("Corrected")
            observation_id = self._observe(
                store, "correction", [first.person_id, wrong.person_id],
                observed_at="2026-04-01T10:00:00+00:00", location="Gate",
            )
            before = store.get_graph_revision()

            store.correct_observation_identity(
                observation_id, wrong.person_id, corrected.person_id, "graph-read-correction",
            )
            after = store.get_graph_revision()
            model = GraphReadService(store).person_graph(first.person_id)

            self.assertNotEqual(before, after)
            self.assertEqual([item.connected_person_id for item in model.edges], [corrected.person_id])
            self.assertEqual(model.edges[0].first_occurrence_at, "2026-04-01T10:00:00+00:00")

    def test_date_location_lifecycle_and_strength_filters_are_backend_owned(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            root = store.create_person("Root", {"country": "IN", "rank": "A"})
            hq = store.create_person("HQ", {"country": "IN", "rank": "B"})
            field = store.create_person("Field", {"country": "US", "rank": "A"})
            deleted = store.create_person("Deleted", {"country": "IN", "rank": "A"})
            self._observe(
                store, "old-hq", [root.person_id, hq.person_id],
                observed_at="2025-01-01T10:00:00+00:00", location="HQ",
            )
            self._observe(
                store, "new-hq", [root.person_id, hq.person_id],
                observed_at="2026-01-01T10:00:00+00:00", location="HQ",
            )
            self._observe(
                store, "field", [root.person_id, field.person_id],
                observed_at="2026-02-01T10:00:00+00:00", location="Field",
            )
            store.archive_person(field.person_id, "archive-field")
            store.permanently_delete_person(deleted.person_id, "delete-node")

            read_service = GraphReadService(store)
            hq_only = read_service.world_graph(GraphReadFilter(
                date_from="2026-01-01", location="HQ",
            ))
            strong = read_service.world_graph(GraphReadFilter(
                min_relationship_strength=2,
            ))
            active = read_service.world_graph(GraphReadFilter(lifecycle=("ACTIVE",)))
            archived = read_service.world_graph(GraphReadFilter(lifecycle=("ARCHIVED",)))
            tombstoned = read_service.world_graph(GraphReadFilter(lifecycle=("DELETED",)))

            self.assertEqual({item.person_id for item in hq_only.nodes}, {root.person_id, hq.person_id})
            self.assertEqual(hq_only.edges[0].evidence_count, 1)
            self.assertEqual(len(strong.edges), 1)
            self.assertEqual(strong.edges[0].evidence_count, 2)
            self.assertNotIn(field.person_id, {item.person_id for item in active.nodes})
            self.assertEqual([item.person_id for item in archived.nodes], [field.person_id])
            self.assertEqual(archived.nodes[0].state_indicator, "HISTORICAL")
            self.assertEqual([item.person_id for item in tombstoned.nodes], [deleted.person_id])
            self.assertEqual(tombstoned.nodes[0].allowed_actions, ("VIEW_HISTORY",))

    def test_world_contract_has_revision_timestamp_counts_and_ui_ready_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("No Face", {"importance": "High"})

            payload = _world_graph_read_payload(GraphReadService(store).world_graph())

            self.assertEqual(payload["contract"], "sentriface.world-graph")
            self.assertTrue(payload["graph_revision"].startswith("g"))
            self.assertTrue(payload["generated_at"])
            self.assertEqual(payload["node_count"], 1)
            self.assertEqual(payload["edge_count"], 0)
            node = payload["nodes"][0]
            self.assertEqual(node["person_id"], person.person_id)
            self.assertEqual(node["biometric_status"], "NO_FACE")
            self.assertIn("allowed_actions", node)
            self.assertIn("summary_intelligence", node)

    def test_graph_revision_is_idempotent_for_retried_evidence_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            observation = store.create_observation(
                "revision-create", participant_ids=[first.person_id, second.person_id],
            )
            store._finalize_observation_without_graph_evidence(
                observation.observation_id, "revision-finalize",
            )
            graph = GlobalIdentityGraphService(store)
            graph.record_observation_evidence(observation.observation_id, "revision-evidence")
            committed = store.get_graph_revision()

            graph.record_observation_evidence(observation.observation_id, "revision-evidence")

            self.assertEqual(store.get_graph_revision(), committed)

    def test_v26_upgrade_adds_revision_state_and_required_read_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                for migration in _schema_migrations():
                    if migration.to_version > 26:
                        break
                    migration.apply(conn)
                conn.commit()
            store = SQLiteIdentityStore(db_path, embedding_dim=2)
            store.initialize()

            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
                tables = {
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                indexes = {
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index'"
                    )
                }
            self.assertIn("graph_state", tables)
            self.assertIn("idx_relationship_evidence_active_endpoints_time", indexes)
            self.assertIn("idx_observations_finalized_time_location", indexes)
            self.assertEqual(store.get_graph_revision(), "g1")


if __name__ == "__main__":
    unittest.main()
