from __future__ import annotations

import base64
import hashlib
import re
import sys
from collections.abc import Callable


FINGERPRINT_NAMESPACE = "sentriface-edge|machine-fingerprint-v2|"
_GUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class MachineFingerprintError(RuntimeError):
    """Raised when Windows cannot provide its stable installation identifier."""


def _read_windows_machine_guid() -> str:
    if sys.platform != "win32":
        raise MachineFingerprintError("Machine licensing is available only on Windows")
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
        ) as key:
            value, value_type = winreg.QueryValueEx(key, "MachineGuid")
    except (OSError, ImportError) as exc:
        raise MachineFingerprintError("Windows machine identity is unavailable") from exc
    if value_type not in {winreg.REG_SZ, winreg.REG_EXPAND_SZ} or not isinstance(value, str):
        raise MachineFingerprintError("Windows machine identity has an invalid registry type")
    return value


def windows_machine_fingerprint(
    *,
    machine_guid_reader: Callable[[], str] | None = None,
) -> str:
    """Return the versioned public fingerprint without exposing the raw GUID."""
    raw = (machine_guid_reader or _read_windows_machine_guid)()
    normalized = str(raw).strip().strip("{}").casefold()
    if not _GUID_PATTERN.fullmatch(normalized):
        raise MachineFingerprintError("Windows machine identity is malformed")
    digest = hashlib.sha256((FINGERPRINT_NAMESPACE + normalized).encode("ascii")).digest()
    encoded = base64.b32encode(digest[:15]).decode("ascii").rstrip("=")
    return "SFE-MC-" + "-".join(encoded[index:index + 5] for index in range(0, len(encoded), 5))
