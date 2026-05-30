from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from sentriface.cli import build_dev_engine


class InitWorkflowTest(unittest.TestCase):
    def test_init_scan_groups_and_confirms(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_dir = temp_path / "images"
            image_dir.mkdir()
            self._write_image(image_dir / "person_a_1.jpg", shade=120)
            self._write_image(image_dir / "person_a_2.jpg", shade=120)
            self._write_image(image_dir / "person_b_1.jpg", shade=180)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            session = engine.create_init_session(image_dir)
            groups = engine.list_init_groups(session.session_id)

            self.assertGreaterEqual(len(groups), 2)
            self.assertEqual(sum(len(group.faces) for group in groups), 3)

            first_group = groups[0]
            person_id = engine.confirm_init_group(
                session.session_id,
                first_group.group_id,
                "Init Person",
            )

            self.assertTrue(person_id)
            updated = engine.list_init_groups(session.session_id)
            confirmed = [group for group in updated if group.group_id == first_group.group_id][0]
            self.assertEqual(confirmed.status, "confirmed")

    def test_init_reject_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            image_dir = temp_path / "images"
            image_dir.mkdir()
            self._write_image(image_dir / "person_a.jpg", shade=120)

            engine = build_dev_engine(temp_path / "data")
            engine.initialize()

            session = engine.create_init_session(image_dir)
            group = engine.list_init_groups(session.session_id)[0]
            engine.reject_init_group(session.session_id, group.group_id)

            updated = engine.list_init_groups(session.session_id)[0]
            self.assertEqual(updated.status, "rejected")

    def _write_image(self, image: Path, shade: int) -> None:
        canvas = np.full((160, 160, 3), shade, dtype=np.uint8)
        cv2.rectangle(canvas, (35, 35), (125, 125), (220, 220, 220), -1)
        cv2.circle(canvas, (62, 70), 7, (20, 20, 20), -1)
        cv2.circle(canvas, (98, 70), 7, (20, 20, 20), -1)
        cv2.ellipse(canvas, (80, 100), (28, 12), 0, 0, 180, (20, 20, 20), 2)
        cv2.imwrite(str(image), canvas)


if __name__ == "__main__":
    unittest.main()

