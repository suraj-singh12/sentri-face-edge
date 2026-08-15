from __future__ import annotations

import json
import hashlib
import shutil
import sqlite3
from contextlib import closing
import tempfile
import unittest
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sentriface.backup_service import (
    BackupError,
    BackupService,
    _with_manifest_fingerprint,
)
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.integrity import ReadOnlyIntegrityChecker
from sentriface.secure_files import ProtectedFileError, authenticate_protected_file, write_protected_bytes
from sentriface.storage.sqlite_store import (
    SCHEMA_VERSION,
    SQLiteIdentityStore,
    _schema_migrations,
    migrate_staged_database,
)


class BackupServiceTest(unittest.TestCase):
    def test_successful_backup_creation_writes_verified_snapshot_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = self._service(db_path, root / "backups")

            record = service.create_backup()

            backup_dir = root / "backups" / record.backup_id
            backup_db = backup_dir / "sentriface.db"
            metadata = json.loads((backup_dir / "backup.json").read_text(encoding="utf-8"))
            self.assertTrue(backup_db.exists())
            self.assertTrue(record.verified)
            self.assertEqual(record.people_count, 1)
            self.assertEqual(record.embedding_count, 1)
            self.assertEqual(record.database_version, SCHEMA_VERSION)
            self.assertEqual(metadata["backup_id"], record.backup_id)
            self.assertEqual(metadata["people_count"], 1)
            self.assertEqual(metadata["embedding_count"], 1)
            self.assertEqual(metadata["database_size_bytes"], backup_db.stat().st_size)
            self.assertTrue(service.verify_backup(record.backup_id))
            self.assertTrue(record.portable)
            self.assertTrue(record.complete)
            self.assertEqual(record.format_version, 3)
            self.assertTrue(record.restorable)
            self.assertEqual(record.integrity_status, "PASS")

    def test_duplicate_timestamp_gets_unique_backup_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = self._service(db_path, root / "backups")

            first = service.create_backup()
            second = service.create_backup()

            self.assertEqual(first.backup_id, "backup_2026-07-15_22-14-08")
            self.assertEqual(second.backup_id, "backup_2026-07-15_22-14-08_01")

    def test_named_operation_backup_is_idempotent_and_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = self._service(db_path, root / "backups")

            first = service.create_backup(
                reason="Before face permanent delete / Person A",
                operation_id="operation-123",
            )
            second = service.create_backup(
                reason="A retry must not create another snapshot",
                operation_id="operation-123",
            )

            self.assertEqual(first, second)
            self.assertEqual(len(service.list_backups()), 1)
            self.assertEqual(first.reason, "Before face permanent delete / Person A")
            self.assertEqual(first.operation_id, "operation-123")
            self.assertIn("before-face-permanent-delete-person-a", first.backup_id)
            metadata = json.loads(
                (root / "backups" / first.backup_id / "backup.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["operation_id"], "operation-123")
            self.assertEqual(metadata["reason"], "Before face permanent delete / Person A")

    def test_named_backup_reason_is_sanitized_inside_managed_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = self._service(db_path, root / "backups")

            record = service.create_backup(reason="../../Before Delete 💥")

            self.assertRegex(record.backup_id, r"^backup_.+_before-delete$")
            self.assertEqual((root / "backups" / record.backup_id).parent, root / "backups")

    def test_incomplete_backup_directory_is_removed_when_verification_fails(self) -> None:
        class FailingVerifyBackupService(BackupService):
            def verify_backup(self, backup_id: str) -> bool:
                return False

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = FailingVerifyBackupService(db_path, root / "backups", now=self._fixed_now)

            with self.assertRaises(BackupError):
                service.create_backup()

            self.assertFalse((root / "backups" / "backup_2026-07-15_22-14-08").exists())

    def test_listing_backups_returns_newest_first(self) -> None:
        times = iter([
            datetime(2026, 7, 12, 18, 30, 41, tzinfo=timezone.utc),
            datetime(2026, 7, 15, 22, 14, 8, tzinfo=timezone.utc),
        ])

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = BackupService(db_path, root / "backups", now=lambda: next(times))
            older = service.create_backup()
            newer = service.create_backup()

            backups = service.list_backups()

            self.assertEqual([item.backup_id for item in backups], [newer.backup_id, older.backup_id])

    def test_retention_keeps_latest_ten_backups(self) -> None:
        counter = {"value": 0}

        def next_time() -> datetime:
            counter["value"] += 1
            return datetime(2026, 7, 15, 22, 0, counter["value"], tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = BackupService(db_path, root / "backups", retention_limit=10, now=next_time)

            created = [service.create_backup().backup_id for _ in range(12)]

            remaining = [item.backup_id for item in service.list_backups()]
            self.assertEqual(len(remaining), 10)
            self.assertNotIn(created[0], remaining)
            self.assertNotIn(created[1], remaining)
            self.assertIn(created[-1], remaining)

    def test_invalid_backup_ids_and_traversal_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = self._service(db_path, root / "backups")

            for backup_id in ["../../database.db", "backup_2026-07-15_22-14-08/../../x", "sentriface.db"]:
                with self.subTest(backup_id=backup_id):
                    with self.assertRaises(BackupError):
                        service.delete_backup(backup_id)

    def test_delete_backup_removes_only_managed_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = self._service(db_path, root / "backups")
            record = service.create_backup()

            service.delete_backup(record.backup_id)

            self.assertFalse((root / "backups" / record.backup_id).exists())
            self.assertTrue(db_path.exists())

    def test_portable_backup_captures_deduplicated_referenced_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            source, crop, sighting = self._seed_database_with_media(db_path, root)
            crop.write_bytes(source.read_bytes())
            service = self._service(db_path, root / "data" / "backups")

            record = service.create_backup()
            backup_path = service._backup_path(record.backup_id)
            metadata = json.loads((backup_path / "backup.json").read_text(encoding="utf-8"))

            self.assertTrue(record.complete)
            self.assertEqual(record.reference_count, 3)
            self.assertEqual(record.file_count, 2)
            self.assertEqual(record.missing_file_count, 0)
            self.assertEqual(len(metadata["path_references"]), 3)
            self.assertEqual(len(metadata["assets"]), 2)
            for asset in metadata["assets"]:
                stored = backup_path / asset["archive_path"]
                self.assertTrue(stored.exists())
                self.assertEqual(
                    hashlib.sha256(stored.read_bytes()).hexdigest(),
                    asset["sha256"],
                )
            source.unlink()
            crop.unlink()
            sighting.unlink()
            self.assertTrue(service.verify_backup(record.backup_id))

    def test_missing_referenced_file_is_reported_without_faking_completeness(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            source, _, _ = self._seed_database_with_media(db_path, root)
            source.unlink()
            service = self._service(db_path, root / "data" / "backups")

            record = service.create_backup()

            self.assertFalse(record.complete)
            self.assertEqual(record.missing_file_count, 1)
            self.assertTrue(record.verified)
            with self.assertRaisesRegex(BackupError, "incomplete"):
                service.restore_backup(record.backup_id, str(uuid.uuid4()))

    def test_tampered_database_or_asset_fails_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            self._seed_database_with_media(db_path, root)
            service = self._service(db_path, root / "data" / "backups")
            record = service.create_backup()
            backup_path = service._backup_path(record.backup_id)
            metadata = json.loads((backup_path / "backup.json").read_text(encoding="utf-8"))
            asset = backup_path / metadata["assets"][0]["archive_path"]
            original = asset.read_bytes()
            asset.write_bytes(original + b"tampered")

            with self.assertRaisesRegex(BackupError, "size mismatch"):
                service.verify_backup(record.backup_id)

            asset.write_bytes(original)
            backup_db = service._database_path(record.backup_id)
            backup_db.write_bytes(b"not sqlite")
            with self.assertRaises(BackupError):
                service.verify_backup(record.backup_id)

    def test_export_import_round_trip_remains_verified_and_restorable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_db = root / "source" / "sentriface.db"
            self._seed_database_with_media(source_db, root / "source-fixtures")
            source_service = self._service(source_db, root / "source" / "backups")
            original = source_service.create_backup(reason="portable-round-trip")
            archive = source_service.export_backup(
                original.backup_id,
                root / "exports" / "portable",
            )

            target_db = root / "target" / "sentriface.db"
            self._seed_database(target_db)
            target_service = self._service(target_db, root / "target" / "backups")
            imported = target_service.import_backup(archive)

            self.assertTrue(imported.complete)
            self.assertTrue(imported.portable)
            self.assertEqual(imported.file_count, original.file_count)
            self.assertTrue(target_service.verify_backup(imported.backup_id))
            result = target_service.restore_backup(
                imported.backup_id,
                str(uuid.uuid4()),
            )
            self.assertTrue(result["restored"])
            with closing(sqlite3.connect(target_db)) as conn, conn:
                restored_paths = conn.execute(
                    "SELECT source_image, crop_path FROM embeddings"
                ).fetchone()
            for restored_path in restored_paths:
                self.assertTrue(Path(restored_path).is_file())
                self.assertIn("restored-media", Path(restored_path).parts)

    def test_restore_replaces_database_rewrites_paths_and_creates_safety_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            source, crop, sighting = self._seed_database_with_media(db_path, root)
            original_bytes = {
                source.name: source.read_bytes(),
                crop.name: crop.read_bytes(),
                sighting.name: sighting.read_bytes(),
            }
            service = self._service(db_path, root / "data" / "backups")
            backup = service.create_backup(reason="known-good")
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute("UPDATE persons SET name = 'Changed after backup'")
            reloads = []

            result = service.restore_backup(
                backup.backup_id,
                str(uuid.uuid4()),
                reload_callback=lambda: reloads.append("reloaded"),
            )

            self.assertEqual(reloads, ["reloaded"])
            self.assertTrue(result["restored"])
            self.assertNotEqual(result["safety_backup_id"], backup.backup_id)
            self.assertTrue(service.verify_backup(result["safety_backup_id"]))
            with closing(sqlite3.connect(db_path)) as conn, conn:
                self.assertEqual(conn.execute("SELECT name FROM persons").fetchone()[0], "Backup Person")
                paths = [
                    *conn.execute("SELECT source_image, crop_path FROM embeddings").fetchone(),
                    conn.execute("SELECT image_path FROM recognition_details").fetchone()[0],
                ]
            for path in paths:
                restored = Path(path)
                self.assertTrue(restored.is_file())
                self.assertIn("restored-media", restored.parts)
            self.assertEqual({Path(path).read_bytes() for path in paths}, set(original_bytes.values()))

    def test_every_database_image_path_column_is_captured_and_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            db_path.parent.mkdir(parents=True)
            shared_image = root / "shared.jpg"
            shared_image.write_bytes(b"shared-image")
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE embeddings(embedding_id TEXT PRIMARY KEY, source_image TEXT, crop_path TEXT);
                    CREATE TABLE pending_additions(pending_id TEXT PRIMARY KEY, source_image TEXT, crop_path TEXT);
                    CREATE TABLE init_faces(init_face_id TEXT PRIMARY KEY, source_image TEXT, crop_path TEXT);
                    CREATE TABLE recognition_details(detail_id TEXT PRIMARY KEY, image_path TEXT);
                    CREATE TABLE observation_media(observation_id TEXT, media_id TEXT, media_path TEXT, PRIMARY KEY(observation_id, media_id));
                    CREATE TABLE photo_reviews(review_id TEXT PRIMARY KEY, media_path TEXT);
                    """
                )
                conn.execute("INSERT INTO embeddings VALUES ('e1', ?, ?)", (str(shared_image), str(shared_image)))
                conn.execute("INSERT INTO pending_additions VALUES ('p1', ?, ?)", (str(shared_image), str(shared_image)))
                conn.execute("INSERT INTO init_faces VALUES ('i1', ?, ?)", (str(shared_image), str(shared_image)))
                conn.execute("INSERT INTO recognition_details VALUES ('d1', ?)", (str(shared_image),))
                conn.execute("INSERT INTO observation_media VALUES ('o1', 'm1', ?)", (str(shared_image),))
                conn.execute("INSERT INTO photo_reviews VALUES ('r1', ?)", (str(shared_image),))
            service = self._service(db_path, root / "data" / "backups")

            backup = service.create_backup()
            manifest = json.loads(
                (service._backup_path(backup.backup_id) / "backup.json").read_text(encoding="utf-8")
            )
            registry_ids = {item["registry_id"] for item in manifest["path_references"]}

            self.assertEqual(backup.reference_count, 9)
            self.assertEqual(backup.file_count, 1)
            self.assertEqual(
                registry_ids,
                {
                    "embeddings.source_image", "embeddings.crop_path",
                    "pending_additions.source_image", "pending_additions.crop_path",
                    "init_faces.source_image", "init_faces.crop_path",
                    "recognition_details.image_path", "observation_media.media_path",
                    "photo_reviews.media_path",
                },
            )

    def test_manifest_cannot_silently_omit_a_database_file_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            self._seed_database_with_media(db_path, root)
            service = self._service(db_path, root / "data" / "backups")
            backup = service.create_backup()
            metadata_path = service._backup_path(backup.backup_id) / "backup.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["path_references"] = metadata["path_references"][1:]
            metadata["reference_count"] -= 1
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            with self.assertRaisesRegex(BackupError, "fingerprint|closure"):
                service.verify_backup(backup.backup_id)

    def test_future_manifest_version_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            self._seed_database(db_path)
            service = self._service(db_path, root / "data" / "backups")
            backup = service.create_backup()
            metadata_path = service._backup_path(backup.backup_id) / "backup.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["format_version"] = 4
            metadata["manifest_version"] = 4
            metadata_path.write_text(
                json.dumps(_with_manifest_fingerprint(metadata)), encoding="utf-8"
            )

            with self.assertRaisesRegex(BackupError, "Unsupported portable backup format"):
                service.verify_backup(backup.backup_id)

    def test_manifest_rejects_unknown_and_duplicate_registry_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            self._seed_database_with_media(db_path, root)
            service = self._service(db_path, root / "data" / "backups")
            backup = service.create_backup()
            metadata_path = service._backup_path(backup.backup_id) / "backup.json"
            original = json.loads(metadata_path.read_text(encoding="utf-8"))
            for mutate, message in (
                (lambda value: value["path_references"][0].update(
                    {"registry_id": "client_controlled.table"}
                ), "registry-owned"),
                (lambda value: value["path_references"].append(
                    dict(value["path_references"][0])
                ), "duplicate media binding"),
            ):
                with self.subTest(message=message):
                    metadata = json.loads(json.dumps(original))
                    mutate(metadata)
                    metadata_path.write_text(
                        json.dumps(_with_manifest_fingerprint(metadata)), encoding="utf-8"
                    )
                    with self.assertRaisesRegex(BackupError, message):
                        service.verify_backup(backup.backup_id)
            metadata_path.write_text(json.dumps(original), encoding="utf-8")

    def test_media_change_during_capture_aborts_without_publishing_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            source, _, _ = self._seed_database_with_media(db_path, root)
            service = self._service(db_path, root / "data" / "backups")
            from sentriface import backup_service as backup_module

            real_copy = backup_module.copy_into_protected_storage

            def copy_then_change(source_path, destination, key):
                result = real_copy(source_path, destination, key)
                if Path(source_path).resolve() == source.resolve():
                    source.write_bytes(source.read_bytes() + b"changed")
                return result

            with patch.object(
                backup_module, "copy_into_protected_storage", side_effect=copy_then_change,
            ):
                with self.assertRaisesRegex(BackupError, "changed during backup"):
                    service.create_backup()
            self.assertEqual(service.list_backups(), [])

    def test_manifest_is_bounded_evidence_and_contains_no_secrets_or_raw_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            source, _, _ = self._seed_database_with_media(db_path, root)
            service = self._service(db_path, root / "data" / "backups")
            backup = service.create_backup(reason="ordinary safety backup")
            raw = (service._backup_path(backup.backup_id) / "backup.json").read_text(
                encoding="utf-8"
            )
            self.assertNotIn(str(source), raw)
            for forbidden in ("master_key", "recovery_code", "export_passphrase", "SELECT "):
                self.assertNotIn(forbidden, raw)
            metadata = json.loads(raw)
            self.assertIn("storage_key_id", metadata)
            self.assertNotIn("table", json.dumps(metadata["path_references"]))
            self.assertNotIn("column", json.dumps(metadata["path_references"]))

    def test_protected_media_authentication_detects_corruption_and_wrong_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "protected.bin"
            key = b"k" * 32
            write_protected_bytes(path, b"authenticated media", key)
            self.assertEqual(authenticate_protected_file(path, key), (True, 19))
            with self.assertRaises(ProtectedFileError):
                authenticate_protected_file(path, b"w" * 32)
            damaged = bytearray(path.read_bytes())
            damaged[-1] ^= 1
            path.write_bytes(damaged)
            with self.assertRaises(ProtectedFileError):
                authenticate_protected_file(path, key)

    def test_every_registered_older_schema_migrates_only_on_staged_copy(self) -> None:
        for source_version in range(SCHEMA_VERSION):
            with self.subTest(source_version=source_version), tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / "source.db"
                with closing(sqlite3.connect(source)) as conn, conn:
                    conn.row_factory = sqlite3.Row
                    for migration in _schema_migrations():
                        if migration.to_version > source_version:
                            break
                        migration.apply(conn)
                staged = Path(temp) / "staged.db"
                shutil.copy2(source, staged)
                self.assertEqual(
                    migrate_staged_database(staged),
                    (source_version, SCHEMA_VERSION),
                )
                with closing(sqlite3.connect(source)) as conn:
                    self.assertEqual(
                        conn.execute("PRAGMA user_version").fetchone()[0], source_version,
                    )

    def test_pre_journal_schema_portable_restore_uses_registered_staged_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_db = root / "source" / "sentriface.db"
            source_db.parent.mkdir(parents=True)
            with closing(sqlite3.connect(source_db)) as conn:
                conn.execute("PRAGMA user_version = 0")
            source_service = BackupService(
                source_db,
                root / "source" / "backups",
                now=self._fixed_now,
                supported_database_version=SCHEMA_VERSION,
            )
            old = source_service.create_backup(reason="schema-v0")
            self.assertEqual(old.integrity_status, "PENDING_MIGRATION")
            archive = source_service.export_backup(old.backup_id, root / "schema-v0")

            target_db = root / "target" / "sentriface.db"
            self._seed_database(target_db)
            target_service = BackupService(
                target_db,
                root / "target" / "backups",
                now=self._fixed_now,
                supported_database_version=SCHEMA_VERSION,
            )
            imported = target_service.import_backup(archive)
            result = target_service.restore_backup(imported.backup_id, str(uuid.uuid4()))

            self.assertEqual((result["source_schema"], result["final_schema"]), (0, SCHEMA_VERSION))
            self.assertEqual(ReadOnlyIntegrityChecker(target_db).run().status, "PASS")

    def test_restore_rebuilds_untrusted_graph_and_preserves_source_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            store = SQLiteIdentityStore(db_path, embedding_dim=4)
            store.initialize()
            owner = store.create_person("Owner")
            mentioned = store.create_person("Mentioned")
            note = GlobalIdentityGraphService(store).create_note(
                owner.person_id,
                "Known relationship",
                str(uuid.uuid4()),
                mentioned_person_ids=[mentioned.person_id],
            )
            with closing(sqlite3.connect(db_path)) as conn, conn:
                source_history = conn.execute(
                    "SELECT operation_id, operation_type, status FROM operation_journal ORDER BY operation_id"
                ).fetchall()
                conn.execute("DELETE FROM graph_connections")
            service = self._service(db_path, root / "data" / "backups")
            backup = service.create_backup(reason="projection-drift")
            self.assertEqual(backup.integrity_status, "PROJECTION_DRIFT")
            self.assertTrue(backup.restorable)
            GlobalIdentityGraphService(store).rebuild_projection(str(uuid.uuid4()))

            operation_id = str(uuid.uuid4())
            result = service.restore_backup(backup.backup_id, operation_id)

            self.assertEqual(result["outcome"], "COMMITTED")
            report = ReadOnlyIntegrityChecker(db_path).run()
            self.assertEqual(report.status, "PASS")
            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM graph_connections").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT content FROM note_revisions WHERE note_id = ?", (note.note_id,)).fetchone()[0], "Known relationship")
                restored_history = conn.execute(
                    "SELECT operation_id, operation_type, status FROM operation_journal ORDER BY operation_id"
                ).fetchall()
            for row in source_history:
                self.assertIn(row, restored_history)
            self.assertIn((operation_id, "backup.restore", "COMMITTED"), restored_history)

    def test_failure_injection_at_every_restore_boundary_leaves_old_authority(self) -> None:
        checkpoints = (
            "before_safety_backup", "after_safety_backup", "before_staging",
            "after_database_staging", "before_migration", "after_migration",
            "after_media_staging", "before_media_rewrite", "after_media_rewrite",
            "before_graph_rebuild", "after_graph_rebuild", "before_staged_integrity",
            "after_staged_integrity", "before_media_install", "after_media_install",
            "before_database_swap", "after_database_swap", "before_reload",
            "after_reload", "before_final_integrity", "after_final_integrity",
            "before_receipt",
        )
        for checkpoint in checkpoints:
            with self.subTest(checkpoint=checkpoint), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                db_path = root / "data" / "sentriface.db"
                self._seed_database_with_media(db_path, root)
                base = self._service(db_path, root / "data" / "backups")
                target = base.create_backup(reason="target")
                with closing(sqlite3.connect(db_path)) as conn, conn:
                    conn.execute("UPDATE persons SET name = 'Current authority'")
                operation_id = str(uuid.uuid4())

                def fail(name):
                    if name == checkpoint:
                        raise RuntimeError(f"failure at {name}")

                service = BackupService(
                    db_path,
                    root / "data" / "backups",
                    now=self._fixed_now,
                    failure_injector=fail,
                )
                with self.assertRaisesRegex(BackupError, "rolled back safely"):
                    service.restore_backup(target.backup_id, operation_id)
                with closing(sqlite3.connect(db_path)) as conn:
                    self.assertEqual(conn.execute("SELECT name FROM persons").fetchone()[0], "Current authority")
                    self.assertEqual(conn.execute(
                        "SELECT status FROM operation_journal WHERE operation_id = ?",
                        (operation_id,),
                    ).fetchone()[0], "FAILED")
                self.assertEqual(ReadOnlyIntegrityChecker(db_path).run().status, "PASS")
                restored = root / "data" / "restored-media"
                self.assertFalse(restored.exists() and any(restored.iterdir()))

    def test_restore_callback_failure_rolls_back_database_and_new_media(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            self._seed_database_with_media(db_path, root)
            service = self._service(db_path, root / "data" / "backups")
            target = service.create_backup(reason="old-state")
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute("UPDATE persons SET name = 'Current state'")
            callback_calls = {"count": 0}

            def fail_once() -> None:
                callback_calls["count"] += 1
                if callback_calls["count"] == 1:
                    raise RuntimeError("simulated index reload failure")

            with self.assertRaisesRegex(BackupError, "simulated index reload failure"):
                service.restore_backup(
                    target.backup_id,
                    str(uuid.uuid4()),
                    reload_callback=fail_once,
                )

            self.assertEqual(callback_calls["count"], 2)
            with closing(sqlite3.connect(db_path)) as conn, conn:
                self.assertEqual(
                    conn.execute("SELECT name FROM persons").fetchone()[0],
                    "Current state",
                )
            restored_root = root / "data" / "restored-media"
            self.assertFalse(
                restored_root.exists() and any(restored_root.iterdir())
            )

    def test_restore_operation_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            self._seed_database_with_media(db_path, root)
            service = self._service(db_path, root / "data" / "backups")
            target = service.create_backup()
            operation_id = str(uuid.uuid4())

            first = service.restore_backup(target.backup_id, operation_id)
            backup_count = len(service.list_backups())
            second = service.restore_backup(target.backup_id, operation_id)

            self.assertEqual(first, second)
            self.assertEqual(len(service.list_backups()), backup_count)

    def test_restore_operation_id_conflict_is_refused_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            self._seed_database_with_media(db_path, root)
            service = self._service(db_path, root / "data" / "backups")
            first_target = service.create_backup(reason="first")
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute("UPDATE persons SET name = 'Second target'")
            second_target = service.create_backup(reason="second")
            operation_id = str(uuid.uuid4())
            service.restore_backup(first_target.backup_id, operation_id)
            with closing(sqlite3.connect(db_path)) as conn:
                name_before = conn.execute("SELECT name FROM persons").fetchone()[0]

            with self.assertRaisesRegex(BackupError, "conflicts"):
                service.restore_backup(second_target.backup_id, operation_id)

            with closing(sqlite3.connect(db_path)) as conn:
                self.assertEqual(conn.execute("SELECT name FROM persons").fetchone()[0], name_before)

    def test_restart_recovers_committed_restore_missing_only_its_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            self._seed_database_with_media(db_path, root)
            base = self._service(db_path, root / "data" / "backups")
            target = base.create_backup(reason="target")
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute("UPDATE persons SET name = 'Displaced live state'")
            operation_id = str(uuid.uuid4())

            def simulate_process_exit(name):
                if name == "before_receipt":
                    raise SystemExit("simulated process termination")

            interrupted = BackupService(
                db_path,
                root / "data" / "backups",
                now=self._fixed_now,
                failure_injector=simulate_process_exit,
            )
            with self.assertRaises(SystemExit):
                interrupted.restore_backup(target.backup_id, operation_id)
            self.assertTrue(interrupted._restore_intent_path(operation_id).is_file())
            self.assertFalse(interrupted._restore_receipt_path(target.backup_id, operation_id).exists())

            restarted = self._service(db_path, root / "data" / "backups")
            outcomes = restarted.recover_interrupted_restores()

            self.assertEqual(outcomes, [{"operation_id": operation_id, "outcome": "COMMITTED"}])
            self.assertTrue(restarted._restore_receipt_path(target.backup_id, operation_id).is_file())
            self.assertFalse(restarted._restore_intent_path(operation_id).exists())
            self.assertEqual(ReadOnlyIntegrityChecker(db_path).run().status, "PASS")

    def test_malicious_or_unexpected_archive_entries_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            self._seed_database(db_path)
            service = self._service(db_path, root / "data" / "backups")
            archive = root / "malicious.sfbackup"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("../outside.txt", b"escape")
                package.writestr("backup.json", b"{}")

            with self.assertRaisesRegex(BackupError, "unsafe path"):
                service.import_backup(archive)

            self.assertFalse((root / "outside.txt").exists())
            self.assertEqual(service.list_backups(), [])

    def test_archive_with_extra_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "source" / "sentriface.db"
            self._seed_database(db_path)
            service = self._service(db_path, root / "source" / "backups")
            backup = service.create_backup()
            archive = service.export_backup(backup.backup_id, root / "valid")
            tampered = root / "tampered.sfbackup"
            shutil.copy2(archive, tampered)
            with zipfile.ZipFile(tampered, "a") as package:
                package.writestr("unexpected.exe", b"payload")
            target = self._service(
                root / "target" / "sentriface.db",
                root / "target" / "backups",
            )

            with self.assertRaisesRegex(BackupError, "unexpected files"):
                target.import_backup(tampered)

    def test_newer_database_version_cannot_be_restored(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "sentriface.db"
            self._seed_database(db_path)
            service = BackupService(
                db_path,
                root / "data" / "backups",
                now=self._fixed_now,
                supported_database_version=SCHEMA_VERSION,
            )
            backup = service.create_backup()
            metadata_path = service._backup_path(backup.backup_id) / "backup.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            backup_db = service._database_path(backup.backup_id)
            with closing(sqlite3.connect(backup_db)) as conn, conn:
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
            metadata["database_version"] = SCHEMA_VERSION + 1
            metadata["database"]["sha256"] = hashlib.sha256(
                backup_db.read_bytes()
            ).hexdigest()
            metadata["database"]["size_bytes"] = backup_db.stat().st_size
            metadata["database_size_bytes"] = backup_db.stat().st_size
            metadata["size_bytes"] = backup_db.stat().st_size
            metadata["integrity"] = service._integrity_metadata(
                backup_db, SCHEMA_VERSION + 1,
            )
            metadata["restorable"] = False
            metadata_path.write_text(
                json.dumps(_with_manifest_fingerprint(metadata)), encoding="utf-8"
            )

            with self.assertRaisesRegex(BackupError, "newer"):
                service.restore_backup(backup.backup_id, str(uuid.uuid4()))

    def _seed_database(self, db_path: Path) -> None:
        store = SQLiteIdentityStore(db_path, embedding_dim=4)
        store.initialize()
        person = store.create_person("Backup Person")
        store.add_embedding(person.person_id, [0.1, 0.2, 0.3, 0.4], quality_score=0.9)

    def _seed_database_with_media(
        self,
        db_path: Path,
        fixture_root: Path,
    ) -> tuple[Path, Path, Path]:
        fixture_root.mkdir(parents=True, exist_ok=True)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        source = fixture_root / "original.jpg"
        crop = db_path.parent / "faces" / "crop.jpg"
        sighting = fixture_root / "sighting.png"
        crop.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"original-image")
        crop.write_bytes(b"face-crop")
        sighting.write_bytes(b"sighting-image")
        store = SQLiteIdentityStore(db_path, embedding_dim=4)
        store.initialize()
        person = store.create_person("Backup Person")
        embedding = store.add_embedding(
            person.person_id,
            [0.1, 0.2, 0.3, 0.4],
            quality_score=0.9,
            source_image=str(source),
            crop_path=str(crop),
        )
        store.add_recognition_detail(
            embedding.embedding_id,
            person.person_id,
            "image-1",
            "Backup Person",
            "strong",
            "2026-07-15",
            "22:14:08",
            "Test",
            1,
            "Backup test",
            image_path=str(sighting),
        )
        return source, crop, sighting

    def _service(self, db_path: Path, backup_dir: Path) -> BackupService:
        return BackupService(db_path, backup_dir, now=self._fixed_now)

    def _fixed_now(self) -> datetime:
        return datetime(2026, 7, 15, 22, 14, 8, tzinfo=timezone.utc)


if __name__ == "__main__":
    unittest.main()
