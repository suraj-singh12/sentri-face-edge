[CmdletBinding()]
param(
    [string]$Subject = "CN=SentriFace Edge Controlled Code Signing",
    [ValidateRange(1, 10)]
    [int]$ValidityYears = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$codeSigningOid = "1.3.6.1.5.5.7.3.3"
$now = Get-Date
$existing = @(
    Get-ChildItem -Path Cert:\CurrentUser\My |
        Where-Object {
            $_.Subject -eq $Subject -and
            $_.HasPrivateKey -and
            $_.NotBefore -le $now -and
            $_.NotAfter -gt $now -and
            (@($_.EnhancedKeyUsageList) | Where-Object {
                [string]$_.ObjectId -eq $codeSigningOid
            })
        }
)
if ($existing.Count -gt 1) {
    throw "More than one valid signing certificate has the exact subject '$Subject'. Select and remove the unintended identity before continuing."
}
if ($existing.Count -eq 1) {
    $certificate = $existing[0]
    Write-Host "Reusing the existing non-file signing identity."
} else {
    $certificate = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $Subject `
        -FriendlyName "SentriFace Edge controlled-machine Authenticode" `
        -CertStoreLocation Cert:\CurrentUser\My `
        -KeyAlgorithm RSA `
        -KeyLength 3072 `
        -HashAlgorithm SHA256 `
        -KeyExportPolicy NonExportable `
        -KeyUsage DigitalSignature `
        -NotAfter $now.AddYears($ValidityYears)
    Write-Host "Created a stable non-exportable Windows code-signing identity."
}

$rsa = [Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey(
    $certificate
)
try {
    if (-not ($rsa -is [Security.Cryptography.RSACng]) -or $rsa.KeySize -lt 2048) {
        throw "The signing identity must use an RSA CNG key of at least 2048 bits."
    }
    if (
        ($rsa.Key.ExportPolicy -band [Security.Cryptography.CngExportPolicies]::AllowExport) -ne 0 -or
        ($rsa.Key.ExportPolicy -band [Security.Cryptography.CngExportPolicies]::AllowPlaintextExport) -ne 0
    ) {
        throw "The signing identity private key must be non-exportable."
    }
} finally {
    if ($rsa) { $rsa.Dispose() }
}

[pscustomobject]@{
    Subject = $certificate.Subject
    Thumbprint = $certificate.Thumbprint
    NotBefore = $certificate.NotBefore.ToUniversalTime().ToString("o")
    NotAfter = $certificate.NotAfter.ToUniversalTime().ToString("o")
    Store = "Cert:\CurrentUser\My"
    TrustInstalled = $false
} | ConvertTo-Json
