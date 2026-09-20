[CmdletBinding()]
param(
    [switch]$DevelopmentBuild,
    [switch]$ProductionRelease,
    [switch]$UseExistingEnvironment,
    [string]$PythonExecutable = "python",
    [string]$DetectorTestModel = $env:SENTRIFACE_RELEASE_TEST_DETECTOR,
    [string]$RecognizerTestModel = $env:SENTRIFACE_RELEASE_TEST_RECOGNIZER,
    [string]$SignToolPath = $env:SENTRIFACE_SIGNTOOL,
    [string]$CertificateThumbprint = $env:SENTRIFACE_SIGNING_THUMBPRINT,
    [string]$TimestampUrl = $env:SENTRIFACE_TIMESTAMP_URL,
    [string]$InnoCompiler = $env:SENTRIFACE_ISCC
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if ($DevelopmentBuild -and $ProductionRelease) {
    throw "-DevelopmentBuild and -ProductionRelease cannot be combined."
}
$CandidateBuild = -not $ProductionRelease
$SigningAvailable = [bool](
    $SignToolPath -and $CertificateThumbprint -and $TimestampUrl
)

function Remove-ControlledDirectory([string]$Path) {
    $resolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $resolvedTarget = [IO.Path]::GetFullPath($Path).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $prefix = $resolvedRoot + [IO.Path]::DirectorySeparatorChar
    if (
        $resolvedTarget -eq $resolvedRoot -or
        -not $resolvedTarget.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "Refusing to remove a directory outside the repository: $resolvedTarget"
    }
    if (Test-Path -LiteralPath $resolvedTarget) {
        Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
    }
}

function Invoke-Checked([string]$Stage, [scriptblock]$Action) {
    Write-Host ""
    Write-Host "==> $Stage"
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Stage failed with exit code $LASTEXITCODE."
    }
}

function Invoke-Sign([string]$Path) {
    if (-not $SigningAvailable) {
        if ($ProductionRelease) {
            throw "Production release signing inputs are required."
        }
        return
    }
    & $SignToolPath sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $Path
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode signing failed for $(Split-Path -Leaf $Path)."
    }
    & $SignToolPath verify /pa /all $Path
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode verification failed for $(Split-Path -Leaf $Path)."
    }
}

if (
    -not [Environment]::Is64BitOperatingSystem -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne
        [Runtime.InteropServices.Architecture]::X64
) {
    throw "The supported release target is Windows x86-64 / AMD64 only."
}

$VersionSource = Get-Content -LiteralPath "src\sentriface\_version.py" -Raw
if ($VersionSource -notmatch 'APP_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"') {
    throw "The authoritative application version is invalid."
}
$Version = $Matches[1]
$VersionQuad = "$Version.0"
$ExpectedTag = "v$Version"
$Branch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Git branch inspection failed."
}

if ($ProductionRelease) {
    if (git status --porcelain) {
        throw "Production release builds require a clean working tree."
    }
    $TagsAtHead = @(git tag --points-at HEAD)
    if ($LASTEXITCODE -ne 0 -or $ExpectedTag -notin $TagsAtHead) {
        throw "Production release builds require the exact tag $ExpectedTag."
    }
    if (-not $SigningAvailable) {
        throw "Production release builds require SignTool, certificate thumbprint, and timestamp URL."
    }
} elseif ($Branch -notlike "release-*") {
    Write-Warning "Candidate builds are intended for a release-* branch; current branch is '$Branch'."
}

if (-not (Test-Path -LiteralPath "requirements-release.lock" -PathType Leaf)) {
    throw "requirements-release.lock is missing."
}
if (-not (Test-Path -LiteralPath "frontend\package-lock.json" -PathType Leaf)) {
    throw "frontend/package-lock.json is missing; npm ci cannot reproduce the UI."
}
if (-not $InnoCompiler) {
    $InnoCompiler = "C:\Program Files\Inno Setup 7\ISCC.exe"
}
if (-not (Test-Path -LiteralPath $InnoCompiler -PathType Leaf)) {
    throw "The Inno Setup 7 compiler was not found. Install the x64 edition or set SENTRIFACE_ISCC."
}
$InnoVersionText = (& $InnoCompiler --version).Trim()
try {
    $InnoVersion = [Version]$InnoVersionText
} catch {
    throw "The configured Inno compiler did not report a valid version."
}
if ($LASTEXITCODE -ne 0 -or $InnoVersion.Major -lt 7) {
    throw "Inno Setup 7 or later is required for a native AMD64 setup executable."
}
if ($SigningAvailable -and -not (Test-Path -LiteralPath $SignToolPath -PathType Leaf)) {
    throw "Configured SignTool was not found."
}
if ([bool]$DetectorTestModel -ne [bool]$RecognizerTestModel) {
    throw "Both detector and recognizer release-test models must be supplied together."
}
if ($DetectorTestModel) {
    $DetectorTestModel = (Resolve-Path -LiteralPath $DetectorTestModel).Path
    $RecognizerTestModel = (Resolve-Path -LiteralPath $RecognizerTestModel).Path
}

