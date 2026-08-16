# P14 release acceptance

## Current result — Windows x64 host acceptance (2026-08-17)

P14 source implementation and unsigned Windows x64 development acceptance are complete on a real Windows 11 x64 host. Standalone, installer, clean install, packaged runtime, unlicensed recovery, licensing refusal cases, model onboarding, firewall enforcement, repair, upgrade, downgrade refusal, uninstall/reinstall, and failed-install rollback passed.

Production release acceptance remains **INCOMPLETE** because no Authenticode credential or timestamp configuration was available and this was an untagged `-DevelopmentBuild` from `pre-packaging` commit `6565780da1039fd3d4abe5484799710c9f83cb21`. No externally issued production `SFE2` token was provided.

The independently established `prod-2026-01` production trust-root match remains verified and was not reopened. Schema remains v28 and no P10/P11/P12/P13 semantic contract changed.

## Windows release gate results

- [ ] Clean exact `v2.0.0` tagged source. Required for production; this documented run used acceptance mode.
- [x] Real Windows 11 x64 host: Python 3.12.10, Nuitka 4.1.3, MSVC 14.3, Node 24.17.0, npm 11.13.0, Inno Setup 6.7.3, Windows SDK SignTool, and Git 2.45.2.
- [x] Windows source gate: 505 backend tests, 106 subtests, and 94 frontend tests passed; 45 skips were environment-classified; production UI build and `git diff --check` passed.
- [x] Current production frontend is embedded and matches source.
- [x] The previously accepted development standalone starts without development Python, reports 1.0.0, binds only `127.0.0.1`, refuses a second instance with exit 2, and shuts down gracefully. The final 2.0.0 artifact must be rebuilt and re-verified.
- [x] SQLCipher, ONNX Runtime, OpenCV, Windows keyring, P10–P13 services, licensing, migrations, and runtime lifecycle load from the package.
- [x] Artifact scan proves no model weights, private license key, PFX, token, database, backup, recovery secret, log, or staging authority is bundled.
- [ ] Executable and installer Authenticode signatures/timestamps. Both report `NotSigned`; credentials were unavailable.
- [x] Final SHA-256 `4c403e3387bb178028cf6c7516c203d7a99b8535143776e79e8ce6a6c36cf074`, dependency/license inventory, and development provenance match the 62,076,665-byte installer.
- [x] Clean install succeeds and ActiveStore has exactly one enabled outbound block for `C:\Program Files\SentriFace Edge\SentriFaceEdge.exe`.
- [x] Fresh unlicensed bootstrap/authentication, model prerequisites, backup creation/list/restore surface, P11 integrity/recovery, profile/support, and malformed activation refusal work.
- [x] Unlicensed ordinary person reads return `402 license_required`; status returns neither raw signed token nor raw MachineGuid.
- [x] Ephemeral-key licensing tests cover valid activation plus tampered signature/payload, wrong key/product/machine, malformed/noncanonical/oversized token, registry corruption, valid-token preservation, admin authorization, and actor spoofing. Production token: `NOT_PROVIDED`.
- [x] Same-version repair replaces the exact final executable, preserves per-user authority byte-for-byte, and refreshes the firewall rule.
- [x] Prior development acceptance upgrade from 0.9.9 to 1.0.0 gracefully stopped the old process, preserved LocalAppData/model/backup and Credential Manager state, and refreshed firewall policy. Upgrade acceptance from the deployed version-1 line to 2.0.0 remains pending for the final artifact.
- [x] Downgrade installer exits 1 before executable, version metadata, or firewall change.
- [x] Uninstall removes binaries, metadata, shortcuts and only the owned firewall rule while preserving all per-user authority.
- [x] Reinstall restores the exact final binary/rule and reconnects to preserved encrypted database, keyring, backup, and active-model state.
- [x] Forced firewall-helper launch failure exits setup 7 before Program Files/metadata creation and leaves no rule or user-authority mutation.
- [x] Final ONNX packaged startup passes OS-policy verification and installs the in-process non-loopback socket guard while loopback remains available.
- [x] Final packaged operator-model upload, two candidate prepares/activations, and explicit rollback commit without path leakage or bundled weights; backup and P11 integrity remain clean.

Unsigned CI artifacts are acceptance diagnostics only and must never be published as production releases.

## Decision

- P14 source implementation: **COMPLETE**.
- Windows x64 development build and packaged-runtime acceptance: **PASS**.
- Production trust-root match (`prod-2026-01`): **PASS** (independently established).
- Authenticode: **NOT VERIFIED**.
- Production-token test: **NOT PROVIDED**.
- Production release readiness: **NO**.
- P14 production release acceptance: **INCOMPLETE** until a clean exact `v2.0.0` build is rebuilt, the final runtime/lifecycle gates are re-verified, and the executable and installer are externally signed/timestamped with verified final signatures.
