from __future__ import annotations

import json
import plistlib
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.os_network_policy import (
    OsNetworkPolicyError,
    inspect_os_network_policy,
    require_os_network_policy,
)


class OsNetworkPolicyTest(unittest.TestCase):
    def test_windows_rejects_shared_python_interpreter(self) -> None:
        with patch("sentriface.os_network_policy.sys.platform", "win32"):
            status = inspect_os_network_policy(Path("python.exe"))
        self.assertFalse(status.enforced)
        self.assertIn("shared Python interpreter", status.detail)

    def test_windows_accepts_exact_active_outbound_block(self) -> None:
        executable = Path("sentriface.exe").resolve()
        payload = json.dumps({
            "enabled": "True",
            "direction": "Outbound",
            "action": "Block",
            "program": str(executable),
        })
        completed = subprocess.CompletedProcess([], 0, payload, "")
        with (
            patch("sentriface.os_network_policy.sys.platform", "win32"),
            patch("sentriface.os_network_policy._run", return_value=completed),
        ):
            status = inspect_os_network_policy(executable)
        self.assertTrue(status.enforced)
        self.assertEqual(status.mechanism, "windows-firewall")

    def test_macos_requires_server_only_app_sandbox(self) -> None:
        entitlements = plistlib.dumps({
            "com.apple.security.app-sandbox": True,
            "com.apple.security.network.server": True,
        }).decode("utf-8")
        completed = subprocess.CompletedProcess([], 0, "", entitlements)
        with (
            patch("sentriface.os_network_policy.sys.platform", "darwin"),
            patch("sentriface.os_network_policy._run", return_value=completed),
        ):
            status = inspect_os_network_policy(Path("/Applications/SentriFace.app"))
        self.assertTrue(status.enforced)
        self.assertEqual(status.mechanism, "macos-app-sandbox")

    def test_linux_requires_deny_any_and_allow_localhost(self) -> None:
        completed = subprocess.CompletedProcess(
            [],
            0,
            (
                "IPAddressDeny=0.0.0.0/0 ::/0\n"
                "IPAddressAllow=127.0.0.0/8 ::1/128\n"
            ),
            "",
        )
        with (
            patch("sentriface.os_network_policy.sys.platform", "linux"),
            patch(
                "sentriface.os_network_policy.Path.read_text",
                return_value="0::/system.slice/sentriface.service\n",
            ),
            patch("sentriface.os_network_policy._run", return_value=completed),
        ):
            status = inspect_os_network_policy()
        self.assertTrue(status.enforced)
        self.assertEqual(status.mechanism, "systemd-ip-firewall")

    def test_requirement_fails_closed_without_supported_policy(self) -> None:
        with (
            patch("sentriface.os_network_policy.sys.platform", "unknown"),
            self.assertRaises(OsNetworkPolicyError),
        ):
            require_os_network_policy()


if __name__ == "__main__":
    unittest.main()
