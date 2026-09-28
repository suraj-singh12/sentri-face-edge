from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.storage.sqlite_store import SQLiteIdentityStore


class JournaledIdentityMutationTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _assert_committed(self, store, operation_id, operation_type) -> dict:
        operation = store.get_operation(operation_id)
        self.assertEqual(operation["operation_type"], operation_type)
        self.assertEqual(operation["status"], "COMMITTED")
        self.assertEqual(operation["actor"]["username"], "operator")
        return operation

    def test_identified_person_profile_and_notes_survive_edit_and_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = self._store(root)
            person = store.create_identified_person(
                "Asha", {"rank": "Captain", "country": "India", "importance": "High", "added_by": "Operator", "tags": ["priority"]},
                "create-roundtrip", actor={"username": "operator"},
            )
            self.assertEqual(store.get_person(person.person_id).metadata["added_by"], "Operator")
            store.update_person_notes(person.person_id, "General context", "", "Operator", "note-roundtrip")
            store.update_person_profile(
                person.person_id, "Asha Rao", "Major", "India", "Critical", "Operator",
                tags=["priority", "reviewed"], operation_id="edit-roundtrip",
            )
            reopened = self._store(root)
            saved = reopened.get_person(person.person_id)
            self.assertEqual(saved.name, "Asha Rao")
            self.assertEqual(saved.metadata["rank"], "Major")
            self.assertEqual(saved.metadata["country"], "India")
            self.assertEqual(saved.metadata["importance"], "Critical")
            self.assertEqual(saved.metadata["added_by"], "Operator")
            self.assertEqual(saved.metadata["tags"], ["priority", "reviewed"])
            self.assertEqual(reopened.get_person_note(person.person_id).content, "General context")

    def test_profile_preferences_and_face_lifecycle_writes_are_journaled(self) -> None:
        actor = {"user_id": "operator-1", "username": "operator"}
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Original")
            embedding = store.add_embedding(person.person_id, (1.0, 0.0), 0.9)

            store.update_person_profile(
                person.person_id, "Renamed", "Officer", "India", "High", "Operator",
                operation_id="profile-op", actor=actor, source="test",
            )
            store.update_person_preferences(
                person.person_id, "preferences-op", favorite=True,
                actor=actor, source="test",
            )
            store.delete_embedding(
                embedding.embedding_id, "delete-face-op", actor, "test",
            )
            store.restore_deleted_embedding(
                embedding.embedding_id, "restore-face-op", actor, "test",
            )
            store.delete_embedding(
                embedding.embedding_id, "delete-face-again-op", actor, "test",
            )
            store.permanently_delete_embedding(
                embedding.embedding_id, "purge-face-op", actor, "test",
            )
            expired = store.add_embedding(person.person_id, (0.0, 1.0), 0.8)
            store.delete_embedding(expired.embedding_id, "delete-expired-op", actor, "test")
            store.purge_expired_deleted_embeddings(
                [expired.embedding_id], "purge-expired-op", "9999-01-01T00:00:00+00:00",
                actor, "test",
            )

            self._assert_committed(store, "profile-op", "identity.profile.update")
            self._assert_committed(store, "preferences-op", "identity.preferences.update")
            self._assert_committed(store, "delete-face-op", "biometric.face.delete")
            self._assert_committed(store, "restore-face-op", "biometric.face.restore")
            self._assert_committed(store, "purge-face-op", "biometric.face.purge")
            self._assert_committed(store, "purge-expired-op", "biometric.face.purge-expired")
            self.assertEqual(store.get_person(person.person_id).name, "Renamed")

    def test_profile_failure_rolls_back_data_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Original")

            with patch(
                "sentriface.storage.sqlite_store._transition_journal_operation",
                side_effect=RuntimeError("forced journal failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "forced journal failure"):
                    store.update_person_profile(
                        person.person_id, "Not committed", None, None, None, "Operator",
                        operation_id="failed-profile-op",
                    )

            self.assertEqual(store.get_person(person.person_id).name, "Original")
            self.assertIsNone(store.get_operation("failed-profile-op"))
            self.assertEqual(store.list_person_changes(person.person_id), [])

    def test_face_failure_rolls_back_data_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Person")
            embedding = store.add_embedding(person.person_id, (1.0, 0.0), 0.9)

            with patch(
                "sentriface.storage.sqlite_store._transition_journal_operation",
                side_effect=RuntimeError("forced journal failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "forced journal failure"):
                    store.delete_embedding(embedding.embedding_id, "failed-face-op")

            self.assertIsNone(store.get_operation("failed-face-op"))
            self.assertEqual(
                [item.embedding_id for item in store.list_embeddings()],
                [embedding.embedding_id],
            )


if __name__ == "__main__":
    unittest.main()
