from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.api_server import _startup_network_policy
from sentriface.os_network_policy import OsNetworkPolicyStatus


class MacosSourceRuntimeTest(unittest.TestCase):
    def test_override_requires_onnx_runtime(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires --runtime onnx"):
            _startup_network_policy("dev", allow_unpacked_source=True)

    def test_override_rejects_unsupported_platform(self) -> None:
        with (
            patch("sentriface.api_server.sys.platform", "freebsd"),
            self.assertRaisesRegex(ValueError, "only on Windows, macOS, and Linux"),
        ):
            _startup_network_policy("onnx", allow_unpacked_source=True)

    def test_override_requires_git_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("sentriface.api_server.sys.platform", "darwin"),
                self.assertRaisesRegex(ValueError, "Git checkout"),
            ):
                _startup_network_policy(
                    "onnx",
                    allow_unpacked_source=True,
                    source_root=Path(directory),
                )

    def test_git_checkout_can_explicitly_use_application_guard_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            (checkout / ".git").mkdir()
            status = OsNetworkPolicyStatus(False, "macos-app-sandbox", "not signed")
            with (
                patch("sentriface.api_server.sys.platform", "darwin"),
                patch("sentriface.api_server.inspect_os_network_policy", return_value=status),
            ):
                resolved = _startup_network_policy(
                    "onnx",
                    allow_unpacked_source=True,
                    source_root=checkout,
                )
            self.assertIsNone(resolved)

    def test_packaged_build_rejects_source_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            (checkout / ".git").mkdir()
            with (
                patch("sentriface.api_server.sys.platform", "darwin"),
                patch("sentriface.api_server.sys.frozen", True, create=True),
                self.assertRaisesRegex(ValueError, "unpackaged Git checkout"),
            ):
                _startup_network_policy(
                    "onnx",
                    allow_unpacked_source=True,
                    source_root=checkout,
                )
    def test_existing_macos_sandbox_remains_monitored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            (checkout / ".git").mkdir()
            status = OsNetworkPolicyStatus(True, "macos-app-sandbox", "enforced")
            with (
                patch("sentriface.api_server.sys.platform", "darwin"),
                patch("sentriface.api_server.inspect_os_network_policy", return_value=status),
            ):
                resolved = _startup_network_policy(
                    "onnx",
                    allow_unpacked_source=True,
                    source_root=checkout,
                )
            self.assertIs(resolved, status)

    def test_windows_git_checkout_can_explicitly_use_application_guard_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            (checkout / ".git").mkdir()
            status = OsNetworkPolicyStatus(False, "windows-firewall", "not installed")
            with (
                patch("sentriface.api_server.sys.platform", "win32"),
                patch("sentriface.api_server.inspect_os_network_policy", return_value=status),
            ):
                resolved = _startup_network_policy(
                    "onnx",
                    allow_unpacked_source=True,
                    source_root=checkout,
                )
            self.assertIsNone(resolved)


if __name__ == "__main__":
    unittest.main()
