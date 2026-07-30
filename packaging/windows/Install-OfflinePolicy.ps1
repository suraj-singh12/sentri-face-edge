[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$ExecutablePath
)

$ErrorActionPreference = "Stop"
$ruleName = "SentriFaceEdge-BlockOutbound"
$resolved = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $ExecutablePath).Path)
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
}
