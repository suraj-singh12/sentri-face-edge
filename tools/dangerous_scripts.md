# Destructive Windows support tools

These utilities are for disposable Windows test machines. Deleting a SentriFace
storage credential can make its encrypted database, media, logs, and backups
permanently unreadable. Create and verify any required exported backup before
using them. Normal application uninstall is data-preserving and does not require
these tools.

## `cleanup_sentriface_test_creds.ps1`

Removes only test-scoped Credential Manager entries matching
`<test-identifier>@SentriFace Edge storage`. It explicitly preserves the
production credential named `SentriFace Edge storage` and skips unrecognized
entries. Use it after test runs and before testing a clean installed instance.

## `cleanup_sentriface_all_creds.ps1`

Removes every Credential Manager entry whose listing contains `SentriFace`,
including the production storage credential. Despite the script's historical
banner wording, this is an all-credential cleanup. Run it only on a disposable
machine after confirming that no encrypted data must remain accessible.

## `wipe_clean_this_machine_installation_and_data.py`

Performs the supported full machine wipe for the current Windows user. It
requires administrator rights and the exact confirmation phrase
`WIPE SENTRIFACE`. It requests graceful shutdown, runs the installed uninstaller
when present, removes the production storage credential and license registry
state, deletes known application/data/model/backup/recovery/log locations,
removes shortcuts and development entry points, and removes the SentriFace-owned
firewall rule. It rejects non-Windows execution and does not accept arbitrary
paths as deletion targets.

For complete cleanup, prefer the Python wipe utility by itself because it
already removes the production credential. The PowerShell scripts are narrower
credential-only helpers; running an additional all-credential cleanup is
normally redundant.
