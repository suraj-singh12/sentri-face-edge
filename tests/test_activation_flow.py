from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32", "Windows activation uses the Windows registry")
class WindowsActivationFlowTest(unittest.TestCase):
    def test_installer_status_helper_reports_machine_and_activation(self) -> None:
        from sentriface.licensing.activation_helper import run_activation_helper

        with tempfile.TemporaryDirectory() as temp:
            result = Path(temp) / "status.txt"
            with (
                patch("sentriface.licensing.activation_helper.is_activated", return_value=True),
                patch(
                    "sentriface.licensing.activation_helper.generate_machine_id",
                    return_value="SFE-MC-TEST1-TEST2-TEST3",
                ),
            ):
                exit_code = run_activation_helper(
                    ["--activation-helper", "status", str(result)]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                result.read_text(encoding="utf-8").splitlines()[:2],
                ["1", "SFE-MC-TEST1-TEST2-TEST3"],
            )

    def test_installer_activation_helper_uses_key_file_and_removes_it(self) -> None:
        from sentriface.licensing.activation_helper import run_activation_helper

        with tempfile.TemporaryDirectory() as temp:
            key_file = Path(temp) / "key.txt"
            result = Path(temp) / "result.txt"
            key_file.write_text("SFE1.payload.signature", encoding="utf-8")
            with (
                patch("sentriface.licensing.activation_helper.save_activation_key") as save_key,
                patch(
                    "sentriface.licensing.activation_helper.generate_machine_id",
                    return_value="SFE-MC-TEST1-TEST2-TEST3",
                ),
            ):
                exit_code = run_activation_helper(
                    ["--activation-helper", "activate", str(key_file), str(result)]
                )

            self.assertEqual(exit_code, 0)
            save_key.assert_called_once_with(
                "SFE1.payload.signature",
                machine_id="SFE-MC-TEST1-TEST2-TEST3",
            )
            self.assertFalse(key_file.exists())
            self.assertEqual(result.read_text(encoding="utf-8").splitlines()[0], "1")

    def test_invalid_installer_activation_is_reported_without_saving(self) -> None:
        from sentriface.licensing.activation_helper import run_activation_helper

        with tempfile.TemporaryDirectory() as temp:
            key_file = Path(temp) / "key.txt"
            result = Path(temp) / "result.txt"
            key_file.write_text("invalid", encoding="utf-8")
            with (
                patch(
                    "sentriface.licensing.activation_helper.save_activation_key",
                    side_effect=ValueError("invalid"),
                ),
                patch(
                    "sentriface.licensing.activation_helper.generate_machine_id",
                    return_value="SFE-MC-TEST1-TEST2-TEST3",
                ),
            ):
                exit_code = run_activation_helper(
                    ["--activation-helper", "activate", str(key_file), str(result)]
                )

            self.assertEqual(exit_code, 1)
            self.assertFalse(key_file.exists())
            lines = result.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], "0")
            self.assertIn("invalid", lines[2].casefold())


if __name__ == "__main__":
    unittest.main()
