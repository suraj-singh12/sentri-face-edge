[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$CommercialInstaller,
    [Parameter(Mandatory=$true)][string]$ResearchInstaller,
    [string]$PreviousInstaller,
    [string]$PythonExecutable = "python",
    [string]$DataDir = (Join-Path $env:LOCALAPPDATA "SentriFace"),
    [string]$InstallDir = (Join-Path $env:ProgramFiles "SentriFace Edge"),
    [string]$Workspace = (Join-Path $env:TEMP "sentriface-installer-rehearsal"),
    [switch]$SkipInitialInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force -Path $Workspace | Out-Null

function Invoke-Setup([string]$Installer, [string]$Name, [switch]$ExpectFailure) {
    $log = Join-Path $Workspace "$Name-setup.log"
    $args = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=`"$log`"")
    $process = Start-Process -FilePath (Resolve-Path $Installer) -ArgumentList $args -Wait -PassThru
    if ($ExpectFailure) {
        if ($process.ExitCode -eq 0) { throw "$Name unexpectedly succeeded; downgrade refusal failed" }
        return
    }
    if ($process.ExitCode -ne 0) { throw "$Name failed with exit code $($process.ExitCode); see $log" }
}

function Invoke-Uninstall([string]$Name) {
    $uninstaller = Get-ChildItem -LiteralPath $InstallDir -Filter "unins*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $uninstaller) { throw "Uninstaller not found in $InstallDir" }
    $log = Join-Path $Workspace "$Name-uninstall.log"
    $args = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=`"$log`"")
    $process = Start-Process -FilePath $uninstaller.FullName -ArgumentList $args -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Uninstall failed with exit code $($process.ExitCode); see $log" }
}

function Save-State([string]$Name) {
    $output = Join-Path $Workspace "$Name.json"
    & $PythonExecutable (Join-Path $Root "scripts\capture_installation_state.py") --data-dir $DataDir --output $output | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not capture installation state $Name" }
    return $output
}

function Compare-State([string]$Before, [string]$After, [string]$Name) {
    $report = Join-Path $Workspace "$Name-comparison.json"
    & $PythonExecutable (Join-Path $Root "scripts\compare_installation_snapshots.py") $Before $After --report $report
    if ($LASTEXITCODE -ne 0) { throw "Data preservation comparison failed for $Name; see $report" }
}

function Assert-Populated([string]$Snapshot) {
    $state = Get-Content -Raw -LiteralPath $Snapshot | ConvertFrom-Json
    if (-not $state.tables.persons -or $state.tables.persons.row_count -lt 3) {
        throw "The installation is not a populated synthetic library. Populate disposable people/events/notes/relationships/media first, then rerun with -SkipInitialInstall. Never use real operator data."
    }
}

function Invoke-AppBriefly([int]$Seconds = 25) {
    $exe = Join-Path $InstallDir "SentriFaceEdge.exe"
    if (-not (Test-Path -LiteralPath $exe)) { throw "Installed executable is missing: $exe" }
    $previousDataDir = $env:SENTRIFACE_DATA_DIR
    $env:SENTRIFACE_DATA_DIR = $DataDir
    try {
        $process = Start-Process -FilePath $exe -WorkingDirectory $InstallDir -PassThru
        Start-Sleep -Seconds $Seconds
        & $exe --request-shutdown | Out-Null
        Start-Sleep -Seconds 5
        if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    } finally {
        if ($null -eq $previousDataDir) { Remove-Item Env:SENTRIFACE_DATA_DIR -ErrorAction SilentlyContinue } else { $env:SENTRIFACE_DATA_DIR = $previousDataDir }
    }
}

if (-not $SkipInitialInstall) {
    Invoke-Setup $CommercialInstaller "01-fresh-commercial"
}
$baseline = Save-State "01-baseline"
Assert-Populated $baseline

Invoke-Setup $CommercialInstaller "02-repair-commercial"
$repair = Save-State "02-after-repair"
Compare-State $baseline $repair "repair"

if (Test-Path -LiteralPath (Join-Path $DataDir "models\.model-authority\active.json")) {
    throw "The baseline already has an active model. Use a populated synthetic library without an active model so Research first-start provisioning is genuinely tested; test no-overwrite behavior as a separate scenario."
}
Invoke-Setup $ResearchInstaller "03-research-transition"
if (-not (Test-Path -LiteralPath (Join-Path $InstallDir "bundled-models\det_500m.onnx"))) { throw "Research payload is missing after transition" }
Invoke-AppBriefly
if (-not (Test-Path -LiteralPath (Join-Path $DataDir "models\.model-authority\active.json"))) { throw "Research first-start provisioning did not activate a model bundle" }
$research = Save-State "03-after-research"
Compare-State $repair $research "research-transition"

Invoke-Setup $CommercialInstaller "04-commercial-transition"
if (Test-Path -LiteralPath (Join-Path $InstallDir "bundled-models")) { throw "Commercial transition retained bundled Research payload" }
$commercial = Save-State "04-after-commercial"
Compare-State $research $commercial "commercial-transition"

Invoke-Uninstall "05-uninstall"
if (-not (Test-Path -LiteralPath (Join-Path $DataDir "sentriface.db"))) { throw "Uninstall removed the encrypted user database" }
Invoke-Setup $CommercialInstaller "06-reinstall-commercial"
Invoke-AppBriefly
$reinstalled = Save-State "06-after-reinstall"
Compare-State $commercial $reinstalled "reinstall-reconnect"

if ($PreviousInstaller) {
    Invoke-Setup $PreviousInstaller "07-downgrade" -ExpectFailure
}

Write-Host "Installer lifecycle rehearsal passed. Evidence: $Workspace"
Write-Host "Not automated here: interrupted installation and deliberately failed migration rehearsal; record those separately before release acceptance."
