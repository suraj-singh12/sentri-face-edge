from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from sentriface.contracts import IdentityStore
from sentriface.engine import DomainWorkflowUnavailableError, FaceEngine
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.identity_service import IdentityService
from sentriface.storage.sqlite_store import SQLiteIdentityStore


class ProductionMutationSurfaceTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def test_identified_no_face_creation_is_journaled_and_has_no_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = IdentityService(store).create_identified_person(
                "Context Person",
                {"context": "Known witness"},
                "create-context-person",
                actor={"user_id": "operator-1", "username": "operator"},
                source="test",
            )

            self.assertEqual(person.lifecycle_status, "ACTIVE")
            self.assertEqual(person.identity_status, "IDENTIFIED")
            self.assertEqual(person.biometric_status, "NO_FACE")
            self.assertEqual(store.list_embeddings_for_person(person.person_id), [])
            operation = store.get_operation("create-context-person")
            self.assertEqual(operation["operation_type"], "identity.create")
            self.assertEqual(operation["status"], "COMMITTED")
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM person_operations").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM person_associations").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM relationship_evidence").fetchone()[0], 0)

    def test_person_creation_and_note_save_are_separate_domain_commits(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            identities = IdentityService(store)
            owner = identities.create_identified_person("Owner", {}, "create-owner")
            mentioned = identities.create_identified_person("Mentioned", {}, "create-mentioned")
            graph = GlobalIdentityGraphService(store)

            self.assertEqual(graph.get_connection_evidence(owner.person_id, mentioned.person_id), [])
            note = graph.create_note(
                owner.person_id,
                "Explicit @Mentioned",
                "save-note",
                mentioned_person_ids=[mentioned.person_id],
            )

            evidence = graph.get_connection_evidence(owner.person_id, mentioned.person_id)
            self.assertEqual(note.mentioned_person_ids, (mentioned.person_id,))
            self.assertEqual(len(evidence), 1)
            self.assertEqual(evidence[0].evidence_type, "NOTE_REFERENCE")
            self.assertEqual(evidence[0].source_entity_type, "NOTE")
            self.assertTrue(evidence[0].source_entity_id)

    def test_obsolete_mutations_are_not_on_production_contract_or_engine(self) -> None:
        for method_name in (
            "create_person",
            "add_embedding",
            "confirm_pending_addition",
            "confirm_init_faces_atomic",
            "create_person_association",
            "create_placeholder_association",
            "remove_person_association",
            "add_recognition_detail",
            "delete_person",
        ):
            self.assertFalse(hasattr(IdentityStore, method_name), method_name)
        for method_name in (
            "confirm_new_person",
            "confirm_existing_person",
            "confirm_pending_as_new_person",
            "confirm_pending_as_existing_person",
            "create_person_association",
            "create_placeholder_association",
            "remove_person_association",
            "add_recognition_detail",
        ):
            self.assertFalse(hasattr(FaceEngine, method_name), method_name)
        self.assertFalse(hasattr(IdentityStore, "set_canonical_person_id"))
        self.assertFalse(hasattr(SQLiteIdentityStore, "set_canonical_person_id"))
        self.assertFalse(hasattr(SQLiteIdentityStore, "rename_person"))

    def test_restore_routes_only_bounded_session_attributed_input_to_p12(self) -> None:
        api_source = (Path(__file__).parents[1] / "src/sentriface/api_server.py").read_text()
        restore_branch = api_source.split(
            'if parsed.path == "/api/backups/restore":', 1,
        )[1].split('if parsed.path == "/api/backups/import":', 1)[0]
        self.assertIn("_validate_backup_restore_payload(payload)", restore_branch)
        self.assertIn("self.server.backups.restore_backup(", restore_branch)
        self.assertIn("actor=self._operation_actor()", restore_branch)
        self.assertNotIn("allow_incomplete", restore_branch)
        self.assertNotIn('payload.get("actor")', restore_branch)

    def test_cli_rename_routes_through_engine_domain_service(self) -> None:
        cli_source = (Path(__file__).parents[1] / "src/sentriface/cli.py").read_text()
        rename_branch = cli_source.split('if args.command == "rename-person":', 1)[1].split(
            'if args.command == "delete-person":', 1,
        )[0]
        self.assertIn("engine.rename_person(", rename_branch)
        self.assertNotIn("identity_store.", rename_branch)
        self.assertNotIn("engine.store.", rename_branch)

    def test_move_face_adapters_route_through_p7_service(self) -> None:
        root = Path(__file__).parents[1]
        api_source = (root / "src/sentriface/api_server.py").read_text()
        cli_source = (root / "src/sentriface/cli.py").read_text()
        self.assertIn("self.server.engine.move_embedding(", api_source)
        self.assertIn("engine.move_embedding(", cli_source)
        self.assertNotIn("Move Face is temporarily unavailable until P7", api_source)
        self.assertTrue(hasattr(SQLiteIdentityStore, "_legacy_move_embedding"))
        self.assertFalse(hasattr(IdentityStore, "_legacy_move_embedding"))

    def test_merge_uses_the_normalized_store_boundary_and_undo_remains_gated(self) -> None:
        self.assertTrue(hasattr(IdentityStore, "preview_identity_merge"))
        self.assertTrue(hasattr(IdentityStore, "execute_identity_merge"))
        engine = object.__new__(FaceEngine)
        with self.assertRaisesRegex(DomainWorkflowUnavailableError, "P8"):
            engine.undo_merge_persons("merge-op", "undo-op")

    def test_authoritative_engine_mutations_require_operation_and_actor(self) -> None:
        engine = object.__new__(FaceEngine)
        with self.assertRaisesRegex(ValueError, "Operation ID"):
            engine.merge_persons("source", "target", None, actor={"user_id": "operator"})
        with self.assertRaisesRegex(ValueError, "actor identity"):
            engine.merge_persons("source", "target", "merge-op", actor=None)
        api_source = (Path(__file__).parents[1] / "src/sentriface/api_server.py").read_text()
        self.assertNotIn("def _optional_operation_id", api_source)
        self.assertIn('_operation_id(payload)', api_source)

    def test_historical_legacy_associations_remain_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            source_person_id, target_person_id = sorted(
                (first.person_id, second.person_id),
            )
            with sqlite3.connect(store.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO person_associations(
                        association_id, source_person_id, target_person_id,
                        relationship_type, created_at, updated_at, created_by,
                        association_origin
                    ) VALUES ('legacy-link', ?, ?, 'ASSOCIATED_WITH',
                              '2026-01-01T00:00:00+00:00',
                              '2026-01-01T00:00:00+00:00', 'Legacy', 'manual')
                    """,
                    (source_person_id, target_person_id),
                )

            associations = store.list_person_associations(first.person_id)
            self.assertEqual([item.association_id for item in associations], ["legacy-link"])


if __name__ == "__main__":
    unittest.main()
