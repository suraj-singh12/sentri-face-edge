from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from sentriface.storage.sqlite_store import (
    SCHEMA_VERSION,
    SQLiteIdentityStore,
    _transition_journal_operation,
)


class OperationJournalTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db")
        store.initialize()
        return store

    def test_begin_operation_records_started_and_structured_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            operation = store.begin_operation(
                "identity-review",
                actor={
                    "user_id": "user-1",
                    "username": "operator.one",
                    "display_name": "Operator One",
                    "roles": ["operator"],
                    "capabilities": ["ignored-snapshot-field"],
                },
                source="check-photo",
                context={"request_id": "request-1"},
                affected_entities=[{"entity_type": "person", "entity_id": "person-1"}],
                details={"face_count": 2, "flags": ["manual-review"]},
            )

            uuid.UUID(operation["operation_id"])
            self.assertEqual(operation["status"], "STARTED")
            self.assertIsNone(operation["completed_at"])
            self.assertEqual(operation["actor"], {
                "user_id": "user-1",
                "username": "operator.one",
                "display_name": "Operator One",
                "roles": ["operator"],
            })
            self.assertEqual(operation["context"], {"request_id": "request-1"})
            self.assertEqual(operation["affected_entities"], [
                {"entity_type": "person", "entity_id": "person-1"},
            ])
            self.assertEqual(operation["details"]["face_count"], 2)
            self.assertEqual(
                [item["to_status"] for item in operation["status_history"]],
                ["STARTED"],
            )
            self.assertEqual(store.get_operation(operation["operation_id"]), operation)

    def test_started_operation_can_be_committed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            operation = store.begin_operation("commit-test", operation_id="commit-1")

            committed = store.mark_operation_committed(
                operation["operation_id"], {"result": "saved"},
            )

            self.assertEqual(committed["status"], "COMMITTED")
            self.assertIsNotNone(committed["completed_at"])
            self.assertEqual(committed["status_history"][-1]["details"], {"result": "saved"})

    def test_started_operation_can_be_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            operation = store.begin_operation("failure-test")

            failed = store.mark_operation_failed(
                operation["operation_id"],
                {"error_type": "ValidationError", "message": "review was incomplete"},
            )

            self.assertEqual(failed["status"], "FAILED")
            self.assertEqual(failed["status_history"][-1]["details"]["error_type"], "ValidationError")

    def test_started_operation_can_be_rolled_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            operation = store.begin_operation("rollback-test")

            rolled_back = store.mark_operation_rolled_back(
                operation["operation_id"], {"reason": "business transaction cancelled"},
            )

            self.assertEqual(rolled_back["status"], "ROLLED_BACK")
            self.assertEqual(rolled_back["status_history"][-1]["from_status"], "STARTED")

    def test_committed_operation_can_be_reverted_only_by_allowed_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            operation = store.begin_operation("revert-test")
            store.mark_operation_committed(operation["operation_id"])

            reverted = store.mark_operation_reverted(
                operation["operation_id"], {"reverted_by_operation_id": "inverse-1"},
            )

            self.assertEqual(reverted["status"], "REVERTED")
            self.assertEqual(
                [item["to_status"] for item in reverted["status_history"]],
                ["STARTED", "COMMITTED", "REVERTED"],
            )
            with self.assertRaisesRegex(ValueError, "REVERTED -> FAILED"):
                store.mark_operation_failed(operation["operation_id"])

    def test_invalid_status_transitions_and_duplicate_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            committed = store.begin_operation("invalid-test", operation_id="stable-operation-id")
            store.mark_operation_committed(committed["operation_id"])

            with self.assertRaisesRegex(ValueError, "COMMITTED -> ROLLED_BACK"):
                store.mark_operation_rolled_back(committed["operation_id"])
            with self.assertRaisesRegex(KeyError, "already exists"):
                store.begin_operation("another-type", operation_id="stable-operation-id")

            failed = store.begin_operation("failed-transition-test")
            store.mark_operation_failed(failed["operation_id"])
            with self.assertRaisesRegex(ValueError, "FAILED -> COMMITTED"):
                store.mark_operation_committed(failed["operation_id"])

    def test_operation_lookup_and_recent_listing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.begin_operation("first", operation_id="operation-1")
            second = store.begin_operation("second", operation_id="operation-2")

            self.assertIsNone(store.get_operation("missing"))
            self.assertEqual(store.get_operation(first["operation_id"])["operation_type"], "first")
            recent = store.list_recent_operations(limit=1)
            self.assertEqual([item["operation_id"] for item in recent], [second["operation_id"]])

    def test_failed_surrounding_transaction_does_not_leave_false_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            operation = store.begin_operation("transaction-test")

            with self.assertRaisesRegex(RuntimeError, "simulated business failure"):
                with store._connect() as conn:
                    _transition_journal_operation(
                        conn, operation["operation_id"], "COMMITTED", {"result": "temporary"},
                    )
                    raise RuntimeError("simulated business failure")

            recovered = store.get_operation(operation["operation_id"])
            self.assertEqual(recovered["status"], "STARTED")
            self.assertEqual(
                [item["to_status"] for item in recovered["status_history"]],
                ["STARTED"],
            )

    def test_v16_migration_preserves_legacy_person_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            legacy_result = {"person_id": "person-1", "changed": True}
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute(
                    """
                    CREATE TABLE persons (
                        person_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        deleted_at TEXT,
                        enrollment_status TEXT NOT NULL DEFAULT 'enrolled',
                        notes TEXT NOT NULL DEFAULT ''
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE embeddings (
                        embedding_id TEXT PRIMARY KEY,
                        person_id TEXT NOT NULL,
                        vector BLOB NOT NULL,
                        quality_score REAL NOT NULL,
                        source_image TEXT,
                        crop_path TEXT,
                        created_at TEXT NOT NULL,
                        deleted_at TEXT,
                        purge_after TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE person_operations (
                        operation_id TEXT PRIMARY KEY,
                        operation_type TEXT NOT NULL,
                        result TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO person_operations VALUES (?, ?, ?, ?)",
                    (
                        "legacy-operation",
                        "archive-person",
                        json.dumps(legacy_result),
                        "2026-08-08T00:00:00+00:00",
                    ),
                )
                conn.execute("PRAGMA user_version = 16")

            SQLiteIdentityStore(db_path).initialize()

            with closing(sqlite3.connect(db_path)) as conn, conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                legacy = conn.execute(
                    "SELECT operation_type, result, created_at FROM person_operations WHERE operation_id = ?",
                    ("legacy-operation",),
                ).fetchone()
                journal_table = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'operation_journal'"
                ).fetchone()

            self.assertEqual(version, SCHEMA_VERSION)
            self.assertEqual(legacy, (
                "archive-person",
                json.dumps(legacy_result),
                "2026-08-08T00:00:00+00:00",
            ))
            self.assertEqual(journal_table[0], "operation_journal")


if __name__ == "__main__":
    unittest.main()
