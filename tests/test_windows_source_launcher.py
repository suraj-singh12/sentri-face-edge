from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "run.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell is required")
class WindowsSourceLauncherTest(unittest.TestCase):
    def _run(self, *arguments: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(LAUNCHER),
                *arguments,
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def test_help_does_not_bootstrap_and_documents_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            env = dict(os.environ, LOCALAPPDATA=temporary)
            result = self._run("help", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dev|onnx|models|reset|help", result.stdout)
        self.assertIn("installed-product", result.stdout)

    def test_reset_helper_is_exactly_scoped_to_windows_development_credentials(self) -> None:
        helper = (ROOT / "scripts" / "reset_windows_dev_credentials.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('Path(local_app_data) / "SentriFace-Dev"', helper)
        self.assertIn('Path(local_app_data) / "SentriFace"', helper)
        self.assertIn("supplied != expected", helper)
        self.assertIn('"SentriFace Edge storage"', helper)
        self.assertIn('"SentriFace Edge disaster recovery"', helper)
        self.assertNotIn("CredEnumerate", helper)

    def test_launcher_refuses_product_authority_and_nested_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            product = Path(temporary) / "SentriFace"
            for target in (product, product / "nested"):
                env = dict(
                    os.environ,
                    LOCALAPPDATA=temporary,
                    SENTRIFACE_DEV_DATA_DIR=str(target),
                )
                result = self._run("help", env=env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("installed-product data directory", result.stderr)

    def test_reset_removes_only_default_development_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary)
            development = local / "SentriFace-Dev"
            production = local / "SentriFace"
            development.mkdir()
            production.mkdir()
            (development / "remove.txt").write_text("development", encoding="utf-8")
            (production / "preserve.txt").write_text("production", encoding="utf-8")
            env = dict(os.environ, LOCALAPPDATA=temporary)
            env.pop("SENTRIFACE_DEV_DATA_DIR", None)
            result = self._run("reset", "--yes", env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(development.exists())
            self.assertEqual(
                (production / "preserve.txt").read_text(encoding="utf-8"),
                "production",
            )

    def test_reset_refuses_custom_development_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            custom = Path(temporary) / "custom-development"
            custom.mkdir()
            marker = custom / "preserve.txt"
            marker.write_text("preserve", encoding="utf-8")
            env = dict(
                os.environ,
                LOCALAPPDATA=temporary,
                SENTRIFACE_DEV_DATA_DIR=str(custom),
            )
            result = self._run("reset", "--yes", env=env)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(marker.is_file())


if __name__ == "__main__":
    unittest.main()
