from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.storage.sqlite_store import SQLiteIdentityStore, SchemaMigrationError


class StartupDomainValidationTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def test_startup_reports_projection_drift_without_repairing_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            observation = store.create_observation(
                "startup-observation", participant_ids=[first.person_id, second.person_id],
            )
            store._finalize_observation_without_graph_evidence(
                observation.observation_id, "startup-finalize",
            )
            graph = GlobalIdentityGraphService(store)
            graph.record_observation_evidence(observation.observation_id, "startup-evidence")
            with store._connect() as conn:
                conn.execute("DELETE FROM graph_connections")
                revision_before = conn.execute(
                    "SELECT revision FROM graph_state WHERE singleton_id = 1"
                ).fetchone()[0]

            with self.assertRaisesRegex(
                SchemaMigrationError,
                "explicit P11-B graph projection rebuild",
            ):
                store.initialize()

            self.assertFalse(store.validate_graph_projection()["valid"])
            self.assertEqual(graph.get_global_projection().connections, ())
            with store._connect() as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT revision FROM graph_state WHERE singleton_id = 1"
                    ).fetchone()[0],
                    revision_before,
                )

    def test_startup_rejects_invalid_current_schema_canonical_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("Invalid Mapping A")
            second = store.create_person("Invalid Mapping B")
            with sqlite3.connect(store.db_path) as conn:
                conn.execute("DROP TRIGGER persons_canonical_update")
                conn.executemany(
                    """
                    UPDATE persons
                    SET lifecycle_status = 'MERGED', canonical_person_id = ?,
                        deleted_at = '2026-08-09T00:00:00+00:00'
                    WHERE person_id = ?
                    """,
                    (
                        (second.person_id, first.person_id),
                        (first.person_id, second.person_id),
                    ),
                )

            with self.assertRaisesRegex(SchemaMigrationError, "invalid canonical mapping"):
                store.initialize()


if __name__ == "__main__":
    unittest.main()
