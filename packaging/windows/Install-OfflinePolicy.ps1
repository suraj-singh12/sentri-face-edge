[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [string]$ExecutablePath
)

$ErrorActionPreference = "Stop"
$ruleName = "SentriFaceEdge-BlockOutbound"
$resolved = [IO.Path]::GetFullPath($ExecutablePath)
$filename = [IO.Path]::GetFileName($resolved)
if ($filename -in @("python.exe", "pythonw.exe", "py.exe")) {
    throw "Refusing to block a shared Python interpreter. Supply the packaged SentriFace executable."
}

if ($PSCmdlet.ShouldProcess($resolved, "Install outbound-deny firewall rule")) {
    Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule
    New-NetFirewallRule `
        -Name $ruleName `
        -DisplayName "SentriFace Edge - deny outbound connections" `
        -Description "Blocks SentriFace from initiating network connections. The local UI connects inbound over loopback." `
        -Direction Outbound `
        -Program $resolved `
        -Action Block `
        -Profile Any `
        -Enabled True | Out-Null

    $rule = Get-NetFirewallRule -Name $ruleName -PolicyStore ActiveStore -ErrorAction Stop
    $application = $rule | Get-NetFirewallApplicationFilter
    $installedProgram = [IO.Path]::GetFullPath(
        [Environment]::ExpandEnvironmentVariables($application.Program)
    )
    if (
        [string]$rule.Enabled -ne "True" -or
        [string]$rule.Direction -ne "Outbound" -or
        [string]$rule.Action -ne "Block" -or
        $installedProgram -ine $resolved
    ) {
        Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue |
            Remove-NetFirewallRule
        throw "The SentriFace outbound firewall rule could not be verified."
    }
}
