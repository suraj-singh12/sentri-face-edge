[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Thumbprint,
    [string]$ExpectedSubject = "CN=SentriFace Edge Controlled Code Signing"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$normalizedThumbprint = $Thumbprint.Replace(" ", "").ToUpperInvariant()
if ($normalizedThumbprint -notmatch '^[0-9A-F]{40,64}$') {
    throw "The signing certificate thumbprint is invalid."
}
$sourcePath = "Cert:\CurrentUser\My\$normalizedThumbprint"
$certificate = Get-Item -LiteralPath $sourcePath -ErrorAction Stop
$codeSigningOid = "1.3.6.1.5.5.7.3.3"
$hasCodeSigningEku = @($certificate.EnhancedKeyUsageList) |
    Where-Object { [string]$_.ObjectId -eq $codeSigningOid }
if (
    $certificate.Subject -ne $ExpectedSubject -or
    -not $certificate.HasPrivateKey -or
    -not $hasCodeSigningEku -or
    $certificate.NotBefore -gt (Get-Date) -or
    $certificate.NotAfter -le (Get-Date)
) {
    throw "The exact certificate does not satisfy the expected subject, private-key, Code Signing EKU, and validity requirements."
}

$temporaryCertificate = Join-Path ([IO.Path]::GetTempPath()) (
    "sentriface-signing-public-{0}.cer" -f ([Guid]::NewGuid().ToString("N"))
)
try {
    Export-Certificate -Cert $certificate -FilePath $temporaryCertificate -Force | Out-Null
    Import-Certificate -FilePath $temporaryCertificate -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
    Import-Certificate -FilePath $temporaryCertificate -CertStoreLocation Cert:\CurrentUser\TrustedPublisher | Out-Null
} finally {
    if (Test-Path -LiteralPath $temporaryCertificate) {
        Remove-Item -LiteralPath $temporaryCertificate -Force
    }
}

$root = Get-Item -LiteralPath "Cert:\CurrentUser\Root\$normalizedThumbprint" -ErrorAction Stop
$publisher = Get-Item -LiteralPath "Cert:\CurrentUser\TrustedPublisher\$normalizedThumbprint" -ErrorAction Stop
if ($root.Subject -ne $ExpectedSubject -or $publisher.Subject -ne $ExpectedSubject) {
    throw "The trusted certificate copies do not match the expected signer."
}

[pscustomobject]@{
    Subject = $ExpectedSubject
    Thumbprint = $normalizedThumbprint
    TrustedRoot = $true
    TrustedPublisher = $true
    Scope = "CurrentUser"
} | ConvertTo-Json
