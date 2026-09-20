"""Inventory or remove provably SentriFace-owned state from a Windows machine.

Dry-run inventory is the default. Destructive execution requires administrator
rights, --execute, and an exact interactive confirmation. Ambiguous legacy
credentials or firewall rules are reported and never deleted automatically.
"""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Iterable

if sys.platform == "win32":
    import winreg
else:
    winreg = None  # type: ignore[assignment]


PRODUCT_NAME = "SentriFace Edge"
DATA_DIRECTORY_NAME = "SentriFace"
INSTALL_DIRECTORY_NAME = "SentriFace Edge"
APPLICATION_EXE = "SentriFaceEdge.exe"
FIREWALL_RULE_NAME = "SentriFaceEdge-BlockOutbound"
FIREWALL_DISPLAY_NAME = "SentriFace Edge - deny outbound connections"
LICENSE_REGISTRY_PATH = r"Software\SentriFaceEdge"
STORAGE_CREDENTIAL_SERVICE = "SentriFace Edge storage"
RECOVERY_CREDENTIAL_SERVICE = "SentriFace Edge disaster recovery"
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


@dataclass(frozen=True)
class Resource:
    key: str
    kind: str
    description: str
    ownership: str
    exists: bool
    target: str


def _known_environment_directory(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    path = Path(value).resolve()
    if path == Path(path.anchor):
        raise RuntimeError(f"Refusing unsafe {name} directory")
    return path


def _account_for_data_dir(data_dir: Path) -> str:
    normalized = str(data_dir.resolve()).casefold().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def _credential_rows() -> list[dict[str, object]]:
    try:
        from win32ctypes.pywin32 import win32cred
    except ImportError:
        try:
            import win32cred  # type: ignore[no-redef]
        except ImportError as exc:
            raise RuntimeError(
                "Windows credential inventory requires the release keyring backend"
            ) from exc
    try:
        rows = win32cred.CredEnumerate()
    except Exception as exc:
        if getattr(exc, "winerror", None) == 1168:
            return []
        raise RuntimeError("Windows Credential Manager inventory failed") from exc
    return [
        {
            "TargetName": str(row.get("TargetName", "")),
            "UserName": str(row.get("UserName", "")),
            "Type": int(row.get("Type", 0)),
        }
        for row in rows
    ]


def _credential_resources(data_dir: Path) -> list[Resource]:
    account = _account_for_data_dir(data_dir)
    expected: dict[tuple[str, str], str] = {}
    for service in (STORAGE_CREDENTIAL_SERVICE, RECOVERY_CREDENTIAL_SERVICE):
        expected[(service.casefold(), account.casefold())] = service
        expected[(f"{account}@{service}".casefold(), account.casefold())] = service

    resources: list[Resource] = []
    for index, row in enumerate(_credential_rows()):
        target = str(row["TargetName"])
        username = str(row["UserName"])
        folded = target.casefold()
        if "sentriface" not in folded:
            continue
        service = expected.get((folded, username.casefold()))
        if service:
            resources.append(
                Resource(
                    key=f"credential:{service}",
                    kind="credential",
                    description=f"Exact default-installation {service} credential",
                    ownership="OWNED",
                    exists=True,
                    target=f"{service} / account {account[:12]}…",
                )
            )
        else:
            resources.append(
                Resource(
                    key=f"ambiguous-credential:{index}",
                    kind="credential",
                    description=(
                        "Legacy or non-default SentriFace-looking credential; ownership "
                        "cannot be proven from current default installation semantics"
                    ),
                    ownership="AMBIGUOUS",
                    exists=True,
                    target=target,
                )
            )
    return resources


def _registry_exists(root: int, path: str, access: int = 0) -> bool:
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | access):
            return True
    except FileNotFoundError:
        return False


