from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

import sentriface.engine as engine_module
from sentriface.components.linear_index import LinearFaceIndex
from sentriface.config import RuntimeConfig
from sentriface.engine import FaceEngine
from sentriface.errors import InputImageError
from sentriface.models import (
    DetectedFace,
    FaceBox,
    MatchDecision,
    PendingAddition,
    PersonMatch,
    QualityReport,
    QualityStatus,
)
from sentriface.storage.sqlite_store import SQLiteIdentityStore


class _Detector:
    def __init__(self, faces=()):
        self.faces = list(faces)

    def detect(self, _path):
        return list(self.faces)


class _Embedder:
    def __init__(self, error: Exception | None = None):
        self.error = error

    def encode(self, _path, _face):
        if self.error:
            raise self.error
        return (1.0, 0.0)


class _Quality:
    def evaluate(self, _image, _face):
        return QualityReport(QualityStatus.GOOD, 1.0)


class PlaceholderEnrollmentTest(unittest.TestCase):
    def _engine(self, root: Path, detector=None, embedder=None) -> FaceEngine:
        config = RuntimeConfig(data_dir=root / "data", embedding_dim=2)
        engine = FaceEngine(
            config,
            detector or _Detector(),
            embedder or _Embedder(),
            LinearFaceIndex(),
            SQLiteIdentityStore(config.db_path, embedding_dim=2),
        )
        engine.initialize()
        engine.quality = _Quality()
        return engine

    def _placeholder(self, engine):
        return engine.create_placeholder_person(
            "Unseen Contact",
            {
                "rank": "Observer",
                "country": "Unknown",
                "importance": "Important",
                "aliases": ["Subject U"],
                "initial_observation": {"place_seen": "Gate A"},
            },
            "Operator",
            "placeholder-enrollment-create",
            notes="Known habit\nVisits on Fridays",
        )

    def _pending(self, engine, vector=(1.0, 0.0), matches=()):
        pending_id = str(uuid.uuid4())
        source = engine.config.data_dir / "uploads" / f"{pending_id}.jpg"
        crop = engine.config.face_dir / "pending" / f"{pending_id}.jpg"
        source.parent.mkdir(parents=True, exist_ok=True)
        crop.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"source")
        crop.write_bytes(b"crop")
        return PendingAddition(
            pending_id=pending_id,
            source_image=str(source),
            face=DetectedFace(FaceBox(1, 1, 80, 80, 0.99), 1.0, crop_path=str(crop)),
            vector=vector,
            matches=list(matches),
            decision=MatchDecision.STRONG if matches else MatchDecision.UNKNOWN,
            quality=QualityReport(QualityStatus.GOOD, 1.0),
        )

    def test_success_preserves_profile_and_supports_further_photos(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            engine = self._engine(Path(temp))
            placeholder = self._placeholder(engine)
            contact = engine.store.create_person("Known Contact")
            association = engine.create_person_association(
                placeholder.person_id, contact.person_id, "Operator", "placeholder-link"
            )
            changes_before = list(engine.list_person_changes(placeholder.person_id))

            first_embedding_id = engine.confirm_existing_person_with_detail(
                self._pending(engine),
                placeholder.person_id,
                {
                    "image_id": "first.jpg#face-01",
                    "image_path": "first.jpg",
                    "name": placeholder.name,
                    "decision": "existing",
                    "seen_date": "2026-08-08",
                    "seen_time": "17:30",
                    "place_seen": "Gate A",
                    "individual_count": 1,
                    "event_occasion": "Observation",
                    "added_by": "Operator",
                    "notes": "First captured face",
                },
                "placeholder-first-photo",
            )

            enrolled = engine.get_person(placeholder.person_id)
            self.assertEqual(enrolled.person_id, placeholder.person_id)
            self.assertEqual(enrolled.enrollment_status, "enrolled")
            self.assertEqual(enrolled.notes, placeholder.notes)
            self.assertEqual(enrolled.metadata, placeholder.metadata)
            self.assertEqual(
                engine.list_person_associations(placeholder.person_id)[0].association_id,
                association.association_id,
            )
            self.assertEqual(engine.list_person_embeddings(placeholder.person_id)[0].embedding_id, first_embedding_id)
            details = engine.store.list_recognition_details_for_person(placeholder.person_id)
            self.assertEqual(len(details), 1)
            self.assertEqual(details[0].place_seen, "Gate A")
            changes_after = engine.list_person_changes(placeholder.person_id)
            self.assertGreater(len(changes_after), len(changes_before))
            self.assertTrue(any(
                change.previous_status == "placeholder" and change.new_status == "enrolled"
                for change in changes_after
            ))

            engine.confirm_existing_person(
                self._pending(engine, vector=(0.0, 1.0)),
                placeholder.person_id,
                "placeholder-second-photo",
            )
            self.assertEqual(len(engine.list_person_embeddings(placeholder.person_id)), 2)

    def test_invalid_image_no_face_and_embedding_failure_leave_placeholder_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            face = DetectedFace(FaceBox(1, 1, 80, 80, 0.99), 1.0)
            engine = self._engine(root, detector=_Detector(), embedder=_Embedder())
            placeholder = self._placeholder(engine)
            original_load = engine_module.load_bgr_image
            try:
                engine_module.load_bgr_image = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    InputImageError("The selected image could not be read", "invalid_image")
                )
                with self.assertRaises(InputImageError):
                    engine.prepare_face_addition(root / "invalid.jpg", 1)

                engine_module.load_bgr_image = lambda *_args, **_kwargs: object()
                with self.assertRaisesRegex(KeyError, "Face 1 is no longer available"):
                    engine.prepare_face_addition(root / "no-face.jpg", 1)

                engine.detector = _Detector([face])
                engine.embedder = _Embedder(RuntimeError("embedding failed"))
                with self.assertRaisesRegex(RuntimeError, "embedding failed"):
                    engine.prepare_face_addition(root / "face.jpg", 1)
            finally:
                engine_module.load_bgr_image = original_load

            unchanged = engine.get_person(placeholder.person_id)
            self.assertEqual(unchanged.enrollment_status, "placeholder")
            self.assertEqual(unchanged.notes, placeholder.notes)
            self.assertEqual(unchanged.metadata, placeholder.metadata)
            self.assertEqual(engine.list_person_embeddings(placeholder.person_id), [])

    def test_conflict_is_available_for_review_before_explicit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            engine = self._engine(Path(temp))
            known = engine.store.create_person("Known Face")
            placeholder = self._placeholder(engine)
            candidate = self._pending(
                engine,
                matches=(PersonMatch(known.person_id, 0.99, ("known-embedding",), 1),),
            )

            self.assertEqual(candidate.matches[0].person_id, known.person_id)
            self.assertNotEqual(candidate.matches[0].person_id, placeholder.person_id)
            self.assertEqual(engine.get_person(placeholder.person_id).enrollment_status, "placeholder")
            self.assertEqual(engine.list_person_embeddings(placeholder.person_id), [])

    def test_confirmation_failure_removes_pending_crop_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            engine = self._engine(Path(temp))
            placeholder = self._placeholder(engine)
            pending = self._pending(engine)
            crop_path = Path(pending.face.crop_path)
            with self.assertRaises(KeyError):
                engine.confirm_existing_person_with_detail(
                    pending,
                    placeholder.person_id,
                    {"name": placeholder.name},
                    "placeholder-rollback",
                )

            self.assertEqual(engine.get_person(placeholder.person_id).enrollment_status, "placeholder")
            self.assertEqual(engine.list_person_embeddings(placeholder.person_id), [])
            self.assertEqual(engine.list_pending_additions(), [])
            self.assertEqual(engine.store.list_recognition_details_for_person(placeholder.person_id), [])
            self.assertFalse(crop_path.exists())


if __name__ == "__main__":
    unittest.main()
