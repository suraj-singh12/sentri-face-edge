from pathlib import Path
import os
import shutil
import subprocess
import sys


TARGETS = [
    # Installed application data
    Path(os.environ.get("PROGRAMDATA", "")) / "SentriFace Edge",

    # User-local application data
    Path(os.environ.get("LOCALAPPDATA", "")) / "SentriFace",

    # Python development artifacts
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Programs"
    / "Python"
    / "Python312"
    / "Lib"
    / "site-packages"
    / "sentriface_edge-0.1.0.dist-info",

    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Programs"
    / "Python"
    / "Python312"
    / "Lib"
    / "site-packages"
    / "__editable__.sentriface_edge-0.1.0.pth",
]


SCRIPT_DIR = (
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Programs"
    / "Python"
    / "Python312"
    / "Scripts"
)


def remove_path(path: Path):
    if not path.exists():
        return

    print(f"Removing: {path}")

    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def main():
    print("=" * 70)
    print("WARNING: SENTRIFACE COMPLETE WIPE")
    print("=" * 70)
    print()
    print(
        "This operation will permanently remove ALL SentriFace related data "
        "found on this computer, including:"
    )
    print()
    print(" - Installed SentriFace application data")
    print(" - Database files")
    print(" - Backups")
    print(" - Logs")
    print(" - User data")
    print(" - Local Python SentriFace development artifacts")
    print()
    print("THIS ACTION CANNOT BE UNDONE.")
    print()

    confirmation = input(
        "Type WIPE SENTRIFACE to permanently continue: "
    )

    if confirmation != "WIPE SENTRIFACE":
        print("Cancelled. Nothing was deleted.")
        return

    print()
    print("Starting wipe...")
    print()

    for target in TARGETS:
        remove_path(target)

    # Remove Python command entry points
    if SCRIPT_DIR.exists():
        for exe in SCRIPT_DIR.glob("sentriface*.exe"):
            remove_path(exe)

    # Remove firewall rule
    try:
        subprocess.run(
            [
                "powershell",
                "-Command",
                "Remove-NetFirewallRule -Name 'SentriFaceEdge-BlockOutbound' "
                "-ErrorAction SilentlyContinue",
            ],
            creationflags=subprocess.CREATE_NO_WINDOW
            if sys.platform == "win32"
            else 0,
            check=False,
        )
        print("Removed firewall rule.")
    except Exception:
        print("Firewall rule removal skipped.")

    print()
    print("=" * 70)
    print("SentriFace wipe completed.")
    print("=" * 70)


if __name__ == "__main__":
    main()