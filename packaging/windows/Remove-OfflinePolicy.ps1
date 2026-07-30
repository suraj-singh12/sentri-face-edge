[CmdletBinding(SupportsShouldProcess)]
param()

$ruleName = "SentriFaceEdge-BlockOutbound"
if ($PSCmdlet.ShouldProcess($ruleName, "Remove SentriFace outbound-deny firewall rule")) {
    Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule
}
