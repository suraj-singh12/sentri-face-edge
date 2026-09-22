# P14 Windows packaging and licensing design

## Status and boundary

P14 implementation is complete in source. The 2026-09-20 unsigned 2.0.0 hardening candidate passes the locked source gates, packaged runtime checks, external ONNX session checks, and strict AMD64 inspection for the Inno Setup 7 installer plus all runtime-native files. Final release acceptance remains pending a clean exact-tag signed/timestamped build and disposable clean-VM installer/model lifecycle run. Schema remains v28 and P10/P11/P12/P13 authority is unchanged.

P14 owns operational licensing, the packaged Windows executable, installer lifecycle, exact-executable outbound firewall policy, version propagation, signing hooks, and release evidence. It does not own identity/domain state, database migrations, backup authority, model authority, recovery authority, or activation issuance secrets.

## Offline SFE2 license authority

The only accepted envelope is `SFE2.<canonical unpadded base64url JSON>.<unpadded base64url Ed25519 signature>`. The payload contains exactly `version`, `product`, `license_id`, `key_id`, `machine`, `edition`, `license_type`, `issued_at`, and `expires_at`. Unknown, duplicate, missing, oversized, malformed, noncanonical, wrongly signed, wrong-product, wrong-machine, future-issued, and invalid-expiry licenses refuse factually. There are no client-selected feature flags.

The production executable embeds only the selected public verification key identified by `prod-2026-01`. Its matching private key is an external issuance asset and must never enter source, CI, build inputs, logs, or release artifacts. Tests generate an ephemeral test-only keypair.

The Windows machine fingerprint is SHA-256 over the fixed `sentriface-edge|machine-fingerprint-v2|` namespace and normalized 64-bit-registry `MachineGuid`. Only the shortened `SFE-MC-...` value is exposed. Missing or malformed machine authority fails closed; there is no BIOS, baseboard, PowerShell, empty-value, database-key, recovery-kit, or backup binding.

Verified tokens persist as bounded `REG_SZ` state under per-user `HKCU\Software\SentriFaceEdge\Licensing\v2`. License state is operational configuration, not SQLite/domain authority, backup content, or an operation-journal event.

## Activation and unlicensed recovery shell

`GET /api/license/status` requires authenticated `view`. `POST /api/license/activate` explicitly requires administrator-only `license_administer`, accepts exactly one signed `token`, and derives the actor from the authenticated session. Status never returns the token or raw machine identity.

Packaged Windows releases start normally without a license. A centralized pre-dispatch policy blocks ordinary product reads/mutations while explicitly retaining authentication/bootstrap, licensing, model prerequisites, backup/export/import/restore, disaster recovery, P11 integrity/recovery, bounded system profile/events, and support export. The React application restricts navigation to Debug/System in this state and renders server status only; it is not the security boundary. Source/development runtimes do not enforce production licensing.

## Windows x64 layout and model exclusion

Immutable application files install under `%ProgramFiles%\SentriFace Edge`. The existing per-user `%LOCALAPPDATA%\SentriFace` data, media, model-bundle, backup, log, receipt, keyring, and instance-lock layout is unchanged. The installer creates no ProgramData authority, edits no database, runs no migration, imports no storage key, and rewrites no P12 media path.

Nuitka builds one standalone distribution containing the UI and required SQLCipher, ONNX Runtime, OpenCV, Windows keyring, and SentriFace services. The artifact inspector rejects ONNX/DAT weights, private-key markers, PFX files, and signing-key names. Detector and recognizer weights are never bundled; P13 local model onboarding remains authoritative.

## Installer lifecycle and offline policy

The stable Inno AppId is `{9B86BE35-3E8F-47F0-A9C2-A4CF4933B985}`. Upgrade signals the running per-user process through a path-hashed Windows event and delegates to P13 graceful shutdown, replaces only Program Files, refreshes and verifies the exact-executable outbound-block rule, and preserves all per-user authority. Installer code never migrates SQLite.

The installer rejects a lower product version. There are no reverse migrations. Uninstall removes binaries, shortcuts, installer metadata, and only the owned firewall rule. It intentionally preserves LocalAppData, models, backups/recovery material, logs, HKCU license state, and OS-keyring state. ProgramData preview installations are unsupported legacy previews and are not silently moved.

