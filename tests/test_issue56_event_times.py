"""Issue #56: an Event time or date is shown only when it was recorded."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sentriface.api_payloads import _sighting_record
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.storage.sqlite_store import SQLiteIdentityStore
from sentriface.storage.sqlite_world import _world_event_time


class EventTimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = SQLiteIdentityStore(Path(self._tmp.name) / "sentriface.db", embedding_dim=2)
        self.store.initialize()
        self.alpha = self.store.create_person("Alpha").person_id
        self.beta = self.store.create_person("Beta").person_id

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _observe(self, prefix: str, observed_at: str | None) -> str:
        observation = self.store.create_observation(
            f"{prefix}-create", participant_ids=[self.alpha, self.beta],
            observed_at=observed_at, location="Pune",
        )
        self.store._finalize_observation_without_graph_evidence(observation.observation_id, f"{prefix}-finalize")
        GlobalIdentityGraphService(self.store).record_observation_evidence(
            observation.observation_id, f"{prefix}-evidence",
        )
        return observation.observation_id

    def test_event_time_reports_only_recorded_values(self) -> None:
        self.assertEqual(_world_event_time("2026-11-22", {"time_precision": "unknown"}),
                         {"date": "2026-11-22", "time_precision": "unknown", "start_time": None, "end_time": None})
        self.assertEqual(_world_event_time("2026-11-22T10:00:00", '{"time_precision": "exact", "start_time": "10:00", "end_time": "11:00"}'),
                         {"date": "2026-11-22", "time_precision": "exact", "start_time": "10:00", "end_time": "11:00"})
        self.assertEqual(_world_event_time("2026-11-22T10:00:00", {"time_precision": "approximate", "start_time": "10:00"}),
                         {"date": "2026-11-22", "time_precision": "approximate", "start_time": "10:00", "end_time": None})
        self.assertEqual(_world_event_time(None, {}),
                         {"date": None, "time_precision": "unknown", "start_time": None, "end_time": None})

    def test_missing_event_date_never_borrows_creation_time(self) -> None:
        self._observe("undated", None)
        sightings = self.store.list_person_sightings(self.alpha)
        self.assertEqual(len(sightings), 1)
        record = _sighting_record(sightings[0])
        self.assertEqual((record["date"], record["time"], record["time_precision"]), ("", "", "unknown"))
        summary = next(item for item in self.store.list_persons() if item.person.person_id == self.alpha)
        self.assertIsNone(summary.last_seen_at)
        graph = self.store.get_person_graph_read(self.alpha)
        edge = graph.edges[0]
        self.assertIsNone(edge.first_occurrence_at)
        self.assertIsNone(edge.last_occurrence_at)

    def test_summary_dates_skip_undated_events(self) -> None:
        self._observe("dated", "2026-11-22")
        self._observe("undated", None)
        summary = next(item for item in self.store.list_persons() if item.person.person_id == self.alpha)
        self.assertEqual(summary.last_seen_at, "2026-11-22")
        self.assertEqual(summary.first_seen_at, "2026-11-22")
        edge = self.store.get_person_graph_read(self.alpha).edges[0]
        self.assertEqual((edge.first_occurrence_at, edge.last_occurrence_at), ("2026-11-22", "2026-11-22"))


if __name__ == "__main__":
    unittest.main()
