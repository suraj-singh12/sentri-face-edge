# P14 release acceptance

## Current result

P14 source implementation and locally available macOS validation are complete. Windows x64 build, clean Windows install lifecycle, and Authenticode verification are **NOT VERIFIED** on the current host and remain release blockers.

## Required Windows release gate

- [ ] Clean exact `v1.0.0` tagged source.
- [ ] Windows x64-compatible build host with Python 3.12, Node 22, Nuitka, and Inno Setup 6.
- [ ] Full backend and frontend tests pass on Windows.
- [ ] Production frontend is embedded and matches source.
- [ ] Standalone executable starts without development Python and reports the authoritative version.
- [ ] SQLCipher, ONNX Runtime, OpenCV, Windows keyring, P10–P13 services, and migrations are present.
- [ ] Artifact inspection proves no model weights, private license key, PFX, token, database, backup, or temporary authority is present.
- [ ] Application executable and installer have valid trusted Authenticode signatures and timestamps.
- [ ] SHA-256, dependency/license inventory, and provenance metadata match the installer.
- [ ] Clean install succeeds and the exact executable outbound rule verifies.
- [ ] Unlicensed authentication, license activation, model prerequisites, backup, restore, P11 recovery, and support surfaces work.
- [ ] Unlicensed ordinary product operations return `license_required`.
- [ ] Valid test license activates; wrong signature/key/product/machine and malformed/noncanonical/oversized/corrupt registry states refuse without leakage.
- [ ] Same-version repair succeeds without changing per-user authority.
- [ ] Upgrade requests P13 graceful shutdown, preserves LocalAppData/HKCU/keyring, and refreshes firewall policy.
- [ ] Downgrade is refused before application files change.
- [ ] Uninstall removes binaries/shortcuts/owned firewall policy and preserves all per-user authority.
- [ ] Reinstall reconnects to preserved state safely.
- [ ] Installer/firewall failure rolls installation back without modifying per-user authority.
- [ ] Non-loopback socket attempts fail and OS-policy verification remains active.
- [ ] P11-A remains clean and P12 backup/restore acceptance remains unchanged after install/upgrade.

Unsigned CI artifacts are acceptance diagnostics only and must never be published as production releases.
