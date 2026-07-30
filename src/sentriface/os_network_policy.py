from __future__ import annotations

import json
import os
import plistlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


WINDOWS_RULE_NAME = "SentriFaceEdge-BlockOutbound"


class OsNetworkPolicyError(RuntimeError):
    """Raised when production starts without a verifiable OS network boundary."""


@dataclass(frozen=True)
class OsNetworkPolicyStatus:
    enforced: bool
    mechanism: str
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "enforced": self.enforced,
            "mechanism": self.mechanism,
            "detail": self.detail,
        }


def inspect_os_network_policy(executable: Path | None = None) -> OsNetworkPolicyStatus:
    """Inspect active kernel/OS policy without generating any network traffic."""
    executable = (executable or Path(sys.executable)).resolve()
    if sys.platform == "win32":
        return _inspect_windows_firewall(executable)
    if sys.platform == "darwin":
        return _inspect_macos_sandbox(executable)
    if sys.platform.startswith("linux"):
        return _inspect_linux_systemd()
    return OsNetworkPolicyStatus(
        False,
        "unsupported-platform",
        f"No SentriFace OS network policy verifier exists for {sys.platform}",
    )


def require_os_network_policy(executable: Path | None = None) -> OsNetworkPolicyStatus:
    status = inspect_os_network_policy(executable)
    if not status.enforced:
        raise OsNetworkPolicyError(
            "SentriFace refused real-model startup because OS-enforced offline mode "
            f"is not active: {status.detail}"
        )
    return status


def _inspect_windows_firewall(executable: Path) -> OsNetworkPolicyStatus:
    if executable.name.casefold() in {"python.exe", "pythonw.exe", "py.exe"}:
        return OsNetworkPolicyStatus(
            False,
            "windows-firewall",
            "A standalone SentriFace executable is required; blocking a shared Python interpreter is unsafe",
        )
    escaped_executable = str(executable).replace("'", "''")
    command = (
        f"$rule=Get-NetFirewallRule -Name '{WINDOWS_RULE_NAME}' "
        "-PolicyStore ActiveStore -ErrorAction SilentlyContinue;"
        "if(-not $rule){exit 3};"
        "$app=$rule|Get-NetFirewallApplicationFilter;"
        "$payload=[ordered]@{"
        "enabled=[string]$rule.Enabled;"
        "direction=[string]$rule.Direction;"
        "action=[string]$rule.Action;"
        "program=[IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($app.Program))"
        "};$payload|ConvertTo-Json -Compress"
    )
    result = _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ]
    )
    if result.returncode != 0:
        return OsNetworkPolicyStatus(
            False,
            "windows-firewall",
            f"Active firewall rule {WINDOWS_RULE_NAME} was not found",
        )
    try:
        payload = json.loads(result.stdout)
        program = str(Path(payload["program"]).resolve())
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return OsNetworkPolicyStatus(False, "windows-firewall", "Firewall rule details were invalid")
    enforced = (
        payload.get("enabled") == "True"
        and payload.get("direction") == "Outbound"
        and payload.get("action") == "Block"
        and program.casefold() == str(executable).casefold()
    )
    return OsNetworkPolicyStatus(
        enforced,
        "windows-firewall",
        (
            f"Outbound initiation is blocked for {executable}"
            if enforced
            else f"Firewall rule does not match the running executable {executable}"
        ),
    )


def _inspect_macos_sandbox(executable: Path) -> OsNetworkPolicyStatus:
    result = _run(["/usr/bin/codesign", "-d", "--entitlements", ":-", str(executable)])
    raw = result.stdout or result.stderr
    start = raw.find("<?xml")
    end = raw.find("</plist>", start)
    if result.returncode != 0 or start < 0 or end < 0:
        return OsNetworkPolicyStatus(
            False,
            "macos-app-sandbox",
            "The running executable has no readable signed App Sandbox entitlements",
        )
    try:
        entitlements = plistlib.loads(raw[start:end + len("</plist>")].encode("utf-8"))
    except (plistlib.InvalidFileException, ValueError):
        return OsNetworkPolicyStatus(False, "macos-app-sandbox", "Signed entitlements were invalid")
    enforced = (
        entitlements.get("com.apple.security.app-sandbox") is True
        and entitlements.get("com.apple.security.network.server") is True
        and entitlements.get("com.apple.security.network.client") is not True
    )
    return OsNetworkPolicyStatus(
        enforced,
        "macos-app-sandbox",
        (
            "App Sandbox permits inbound server connections but denies client-initiated network access"
            if enforced
            else "App must enable App Sandbox and network.server without network.client"
        ),
    )


def _inspect_linux_systemd() -> OsNetworkPolicyStatus:
    try:
        cgroup = Path("/proc/self/cgroup").read_text(encoding="utf-8")
    except OSError as exc:
        return OsNetworkPolicyStatus(False, "systemd-ip-firewall", f"Cannot read process cgroup: {exc}")
    matches = re.findall(r"(?:^|/)([^/\n]+\.service)(?:/|$)", cgroup, re.MULTILINE)
    if not matches:
        return OsNetworkPolicyStatus(
            False,
            "systemd-ip-firewall",
            "Production must run inside the SentriFace systemd service",
        )
    unit = matches[-1]
    result = _run(
        [
            "systemctl",
            "show",
            unit,
            "--property=IPAddressDeny",
            "--property=IPAddressAllow",
            "--no-pager",
        ]
    )
    if result.returncode != 0:
        return OsNetworkPolicyStatus(False, "systemd-ip-firewall", f"Cannot inspect {unit}")
    properties = dict(
        line.split("=", 1)
        for line in result.stdout.splitlines()
        if "=" in line
    )
    denied = properties.get("IPAddressDeny", "")
    allowed = properties.get("IPAddressAllow", "")
    deny_all = "0.0.0.0/0" in denied and "::/0" in denied
    allow_loopback = "127.0.0.0/8" in allowed and "::1/128" in allowed
    enforced = deny_all and allow_loopback
    return OsNetworkPolicyStatus(
        enforced,
        "systemd-ip-firewall",
        (
            f"{unit} denies all IP traffic except loopback"
            if enforced
            else f"{unit} must set IPAddressDeny=any and IPAddressAllow=localhost"
        ),
    )


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(command, 127, "", str(exc))
