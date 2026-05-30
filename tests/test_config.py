from __future__ import annotations

import unittest
from pathlib import Path

from sentriface.config import HardwareProfile, config_for_hardware


class HardwareConfigTest(unittest.TestCase):
    def test_low_profile_keeps_i3_responsive(self) -> None:
        profile = HardwareProfile(
            cpu_count=4,
            memory_gb=4.0,
            tier="low",
            reason="test",
        )

        config = config_for_hardware(profile, data_dir=Path("data"))

        self.assertEqual(config.max_workers, 1)
        self.assertEqual(config.batch_size, 1)
        self.assertLessEqual(config.max_image_edge, 960)
        self.assertTrue(config.prefer_small_models)
        self.assertEqual(config.index_backend, "linear")

    def test_medium_profile_allows_small_parallel_batches(self) -> None:
        profile = HardwareProfile(
            cpu_count=8,
            memory_gb=8.0,
            tier="medium",
            reason="test",
        )

        config = config_for_hardware(profile, data_dir=Path("data"))

        self.assertEqual(config.max_workers, 2)
        self.assertEqual(config.batch_size, 2)
        self.assertEqual(config.index_backend, "hnswlib")


if __name__ == "__main__":
    unittest.main()
