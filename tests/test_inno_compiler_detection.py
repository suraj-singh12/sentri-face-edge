from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
pytestmark = pytest.mark.skipif(
    os.name != "nt" or not POWERSHELL, reason="Windows PowerShell is required"
)
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("banner", "exit_code", "accepted"),
    [
        ("Inno Setup 7 Command-Line Compiler", 0, True),
        ("Inno Setup 8 Command-Line Compiler", 0, True),
        ("Inno Setup 7 (32-bit) Command-Line Compiler", 0, True),
        ("Inno Setup 6.4.3 Command-Line Compiler", 0, False),
        ("", 0, False),
        ("unrecognized compiler", 0, False),
        ("Inno Setup 7 Command-Line Compiler", 1, False),
    ],
)
def test_compiler_banner_validation(
    tmp_path: Path, banner: str, exit_code: int, accepted: bool
) -> None:
    build = (ROOT / "build_release.ps1").read_text(encoding="utf-8")
    start = build.index("$InnoQueryErrorPreference =")
    end = build.index("if ($SigningAvailable -and", start)
    # A native command is essential: Windows PowerShell 5.1 treats native stderr
    # as ErrorRecords under Stop, even with redirection. ISCC /? writes help there.
    compiler = tmp_path / "fake-iscc.cmd"
    compiler.write_text(
        '@echo off\n'
        'if not "%~1"=="/?" exit /b 99\n'
        + (f"echo {banner}\n" if banner else "")
        + "echo Copyright (C) Jordan Russell\n"
        + "echo Usage: iscc [options] scriptfile.iss 1>&2\n"
        + f"exit /b {exit_code}\n",
        encoding="ascii",
    )
    compiler_literal = str(compiler).replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
$InnoCompiler = '{compiler_literal}'
try {{
{build[start:end]}
}} catch {{
    Write-Output $_.Exception.Message
    exit 1
}}
if ($ErrorActionPreference -ne 'Stop') {{ throw 'Error preference was not restored' }}
"""
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    if accepted:
        assert f"Validated compiler: {banner}" in result.stdout
