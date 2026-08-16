from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sentriface import __version__
from sentriface._version import APP_VERSION
from sentriface.licensing.public_keys import production_public_keys
from sentriface.runtime_hardening import WindowsShutdownSignal
from scripts.inspect_release_artifacts import inspect


ROOT = Path(__file__).resolve().parents[1]


class P14PackagingContractTest(unittest.TestCase):
    def test_one_release_version_authority_drives_python_build_and_installer(self) -> None:
        self.assertEqual(__version__, APP_VERSION)
        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+$")
        build = (ROOT / "build_release.ps1").read_text(encoding="utf-8")
        installer = (ROOT / "installer" / "SentriFaceEdge.iss").read_text(encoding="utf-8")
        self.assertIn("src\\sentriface\\_version.py", build)
        self.assertIn('/DMyAppVersion=$Version', build)
        self.assertIn("#error MyAppVersion must be supplied", installer)
        self.assertNotIn('#define MyAppVersion "', installer)

    def test_installer_preserves_per_user_authority_and_has_no_activation_helper(self) -> None:
        installer = (ROOT / "installer" / "SentriFaceEdge.iss").read_text(encoding="utf-8")
        folded = installer.casefold()
        self.assertIn("defaultdirname={autopf}\\sentriface edge", folded)
        self.assertNotIn("programdata", folded)
        self.assertNotIn("commonappdata", folded)
        self.assertNotIn("activation", folded)
        self.assertNotIn("[dirs]", folded)
        self.assertIn("--request-shutdown", installer)
        self.assertIn("downgrades are not supported", folded)
        self.assertIn("removesentrifacefirewall", folded)
        self.assertIn("procedure deinitializesetup", folded)
        self.assertIn("previousinstallation", folded)

    def test_build_excludes_models_and_requires_native_runtime_components(self) -> None:
        build = (ROOT / "build_release.ps1").read_text(encoding="utf-8")
        self.assertIn("--mode=standalone", build)
        for package in ("sqlcipher3", "onnxruntime", "cv2", "keyring.backends.Windows"):
            self.assertIn(f"--include-package={package}", build)
        self.assertNotIn("packaging\\runtime\\core", build)
        self.assertNotIn("--include-data-file", build)

    def test_firewall_install_is_exact_and_self_verifying(self) -> None:
        script = (ROOT / "packaging" / "windows" / "Install-OfflinePolicy.ps1").read_text(encoding="utf-8")
        for text in ("-Direction Outbound", "-Program $resolved", "-Action Block", "PolicyStore ActiveStore", "$installedProgram -ine $resolved"):
            self.assertIn(text, script)
        installer = (ROOT / "installer" / "SentriFaceEdge.iss").read_text(encoding="utf-8")
        self.assertIn("ExtractTemporaryFile('Install-OfflinePolicy.ps1')", installer)
        self.assertIn("function PrepareToInstall", installer)
        self.assertIn("Result := 'SentriFace offline firewall setup or verification failed.'", installer)
        self.assertNotIn("ssPostInstall then InstallOfflinePolicy", installer)

        self.assertIn('Flags: dontcopy', installer)
        self.assertNotIn('-File ""', installer.split('[Code]', 1)[1])
    def test_public_trust_root_contains_only_ed25519_public_bytes(self) -> None:
        keys = production_public_keys()
        self.assertEqual(set(keys), {"prod-2026-01"})
        self.assertEqual(len(keys["prod-2026-01"]), 32)
        source = (ROOT / "src" / "sentriface" / "licensing" / "public_keys.py").read_text(encoding="utf-8")
        self.assertNotIn("PRIVATE KEY", source)
        self.assertNotIn("private_key", source.casefold())

    def test_artifact_inspector_refuses_model_weights_and_private_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            distribution = Path(temporary)
            for name in ("SentriFaceEdge.exe", "sentriface.pyd", "onnxruntime.dll", "cv2.pyd", "sqlcipher3.pyd"):
                (distribution / name).write_bytes(b"safe")
            self.assertEqual(inspect(distribution, APP_VERSION), [])
            (distribution / "detector.onnx").write_bytes(b"weights")
            self.assertTrue(any("forbidden release content" in item for item in inspect(distribution, APP_VERSION)))
            (distribution / "detector.onnx").unlink()
            (distribution / "secret.txt").write_bytes(b"-----BEGIN PRIVATE KEY-----")
            self.assertTrue(any("private key material" in item for item in inspect(distribution, APP_VERSION)))

    def test_installer_shutdown_signal_name_does_not_leak_data_path(self) -> None:
        signal = WindowsShutdownSignal(Path("C:/Users/Secret/AppData/Local/SentriFace"))
        self.assertTrue(signal.name.startswith("Local\\SentriFaceEdge-Shutdown-"))
        self.assertNotIn("Secret", signal.name)


if __name__ == "__main__":
    unittest.main()
