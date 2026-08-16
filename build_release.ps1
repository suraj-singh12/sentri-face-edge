[CmdletBinding()]
param(
    [switch]$DevelopmentBuild,
    [string]$SignToolPath = $env:SENTRIFACE_SIGNTOOL,
    [string]$CertificateThumbprint = $env:SENTRIFACE_SIGNING_THUMBPRINT,
    [string]$TimestampUrl = $env:SENTRIFACE_TIMESTAMP_URL,
    [string]$InnoCompiler = $env:SENTRIFACE_ISCC
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -notin @("AMD64", "ARM64")) {
    throw "The SentriFace release build requires 64-bit Windows with x64 compatibility."
}

$VersionSource = Get-Content -LiteralPath "src\sentriface\_version.py" -Raw
if ($VersionSource -notmatch 'APP_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"') {
    throw "The authoritative application version is invalid."
}
$Version = $Matches[1]
$VersionQuad = "$Version.0"

if (-not $DevelopmentBuild) {
    if (git status --porcelain) { throw "Release builds require a clean working tree." }
    $ExpectedTag = "v$Version"
    $TagsAtHead = @(git tag --points-at HEAD)
    if ($LASTEXITCODE -ne 0 -or $ExpectedTag -notin $TagsAtHead) {
        throw "Release builds require the exact tag $ExpectedTag."
    }
}

if (-not $InnoCompiler) {
    $InnoCompiler = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path -LiteralPath $InnoCompiler -PathType Leaf)) {
    throw "Inno Setup 6 was not found. Set SENTRIFACE_ISCC."
}

function Invoke-Sign([string]$Path) {
    if (-not $SignToolPath -or -not $CertificateThumbprint -or -not $TimestampUrl) {
        if ($DevelopmentBuild) { return }
        throw "Signing inputs are required for a release build."
    }
    & $SignToolPath sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $Path
    if ($LASTEXITCODE -ne 0) { throw "Authenticode signing failed." }
    & $SignToolPath verify /pa /all $Path
    if ($LASTEXITCODE -ne 0) { throw "Authenticode verification failed." }
}

if (Test-Path -LiteralPath "build") { Remove-Item -LiteralPath "build" -Recurse -Force }
if (Test-Path -LiteralPath "installer_output") { Remove-Item -LiteralPath "installer_output" -Recurse -Force }

python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
npm --prefix frontend test
if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }
npm --prefix frontend run build
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
if (-not $DevelopmentBuild) {
    git diff --exit-code -- src\sentriface\ui_static
    if ($LASTEXITCODE -ne 0) { throw "Generated frontend assets do not match tagged source." }
}

python -m nuitka `
    --mode=standalone `
    --output-dir=build `
    --output-filename=SentriFaceEdge.exe `
    --windows-console-mode=disable `
    --windows-icon-from-ico=packaging\windows\SentriFace.ico `
    --company-name="SentriFace" `
    --product-name="SentriFace Edge" `
    --file-description="SentriFace Edge offline recognition" `
    --file-version=$VersionQuad `
    --product-version=$VersionQuad `
    --include-package=sentriface `
    --include-package=sqlcipher3 `
    --include-package=onnxruntime `
    --include-package=cv2 `
    --include-package=keyring.backends.Windows `
    --include-data-dir=src\sentriface\ui_static=sentriface\ui_static `
    --nofollow-import-to=tkinter `
    src\sentriface\ui.py
if ($LASTEXITCODE -ne 0) { throw "Nuitka build failed." }

$Distribution = "build\ui.dist"
$Application = Join-Path $Distribution "SentriFaceEdge.exe"
python scripts\inspect_release_artifacts.py --distribution $Distribution --version $Version
if ($LASTEXITCODE -ne 0) { throw "Artifact inspection failed." }
python scripts\windows_packaged_smoke.py --distribution $Distribution --version $Version
if ($LASTEXITCODE -ne 0) { throw "Packaged executable smoke failed." }
Invoke-Sign $Application

& $InnoCompiler "/DMyAppVersion=$Version" "/DMyAppVersionQuad=$VersionQuad" "installer\SentriFaceEdge.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

$Installer = "installer_output\SentriFaceEdge-$Version-x64.exe"
Invoke-Sign $Installer
$Digest = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
"$Digest  $(Split-Path -Leaf $Installer)" | Set-Content -LiteralPath "$Installer.sha256" -Encoding ascii
$MetadataArguments = @("scripts\write_release_metadata.py", "--version", $Version, "--installer", $Installer)
if ($DevelopmentBuild) { $MetadataArguments += "--development" }
python @MetadataArguments
python scripts\write_dependency_inventory.py --output "installer_output\SentriFaceEdge-$Version-dependencies.json"

Write-Host "Release artifact: $Installer"
