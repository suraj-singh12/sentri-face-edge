"""Permanently remove SentriFace Edge from a Windows machine.

This is an intentionally destructive, Windows-only support utility.  It uses
only server-owned SentriFace paths and identifiers; environment overrides are
not accepted as deletion targets.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

if sys.platform == "win32":
    import winreg
else:  # Keep accidental non-Windows execution factual and non-destructive.
    winreg = None  # type: ignore[assignment]


PRODUCT_NAME = "SentriFace Edge"
DATA_DIRECTORY_NAME = "SentriFace"
INSTALL_DIRECTORY_NAME = "SentriFace Edge"
FIREWALL_RULE_NAME = "SentriFaceEdge-BlockOutbound"
LICENSE_REGISTRY_PATH = r"Software\SentriFaceEdge"
STORAGE_CREDENTIAL_TARGET = "SentriFace Edge storage"
UNINSTALL_REGISTRY_PATH = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    r"\{9B86BE35-3E8F-47F0-A9C2-A4CF4933B985}_is1"
)
CONFIRMATION = "WIPE SENTRIFACE"

ENTRY_POINTS = (
    "sentriface.exe",
    "sentriface-ui.exe",
    "sentriface-admin-reset.exe",
    "sentriface-models.exe",
)


def _known_environment_directory(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    path = Path(value).resolve()
    if path == Path(path.anchor):
        raise RuntimeError(f"Refusing unsafe {name} directory")
    return path


def _require_windows_administrator() -> None:
    if sys.platform != "win32":
        raise SystemExit("This cleanup utility runs only on Windows.")
    try:
        elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        elevated = False
    if not elevated:
        raise SystemExit(
            "Open Command Prompt or PowerShell as Administrator, then run this utility again."
        )


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    print(f"Removing: {path}")
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
    except OSError as exc:
        raise RuntimeError(f"Could not remove {path}: {exc}") from exc


def _request_graceful_shutdown(install_dir: Path | None) -> None:
    executable = install_dir / "SentriFaceEdge.exe" if install_dir else None
    if not executable or not executable.is_file():
        return
    print("Requesting graceful application shutdown...")
    subprocess.run(
        [str(executable), "--request-shutdown"],
        cwd=str(install_dir),
        check=False,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    time.sleep(2)


def _installed_uninstaller() -> Path | None:
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for access in (
            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0),
        ):
            try:
                with winreg.OpenKey(root, UNINSTALL_REGISTRY_PATH, 0, access) as key:
                    location, value_type = winreg.QueryValueEx(key, "InstallLocation")
            except (FileNotFoundError, OSError):
                continue
            if value_type != winreg.REG_SZ or not isinstance(location, str):
                continue
            install_dir = Path(location).resolve()
            if install_dir.name.casefold() != INSTALL_DIRECTORY_NAME.casefold():
                continue
            uninstallers = sorted(install_dir.glob("unins*.exe"))
            if len(uninstallers) == 1 and uninstallers[0].parent == install_dir:
                return uninstallers[0]
    return None


def _run_uninstaller(uninstaller: Path | None) -> None:
    if not uninstaller:
        return
    print("Removing the installed application...")
    result = subprocess.run(
        [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        check=False,
        timeout=180,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(f"The SentriFace uninstaller failed ({result.returncode}).")


def _delete_registry_tree(root: int, path: str, root_label: str) -> None:
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            children: list[str] = []
            index = 0
            while True:
                try:
                    children.append(winreg.EnumKey(key, index))
                    index += 1
                except OSError:
                    break
        for child in children:
            _delete_registry_tree(root, path + "\\" + child, root_label)
        winreg.DeleteKey(root, path)
        print(f"Removed registry state: {root_label}\\{path}")
    except FileNotFoundError:
        return


def _delete_storage_credential() -> None:
    # Python keyring's Windows backend stores this installation key as a
    # generic credential whose target is the fixed service name.
    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    delete = advapi32.CredDeleteW
    delete.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
    delete.restype = wintypes.BOOL
    if delete(STORAGE_CREDENTIAL_TARGET, 1, 0):  # CRED_TYPE_GENERIC
        print("Removed SentriFace storage key from Windows Credential Manager.")
        return
    error = ctypes.get_last_error()
    if error != 1168:  # ERROR_NOT_FOUND
        raise RuntimeError(f"Could not remove the SentriFace storage credential ({error}).")


def _remove_firewall_rule() -> None:
    command = (
        f"Get-NetFirewallRule -Name '{FIREWALL_RULE_NAME}' "
        "-ErrorAction SilentlyContinue | Remove-NetFirewallRule"
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        check=False,
        timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError("The SentriFace firewall rule could not be removed.")
    print("Removed the SentriFace-owned firewall rule (if present).")


def _remove_development_artifacts(local_app_data: Path | None) -> None:
    if not local_app_data:
        return
    python_root = local_app_data / "Programs" / "Python"
    if not python_root.is_dir():
        return
    for installation in python_root.glob("Python*"):
        site_packages = installation / "Lib" / "site-packages"
        if site_packages.is_dir():
            for pattern in (
                "sentriface_edge-*.dist-info",
                "__editable__.sentriface_edge-*.pth",
            ):
                for artifact in site_packages.glob(pattern):
                    _remove_path(artifact)
        scripts = installation / "Scripts"
        for name in ENTRY_POINTS:
            _remove_path(scripts / name)


def main() -> None:
    _require_windows_administrator()

    local_app_data = _known_environment_directory("LOCALAPPDATA")
    program_data = _known_environment_directory("PROGRAMDATA")
    program_files = _known_environment_directory("ProgramFiles")
    data_dir = local_app_data / DATA_DIRECTORY_NAME if local_app_data else None
    legacy_data_dir = program_data / PRODUCT_NAME if program_data else None
    install_dir = program_files / INSTALL_DIRECTORY_NAME if program_files else None

    print("=" * 72)
    print("WARNING: SENTRIFACE EDGE COMPLETE MACHINE WIPE")
    print("=" * 72)
    print(
        "This permanently removes the installed application, every local database, "
        "media file, model bundle, backup, recovery artifact, log, license, encryption "
        "key, and SentriFace-owned firewall rule for this Windows user."
    )
    print("\nNo SentriFace backup or recovery material on this machine will remain.")
    print("THIS ACTION CANNOT BE UNDONE.\n")
    if input(f"Type {CONFIRMATION} to continue: ") != CONFIRMATION:
        print("Cancelled. Nothing was deleted.")
        return

    uninstaller = _installed_uninstaller()
    _request_graceful_shutdown(install_dir)
    _run_uninstaller(uninstaller)

    # Credential removal happens before data removal so the exact current
    # per-user authority is deliberately destroyed as one cleanup operation.
    _delete_storage_credential()
    _delete_registry_tree(winreg.HKEY_CURRENT_USER, LICENSE_REGISTRY_PATH, "HKCU")

    for target in (data_dir, legacy_data_dir, install_dir):
        if target is not None:
            _remove_path(target)

    # Normally Inno Setup removes these. Exact fallback cleanup also covers a
    # damaged installation whose uninstaller is no longer present.
    _delete_registry_tree(
        winreg.HKEY_LOCAL_MACHINE,
        UNINSTALL_REGISTRY_PATH,
        "HKLM",
    )
    app_data = _known_environment_directory("APPDATA")
    public_dir = _known_environment_directory("PUBLIC")
    user_profile = _known_environment_directory("USERPROFILE")
    shortcut_targets = (
        (program_data / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "SentriFace Edge.lnk")
        if program_data else None,
        (app_data / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "SentriFace Edge.lnk")
        if app_data else None,
        (public_dir / "Desktop" / "SentriFace Edge.lnk") if public_dir else None,
        (user_profile / "Desktop" / "SentriFace Edge.lnk") if user_profile else None,
    )
    for shortcut in shortcut_targets:
        if shortcut is not None:
            _remove_path(shortcut)

    _remove_development_artifacts(local_app_data)
    _remove_firewall_rule()

    print("\n" + "=" * 72)
    print("SentriFace Edge installation and machine data were permanently removed.")
    print("=" * 72)


if __name__ == "__main__":
    main()
