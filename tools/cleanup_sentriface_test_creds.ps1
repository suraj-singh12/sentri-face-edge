<#
NOTICE:
=======

SentriFace Edge TEST Credential Cleanup Tool

THIS SCRIPT IS ONLY FOR TEST MACHINES.

This script removes ONLY test-scoped SentriFace Edge
Credential Manager entries.

It deliberately PRESERVES the real installation credential:

    SentriFace Edge storage

WARNING:
========

Do NOT run this on a machine containing important encrypted
SentriFace Edge data unless you understand the consequences.

The production credential:

    SentriFace Edge storage

is explicitly excluded and will NEVER be deleted by this script.

Only credentials matching the TEST form:

    <test-identifier>@SentriFace Edge storage

are removed.

Use only on disposable/test environments.
#>

Write-Host ""
Write-Host "SentriFace Edge TEST Credential Cleanup" -ForegroundColor Yellow
Write-Host "======================================="
Write-Host ""

Write-Host "The production credential will be preserved:" -ForegroundColor Green
Write-Host "  SentriFace Edge storage"
Write-Host ""

$confirm = Read-Host "Type CLEANUP to continue"

if ($confirm -ne "CLEANUP") {
    Write-Host "Cancelled."
    exit 0
}

$count = 0

cmdkey /list |
Select-String "SentriFace Edge storage" |
ForEach-Object {

    $target = ($_ -replace ".*target=", "").Trim()

    if (-not $target) {
        return
    }

    # NEVER delete the real installation credential.
    if ($target -eq "SentriFace Edge storage") {
        Write-Host "Preserving production credential: $target" -ForegroundColor Green
        return
    }

    # Only delete test-scoped credentials:
    # <identifier>@SentriFace Edge storage
    if ($target -match '^[^@]+@SentriFace Edge storage$') {
        Write-Host "Deleting TEST credential: $target" -ForegroundColor Yellow

        Start-Process cmdkey.exe `
            -ArgumentList "/delete:$target" `
            -Wait `
            -NoNewWindow

        $count++
    }
    else {
        Write-Host "Skipping unrecognized credential: $target" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "Removed $count TEST credential(s)." -ForegroundColor Yellow
Write-Host ""
Write-Host "Production credential was preserved."
Write-Host ""
Write-Host "Verify remaining SentriFace credentials with:"
Write-Host 'cmdkey /list | findstr /i "SentriFace"'
