# P14 release acceptance

## Current result — Windows source mode and pre-tag RC hardening (2026-09-21)

The `release-v2.0.0-hardening` worktree now has an isolated Windows source
launcher, a narrowly scoped development reset, a controlled self-signing path,
and a repeatable locked AMD64 build. The final 62,976,029-byte engineering
candidate is
`SentriFaceEdge-2.0.0-x64-unsigned-pretag-rc.exe`, with SHA-256
`ef388d7ed3aa8dc55beaaa75505c870e56a976cb6e0c71eb8e24de831c812ab8`.
It is deliberately labeled unsigned and pre-tag; it is not the canonical
`rc-v2.0.0` artifact and is not production accepted.

- The Windows launcher uses a repository-local Python 3.11/3.12 environment and
  `%LOCALAPPDATA%\SentriFace-Dev`. It refuses the production data root and
  overlapping paths. Its reset removes only the default development root and
  the two exact hash-derived development vault identities after deliberate
  confirmation; it refuses custom paths and reparse points.
- Fresh synthetic startup, compiled-frontend authorization, loopback-only HTTP,
  second-instance refusal, graceful shutdown, immediate restart, and complete
  development reset passed. The post-reset machine inventory contained no
  development credential, data root, process, or test directory.
- Real local detector and recognizer ONNX files were onboarded in source mode.
  Both sessions selected `CPUExecutionProvider`; prepare, activate, restart
  persistence, explicit rollback, and post-rollback restart persistence passed.
  The source-only ONNX escape hatch remains restricted to Windows/macOS Git
  checkouts and is refused by frozen/packaged runtimes.
- The final isolated build reran 529 backend tests, 106 subtests, and 94 frontend
  tests: all passed, with 45 environment-classified backend skips. The exact
  frontend lock audited with zero known vulnerabilities and the production Vite
  build completed; its large-chunk message remains an optimization advisory.
- The release environment matched `requirements-release.lock`, dependency
  consistency passed, and the bundle-derived dependency/license inventory was
  emitted separately from build tools. A second complete locked build also
  passed, demonstrating repeatable gates and cleanup; timestamps make the two
  installer byte streams intentionally non-identical. Missing direct license
  fields are resolved from standard package classifiers, leaving no bundled or
  build-tool record with an `UNKNOWN` license value.
- Inno Setup 7.1 produced a native AMD64 installer. The artifact inspector parsed
  the installer and every packaged `.exe`, `.dll`, and `.pyd`; every inspected
  native binary was AMD64, no I386 or ARM64 binary was accepted, and the release
  closure contained 61 files with no model weights or private keys.
- The packaged runtime self-test passed Windows vault create/retrieve/cleanup,
  SQLCipher encryption, protected-file round trip, OpenCV, ONNX Runtime CPU
  execution, both external model sessions, compiled loopback UI authorization,
  graceful shutdown, and instance-lock release. Full model onboarding is marked
  `PENDING_NOT_EXERCISED` in that packaged report because the installer itself
  was not run; the complete equivalent lifecycle passed in the isolated source
  profile as recorded above.
- Read-only final machine inventory matched the pre-existing production shape:
  the real `%LOCALAPPDATA%\SentriFace` authority, its HKCU state, and its exact
  production storage credential remain. No Program Files installation, uninstall
  registration, shortcut, outbound firewall rule, development authority, build
  directory, or SentriFace process was left behind.
- A 3072-bit, SHA-256, non-exportable CurrentUser signing identity was created at
  exact subject `CN=SentriFace Edge Controlled Code Signing`, thumbprint
  `49D19D04D111C54E64E56177BF4990A35ECB800E`, valid from
  2026-09-20T18:33:07Z through 2031-09-20T18:43:06Z. Reuse validation passed and
  no PFX or private key was exported. The certificate is not present in the
  CurrentUser Root or TrustedPublisher stores: that persistent trust change was
  not authorized, so the final candidate remains unsigned.

This host contains real SentriFace data and has no Windows Sandbox or disposable
VM fixture available to this session. The destructive sanitizer and current-
artifact installer execution, repair, upgrade, downgrade, uninstall, reinstall,
and failed-install rollback were therefore not run on this host. Historical
lifecycle evidence below remains valid for the earlier artifact, but it does not
substitute for a disposable-machine lifecycle run of this final candidate.

Current RC blockers are: install and verify the controlled certificate in the
CurrentUser Root and TrustedPublisher stores with explicit operator approval,
then build and verify the signed pre-tag candidate; execute the final signed
artifact's full installer lifecycle and packaged model onboarding/activation/
rollback on a disposable Windows 11 AMD64 fixture. The installed Inno Setup
compiler identifies itself as non-commercial-use-only, so the release owner
must confirm the applicable distribution terms; this is a legal/operational
follow-up, not a technical build failure. A production `SFE2` token is
additionally required only if production-token acceptance is part of the
release gate. Human review, commit, exact `rc-v2.0.0` tagging, and the tagged
rebuild remain the deliberately separate finalization step.

Current decision: source development and unsigned build hardening **PASS**;
canonical RC readiness **NO** until the signing/trust and disposable-machine
lifecycle blockers above are closed.

## Historical result — Windows x64 host acceptance (2026-08-17)

P14 source implementation and unsigned Windows x64 development acceptance are complete on a real Windows 11 x64 host. Standalone, installer, clean install, packaged runtime, unlicensed recovery, licensing refusal cases, model onboarding, firewall enforcement, repair, upgrade, downgrade refusal, uninstall/reinstall, and failed-install rollback passed.

Production release acceptance remains **INCOMPLETE** because no Authenticode credential or timestamp configuration was available and this was an untagged `-DevelopmentBuild` from `pre-packaging` commit `6565780da1039fd3d4abe5484799710c9f83cb21`. No externally issued production `SFE2` token was provided.

The independently established `prod-2026-01` production trust-root match remains verified and was not reopened. Schema remains v28 and no P10/P11/P12/P13 semantic contract changed.

## Historical Windows release gate results (2026-08-17 artifact only)

The checked items below describe the earlier diagnostic installer. They are not
acceptance evidence for the current 2.0.0 pre-tag candidate.

- [ ] Clean exact `rc-v2.0.0` or `release-v2.0.0` tagged source. Required for production; this documented run used acceptance mode.
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
- P14 production release acceptance: **INCOMPLETE** until a clean exact `rc-v2.0.0` or `release-v2.0.0` build is produced, the current artifact's installer/model lifecycle gates are verified on a disposable Windows host, and executable and installer signatures are verified.