def _firewall_resource(install_dir: Path | None) -> Resource:
    command = (
        "$rule=Get-NetFirewallRule -Name 'SentriFaceEdge-BlockOutbound' "
        "-PolicyStore ActiveStore -ErrorAction SilentlyContinue;"
        "if($rule){$app=$rule|Get-NetFirewallApplicationFilter;"
        "[ordered]@{Name=$rule.Name;DisplayName=$rule.DisplayName;"
        "Direction=[string]$rule.Direction;Action=[string]$rule.Action;"
        "Enabled=[string]$rule.Enabled;Program=$app.Program}|ConvertTo-Json -Compress};exit 0"
    )
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0 or completed.stderr.strip():
        detail = (completed.stderr or completed.stdout).strip()[-500:]
        raise RuntimeError(f"SentriFace firewall inventory failed: {detail}")
    if not completed.stdout.strip():
        return Resource(
            "firewall",
            "firewall",
            "Exact SentriFace outbound-deny firewall rule",
            "OWNED",
            False,
            FIREWALL_RULE_NAME,
        )
    payload = json.loads(completed.stdout)
    expected_program = (install_dir / APPLICATION_EXE).resolve() if install_dir else None
    try:
        actual_program = Path(
            os.path.expandvars(str(payload.get("Program", "")))
        ).resolve()
    except OSError:
        actual_program = None
    owned = (
        str(payload.get("Name")) == FIREWALL_RULE_NAME
        and str(payload.get("DisplayName")) == FIREWALL_DISPLAY_NAME
        and str(payload.get("Direction")) == "Outbound"
        and str(payload.get("Action")) == "Block"
        and str(payload.get("Enabled")) == "True"
        and expected_program is not None
        and actual_program == expected_program
    )
    return Resource(
        "firewall",
        "firewall",
        "Exact SentriFace outbound-deny firewall rule",
        "OWNED" if owned else "AMBIGUOUS",
        True,
        f"{FIREWALL_RULE_NAME} -> {actual_program or 'unresolved program'}",
    )


def _path_resource(key: str, description: str, path: Path | None) -> Resource:
    return Resource(
        key,
        "path",
        description,
        "OWNED",
        bool(path and (path.exists() or path.is_symlink())),
        str(path) if path else "unavailable",
    )


def _registry_resource(
    key: str,
    description: str,
    root: int,
    path: str,
    label: str,
    *,
    access: int = 0,
) -> Resource:
    return Resource(
        key,
        "registry",
        description,
        "OWNED",
        _registry_exists(root, path, access),
        f"{label}\\{path}",
    )


def _machine_paths() -> dict[str, Path | None]:
    local_app_data = _known_environment_directory("LOCALAPPDATA")
    program_data = _known_environment_directory("PROGRAMDATA")
    program_files = _known_environment_directory("ProgramFiles")
    app_data = _known_environment_directory("APPDATA")
    public_dir = _known_environment_directory("PUBLIC")
    user_profile = _known_environment_directory("USERPROFILE")
    return {
        "local_app_data": local_app_data,
        "program_data": program_data,
        "program_files": program_files,
        "data_dir": local_app_data / DATA_DIRECTORY_NAME if local_app_data else None,
        "legacy_data_dir": program_data / PRODUCT_NAME if program_data else None,
        "install_dir": program_files / INSTALL_DIRECTORY_NAME if program_files else None,
        "common_start": (
            program_data / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            / "SentriFace Edge.lnk"
        ) if program_data else None,
        "user_start": (
            app_data / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            / "SentriFace Edge.lnk"
        ) if app_data else None,
        "public_desktop": (
            public_dir / "Desktop" / "SentriFace Edge.lnk"
        ) if public_dir else None,
        "user_desktop": (
            user_profile / "Desktop" / "SentriFace Edge.lnk"
        ) if user_profile else None,
    }


def _development_resources(local_app_data: Path | None) -> list[Resource]:
    if local_app_data is None:
        return []
    python_root = local_app_data / "Programs" / "Python"
    if not python_root.is_dir():
        return []
    discovered: list[Path] = []
    for installation in sorted(python_root.glob("Python*")):
        site_packages = installation / "Lib" / "site-packages"
        if site_packages.is_dir():
            for pattern in (
                "sentriface_edge-*.dist-info",
                "__editable__.sentriface_edge-*.pth",
            ):
                discovered.extend(sorted(site_packages.glob(pattern)))
        scripts = installation / "Scripts"
        for name in ENTRY_POINTS:
            candidate = scripts / name
            if candidate.exists() or candidate.is_symlink():
                discovered.append(candidate)
    return [
        Resource(
            f"development-path:{index}",
            "development-path",
            "Exact discovered SentriFace development artifact",
            "OWNED",
            True,
            str(artifact),
        )
        for index, artifact in enumerate(discovered)
    ]

