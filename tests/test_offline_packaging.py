from __future__ import annotations

import plistlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OfflinePackagingTest(unittest.TestCase):
    def test_macos_entitlements_allow_server_but_not_network_client(self) -> None:
        with (ROOT / "packaging" / "macos" / "SentriFace.entitlements").open("rb") as source:
            entitlements = plistlib.load(source)
        self.assertIs(entitlements["com.apple.security.app-sandbox"], True)
        self.assertIs(entitlements["com.apple.security.network.server"], True)
        self.assertNotIn("com.apple.security.network.client", entitlements)

    def test_linux_service_denies_every_address_except_loopback(self) -> None:
        service = (ROOT / "packaging" / "linux" / "sentriface.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("IPAddressDeny=any", service)
        self.assertIn("IPAddressAllow=localhost", service)
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", service)
        self.assertIn("--data-dir /var/lib/sentriface", service)

    def test_windows_policy_is_exact_executable_outbound_block(self) -> None:
        script = (
            ROOT / "packaging" / "windows" / "Install-OfflinePolicy.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("-Direction Outbound", script)
        self.assertIn("-Program $resolved", script)
        self.assertIn("-Action Block", script)
        self.assertIn("Refusing to block a shared Python interpreter", script)
        self.assertIn("PolicyStore ActiveStore", script)
        self.assertIn("$installedProgram -ine $resolved", script)


if __name__ == "__main__":
    unittest.main()
