# OS-enforced offline packaging contract

Real-model SentriFace startup is fail-closed. The production UI and ONNX CLI
inspect the active operating-system policy before loading models or opening the
encrypted data store. The Python loopback socket guard remains a second layer;
it is not accepted as the release boundary by itself.

## Windows

The Windows 11 x64 release authority requires Python 3.12, Node/npm, MSVC, and the x64 edition of Inno Setup 7. It is the repository-root command:

```powershell
.\build_release.ps1
```

On a `release-*` preparation branch it creates an isolated Python environment
from `requirements-release.lock`, uses `frontend/package-lock.json`, runs the
backend and frontend gates, builds the standalone application and installer,
verifies every packaged `.exe`/`.dll`/`.pyd` PE header as AMD64, exercises the
packaged native/runtime stack, and writes checksums plus inspection,
dependency/license, runtime, and provenance evidence under
`dist\windows-x64\<version>\`. Without external signing inputs the installer is
named `*-unsigned-pretag-rc.exe` and is explicitly not the canonical RC.

A production build is deliberately separate:

```powershell
.\build_release.ps1 -ProductionRelease
```

It requires a clean exact `rc-v<version>` or `release-v<version>` tag and
external SignTool, an exact certificate thumbprint, and the expected signer
subject. A timestamp URL is optional for controlled-machine self-signing and
recommended when a compatible timestamp authority is available. Those inputs
sign and verify both the application and installer; private signing material
never enters the repository.

For controlled Windows machines, create one stable, non-exportable RSA identity
once and explicitly trust its public certificate separately:

```powershell
.\packaging\windows\New-SentriFaceCodeSigningCertificate.ps1
.\packaging\windows\Trust-SentriFaceCodeSigningCertificate.ps1 `
  -Thumbprint <exact-thumbprint> `
  -ExpectedSubject "CN=SentriFace Edge Controlled Code Signing"
```

The trust step changes the selected user's Root and TrustedPublisher stores and
must be an explicit operator decision; normal installation never does this.
Configure future builds with `SENTRIFACE_SIGNTOOL`,
`SENTRIFACE_SIGNING_THUMBPRINT`, `SENTRIFACE_SIGNING_SUBJECT`, and optionally
`SENTRIFACE_TIMESTAMP_URL`. The build never selects an arbitrary certificate.
Self-signing establishes trust only on machines where that public certificate
was deliberately trusted; it does not provide universal SmartScreen reputation.

During elevated installation the same exact firewall helper contract is:

```powershell
.\windows\Install-OfflinePolicy.ps1 -ExecutablePath "C:\Program Files\SentriFace Edge\SentriFaceEdge.exe"
```

The installer removes the rule during uninstall with
`windows\Remove-OfflinePolicy.ps1`. The application rejects rules bound to a
shared Python interpreter and verifies the active rule is enabled, outbound,
blocking, and bound to the exact running executable. Firewall setup writes a
bounded temporary diagnostic record and reports its path when verification
fails.

For an Inno diagnostic log, launch a release-test installer with an explicit
local path, for example:

```powershell
.\SentriFaceEdge-2.0.0-x64-unsigned-pretag-rc.exe /LOG="$env:TEMP\SentriFaceEdge-install.log"
```

The log is a support artifact; review and remove it after the failed or
diagnostic run. Never attach user databases, recovery kits, model files, or
credential exports to a support report.
## macOS

Sign the application with `macos/SentriFace.entitlements`. It enables App
Sandbox and incoming server connections but intentionally omits the outgoing
client entitlement. The application verifies the signed entitlements at
startup. Signing and notarization are still required for distribution.

## Linux

Install the packaged executable under `/opt/sentriface`, create the dedicated
`sentriface` service account and data directory, then install
`linux/sentriface.service`. Its systemd IP firewall denies every IPv4/IPv6
address except loopback. The application verifies the active service
properties at startup.

Paths in the service template must be resolved by the installer. Do not weaken
`IPAddressDeny=any` or add non-loopback entries to `IPAddressAllow`.

## Application icons

Use the platform-specific assets supplied with this packaging contract:

- Windows executable and installer: `windows/SentriFace.ico`
- macOS application bundle (`CFBundleIconFile`): `macos/SentriFace.icns`
- Linux desktop entry and application menu: `linux/sentriface.png`

The editable high-resolution raster master is
`assets/sentriface-app-icon-1024.png`. Browser favicon and touch-icon variants
are copied from the same mark during the frontend build.