def inventory() -> list[Resource]:
    if sys.platform != "win32":
        raise SystemExit("This sanitization utility runs only on Windows.")
    paths = _machine_paths()
    data_dir = paths["data_dir"]
    if data_dir is None:
        raise RuntimeError("LOCALAPPDATA is unavailable; ownership cannot be established")
    resources = [
        _path_resource("install-dir", "Installed immutable application files", paths["install_dir"]),
        _path_resource("data-dir", "Current per-user data, models, backups, logs, and recovery state", data_dir),
        _path_resource("legacy-data-dir", "Exact legacy ProgramData preview authority", paths["legacy_data_dir"]),
        _path_resource("common-start", "Common Start Menu shortcut", paths["common_start"]),
        _path_resource("user-start", "Per-user Start Menu shortcut", paths["user_start"]),
        _path_resource("public-desktop", "Public desktop shortcut", paths["public_desktop"]),
        _path_resource("user-desktop", "Per-user desktop shortcut", paths["user_desktop"]),
        _registry_resource(
            "license-registry",
            "Per-user licensing and operational registry state",
            winreg.HKEY_CURRENT_USER,
            LICENSE_REGISTRY_PATH,
            "HKCU",
        ),
        _registry_resource(
            "uninstall-registry",
            "Inno Setup installation registration",
            winreg.HKEY_LOCAL_MACHINE,
            UNINSTALL_REGISTRY_PATH,
            "HKLM",
            access=getattr(winreg, "KEY_WOW64_64KEY", 0),
        ),
    ]
    resources.extend(_credential_resources(data_dir))
    resources.extend(_development_resources(paths["local_app_data"]))
    resources.append(_firewall_resource(paths["install_dir"]))
    return resources


def _require_windows_administrator() -> None:
    try:
        elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        elevated = False
    if not elevated:
        raise SystemExit(
            "Open Command Prompt or PowerShell as Administrator, then run with --execute."
        )


def _remove_path(path: Path | None) -> None:
    if path is None or (not path.exists() and not path.is_symlink()):
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def _delete_registry_tree(root: int, path: str, *, access: int = 0) -> None:
    flags = winreg.KEY_READ | winreg.KEY_WRITE | access
    try:
        with winreg.OpenKey(root, path, 0, flags) as key:
            children: list[str] = []
            index = 0
            while True:
                try:
                    children.append(winreg.EnumKey(key, index))
                    index += 1
                except OSError:
                    break
        for child in children:
            _delete_registry_tree(root, path + "\\" + child, access=access)
        winreg.DeleteKeyEx(root, path, access, 0)
    except AttributeError:
        try:
            winreg.DeleteKey(root, path)
        except FileNotFoundError:
            pass
    except FileNotFoundError:
        pass


def _installed_uninstaller(install_dir: Path | None) -> Path | None:
    if install_dir is None:
        return None
    for access in (
        getattr(winreg, "KEY_WOW64_64KEY", 0),
        getattr(winreg, "KEY_WOW64_32KEY", 0),
    ):
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                UNINSTALL_REGISTRY_PATH,
                0,
                winreg.KEY_READ | access,
            ) as key:
                location, value_type = winreg.QueryValueEx(key, "InstallLocation")
        except (FileNotFoundError, OSError):
            continue
        if value_type != winreg.REG_SZ or not isinstance(location, str):
            continue
        registered = Path(location).resolve()
        if registered != install_dir.resolve():
            continue
        uninstallers = sorted(registered.glob("unins*.exe"))
        if len(uninstallers) == 1 and uninstallers[0].parent == registered:
            return uninstallers[0]
    return None


