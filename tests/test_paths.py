from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.paths import default_data_dir, default_model_dir, source_development_data_dir


class ApplicationPathsTest(unittest.TestCase):
    def test_explicit_environment_paths_win(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "SENTRIFACE_DATA_DIR": "custom-data",
                "SENTRIFACE_MODEL_DIR": "custom-models",
            },
            clear=False,
        ):
            self.assertEqual(default_data_dir(), Path("custom-data"))
            self.assertEqual(default_model_dir(), Path("custom-models"))

    def test_linux_path_honors_xdg_data_home(self) -> None:
        with (
            patch("sentriface.paths.sys.platform", "linux"),
            patch.dict(
                "os.environ",
                {"XDG_DATA_HOME": "/tmp/xdg"},
                clear=True,
            ),
        ):
            self.assertEqual(default_data_dir(), Path("/tmp/xdg/sentriface"))

    def test_macos_path_uses_application_support(self) -> None:
        with (
            patch("sentriface.paths.sys.platform", "darwin"),
            patch("sentriface.paths.Path.home", return_value=Path("/Users/tester")),
            patch.dict("os.environ", {}, clear=True),
        ):
            self.assertEqual(
                default_data_dir(),
                Path("/Users/tester/Library/Application Support/SentriFace"),
            )

    def test_macos_source_development_path_is_not_product_data(self) -> None:
        with (
            patch("sentriface.paths.sys.platform", "darwin"),
            patch("sentriface.paths.Path.home", return_value=Path("/Users/tester")),
        ):
            self.assertEqual(
                source_development_data_dir(),
                Path("/Users/tester/Library/Application Support/SentriFace-Dev"),
            )
            self.assertNotEqual(source_development_data_dir(), default_data_dir())


if __name__ == "__main__":
    unittest.main()
