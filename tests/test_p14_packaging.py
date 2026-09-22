from __future__ import annotations

import struct
import tempfile
import unittest
from email.message import Message
from pathlib import Path

from sentriface import __version__
from sentriface._version import APP_VERSION
from sentriface.licensing.public_keys import production_public_keys
from sentriface.runtime_hardening import WindowsShutdownSignal
from scripts.inspect_release_artifacts import inspect, inspect_distribution
from scripts.write_dependency_inventory import _package_record


ROOT = Path(__file__).resolve().parents[1]


def _write_pe(path: Path, machine: int = 0x8664) -> None:
    payload = bytearray(70)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 64)
    payload[64:68] = b"PE\x00\x00"
    struct.pack_into("<H", payload, 68, machine)
    path.write_bytes(payload)


class _DistributionFixture:
    def __init__(self, metadata: Message, version: str = "1.0") -> None:
        self.metadata = metadata
        self.version = version


class P14PackagingContractTest(unittest.TestCase):
    def test_dependency_inventory_uses_license_classifier_when_fields_are_absent(self) -> None:
        metadata = Message()
        metadata["Name"] = "example-package"
        metadata["Classifier"] = "License :: OSI Approved :: MIT License"
        record = _package_record(_DistributionFixture(metadata))  # type: ignore[arg-type]
        self.assertEqual(record["license"], "MIT License")

    def test_one_release_version_authority_drives_python_build_and_installer(self) -> None:
        self.assertEqual(__version__, APP_VERSION)
        self.assertEqual(APP_VERSION, "2.0.0")
        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+$")
        build = (ROOT / "build_release.ps1").read_text(encoding="utf-8")
        installer = (ROOT / "installer" / "SentriFaceEdge.iss").read_text(encoding="utf-8")
        self.assertIn("src\\sentriface\\_version.py", build)
        self.assertIn('/DMyAppVersion=$Version', build)
        self.assertIn("#error MyAppVersion must be supplied", installer)
        self.assertNotIn('#define MyAppVersion "', installer)

    def test_release_tag_guard_fails_cleanly_without_git_describe(self) -> None:
        build = (ROOT / "build_release.ps1").read_text(encoding="utf-8")
        self.assertIn("git tag --points-at HEAD", build)
        self.assertIn('"rc-v$Version", "release-v$Version"', build)
        self.assertIn("$AcceptedTagsAtHead.Count -ne 1", build)
        self.assertNotIn('$ExpectedTag = "v$Version"', build)
        self.assertNotIn("git describe", build)

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

    def test_one_command_build_uses_locked_isolated_evidence_pipeline(self) -> None:
        build = (ROOT / "build_release.ps1").read_text(encoding="utf-8")
        self.assertIn("requirements-release.lock", build)
        self.assertIn("frontend\\package-lock.json", build)
        self.assertIn("npm --prefix frontend ci", build)
        self.assertIn("scripts\\verify_release_lock.py", build)
        self.assertIn("scripts\\inspect_release_artifacts.py", build)
        self.assertIn("scripts\\windows_packaged_smoke.py", build)
        self.assertIn("scripts\\write_dependency_inventory.py", build)
        self.assertIn("dist\\windows-x64\\$Version", build)
        self.assertIn("$ProductionRelease", build)
        self.assertIn("$AcceptedTagsAtHead.Count -ne 1", build)
        self.assertNotIn("installer_output", build)
        self.assertIn("Inno Setup 7 or later", build)
        self.assertIn("Install current SentriFace source", build)
        self.assertIn("-p no:cacheprovider", build)
        self.assertIn("--installer", build)

    def test_controlled_machine_signing_uses_exact_nonexportable_identity(self) -> None:
        build = (ROOT / "build_release.ps1").read_text(encoding="utf-8")
        create = (
            ROOT / "packaging" / "windows" / "New-SentriFaceCodeSigningCertificate.ps1"
        ).read_text(encoding="utf-8")
        trust = (
            ROOT / "packaging" / "windows" / "Trust-SentriFaceCodeSigningCertificate.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("CertificateSubject", build)
        self.assertIn("CertificateThumbprint", build)
        self.assertIn("Get-AuthenticodeSignature", build)
        self.assertIn('"-signed-pretag-rc"', build)
        self.assertIn("KeyAlgorithm RSA", create)
        self.assertIn("HashAlgorithm SHA256", create)
        self.assertIn("KeyExportPolicy NonExportable", create)
        self.assertIn("AllowPlaintextExport", create)
        self.assertIn("private key must be non-exportable", build)
        self.assertNotIn("Export-PfxCertificate", create)
        self.assertIn("Cert:\\CurrentUser\\Root", trust)
        self.assertIn("Cert:\\CurrentUser\\TrustedPublisher", trust)
        self.assertIn("ExpectedSubject", trust)

    def test_build_excludes_models_and_requires_native_runtime_components(self) -> None:
        build = (ROOT / "build_release.ps1").read_text(encoding="utf-8")
        self.assertIn("--mode=standalone", build)
        for package in ("sqlcipher3", "onnxruntime", "cv2", "keyring.backends.Windows"):
            self.assertIn(f"--include-package={package}", build)
        self.assertNotIn("packaging\\runtime\\core", build)
        self.assertNotIn("--include-data-file", build)

    def test_installer_is_native_amd64_and_excludes_arm64_hosts(self) -> None:
        installer_source = (ROOT / "installer" / "SentriFaceEdge.iss").read_text(
            encoding="utf-8"
        )
        self.assertIn("SetupArchitecture=x64", installer_source)
        self.assertIn("ArchitecturesAllowed=x64os", installer_source)
        self.assertIn("ArchitecturesInstallIn64BitMode=x64os", installer_source)
        self.assertNotIn("x64compatible", installer_source)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            distribution = root / "distribution"
            distribution.mkdir()
            for name in (
                "SentriFaceEdge.exe",
                "sentriface.pyd",
                "onnxruntime.dll",
                "cv2.pyd",
                "sqlcipher3.pyd",
            ):
                _write_pe(distribution / name)
            setup = root / "setup.exe"
            _write_pe(setup)
            report = inspect_distribution(
                distribution,
                APP_VERSION,
                installer=setup,
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["installer"]["architecture"], "AMD64")
            _write_pe(setup, 0x014C)
            report = inspect_distribution(
                distribution,
                APP_VERSION,
                installer=setup,
            )
            self.assertTrue(
                any("installer architecture I386" in error for error in report["errors"])
            )

    def test_firewall_install_is_exact_and_self_verifying(self) -> None:
        script = (ROOT / "packaging" / "windows" / "Install-OfflinePolicy.ps1").read_text(encoding="utf-8")
        for text in ('Direction = "Outbound"', 'Program = $resolved', 'Action = "Block"', "PolicyStore ActiveStore", "$installedProgram -ine $resolved"):
            self.assertIn(text, script)
        installer = (ROOT / "installer" / "SentriFaceEdge.iss").read_text(encoding="utf-8")
        self.assertIn("ExtractTemporaryFile('Install-OfflinePolicy.ps1')", installer)
        self.assertIn("function PrepareToInstall", installer)
        self.assertIn("SentriFace offline firewall setup or verification failed. Diagnostic log:", installer)
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
                _write_pe(distribution / name)
            self.assertEqual(inspect(distribution, APP_VERSION), [])
            _write_pe(distribution / "unexpected-x86.dll", 0x014C)
            self.assertTrue(any("unexpected Windows PE architecture I386" in item for item in inspect(distribution, APP_VERSION)))
            (distribution / "unexpected-x86.dll").unlink()
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
