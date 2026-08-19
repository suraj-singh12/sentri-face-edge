<#
NOTICE:
=======
SentriFace Edge Test Credential Cleanup Tool

THIS SCRIPT IS ONLY FOR TEST MACHINES.

Run this ONLY after completing test runs that create temporary
SentriFace Edge instances.

This script removes Windows Credential Manager entries created by
SentriFace Edge test environments.

WARNING:
========
Do NOT run this on a machine containing a real SentriFace Edge
installation or important encrypted data.

Removing the stored SentriFace storage key can make an existing
database/media store permanently inaccessible because the encryption
key required to unlock it is stored in Windows Credential Manager.

Use only on disposable test environments.
#>

Write-Host ""
Write-Host "SentriFace Edge Test Credential Cleanup" -ForegroundColor Yellow
Write-Host "======================================"
Write-Host ""

$confirm = Read-Host "Type CLEANUP to continue"

if ($confirm -ne "CLEANUP") {
    Write-Host "Cancelled."
    exit 0
}

$count = 0

cmdkey /list |
Select-String "SentriFace" |
ForEach-Object {

    $target = ($_ -replace ".*target=", "").Trim()

    if ($target) {
        Write-Host "Deleting: $target"

        Start-Process cmdkey.exe `
            -ArgumentList "/delete:$target" `
            -Wait `
            -NoNewWindow

        $count++
    }
}

Write-Host ""
Write-Host "Removed $count SentriFace Credential Manager entries."
Write-Host "Verify with:"
Write-Host 'cmdkey /list | findstr /i "SentriFace"'
