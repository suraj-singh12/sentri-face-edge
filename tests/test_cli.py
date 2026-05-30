from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from sentriface import cli


class CliTest(unittest.TestCase):
    def test_profile_command_prints_runtime_settings(self) -> None:
        output = io.StringIO()

        with patch("sys.argv", ["sentriface", "--profile", "low", "profile"]):
            with redirect_stdout(output):
                code = cli.main()

        self.assertEqual(code, 0)
        text = output.getvalue()
        self.assertIn("tier=low", text)
        self.assertIn("max_workers=1", text)
        self.assertIn("runtime=dev", text)

    def test_json_profile_command(self) -> None:
        output = io.StringIO()

        with patch("sys.argv", ["sentriface", "--json", "--profile", "low", "profile"]):
            with redirect_stdout(output):
                code = cli.main()

        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["tier"], "low")
        self.assertEqual(payload["max_workers"], 1)

    def test_missing_onnx_model_is_user_facing_error(self) -> None:
        output = io.StringIO()

        with patch(
            "sys.argv",
            [
                "sentriface",
                "--runtime",
                "onnx",
                "--detector-model",
                "missing-detector.onnx",
                "init-db",
            ],
        ):
            with redirect_stdout(output):
                code = cli.main()

        self.assertEqual(code, 1)
        self.assertIn("error=Model file not found", output.getvalue())


if __name__ == "__main__":
    unittest.main()
