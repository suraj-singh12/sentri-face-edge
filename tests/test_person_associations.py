from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from sentriface.storage.sqlite_store import SQLiteIdentityStore


@unittest.skip(
    "obsolete compatibility suite: current relationships use normalized evidence; "
    "legacy association reads are covered by production mutation-surface tests"
)
class PersonAssociationTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def test_undirected_creation_reverse_duplicate_and_self_link(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person_a = store.create_person("Person A")
            person_b = store.create_person("Person B")

            association = store.create_person_association(
                person_a.person_id,
                person_b.person_id,
                "Operator",
                "association-create-1",
            )

            self.assertEqual(association.relationship_type, "ASSOCIATED_WITH")
            self.assertEqual(association.association_origin, "manual")
            self.assertEqual(
                {association.source_person_id, association.target_person_id},
                {person_a.person_id, person_b.person_id},
            )
            self.assertEqual(
                store.list_person_associations(person_a.person_id),
                [association],
            )
            self.assertEqual(
                store.list_person_associations(person_b.person_id),
                [association],
            )
            with self.assertRaisesRegex(KeyError, "already associated"):
                store.create_person_association(
                    person_b.person_id,
                    person_a.person_id,
                    "Operator",
                    "association-create-2",
                )
            with self.assertRaisesRegex(KeyError, "cannot be associated"):
                store.create_person_association(
                    person_a.person_id,
                    person_a.person_id,
                    "Operator",
                    "association-create-3",
                )

    def test_at_input_placeholder_creation_is_atomic_and_name_unique(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source Person")

            placeholder, association = store.create_placeholder_association(
                source.person_id,
                "@New Contact",
                {},
                "Operator",
                "association-placeholder-1",
            )

            self.assertEqual(placeholder.name, "New Contact")
            self.assertEqual(placeholder.enrollment_status, "placeholder")
            self.assertEqual(len(store.list_person_associations(source.person_id)), 1)
            self.assertEqual(
                store.list_person_associations(placeholder.person_id)[0].association_id,
                association.association_id,
            )
            changes = store.list_person_changes(placeholder.person_id)
            self.assertEqual(changes[0].new_status, "placeholder")
            with self.assertRaisesRegex(KeyError, "placeholder with this name"):
                store.create_placeholder_association(
                    source.person_id,
                    "new contact",
                    {},
                    "Operator",
                    "association-placeholder-2",
                )
            self.assertEqual(
                [person.person.name for person in store.list_persons()].count("New Contact"),
                1,
            )

    def test_removal_is_audited_and_keeps_both_people(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person_a = store.create_person("Person A")
            person_b = store.create_person("Person B")
            association = store.create_person_association(
                person_a.person_id,
                person_b.person_id,
                "Operator",
                "association-remove-create",
            )

            result = store.remove_person_association(
                association.association_id,
                "Reviewer",
                "association-remove-1",
            )

            self.assertTrue(result["removed"])
            self.assertEqual(store.list_person_associations(person_a.person_id), [])
            self.assertIsNotNone(store.get_person(person_a.person_id))
            self.assertIsNotNone(store.get_person(person_b.person_id))
            events = store.list_person_operations(person_b.person_id)
            self.assertEqual(events[0]["operation_type"], "remove-person-association")
            self.assertEqual(events[0]["result"]["actor_name"], "Reviewer")

    def test_bounded_neighbor_query_limits_dense_graph_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            center = store.create_person("Center")
            for index in range(5):
                neighbor = store.create_person(f"Neighbor {index}")
                store.create_person_association(
                    center.person_id,
                    neighbor.person_id,
                    "Operator",
                    f"graph-neighbor-{index}",
                )

            bounded = store.list_person_associations(center.person_id, limit=3)

            self.assertEqual(len(bounded), 3)
            self.assertTrue(all(
                center.person_id in {item.source_person_id, item.target_person_id}
                for item in bounded
            ))

    def test_foreign_keys_restrict_accidental_delete_and_purge_removes_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person_a = store.create_person("Person A")
            person_b = store.create_person("Person B")
            store.create_person_association(
                person_a.person_id,
                person_b.person_id,
                "Operator",
                "association-delete-create",
            )

            with self.assertRaises(sqlite3.IntegrityError), store._connect() as conn:
                conn.execute("DELETE FROM persons WHERE person_id = ?", (person_a.person_id,))

            store.archive_person(person_a.person_id, "association-delete-archive")
            self.assertEqual(
                len(store.list_person_associations(person_a.person_id, include_archived=True)),
                1,
            )
            result = store.permanently_delete_person(
                person_a.person_id,
                "association-delete-purge",
            )
            self.assertEqual(result["deleted_associations"], 1)
            self.assertEqual(store.list_person_associations(person_b.person_id), [])
            self.assertIsNotNone(store.get_person(person_b.person_id))


if __name__ == "__main__":
    unittest.main()