def _request_graceful_shutdown(install_dir: Path | None) -> None:
    executable = install_dir / APPLICATION_EXE if install_dir else None
    if not executable or not executable.is_file():
        return
    subprocess.run(
        [str(executable), "--request-shutdown"],
        cwd=str(install_dir),
        check=False,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    time.sleep(2)


def _run_uninstaller(uninstaller: Path | None) -> None:
    if not uninstaller:
        return
    result = subprocess.run(
        [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        check=False,
        timeout=180,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise RuntimeError(f"The SentriFace uninstaller failed ({result.returncode}).")


def _delete_exact_credentials(data_dir: Path) -> None:
    import keyring
    from keyring.errors import PasswordDeleteError

    account = _account_for_data_dir(data_dir)
    for service in (STORAGE_CREDENTIAL_SERVICE, RECOVERY_CREDENTIAL_SERVICE):
        if keyring.get_password(service, account) is None:
            continue
        try:
            keyring.delete_password(service, account)
        except PasswordDeleteError as exc:
            raise RuntimeError(
                f"Exact owned credential could not be deleted: {service}"
            ) from exc
        if keyring.get_password(service, account) is not None:
            raise RuntimeError(
                f"Exact owned credential remains after deletion: {service}"
            )


def _remove_firewall_rule(resource: Resource) -> None:
    if not resource.exists:
        return
    if resource.ownership != "OWNED":
        raise RuntimeError("Ambiguous firewall state was preserved")
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "Get-NetFirewallRule -Name 'SentriFaceEdge-BlockOutbound' "
                "-ErrorAction Stop | Remove-NetFirewallRule"
            ),
        ],
        check=False,
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        raise RuntimeError("The exact SentriFace firewall rule could not be removed")



def _print_inventory(resources: Iterable[Resource], *, json_output: bool) -> None:
    resources = list(resources)
    if json_output:
        print(json.dumps([asdict(item) for item in resources], indent=2, sort_keys=True))
        return
    print("SentriFace Edge machine-state inventory")
    print("=" * 42)
    for item in resources:
        state = "present" if item.exists else "absent"
        print(f"[{item.ownership:9}] [{state:7}] {item.description}")
        print(f"  {item.target}")
    ambiguous = sum(item.exists and item.ownership == "AMBIGUOUS" for item in resources)
    print()
    print(f"Ambiguous resources preserved automatically: {ambiguous}")
    print("Dry run only. Nothing was changed.")


def execute(resources: list[Resource]) -> None:
    _require_windows_administrator()
    ambiguous = [item for item in resources if item.exists and item.ownership == "AMBIGUOUS"]
    if ambiguous:
        print("The following ambiguous resources will be preserved:")
        for item in ambiguous:
            print(f"  - {item.description}: {item.target}")
    print()
    print(
        "This permanently removes the installed application and all provably "
        "SentriFace-owned authority for the current Windows user."
    )
    if input(f"Type {CONFIRMATION} to continue: ") != CONFIRMATION:
        raise SystemExit("Cancelled. Nothing was deleted.")

    paths = _machine_paths()
    install_dir = paths["install_dir"]
    data_dir = paths["data_dir"]
    if data_dir is None:
        raise RuntimeError("LOCALAPPDATA is unavailable; refusing destructive execution")

    uninstaller = _installed_uninstaller(install_dir)
    _request_graceful_shutdown(install_dir)
    _run_uninstaller(uninstaller)
    _delete_exact_credentials(data_dir)
    _delete_registry_tree(winreg.HKEY_CURRENT_USER, LICENSE_REGISTRY_PATH)
    for key in (
        "data_dir",
        "legacy_data_dir",
        "install_dir",
        "common_start",
        "user_start",
        "public_desktop",
        "user_desktop",
    ):
        _remove_path(paths[key])
    _delete_registry_tree(
        winreg.HKEY_LOCAL_MACHINE,
        UNINSTALL_REGISTRY_PATH,
        access=getattr(winreg, "KEY_WOW64_64KEY", 0),
    )
    for item in resources:
        if item.kind == "development-path" and item.ownership == "OWNED":
            _remove_path(Path(item.target))
    firewall = next(item for item in resources if item.key == "firewall")
    _remove_firewall_rule(firewall)

    remaining = [
        item for item in inventory()
        if item.exists and item.ownership == "OWNED"
    ]
    if remaining:
        for item in remaining:
            print(f"FAILED TO REMOVE: {item.description}: {item.target}", file=sys.stderr)
        raise SystemExit(2)
    print("All provably SentriFace-owned machine state was removed.")
    if ambiguous:
        print(f"{len(ambiguous)} ambiguous resource(s) were intentionally preserved.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory SentriFace Windows state, or deliberately remove only "
            "provably owned state from a disposable/release-test machine."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help=f"delete owned state after typing the exact phrase {CONFIRMATION!r}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable inventory (dry run only)",
    )
    args = parser.parse_args()
    if args.execute and args.json:
        parser.error("--json is inventory-only and cannot be combined with --execute")
    resources = inventory()
    if args.execute:
        execute(resources)
    else:
        _print_inventory(resources, json_output=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
