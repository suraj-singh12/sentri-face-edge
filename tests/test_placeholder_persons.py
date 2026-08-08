from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sentriface.components.linear_index import LinearFaceIndex
from sentriface.storage.sqlite_store import SQLiteIdentityStore


class PlaceholderPersonTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def test_creation_display_data_duplicate_names_and_empty_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_placeholder_person(
                "  Alex Morgan  ",
                {"rank": "Visitor"},
                "Operator",
                "placeholder-create-1",
            )

            self.assertEqual(person.name, "Alex Morgan")
            self.assertEqual(person.enrollment_status, "placeholder")
            summary = store.list_persons()[0]
            self.assertEqual(summary.embedding_count, 0)
            self.assertEqual(summary.person.metadata["rank"], "Visitor")
            self.assertEqual(store.list_embeddings_for_person(person.person_id), [])
            index = LinearFaceIndex()
            index.rebuild(store.list_embeddings())
            self.assertEqual(index.search((1.0, 0.0), 5), [])

            with self.assertRaisesRegex(KeyError, "placeholder with this name"):
                store.create_placeholder_person(
                    "alex morgan",
                    {},
                    "Operator",
                    "placeholder-create-2",
                )
            enrolled = store.create_person("Alex Morgan")
            self.assertNotEqual(enrolled.person_id, person.person_id)
            creation = store.list_person_changes(person.person_id)[0]
            self.assertEqual(creation.new_status, "placeholder")

    def test_first_embedding_enrolls_person_and_releases_placeholder_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_placeholder_person(
                "Future Visitor",
                {},
                "Operator",
                "placeholder-enroll-1",
            )

            embedding = store.add_embedding(person.person_id, (1.0, 0.0), 0.9)

            self.assertEqual(store.get_person(person.person_id).enrollment_status, "enrolled")
            index = LinearFaceIndex()
            index.rebuild(store.list_embeddings())
            self.assertEqual(index.search((1.0, 0.0), 1)[0].embedding_id, embedding.embedding_id)
            changes = store.list_person_changes(person.person_id)
            self.assertTrue(any(
                change.previous_status == "placeholder" and change.new_status == "enrolled"
                for change in changes
            ))
            replacement = store.create_placeholder_person(
                "future visitor",
                {},
                "Operator",
                "placeholder-enroll-2",
            )
            self.assertEqual(replacement.enrollment_status, "placeholder")

    def test_placeholder_uses_existing_archive_and_deletion_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_placeholder_person(
                "Temporary Identity",
                {},
                "Operator",
                "placeholder-delete-1",
            )

            store.archive_person(person.person_id, "placeholder-archive-1")
            self.assertIsNone(store.get_person(person.person_id))
            result = store.permanently_delete_person(
                person.person_id,
                "placeholder-purge-1",
            )
            self.assertEqual(result["deleted_embeddings"], 0)
            self.assertIsNone(store.get_person(person.person_id, include_archived=True))


if __name__ == "__main__":
    unittest.main()
