param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("Commercial", "Research")]
    [string]$Variant,
    [Parameter(Mandatory=$true)]
    [string]$Installer,
    [Parameter(Mandatory=$true)]
    [string]$InstallDir,
    [Parameter(Mandatory=$true)]
    [string]$ReportPath
)

$ErrorActionPreference = "Stop"
$ResearchModels = @{
    "det_500m.onnx" = @{
        Size = 2524817
        Sha256 = "5e4447f50245bbd7966bd6c0fa52938c61474a04ec7def48753668a9d8b4ea3a"
    }
    "w600k_r50.onnx" = @{
        Size = 174383860
        Sha256 = "4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43"
    }
}

$errors = New-Object System.Collections.Generic.List[string]
$payloadRecords = @()
$installer = (Resolve-Path -LiteralPath $Installer).Path
$installLog = "$InstallDir-install.log"
$uninstallLog = "$InstallDir-uninstall.log"
if (Test-Path -LiteralPath $InstallDir) {
    Remove-Item -LiteralPath $InstallDir -Recurse -Force
}
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
$uninstallExit = $null

try {
    $installArguments = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="' + $installLog + '" /DIR="' + $InstallDir + '"'
    $installProcess = Start-Process -FilePath $installer -ArgumentList $installArguments -Wait -PassThru
    if ($installProcess.ExitCode -ne 0) {
        $errors.Add("Installer exited with code $($installProcess.ExitCode)")
    }
    if (-not (Test-Path -LiteralPath (Join-Path $InstallDir "SentriFaceEdge.exe") -PathType Leaf)) {
        $errors.Add("Installed SentriFaceEdge.exe is missing")
    }

    $onnxFiles = @(Get-ChildItem -LiteralPath $InstallDir -Recurse -File -Filter *.onnx -ErrorAction SilentlyContinue)
    if ($Variant -eq "Commercial") {
        if (Test-Path -LiteralPath (Join-Path $InstallDir "bundled-models")) {
            $errors.Add("Commercial installation contains a bundled model payload")
        }
        if ($onnxFiles.Count -ne 0) {
            $errors.Add("Commercial installation contains $($onnxFiles.Count) ONNX weight file(s)")
        }
    } else {
        $payloadDir = Join-Path $InstallDir "bundled-models"
        if (-not (Test-Path -LiteralPath $payloadDir -PathType Container)) {
            $errors.Add("Research bundled model payload is missing")
        } else {
            $payloadFiles = @(Get-ChildItem -LiteralPath $payloadDir -File)
            $payloadNames = @($payloadFiles | ForEach-Object { $_.Name } | Sort-Object)
            $requiredNames = @("det_500m.onnx", "research-model-provenance.json", "THIRD-PARTY-MODEL-NOTICE.txt", "w600k_r50.onnx")
            if (($payloadNames -join "`n") -ne ($requiredNames -join "`n")) {
                $errors.Add("Research payload does not contain exactly the approved files")
            }
            foreach ($name in $ResearchModels.Keys) {
                $path = Join-Path $payloadDir $name
                if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                    continue
                }
                $item = Get-Item -LiteralPath $path
                $digest = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
                if ($item.Length -ne $ResearchModels[$name].Size -or $digest -ne $ResearchModels[$name].Sha256) {
                    $errors.Add("Research model identity mismatch: $name")
                }
                $payloadRecords += [ordered]@{ path = $name; size = $item.Length; sha256 = $digest }
            }
        }
        if ($onnxFiles.Count -ne 2) {
            $errors.Add("Research installation contains $($onnxFiles.Count) ONNX weight file(s), expected exactly 2")
        }
    }
} finally {
    $uninstaller = Join-Path $InstallDir "unins000.exe"
    if (Test-Path -LiteralPath $uninstaller -PathType Leaf) {
        $uninstallArguments = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="' + $uninstallLog + '"'
        $uninstallProcess = Start-Process -FilePath $uninstaller -ArgumentList $uninstallArguments -Wait -PassThru
        $uninstallExit = $uninstallProcess.ExitCode
        if ($uninstallProcess.ExitCode -ne 0) {
            $errors.Add("Uninstaller exited with code $($uninstallProcess.ExitCode)")
        }
    } else {
        $errors.Add("Installed uninstaller is missing")
    }
    $rule = Get-NetFirewallRule -Name "SentriFaceEdge-BlockOutbound" -ErrorAction SilentlyContinue
    if ($rule) {
        $errors.Add("Offline firewall rule remained after uninstall")
    }
    $report = [ordered]@{
        contract = "sentriface.installed-variant-inspection"
        contract_version = 1
        status = $(if ($errors.Count -eq 0) { "PASS" } else { "FAIL" })
        variant = $Variant
        installer = Split-Path -Leaf $installer
        installer_sha256 = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
        uninstall_exit_code = $uninstallExit
        model_payload = $payloadRecords
        errors = $errors
    }
    $reportParent = Split-Path -Parent $ReportPath
    if ($reportParent) { New-Item -ItemType Directory -Path $reportParent -Force | Out-Null }
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding utf8
    if (Test-Path -LiteralPath $InstallDir) {
        Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
if ($errors.Count -ne 0) {
    $errors | ForEach-Object { Write-Error $_ }
    exit 1
}
Write-Host "$Variant installed-artifact inspection passed"
