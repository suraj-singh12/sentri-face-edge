from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
pytestmark = pytest.mark.skipif(not POWERSHELL, reason="PowerShell is required")
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
def test_compiler_banner_validation(banner: str, exit_code: int, accepted: bool) -> None:
    build = (ROOT / "build_release.ps1").read_text(encoding="utf-8")
    start = build.index("$InnoBannerOutput =")
    end = build.index("if ($SigningAvailable -and", start)
    # Execute the production validation without building or changing the machine.
    # The fake command supplies ISCC's stdout and native exit code contract.
    script = f"""
$ErrorActionPreference = 'Stop'
function Invoke-FakeCompiler {{
    if ($args.Count -ne 1 -or $args[0] -ne '/?') {{ throw 'Expected /?' }}
    $global:LASTEXITCODE = {exit_code}
    if ('{banner}') {{ '{banner}' }}
    'Copyright (C) Jordan Russell'
}}
$InnoCompiler = 'Invoke-FakeCompiler'
try {{
{build[start:end]}
}} catch {{
    Write-Output $_.Exception.Message
    exit 1
}}
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
