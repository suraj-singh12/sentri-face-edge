from __future__ import annotations

import base64
import hashlib
import sqlite3
from contextlib import closing
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np

from sentriface.cli import build_dev_engine
from sentriface.backup_service import BackupError, BackupService
from sentriface.engine import _canonical_source_path
from sentriface.errors import InputValidationError
from sentriface.models import EmbeddingRecord
from sentriface.secure_files import is_protected_file, read_protected_bytes
from sentriface.api_server import (
    OperationGate,
    UPLOAD_MAX_PIXELS,
    UPLOAD_RESIZE_LIMIT_BYTES,
    SentriFaceApiServer,
    _discard_upload_batch,
    _has_duplicate_embedding,
    _pending,
    _person_summary,
    _init_group,
    _recognition,
    _save_upload,
    _save_upload_batch,
    _save_upload_chunk,
)


class ApiSerializationTest(unittest.TestCase):
    def test_recognition_browse_ranks_people_only_for_the_selected_face(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(root / "data")
            engine.initialize()
            session = engine.create_init_session(image)
            group = engine.list_init_groups(session.session_id)[0]
            vector = group.faces[0].vector

            closest = engine.store.create_person("Closest")
            engine.store.add_embedding(
                closest.person_id,
                vector,
                quality_score=1.0,
                source_image=str(image),
            )
            opposite = engine.store.create_person("Opposite")
            engine.store.add_embedding(
                opposite.person_id,
                tuple(-value for value in vector),
                quality_score=1.0,
                source_image=str(image),
            )
            without_reference = engine.store.create_person("No Reference")

            candidates = engine.ranked_people_for_recognition_face(
                image,
                1,
                expected_box=group.faces[0].face.box,
            )

            self.assertEqual(candidates[0].summary.person.person_id, closest.person_id)
            self.assertEqual(candidates[-1].summary.person.person_id, without_reference.person_id)
            self.assertEqual(
                {candidate.summary.person.person_id for candidate in candidates},
                {closest.person_id, opposite.person_id, without_reference.person_id},
            )

    def test_browse_people_ranks_every_active_person_in_one_bulk_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(root / "data")
            engine.initialize()
            session = engine.create_init_session(image)
            group = engine.list_init_groups(session.session_id)[0]
            vector = group.faces[0].vector

            expected = []
            for name, scale in (("Closest", 1.0), ("Middle", 0.6), ("Lowest", 0.2)):
                person = engine.store.create_person(name)
                engine.store.add_embedding(
                    person.person_id,
                    tuple(value * scale for value in vector),
                    quality_score=1.0,
                    source_image=str(image),
                )
                expected.append(person.person_id)
            without_photo = engine.store.create_person("No Reference")

            candidates = engine.ranked_people_for_init_group(group)

            self.assertEqual(
                [candidate.summary.person.person_id for candidate in candidates],
                [*expected, without_photo.person_id],
            )
            self.assertEqual([candidate.match is not None for candidate in candidates], [True, True, True, False])

    def test_partially_initialized_server_closes_without_masking_bind_error(self) -> None:
        server = object.__new__(SentriFaceApiServer)
        server.socket = Mock()

        server.server_close()

        server.socket.close.assert_called_once_with()

    def test_restore_operation_gate_waits_for_active_work_and_blocks_new_work(self) -> None:
        gate = OperationGate()
        active_started = threading.Event()
        release_active = threading.Event()
        exclusive_started = threading.Event()
        release_exclusive = threading.Event()
        late_shared_started = threading.Event()

        def active_work() -> None:
            with gate.shared():
                active_started.set()
                release_active.wait(timeout=2)

        def restore_work() -> None:
            with gate.exclusive():
                exclusive_started.set()
                release_exclusive.wait(timeout=2)

        def late_work() -> None:
            with gate.shared():
                late_shared_started.set()

        active = threading.Thread(target=active_work)
        restore = threading.Thread(target=restore_work)
        late = threading.Thread(target=late_work)
        active.start()
        self.assertTrue(active_started.wait(timeout=1))
        restore.start()
        time.sleep(0.03)
        late.start()
        self.assertFalse(exclusive_started.wait(timeout=0.05))
        self.assertFalse(late_shared_started.wait(timeout=0.05))
        release_active.set()
        self.assertTrue(exclusive_started.wait(timeout=1))
        self.assertFalse(late_shared_started.wait(timeout=0.05))
        release_exclusive.set()
        self.assertTrue(late_shared_started.wait(timeout=1))
        active.join(timeout=1)
        restore.join(timeout=1)
        late.join(timeout=1)

    def test_queue_cancellation_registry_preserves_cancel_before_scan_race(self) -> None:
        server = object.__new__(SentriFaceApiServer)
        server.queue_progress = {}
        server.queue_progress_lock = threading.Lock()
        server.queue_cancellations = {}
        server.queue_cancellation_created = {}
        server.active_queue_jobs = set()

        self.assertTrue(server.request_queue_cancellation("job-1"))
        cancellation = server.register_queue_job("job-1")

        self.assertTrue(cancellation.is_set())
        self.assertEqual(server.queue_progress_snapshot("job-1")["status"], "cancelling")
        server.finish_queue_job("job-1")
        self.assertNotIn("job-1", server.queue_cancellations)
        self.assertNotIn("job-1", server.queue_cancellation_created)
        self.assertNotIn("job-1", server.active_queue_jobs)

        live_cancellation = server.register_queue_job("job-2")
        server.queue_cancellation_created["job-2"] = 0
        self.assertTrue(server.request_queue_cancellation("job-2"))
        self.assertIs(server.queue_cancellations["job-2"], live_cancellation)
        self.assertTrue(live_cancellation.is_set())
        server.finish_queue_job("job-2")

    def test_people_deletion_backup_precedes_mutation_and_retry_reuses_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_dir = root / "data"
            image = root / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(data_dir)
            engine.initialize()
            person_id = engine.confirm_new_person(
                engine.prepare_additions(image)[0],
                "Backup First",
            )
            server = object.__new__(SentriFaceApiServer)
            server.engine = engine
            server.backups = BackupService(engine.config.db_path, engine.config.backup_dir)
            operation_id = str(uuid.uuid4())

            first = server.backed_up_people_deletion(
                operation_id,
                "archive-person",
                "before-person-archive-backup-first",
                lambda: engine.archive_person(person_id, operation_id),
            )
            second = server.backed_up_people_deletion(
                operation_id,
                "archive-person",
                "ignored-retry-name",
                lambda: engine.archive_person(person_id, operation_id),
            )

            self.assertEqual(first["backup"]["backup_id"], second["backup"]["backup_id"])
            self.assertEqual(len(server.backups.list_backups()), 1)
            backup_db = (
                engine.config.backup_dir
                / first["backup"]["backup_id"]
                / engine.config.db_path.name
            )
            with closing(sqlite3.connect(backup_db)) as conn, conn:
                archived_in_backup = conn.execute(
                    "SELECT deleted_at FROM persons WHERE person_id = ?",
                    (person_id,),
                ).fetchone()[0]
            self.assertIsNone(archived_in_backup)
            self.assertIsNotNone(engine.get_person(person_id, include_archived=True).deleted_at)

    def test_failed_pre_delete_backup_prevents_mutation(self) -> None:
        class FailingBackups:
            def find_by_operation(self, operation_id: str):
                return None

            def create_backup(self, **kwargs):
                raise BackupError("verification failed")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(root / "data")
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "Safe")
            server = object.__new__(SentriFaceApiServer)
            server.engine = engine
            server.backups = FailingBackups()
            operation_id = str(uuid.uuid4())

            with self.assertRaises(BackupError):
                server.backed_up_people_deletion(
                    operation_id,
                    "archive-person",
                    "before-person-archive-safe",
                    lambda: engine.archive_person(person_id, operation_id),
                )

            self.assertIsNotNone(engine.get_person(person_id))
            self.assertIsNone(engine.get_person_operation(operation_id, "archive-person"))

    def test_expired_deleted_faces_are_backed_up_then_purged_as_one_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first_image = root / "first.jpg"
            second_image = root / "second.jpg"
            self._write_image(first_image)
            self._write_image(second_image)
            engine = build_dev_engine(root / "data")
            engine.initialize()
            first_person = engine.confirm_new_person(
                engine.prepare_additions(first_image)[0],
                "First Expiry",
            )
            second_person = engine.confirm_new_person(
                engine.prepare_additions(second_image)[0],
                "Second Expiry",
            )
            embedding_ids = [
                engine.list_person_embeddings(first_person)[0].embedding_id,
                engine.list_person_embeddings(second_person)[0].embedding_id,
            ]
            for embedding_id in embedding_ids:
                engine.delete_embedding(embedding_id, str(uuid.uuid4()))
            with closing(sqlite3.connect(engine.config.db_path)) as conn, conn:
                conn.executemany(
                    "UPDATE embeddings SET purge_after = ? WHERE embedding_id = ?",
                    [
                        ("2020-01-01T00:00:00+00:00", embedding_id)
                        for embedding_id in embedding_ids
                    ],
                )
            server = object.__new__(SentriFaceApiServer)
            server.engine = engine
            server.backups = BackupService(engine.config.db_path, engine.config.backup_dir)
            server.log_event = lambda *args, **kwargs: None

            self.assertEqual(server.purge_expired_deleted_faces(), 2)
            self.assertEqual(server.purge_expired_deleted_faces(), 0)

            for embedding_id in embedding_ids:
                self.assertIsNone(engine.get_embedding_lifecycle(embedding_id))
            self.assertEqual(len(server.backups.list_backups()), 1)
            self.assertIn(
                "before-expired-face-purge-2-faces",
                server.backups.list_backups()[0].backup_id,
            )
            backup = server.backups.list_backups()[0]
            with closing(sqlite3.connect(server.backups._database_path(backup.backup_id))) as conn, conn:
                placeholders = ", ".join("?" for _ in embedding_ids)
                backed_up_faces = conn.execute(
                    f"""
                    SELECT COUNT(*) FROM embeddings
                    WHERE embedding_id IN ({placeholders})
                      AND deleted_at IS NOT NULL
                    """,
                    embedding_ids,
                ).fetchone()[0]
            self.assertEqual(backed_up_faces, 2)

    def test_duplicate_embedding_detection_uses_near_exact_score(self) -> None:
        embeddings = [
            EmbeddingRecord(
                embedding_id="embedding-1",
                person_id="person-1",
                vector=(1.0, 0.0, 0.0, 0.0),
                quality_score=0.9,
            )
        ]

        self.assertTrue(_has_duplicate_embedding((1.0, 0.0, 0.0, 0.0), embeddings))
        self.assertFalse(_has_duplicate_embedding((0.0, 1.0, 0.0, 0.0), embeddings))

    def test_recognition_payload_contains_debuggable_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            pending = engine.prepare_additions(image)[0]
            person_id = engine.confirm_new_person(pending, "UI Person")

            result = engine.recognize(image)[0]
            payload = _recognition(engine, result, 1)

            self.assertEqual(payload["decision"], "strong")
            self.assertEqual(payload["matches"][0]["person_id"], person_id)
            self.assertTrue(payload["matches"][0]["representative_image"])
            self.assertIn("box", payload)
            self.assertIn("quality", payload)

    def test_pending_and_person_payloads_are_ui_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.jpg"
            self._write_image(image)
            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            prepared = engine.queue_additions(image)
            pending_payload = _pending(engine, prepared.accepted[0])
            person_id = engine.confirm_pending_as_new_person(pending_payload["pending_id"], "Queued Person")
            person_payload = _person_summary(engine.list_persons()[0], engine)

            self.assertEqual(person_payload["person_id"], person_id)
            self.assertEqual(person_payload["embedding_count"], 1)
            self.assertTrue(person_payload["representative_image"])
            self.assertIn("crop_path", pending_payload)
            self.assertIn("quality", pending_payload)

    def test_person_summary_prefers_durable_crop_over_transient_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "external-original.jpg"
            crop = root / "data" / "faces" / "pending" / "saved-crop.jpg"
            self._write_image(source)
            crop.parent.mkdir(parents=True, exist_ok=True)
            self._write_image(crop)
            engine = build_dev_engine(root / "data")
            engine.initialize()
            person = engine.store.create_person("Durable Photo")
            engine.store.add_embedding(
                person.person_id,
                [0.0] * engine.config.embedding_dim,
                quality_score=1.0,
                source_image=str(source),
                crop_path=str(crop),
            )

            payload = _person_summary(engine.list_persons()[0], engine)

            self.assertEqual(payload["representative_image"], str(crop))

    def test_queue_group_falls_back_to_source_when_crop_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "incoming.jpg"
            self._write_image(source)
            engine = build_dev_engine(root / "data")
            engine.initialize()
            session = engine.create_init_session(source)
            group = engine.list_init_groups(session.session_id)[0]
            missing_crop = Path(group.faces[0].face.crop_path)
            missing_crop.unlink()

            payload = _init_group(engine, group)

            self.assertEqual(payload["representative_image"], str(source))
            self.assertEqual(payload["faces"][0]["image_path"], str(source))

    def test_upload_save_writes_image_inside_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            image_bytes = self._image_bytes(".jpg")
            encoded = base64.b64encode(image_bytes).decode("ascii")

            saved = _save_upload(data_dir, "face.jpg", f"data:image/jpeg;base64,{encoded}")

            self.assertTrue(saved.exists())
            self.assertEqual(saved.parent, data_dir / "uploads" / "objects")
            self.assertEqual(saved.read_bytes(), image_bytes)

    def test_identical_uploads_reuse_one_physical_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            image_bytes = self._image_bytes(".jpg")
            encoded = base64.b64encode(image_bytes).decode("ascii")

            first = _save_upload(data_dir, "first.jpg", encoded)
            second = _save_upload(data_dir, "second.jpg", encoded)

            self.assertEqual(first, second)
            self.assertEqual(
                list((data_dir / "uploads" / "objects").glob("*.jpg")),
                [first],
            )

    def test_identical_protected_uploads_reuse_one_authenticated_object(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            storage_key = b"k" * 32
            image_bytes = self._image_bytes(".png")
            encoded = base64.b64encode(image_bytes).decode("ascii")

            first = _save_upload(data_dir, "first.png", encoded, storage_key=storage_key)
            second = _save_upload(data_dir, "second.png", encoded, storage_key=storage_key)

            self.assertEqual(first, second)
            self.assertTrue(is_protected_file(first))
            self.assertEqual(read_protected_bytes(first, storage_key), image_bytes)

    def test_legacy_database_image_is_hard_linked_into_canonical_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            legacy = data_dir / "uploads" / "legacy-uuid.jpg"
            legacy.parent.mkdir(parents=True)
            image_bytes = self._image_bytes(".jpg")
            legacy.write_bytes(image_bytes)
            digest = hashlib.sha256(image_bytes).hexdigest()

            saved = _save_upload(
                data_dir,
                "again.jpg",
                base64.b64encode(image_bytes).decode("ascii"),
                known_objects={digest: legacy},
            )

            self.assertTrue(saved.samefile(legacy))
            self.assertEqual(saved.name, f"{digest}.jpg")

    def test_queue_uploads_stage_hard_links_to_the_same_canonical_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            image_bytes = self._image_bytes(".jpg")

            first_dir, first = _save_upload_chunk(
                data_dir, str(uuid.uuid4()), "first.jpg", "one/first.jpg", image_bytes
            )
            second_dir, second = _save_upload_chunk(
                data_dir, str(uuid.uuid4()), "second.jpg", "two/second.jpg", image_bytes
            )

            self.assertNotEqual(first_dir, second_dir)
            canonical = next((data_dir / "uploads" / "objects").glob("*.jpg"))
            self.assertTrue(first.samefile(canonical))
            self.assertTrue(second.samefile(canonical))
            self.assertEqual(_canonical_source_path(first, data_dir), str(canonical))
            self.assertEqual(_canonical_source_path(second, data_dir), str(canonical))
            self.assertEqual(
                len(list((data_dir / "uploads" / "objects").glob("*.jpg"))),
                1,
            )

    def test_upload_save_reduces_large_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            rng = np.random.default_rng(123)
            image = rng.integers(0, 255, (1800, 1800, 3), dtype=np.uint8)
            ok, encoded_image = cv2.imencode(".png", image)
            self.assertTrue(ok)
            original = encoded_image.tobytes()
            self.assertGreater(len(original), UPLOAD_RESIZE_LIMIT_BYTES)
            encoded = base64.b64encode(original).decode("ascii")

            saved = _save_upload(data_dir, "large.png", f"data:image/png;base64,{encoded}")

            self.assertTrue(saved.exists())
            self.assertEqual(saved.suffix, ".jpg")
            self.assertLessEqual(saved.stat().st_size, UPLOAD_RESIZE_LIMIT_BYTES)

    def test_upload_save_rejects_unsupported_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(InputValidationError):
                _save_upload(Path(temp), "note.txt", "bm90IGFuIGltYWdl")

    def test_upload_save_rejects_fake_image_and_extension_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            fake = base64.b64encode(b"not really a jpeg").decode("ascii")
            png = base64.b64encode(self._image_bytes(".png")).decode("ascii")

            with self.assertRaisesRegex(InputValidationError, "not a supported image"):
                _save_upload(data_dir, "fake.jpg", fake)
            with self.assertRaisesRegex(InputValidationError, "do not match"):
                _save_upload(data_dir, "mismatch.jpg", png)

            self.assertFalse((data_dir / "uploads").exists())

    def test_upload_batch_writes_supported_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            first = base64.b64encode(self._image_bytes(".jpg")).decode("ascii")
            second = base64.b64encode(self._image_bytes(".png")).decode("ascii")

            batch_dir, count, rejected = _save_upload_batch(
                data_dir,
                [
                    {
                        "filename": "a.jpg",
                        "relative_path": "folder/a.jpg",
                        "data": f"data:image/jpeg;base64,{first}",
                    },
                    {
                        "filename": "b.png",
                        "relative_path": "folder/nested/b.png",
                        "data": f"data:image/png;base64,{second}",
                    },
                    {
                        "filename": "skip.txt",
                        "relative_path": "folder/skip.txt",
                        "data": "c2tpcA==",
                    },
                ],
            )

            self.assertEqual(count, 2)
            self.assertEqual(rejected, 1)
            self.assertEqual(len(list((batch_dir / "folder").glob("*.jpg"))), 1)
            self.assertEqual(len(list((batch_dir / "folder" / "nested").glob("*.png"))), 1)
            self.assertFalse((batch_dir / "folder" / "skip.txt").exists())

    def test_upload_batch_skips_all_invalid_items_as_one_failed_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            fake = base64.b64encode(b"not an image").decode("ascii")

            with self.assertRaisesRegex(InputValidationError, "No valid image files"):
                _save_upload_batch(
                    data_dir,
                    [
                        {"filename": "fake.jpg", "data": fake},
                        {"filename": "note.txt", "data": fake},
                        {"filename": "missing-data.jpg"},
                    ],
                )

            batches = data_dir / "uploads" / "batches"
            self.assertFalse(batches.exists() and any(batches.iterdir()))

    def test_upload_chunks_share_staging_folder_and_can_be_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            upload_id = str(uuid.uuid4())

            first_dir, first_path = _save_upload_chunk(
                data_dir,
                upload_id,
                "a.jpg",
                "folder/a.jpg",
                self._image_bytes(".jpg"),
            )
            second_dir, second_path = _save_upload_chunk(
                data_dir,
                upload_id,
                "b.png",
                "folder/nested/b.png",
                self._image_bytes(".png"),
            )

            self.assertEqual(first_dir, second_dir)
            self.assertTrue(first_path.exists())
            self.assertTrue(second_path.exists())
            self.assertTrue(_discard_upload_batch(data_dir, upload_id))
            self.assertFalse(first_dir.exists())
            self.assertFalse(_discard_upload_batch(data_dir, upload_id))

    def test_upload_chunk_rejects_invalid_staging_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(KeyError):
                _save_upload_chunk(
                    Path(temp) / "data",
                    "../../outside",
                    "a.jpg",
                    "folder/a.jpg",
                    self._image_bytes(".jpg"),
                )

    def test_upload_chunk_rejects_path_traversal_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            with self.assertRaisesRegex(InputValidationError, "Invalid upload path"):
                _save_upload_chunk(
                    data_dir,
                    str(uuid.uuid4()),
                    "a.jpg",
                    "../outside/a.jpg",
                    self._image_bytes(".jpg"),
                )
            self.assertFalse((data_dir / "uploads").exists())

    def test_upload_chunk_rejects_unusable_path_component_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            with self.assertRaisesRegex(InputValidationError, "Invalid upload path"):
                _save_upload_chunk(
                    data_dir,
                    str(uuid.uuid4()),
                    "a.jpg",
                    f"{'x' * 256}/a.jpg",
                    self._image_bytes(".jpg"),
                )
            self.assertFalse((data_dir / "uploads").exists())

    def test_upload_save_accepts_jpeg_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            saved = _save_upload(
                Path(temp) / "data",
                "face.jpeg",
                base64.b64encode(self._image_bytes(".jpg")).decode("ascii"),
            )

            self.assertEqual(saved.suffix, ".jpg")
            self.assertTrue(saved.exists())

    def test_upload_batch_skips_unsafe_path_but_keeps_valid_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            encoded = base64.b64encode(self._image_bytes(".jpg")).decode("ascii")

            batch_dir, count, rejected = _save_upload_batch(
                data_dir,
                [
                    {
                        "filename": "outside.jpg",
                        "relative_path": "../outside.jpg",
                        "data": encoded,
                    },
                    {
                        "filename": "inside.jpg",
                        "relative_path": "safe/inside.jpg",
                        "data": encoded,
                    },
                ],
            )

            self.assertEqual((count, rejected), (1, 1))
            self.assertEqual(len(list(batch_dir.rglob("*.jpg"))), 1)
            self.assertFalse((data_dir.parent / "outside.jpg").exists())

    def test_upload_limits_reject_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            from unittest.mock import patch

            with patch("sentriface.api_server.UPLOAD_REQUEST_LIMIT_BYTES", 8):
                with self.assertRaisesRegex(InputValidationError, "25 MB"):
                    _save_upload_chunk(
                        data_dir,
                        str(uuid.uuid4()),
                        "oversized.jpg",
                        "oversized.jpg",
                        self._image_bytes(".jpg"),
                    )

            self.assertFalse((data_dir / "uploads").exists())

    def test_upload_dimension_limit_rejects_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            side = int(UPLOAD_MAX_PIXELS**0.5) + 1
            # Avoid allocating the production limit in a test by temporarily
            # exercising the same guard with a conservative local threshold.
            from unittest.mock import patch

            with patch("sentriface.api_server.UPLOAD_MAX_PIXELS", 100):
                with self.assertRaisesRegex(InputValidationError, "dimensions"):
                    _save_upload_chunk(
                        data_dir,
                        str(uuid.uuid4()),
                        "wide.png",
                        "wide.png",
                        self._image_bytes(".png"),
                    )

            self.assertGreater(side, 0)
            self.assertFalse((data_dir / "uploads").exists())

    def _write_image(self, image: Path) -> None:
        canvas = np.full((160, 160, 3), 128, dtype=np.uint8)
        cv2.rectangle(canvas, (35, 35), (125, 125), (220, 220, 220), -1)
        cv2.circle(canvas, (62, 70), 7, (20, 20, 20), -1)
        cv2.circle(canvas, (98, 70), 7, (20, 20, 20), -1)
        cv2.ellipse(canvas, (80, 100), (28, 12), 0, 0, 180, (20, 20, 20), 2)
        cv2.imwrite(str(image), canvas)

    def _image_bytes(self, suffix: str) -> bytes:
        canvas = np.full((64, 64, 3), 128, dtype=np.uint8)
        ok, encoded = cv2.imencode(suffix, canvas)
        self.assertTrue(ok)
        return encoded.tobytes()


if __name__ == "__main__":
    unittest.main()
