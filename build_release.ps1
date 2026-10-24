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
    [string]$CertificateSubject = $env:SENTRIFACE_SIGNING_SUBJECT,
    [ValidateSet("CurrentUser", "LocalMachine")]
    [string]$CertificateStoreLocation = $(
        if ($env:SENTRIFACE_SIGNING_STORE) { $env:SENTRIFACE_SIGNING_STORE } else { "CurrentUser" }
    ),
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
$AnySigningInput = [bool]($SignToolPath -or $CertificateThumbprint -or $CertificateSubject)
$SigningAvailable = [bool]($SignToolPath -and $CertificateThumbprint -and $CertificateSubject)
if ($AnySigningInput -and -not $SigningAvailable) {
    throw "Signing requires SignTool, an exact certificate thumbprint, and the expected signer subject."
}

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
    $signArguments = @("sign", "/s", "My", "/sha1", $CertificateThumbprint, "/fd", "SHA256")
    if ($CertificateStoreLocation -eq "LocalMachine") {
        $signArguments += "/sm"
    }
    if ($TimestampUrl) {
        $signArguments += @("/tr", $TimestampUrl, "/td", "SHA256")
    }
    $signArguments += $Path
    & $SignToolPath @signArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode signing failed for $(Split-Path -Leaf $Path)."
    }
    & $SignToolPath verify /pa /all $Path
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode verification failed for $(Split-Path -Leaf $Path)."
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if (
        $signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid -or
        -not $signature.SignerCertificate -or
        $signature.SignerCertificate.Thumbprint -ne $CertificateThumbprint -or
        $signature.SignerCertificate.Subject -ne $CertificateSubject
    ) {
        throw "Authenticode signer or trust verification failed for $(Split-Path -Leaf $Path)."
    }
}

function Assert-SigningCertificate {
    if (-not $SigningAvailable) {
        return
    }
    $normalizedThumbprint = $CertificateThumbprint.Replace(" ", "").ToUpperInvariant()
    if ($normalizedThumbprint -notmatch '^[0-9A-F]{40,64}$') {
        throw "The configured signing certificate thumbprint is invalid."
    }
    $script:CertificateThumbprint = $normalizedThumbprint
    $certificatePath = "Cert:\$CertificateStoreLocation\My\$normalizedThumbprint"
    $certificate = Get-Item -LiteralPath $certificatePath -ErrorAction Stop
    $codeSigningOid = "1.3.6.1.5.5.7.3.3"
    $hasCodeSigningEku = @($certificate.EnhancedKeyUsageList) |
        Where-Object { [string]$_.ObjectId -eq $codeSigningOid }
    if (
        -not $certificate.HasPrivateKey -or
        $certificate.Subject -ne $CertificateSubject -or
        -not $hasCodeSigningEku -or
        $certificate.NotBefore -gt (Get-Date) -or
        $certificate.NotAfter -le (Get-Date)
    ) {
        throw "The configured signing identity does not satisfy the exact subject, private-key, Code Signing EKU, and validity requirements."
    }
    if (-not ($certificate.PublicKey.Oid.Value -in @("1.2.840.113549.1.1.1", "1.2.840.113549.1.1.11"))) {
        throw "The configured signing certificate must use RSA."
    }
    $rsa = [Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey(
        $certificate
    )
    try {
        if (-not ($rsa -is [Security.Cryptography.RSACng]) -or $rsa.KeySize -lt 2048) {
            throw "The configured signing identity must use an RSA CNG key of at least 2048 bits."
        }
        if (
            ($rsa.Key.ExportPolicy -band [Security.Cryptography.CngExportPolicies]::AllowExport) -ne 0 -or
            ($rsa.Key.ExportPolicy -band [Security.Cryptography.CngExportPolicies]::AllowPlaintextExport) -ne 0
        ) {
            throw "The configured signing identity private key must be non-exportable."
        }
    } finally {
        if ($rsa) { $rsa.Dispose() }
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
$ExpectedTags = @("rc-v$Version", "release-v$Version")
# GitHub Actions checks out a detached HEAD. PowerShell returns $null for
# a native command with no output; never call .Trim() on that result.
# Candidate builds can run detached, but production tags/signatures remain strict.
$BranchOutput = @(git branch --show-current)
if ($LASTEXITCODE -ne 0) {
    throw "Git branch inspection failed."
}
$Branch = ""
if ($BranchOutput.Count -gt 0 -and $null -ne $BranchOutput[0]) {
    $Branch = ([string]$BranchOutput[0]).Trim()
}

if ($ProductionRelease) {
    if (git status --porcelain) {
        throw "Production release builds require a clean working tree."
    }
    $TagsAtHead = @(git tag --points-at HEAD)
    $AcceptedTagsAtHead = @($TagsAtHead | Where-Object { $_ -in $ExpectedTags })
    if ($LASTEXITCODE -ne 0 -or $AcceptedTagsAtHead.Count -ne 1) {
        throw "Production release builds require exactly one accepted tag: $($ExpectedTags -join ' or ')."
    }
    if (-not $SigningAvailable) {
        throw "Production release builds require SignTool, certificate thumbprint, and expected signer subject."
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
# ISCC.exe does not promise GNU-style --version stdout; on Actions this
# returned no text and .Trim() aborted the unsigned candidate before testing.
# Check the Windows executable's authoritative numeric file version instead.
$InnoFileVersion = (Get-Item -LiteralPath $InnoCompiler -ErrorAction Stop).VersionInfo
if (-not $InnoFileVersion -or $InnoFileVersion.FileMajorPart -lt 7) {
    throw "Inno Setup 7 or later is required for a native AMD64 setup executable."
}
if ($SigningAvailable -and -not (Test-Path -LiteralPath $SignToolPath -PathType Leaf)) {
    throw "Configured SignTool was not found."
}
Assert-SigningCertificate
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
        "-signed-pretag-rc"
    } else {
        "-unsigned-pretag-rc"
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
        Write-Host "Acceptance class: pre-tag RC-ready candidate (not the canonical rc-v$Version artifact)"
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
