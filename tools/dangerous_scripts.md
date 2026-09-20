# Destructive Windows support tool

SentriFace has one supported complete-machine sanitization path:

```powershell
python tools\wipe_clean_this_machine_installation_and_data.py
```

That command is inventory-only. It reports exact current installation paths,
registry state, firewall state, and Credential Manager entries without printing
credential values or changing the machine.

On a disposable release-test machine, deliberate removal is:

```powershell
python tools\wipe_clean_this_machine_installation_and_data.py --execute
```

Execution requires administrator rights and the exact interactive phrase
`WIPE SENTRIFACE`. It requests graceful shutdown, uses the registered
uninstaller when available, and removes only resources whose ownership is
provable from fixed SentriFace identifiers:

- the exact Program Files installation and shortcuts;
- the exact LocalAppData application authority and exact legacy ProgramData
  preview directory;
- the stable Inno Setup registration;
- `HKCU\Software\SentriFaceEdge`;
- the exact verified outbound firewall rule;
- storage and disaster-recovery credentials whose account hash exactly matches
  the normal `%LOCALAPPDATA%\SentriFace` installation;
- exact SentriFace development entry points and installation metadata.

The utility re-inventories after deletion and exits non-zero if any resource it
promised to remove remains.

Credential Manager entries for custom data roots, historical tests, or legacy
naming cannot be proven to belong to the default installation from their name
alone. They are reported as `AMBIGUOUS` and are never deleted automatically.
Likewise, a firewall rule with the product name but an unexpected executable or
properties is preserved for manual review. Do not use wildcard credential or
registry deletion as a substitute.

Removing the exact storage credential makes the matching encrypted database,
media, logs, and backups permanently unreadable. Normal application uninstall
is intentionally data-preserving and does not run this sanitizer.
