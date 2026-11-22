from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from sentriface.models import DetectedFace, FaceBox, MatchDecision, PendingAddition, QualityReport, QualityStatus
from sentriface.storage.sqlite_store import SQLiteIdentityStore

CONTRACT = json.loads((Path(__file__).parent / "fixtures" / "review_completion_contract.json").read_text())


class ReviewCompletionContractTest(unittest.TestCase):
    """Backend half of the completion rule shared with frontend/src/reviewState.js."""

    def _review(self, store: SQLiteIdentityStore, count: int) -> None:
        media_path = "/managed/photo.jpg"
        faces = []
        for index in range(count):
            pending_id = f"pending-{index}"
            store.save_pending_addition(PendingAddition(
                pending_id=pending_id,
                source_image=media_path,
                face=DetectedFace(box=FaceBox(1, 2, 10, 12, 0.99), quality_score=0.9, crop_path=f"{media_path}.{index}.crop.jpg"),
                vector=(1.0 - index * 0.1, index * 0.1),
                matches=[],
                decision=MatchDecision.UNKNOWN,
                quality=QualityReport(QualityStatus.GOOD, 0.9),
            ))
            faces.append({"face_id": f"face-{index}", "staged_face_type": "PENDING_ADDITION", "staged_face_id": pending_id})
        store.create_photo_review("review", "photo.jpg", faces, media_path=media_path)

    def test_backend_matches_shared_contract(self) -> None:
        for case in CONTRACT["cases"]:
            if not case["decisions"]:
                continue
            with self.subTest(case["name"]), tempfile.TemporaryDirectory() as temp:
                store = SQLiteIdentityStore(Path(temp) / "sentriface.db", embedding_dim=2)
                store.initialize()
                self._review(store, len(case["decisions"]))
                existing = store.create_person("Existing")
                for index, decision in enumerate(case["decisions"]):
                    if decision is None:
                        continue
                    values = {}
                    if decision == "ACCEPT_EXISTING_PERSON":
                        values["person_id"] = existing.person_id
                    if decision == "ACCEPT_NEW_PERSON":
                        values["new_person_name"] = f"New {index}"
                    store.set_photo_review_face_decision("review", f"face-{index}", decision, **values)
                if case["backend_error"] is None:
                    store.complete_photo_review("review", "contract-op")
                    self.assertEqual(store.get_operation("contract-op")["status"], "COMMITTED")
                else:
                    with self.assertRaisesRegex(ValueError, re.escape(case["backend_error"])):
                        store.complete_photo_review("review", "contract-op")

    def test_frontend_ready_exactly_when_backend_completes(self) -> None:
        for case in CONTRACT["cases"]:
            self.assertEqual(case["frontend_ready"], case["backend_error"] is None, case["name"])


if __name__ == "__main__":
    unittest.main()
