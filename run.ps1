# Windows source-development entry point. This deliberately uses a different
# authority root from the installed product so both can exist on one machine.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ProjectDir ".venv312"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$Mode = if ($args.Count -gt 0) { [string]$args[0] } else { "dev" }
$ModeArguments = @(if ($args.Count -gt 1) { $args[1..($args.Count - 1)] })
$LocalAppData = if ($env:LOCALAPPDATA) {
    $env:LOCALAPPDATA
} else {
    Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) ""
}

function Get-NormalizedPath([string]$Path) {
    return [IO.Path]::GetFullPath(
        [Environment]::ExpandEnvironmentVariables($Path)
    ).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
}

function Test-SameOrNestedPath([string]$First, [string]$Second) {
    if ($First.Equals($Second, [StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    $prefix = $Second + [IO.Path]::DirectorySeparatorChar
    return $First.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function Show-Usage {
    @"
Usage: .\run.ps1 [dev|onnx|models|reset|help] [model-setup options]

  dev     Start the synthetic, no-model source runtime (default).
  onnx    Start the real ONNX source runtime using this development authority.
  models  Install operator-supplied models into this development authority.
  reset   Remove only the default development authority after confirmation.

Set SENTRIFACE_DEV_DATA_DIR to use a different development authority. It must
not equal, contain, or be contained by the installed-product SentriFace data
directory. Reset intentionally refuses custom development locations.
"@ | Write-Host
}

$DefaultDevDataDir = Get-NormalizedPath (Join-Path $LocalAppData "SentriFace-Dev")
$ProductionDataDir = Get-NormalizedPath (Join-Path $LocalAppData "SentriFace")
$DevDataDir = if ($env:SENTRIFACE_DEV_DATA_DIR) {
    Get-NormalizedPath $env:SENTRIFACE_DEV_DATA_DIR
} else {
    $DefaultDevDataDir
}

if (
    (Test-SameOrNestedPath $DevDataDir $ProductionDataDir) -or
    (Test-SameOrNestedPath $ProductionDataDir $DevDataDir)
) {
    throw "Refusing to use or overlap the installed-product data directory for source development."
}

switch ($Mode.ToLowerInvariant()) {
    { $_ -in @("help", "-h", "--help") } {
        Show-Usage
        exit 0
    }
    { $_ -in @("dev", "onnx", "models", "reset") } {
        $Mode = $_
    }
    default {
        Write-Error "Unknown source-development mode: $Mode"
        Show-Usage
        exit 2
    }
}

if ($Mode -eq "reset") {
    if (-not $DevDataDir.Equals($DefaultDevDataDir, [StringComparison]::OrdinalIgnoreCase)) {
        throw (
            "For safety, reset is available only for the default SentriFace-Dev " +
            "data directory. Remove a custom SENTRIFACE_DEV_DATA_DIR only after " +
            "independently verifying its path."
        )
    }
    $expectedParent = Get-NormalizedPath $LocalAppData
    $actualParent = Get-NormalizedPath (Split-Path -Parent $DevDataDir)
    if (
        -not $actualParent.Equals($expectedParent, [StringComparison]::OrdinalIgnoreCase) -or
        (Split-Path -Leaf $DevDataDir) -ne "SentriFace-Dev"
    ) {
        throw "Refusing an unexpected development reset target: $DevDataDir"
    }
    if (Test-Path -LiteralPath $DevDataDir) {
        $item = Get-Item -LiteralPath $DevDataDir -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to reset a reparse-point development directory: $DevDataDir"
        }
    }
    if ($ModeArguments.Count -eq 0 -or $ModeArguments[0] -ne "--yes") {
        Write-Host "This removes only: $DevDataDir"
        $confirmation = Read-Host "Type RESET-DEV to continue"
        if ($confirmation -ne "RESET-DEV") {
            Write-Host "Development reset cancelled."
            exit 0
        }
    }
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    $CredentialPython = if (Test-Path -LiteralPath $Python -PathType Leaf) {
        $Python
    } elseif ($systemPython) {
        $systemPython.Source
    } else {
        $null
    }
    if (-not $CredentialPython) {
        throw "Python with the Windows keyring backend is required to remove the exact development vault identity safely."
    }
    & $CredentialPython (Join-Path $ProjectDir "scripts\reset_windows_dev_credentials.py") --data-dir $DevDataDir
    if ($LASTEXITCODE -ne 0) {
        throw "Development vault cleanup failed; filesystem state was preserved."
    }
    if (Test-Path -LiteralPath $DevDataDir) {
        Remove-Item -LiteralPath $DevDataDir -Recurse -Force
    }
    Write-Host "Removed SentriFace source-development data: $DevDataDir"
    exit 0
}

Set-Location $ProjectDir

if ((Test-Path -LiteralPath $VenvDir) -and -not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw (
        "The repository virtual environment is incomplete: $VenvDir`n" +
        "Remove only that virtual environment, then run .\run.ps1 again."
    )
}

function Test-SupportedPython([string]$Command, [string[]]$PrefixArguments) {
    try {
        & $Command @PrefixArguments -c (
            "import platform,struct,sys; " +
            "ok=(3,11)<=sys.version_info[:2]<=(3,12) and struct.calcsize('P')==8 " +
            "and platform.machine().lower() in {'amd64','x86_64'}; " +
            "raise SystemExit(0 if ok else 1)"
        ) *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    $Candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $Candidates += [pscustomobject]@{ Command = "py"; Prefix = @("-3.12") }
        $Candidates += [pscustomobject]@{ Command = "py"; Prefix = @("-3.11") }
    }
    foreach ($name in @("python3.12", "python3.11", "python")) {
        if (Get-Command $name -ErrorAction SilentlyContinue) {
            $Candidates += [pscustomobject]@{ Command = $name; Prefix = @() }
        }
    }
    foreach ($candidate in $Candidates) {
        if (Test-SupportedPython $candidate.Command $candidate.Prefix) {
            & $candidate.Command @($candidate.Prefix) -m venv $VenvDir
            if ($LASTEXITCODE -ne 0) {
                throw "Creating the repository virtual environment failed."
            }
            break
        }
    }
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw (
        "SentriFace Windows source development requires a 64-bit AMD64 Python " +
        "3.11 or 3.12 installation. Install one, then run .\run.ps1 again."
    )
}
if (-not (Test-SupportedPython $Python @())) {
    throw "The repository virtual environment must use 64-bit AMD64 Python 3.11 or 3.12: $Python"
}

$DependencyFiles = @(
    "pyproject.toml",
    "requirements-runtime.txt",
    "requirements-test.txt",
    "requirements-index.txt"
)
$FingerprintMaterial = foreach ($file in $DependencyFiles) {
    $digest = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
    "$file=$digest"
}
$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $fingerprintBytes = [Text.Encoding]::UTF8.GetBytes(($FingerprintMaterial -join "`n"))
    $DependencyFingerprint = ([BitConverter]::ToString(
        $sha256.ComputeHash($fingerprintBytes)
    )).Replace("-", "").ToLowerInvariant()
} finally {
    $sha256.Dispose()
}
$FingerprintFile = Join-Path $VenvDir ".sentriface-dependencies.sha256"
$DependenciesReady = $false
if (Test-Path -LiteralPath $FingerprintFile -PathType Leaf) {
    $recorded = (Get-Content -Raw -LiteralPath $FingerprintFile).Trim()
    if ($recorded -eq $DependencyFingerprint) {
        & $Python -c "import cv2, onnxruntime, pytest, sentriface, sqlcipher3" *> $null
        $DependenciesReady = $LASTEXITCODE -eq 0
    }
}
if (-not $DependenciesReady) {
    Write-Host "Installing or updating repository development dependencies..."
    & $Python -m pip install -e ".[test]"
    if ($LASTEXITCODE -ne 0) {
        throw "Installing repository development dependencies failed."
    }
    Set-Content -LiteralPath $FingerprintFile -Value $DependencyFingerprint -Encoding ascii
}

$env:SENTRIFACE_DATA_DIR = $DevDataDir
$env:SENTRIFACE_DEV_MODE = "1"
Write-Host "SentriFace source mode: $Mode"
Write-Host "Source-development data: $DevDataDir"
Write-Host "Installed-product data remains separate: $ProductionDataDir"

switch ($Mode) {
    "dev" {
        & $Python -m sentriface.ui --runtime dev --data-dir $DevDataDir @ModeArguments
    }
    "onnx" {
        & $Python -m sentriface.ui --runtime onnx --allow-unpackaged-source-onnx --data-dir $DevDataDir @ModeArguments
    }
    "models" {
        & $Python -m sentriface.model_setup --models-dir (Join-Path $DevDataDir "models") @ModeArguments
    }
}
exit $LASTEXITCODE
