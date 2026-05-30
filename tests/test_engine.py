from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sentriface.cli import build_dev_engine
from sentriface.models import MatchDecision


class EngineWorkflowTest(unittest.TestCase):
    def test_add_and_recognize_same_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.bin"
            image.write_bytes(b"fake-image-content")

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            pending = engine.prepare_additions(image)
            self.assertEqual(len(pending), 1)
            person_id = engine.confirm_new_person(pending[0], "Test Person")

            results = engine.recognize(image)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].decision, MatchDecision.STRONG)
            self.assertEqual(results[0].matches[0].person_id, person_id)

    def test_queue_and_confirm_pending_existing_person(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image = temp_path / "face.bin"
            image.write_bytes(b"fake-image-content")

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()
            pending = engine.queue_additions(image)
            self.assertEqual(len(pending), 1)
            self.assertEqual(len(engine.list_pending_additions()), 1)

            person_id = engine.confirm_pending_as_new_person(pending[0].pending_id, "Test Person")
            self.assertEqual(engine.list_pending_additions(), [])

            second = engine.queue_additions(image)
            self.assertEqual(second[0].decision, MatchDecision.STRONG)
            embedding_id = engine.confirm_pending_as_existing_person(
                second[0].pending_id,
                person_id,
            )

            self.assertTrue(embedding_id)
            self.assertEqual(engine.list_pending_additions(), [])


if __name__ == "__main__":
    unittest.main()