$BuildRoot = Join-Path $Root "build"
$OutputRoot = Join-Path $Root "dist\windows-x64\$Version"
Remove-ControlledDirectory $BuildRoot
Remove-ControlledDirectory $OutputRoot
New-Item -ItemType Directory -Path $BuildRoot, $OutputRoot -Force | Out-Null
$ReleasePipCache = Join-Path $BuildRoot "pip-cache"
$BuildLog = Join-Path $OutputRoot "build.log"
$ReleaseEnvironment = ""
$Succeeded = $false
Start-Transcript -LiteralPath $BuildLog -Force | Out-Null

try {
    if ($UseExistingEnvironment) {
        $ReleasePython = (Get-Command $PythonExecutable -ErrorAction Stop).Source
    } else {
        $ReleaseEnvironment = Join-Path $BuildRoot "release-venv"
        Invoke-Checked "Create isolated release environment" {
            & $PythonExecutable -m venv $ReleaseEnvironment
        }
        $ReleasePython = Join-Path $ReleaseEnvironment "Scripts\python.exe"
        Invoke-Checked "Install exact release dependency lock" {
            & $ReleasePython -m pip install --disable-pip-version-check --retries 5 --timeout 120 --cache-dir $ReleasePipCache --requirement requirements-release.lock
        }
    }

    Invoke-Checked "Install current SentriFace source without dependency re-resolution" {
        & $ReleasePython -m pip install --disable-pip-version-check --cache-dir $ReleasePipCache --no-build-isolation --no-deps .
    }

    Invoke-Checked "Verify locked AMD64 release environment" {
        & $ReleasePython scripts\verify_release_lock.py --lock requirements-release.lock
    }
    Invoke-Checked "Verify installed Python dependency consistency" {
        & $ReleasePython -m pip check
    }
    Invoke-Checked "Run backend regression suite" {
        & $ReleasePython -m pytest -q -p no:cacheprovider
    }
    Invoke-Checked "Install exact frontend dependency lock" {
        npm --prefix frontend ci --ignore-scripts
    }
    Invoke-Checked "Run frontend regression suite" {
        npm --prefix frontend test
    }
    Invoke-Checked "Build production frontend" {
        npm --prefix frontend run build
    }
    Invoke-Checked "Validate source whitespace" {
        git diff --check
    }
    if ($ProductionRelease) {
        Invoke-Checked "Verify tagged frontend assets" {
            git diff --exit-code -- src\sentriface\ui_static
        }
    }

    $NuitkaArgs = @(
        "--mode=standalone",
        "--output-dir=$BuildRoot",
        "--output-filename=SentriFaceEdge.exe",
        "--windows-console-mode=disable",
        "--windows-icon-from-ico=packaging\windows\SentriFace.ico",
        "--company-name=SentriFace",
        "--product-name=SentriFace Edge",
        "--file-description=SentriFace Edge offline recognition",
        "--file-version=$VersionQuad",
        "--product-version=$VersionQuad",
        "--include-package=sentriface",
        "--include-package=sqlcipher3",
        "--include-package=onnxruntime",
        "--include-package=cv2",
        "--include-package=keyring.backends.Windows",
        "--include-data-dir=src\sentriface\ui_static=sentriface\ui_static",
        "--nofollow-import-to=tkinter,hnswlib,qhnswlib",
        "--report=$BuildRoot\nuitka-report.xml",
        "src\sentriface\ui.py"
    )
    Invoke-Checked "Build Windows AMD64 standalone application" {
        & $ReleasePython -m nuitka @NuitkaArgs
    }

    $Distribution = Join-Path $BuildRoot "ui.dist"
    $NuitkaBuild = Join-Path $BuildRoot "ui.build"
    $Application = Join-Path $Distribution "SentriFaceEdge.exe"
    Invoke-Sign $Application

    $InspectionReport = Join-Path $OutputRoot "artifact-inspection.json"

    $RuntimeReport = Join-Path $OutputRoot "packaged-runtime.json"
    $SmokeArgs = @(
        "scripts\windows_packaged_smoke.py",
        "--distribution", $Distribution,
        "--version", $Version,
        "--report", $RuntimeReport
    )
    if ($DetectorTestModel) {
        $SmokeArgs += @(
            "--detector-model", $DetectorTestModel,
            "--recognizer-model", $RecognizerTestModel
        )
    }
    Invoke-Checked "Exercise packaged native runtime and owned cleanup" {
        & $ReleasePython @SmokeArgs
    }

    $DependencyReport = Join-Path $OutputRoot "dependency-inventory.json"
    Invoke-Checked "Derive bundled dependency and license inventory" {
        & $ReleasePython scripts\write_dependency_inventory.py --output $DependencyReport --build-dir $NuitkaBuild --distribution $Distribution --lockfile requirements-release.lock
    }

    $ArtifactSuffix = if ($ProductionRelease) {
        ""
    } elseif ($SigningAvailable) {
        "-rc"
    } else {
        "-unsigned-rc"
    }
    $ArtifactBase = "SentriFaceEdge-$Version-x64$ArtifactSuffix"
    Invoke-Checked "Build Inno Setup installer" {
        & $InnoCompiler "/DMyAppVersion=$Version" "/DMyAppVersionQuad=$VersionQuad" "/O$OutputRoot" "/F$ArtifactBase" "installer\SentriFaceEdge.iss"
    }
    $Installer = Join-Path $OutputRoot "$ArtifactBase.exe"
    Invoke-Sign $Installer

    Invoke-Checked "Inspect AMD64 installer and release content closure" {
        & $ReleasePython scripts\inspect_release_artifacts.py --distribution $Distribution --installer $Installer --version $Version --report $InspectionReport --forbidden-path $Root
    }

    $MetadataArguments = @(
        "scripts\write_release_metadata.py",
        "--version", $Version,
        "--installer", $Installer,
        "--application", $Application,
        "--inspection", $InspectionReport,
        "--runtime-report", $RuntimeReport,
        "--dependencies", $DependencyReport,
        "--lockfile", "requirements-release.lock"
    )
    if ($CandidateBuild) {
        $MetadataArguments += "--development"
    }
    if ($SigningAvailable) {
        $MetadataArguments += "--signed"
    }
    Invoke-Checked "Write release provenance" {
        & $ReleasePython @MetadataArguments
    }

    $InstallerDigest = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
    "$InstallerDigest  $(Split-Path -Leaf $Installer)" |
        Set-Content -LiteralPath "$Installer.sha256" -Encoding ascii
    $ChecksumPath = Join-Path $OutputRoot "checksums.sha256"
    Get-ChildItem -LiteralPath $OutputRoot -File |
        Where-Object { $_.FullName -ne $ChecksumPath -and $_.FullName -ne $BuildLog } |
        Sort-Object Name |
        ForEach-Object {
            $digest = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            "$digest  $($_.Name)"
        } | Set-Content -LiteralPath $ChecksumPath -Encoding ascii

    $Succeeded = $true
    Write-Host ""
    Write-Host "Validated Windows x64 installer: $Installer"
    if ($CandidateBuild) {
        Write-Host "Acceptance class: development/release candidate (not production accepted)"
    } else {
        Write-Host "Acceptance class: exact-tag Authenticode-signed production artifact"
    }
    if (-not $DetectorTestModel) {
        Write-Host "External model session acceptance: PENDING_NO_INPUTS"
    }
    Write-Host "Packaged model onboarding/activation/rollback: PENDING_NOT_EXERCISED"
} finally {
    Stop-Transcript | Out-Null
    if ($ReleaseEnvironment -and (Test-Path -LiteralPath $ReleaseEnvironment)) {
        Remove-ControlledDirectory $ReleaseEnvironment
    }
    if ($Succeeded -and (Test-Path -LiteralPath $BuildRoot)) {
        Remove-ControlledDirectory $BuildRoot
    }
}