The outbound firewall installer removes/recreates only `SentriFaceEdge-BlockOutbound`, then verifies ActiveStore direction, action, enabled state, and exact executable path. Failure is fatal. The in-process socket guard and startup OS-policy verifier remain defense in depth.

## Windows machine-state ownership and sanitization

| Resource | Created/updated by | Normal uninstall | Complete-machine sanitizer |
| --- | --- | --- | --- |
| Program Files application, shortcuts, Inno registration | Inno Setup | Removed | Removed by exact path/registration fallback |
| `SentriFaceEdge-BlockOutbound` | Installer firewall helper | Removed | Removed only when rule properties and exact application path verify |
| `%LOCALAPPDATA%\SentriFace` database, media, models, backups, logs, receipts, locks | Packaged runtime and operator actions | Preserved | Removed as the exact default per-user authority |
| `HKCU\Software\SentriFaceEdge\Licensing\v2` | Successful offline activation | Preserved | Removed through the exact product registry tree |
| Storage and disaster-recovery vault credentials | Runtime/recovery authority, keyed by SHA-256 of resolved data root | Preserved | Default-data-root accounts are deleted through exact keyring service/account lookup |
| MachineGuid | Windows | Never modified | Never modified |
| Release-test credentials and temporary data | The individual packaged-runtime test | Not applicable | The creating test deletes its exact service/account and temporary tree in `finally` |
| Build environment/intermediates | `build_release.ps1` below repository `build\` | Not applicable | Removed by the build after success; isolated environment is removed on failure too |

`tools/wipe_clean_this_machine_installation_and_data.py` is the only supported
complete-machine sanitization path. Its default mode is read-only inventory.
Destructive execution requires administrator rights, `--execute`, and the exact
interactive confirmation phrase. It re-inventories after execution and fails
non-zero if promised state remains. Credentials for custom roots, historical
tests, or legacy naming are reported as ambiguous and never deleted by pattern.

## Reproducible build and evidence boundary

`build_release.ps1` is the single Windows x64 build authority. The default
release-branch invocation produces a clearly named development/release-candidate
installer. `-ProductionRelease` retains the clean exact-tag and external
Authenticode/timestamp requirements.

The build creates an isolated environment from exact
`requirements-release.lock` pins, verifies the resolved environment, installs
the local source without dependency re-resolution, and uses
`frontend/package-lock.json` through `npm ci`. Optional HNSW is deliberately not
part of the Windows production closure; the documented synchronized linear
fallback is packaged consistently.

Nuitka's compiled-module build tree is mapped back to installed distribution
metadata so the dependency/license inventory describes bundled runtime
components, while build-only tools are listed separately. Release inspection
parses every packaged PE header for `.exe`, `.dll`, and `.pyd` files and requires
AMD64 throughout. The packaged self-test creates an exact test-owned vault
credential and temporary data root, verifies key retrieval, SQLCipher, secure
files, OpenCV, ONNX Runtime CPU provider, loopback HTTP/static UI, clean
shutdown, and instance-lock release, then deletes and verifies its own
credential and temporary root. Externally supplied detector and recognizer
models add real ONNX session acceptance; absence is recorded as pending rather
than passed.
## Version, signing, and release boundary

`src/sentriface/_version.py::APP_VERSION` is the single release version. The build reads it and passes it to Python metadata, Nuitka resources, Inno Setup, artifact names, checksum, and provenance output. Release mode requires a clean tree at exact tag `rc-v<version>` or `release-v<version>`.

Signing uses exact external Windows certificate-store inputs: SignTool path,
certificate thumbprint, expected subject, and optional timestamp URL. The
controlled-machine workflow creates one reusable non-exportable RSA Code Signing
identity and keeps trust installation separate and explicit. The build validates
the exact private-key identity, signs/verifies the application, builds the
installer, signs/verifies the installer, and then emits SHA-256,
dependency/license inventory, and provenance metadata. No PFX or private key is
written to source or artifacts. Self-signing does not imply public SmartScreen
trust. Timestamp network access, when configured, exists only in release
infrastructure; the installed runtime stays offline.
