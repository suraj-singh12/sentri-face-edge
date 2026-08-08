from __future__ import annotations

import tempfile
import unittest
import sqlite3
from pathlib import Path

from sentriface.storage.sqlite_store import SQLiteIdentityStore


class PersonNotesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = SQLiteIdentityStore(Path(self.tempdir.name) / "identity.sqlite3", embedding_dim=3)
        self.store.initialize()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_create_read_update_clear_unchanged_and_history(self) -> None:
        person = self.store.create_person("Notes Person", notes="  first\n  line  ")
        self.assertEqual(self.store.get_person(person.person_id).notes, "first\n  line")

        changed, updated, change = self.store.update_person_notes(
            person.person_id, "  next\n\n  paragraph  ", "first\n  line", "Operator", "notes-1",
        )
        self.assertTrue(changed)
        self.assertEqual(updated.notes, "next\n\n  paragraph")
        self.assertEqual(change.previous_notes, "first\n  line")
        self.assertEqual(change.new_notes, "next\n\n  paragraph")
        self.assertEqual(change.editor_name, "Operator")
        self.assertTrue(change.created_at)

        changed, unchanged, no_change = self.store.update_person_notes(
            person.person_id, "next\n\n  paragraph", "next\n\n  paragraph", "Operator", "notes-2",
        )
        self.assertFalse(changed)
        self.assertEqual(unchanged.notes, "next\n\n  paragraph")
        self.assertIsNone(no_change)
        self.assertEqual(len(self.store.list_person_changes(person.person_id)), 1)

        changed, cleared, clear_change = self.store.update_person_notes(
            person.person_id, " \n ", "next\n\n  paragraph", "Operator", "notes-3",
        )
        self.assertTrue(changed)
        self.assertEqual(cleared.notes, "")
        self.assertEqual(clear_change.new_notes, "")
        self.assertEqual(len(self.store.list_person_changes(person.person_id)), 2)

    def test_stale_and_deleted_person_updates_are_rejected_without_history(self) -> None:
        person = self.store.create_person("Concurrent", notes="current")
        with self.assertRaisesRegex(KeyError, "changed elsewhere"):
            self.store.update_person_notes(
                person.person_id, "replacement", "stale", "Operator", "notes-stale",
            )
        self.assertEqual(self.store.get_person(person.person_id).notes, "current")
        self.assertEqual(self.store.list_person_changes(person.person_id), [])

        self.store.archive_person(person.person_id, "archive-notes")
        with self.assertRaisesRegex(KeyError, "no longer exists"):
            self.store.update_person_notes(
                person.person_id, "replacement", "current", "Operator", "notes-deleted",
            )

    def test_sighting_notes_are_independent_from_profile_notes(self) -> None:
        person = self.store.create_person("Sighting Notes", notes="profile note")
        embedding = self.store.add_embedding(person.person_id, (1.0, 0.0, 0.0), 0.9)
        detail = self.store.add_recognition_detail(
            embedding.embedding_id, person.person_id, "image-1", person.name, "existing",
            "2026-08-08", "10:30", "Gate A", 1, "Visit", notes="  sighting note  ",
        )
        self.assertEqual(detail.notes, "sighting note")
        self.assertEqual(self.store.list_recognition_details_for_person(person.person_id)[0].notes, "sighting note")
        self.assertEqual(self.store.get_person(person.person_id).notes, "profile note")

    def test_mentions_create_automatic_associations_and_manual_link_upgrades_origin(self) -> None:
        owner = self.store.create_person("Owner")
        mentioned = self.store.create_person("Mentioned Person")
        changed, _, _ = self.store.update_person_notes(
            owner.person_id,
            "Met with @Mentioned Person today",
            "",
            "Operator",
            "notes-mention",
            [mentioned.person_id],
        )
        self.assertTrue(changed)
        association = self.store.list_person_associations(owner.person_id)[0]
        self.assertEqual(association.association_origin, "automatic_mention")

        upgraded = self.store.create_person_association(
            mentioned.person_id, owner.person_id, "Operator", "manual-upgrade",
        )
        self.assertEqual(upgraded.association_id, association.association_id)
        self.assertEqual(upgraded.association_origin, "manual")

    def test_sighting_mentions_also_create_automatic_associations(self) -> None:
        owner = self.store.create_person("Observed")
        mentioned = self.store.create_person("Companion")
        embedding = self.store.add_embedding(owner.person_id, (0.0, 1.0, 0.0), 0.9)
        self.store.add_recognition_detail(
            embedding.embedding_id,
            owner.person_id,
            "image-mention",
            owner.name,
            "existing",
            "2026-08-08",
            "11:00",
            "Lobby",
            2,
            "Visit",
            notes="Seen with @Companion",
        )
        association = self.store.list_person_associations(owner.person_id)[0]
        self.assertEqual(association.association_origin, "automatic_mention")

    def test_duplicate_names_require_an_explicit_suggestion_selection(self) -> None:
        owner = self.store.create_person("Duplicate Owner")
        first = self.store.create_person("Same Name")
        second = self.store.create_person("Same Name")
        self.store.update_person_notes(
            owner.person_id, "With @Same Name", "", "Operator", "duplicate-unselected",
        )
        self.assertEqual(self.store.list_person_associations(owner.person_id), [])

        self.store.update_person_notes(
            owner.person_id,
            "With @Same Name.",
            "With @Same Name",
            "Operator",
            "duplicate-selected",
            [second.person_id],
        )
        association = self.store.list_person_associations(owner.person_id)[0]
        self.assertEqual(
            {association.source_person_id, association.target_person_id},
            {owner.person_id, second.person_id},
        )
        self.assertNotIn(first.person_id, {association.source_person_id, association.target_person_id})

    def test_v14_migration_adds_empty_notes_without_changing_existing_data(self) -> None:
        path = Path(self.tempdir.name) / "legacy.sqlite3"
        with sqlite3.connect(path) as conn:
            conn.executescript("""
                CREATE TABLE persons (
                    person_id TEXT PRIMARY KEY, name TEXT NOT NULL, metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL, deleted_at TEXT, enrollment_status TEXT NOT NULL
                );
                CREATE TABLE recognition_details (
                    detail_id TEXT PRIMARY KEY, embedding_id TEXT NOT NULL, person_id TEXT NOT NULL,
                    image_id TEXT NOT NULL, image_path TEXT, name TEXT NOT NULL, decision TEXT NOT NULL,
                    seen_date TEXT NOT NULL, seen_time TEXT NOT NULL, place_seen TEXT NOT NULL,
                    individual_count INTEGER NOT NULL, event_occasion TEXT NOT NULL,
                    rank TEXT, country TEXT, importance TEXT, added_by TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE person_change_history (
                    change_id TEXT PRIMARY KEY, person_id TEXT NOT NULL,
                    previous_name TEXT NOT NULL, new_name TEXT NOT NULL,
                    previous_rank TEXT, new_rank TEXT, previous_country TEXT, new_country TEXT,
                    previous_importance TEXT, new_importance TEXT, previous_status TEXT, new_status TEXT,
                    editor_name TEXT NOT NULL, created_at TEXT NOT NULL
                );
                INSERT INTO persons VALUES ('legacy', 'Legacy Person', '{"rank":"Staff"}', '2025-01-01', NULL, 'enrolled');
                PRAGMA user_version = 14;
            """)
        store = SQLiteIdentityStore(path, embedding_dim=3)
        store.initialize()
        legacy = store.get_person("legacy")
        self.assertEqual(legacy.name, "Legacy Person")
        self.assertEqual(legacy.metadata["rank"], "Staff")
        self.assertEqual(legacy.notes, "")
        with sqlite3.connect(path) as conn:
            self.assertIn("notes", {row[1] for row in conn.execute("PRAGMA table_info(persons)")})
            self.assertIn("notes", {row[1] for row in conn.execute("PRAGMA table_info(recognition_details)")})
            self.assertIn("previous_notes", {row[1] for row in conn.execute("PRAGMA table_info(person_change_history)")})


if __name__ == "__main__":
    unittest.main()
