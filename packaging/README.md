# OS-enforced offline packaging contract

Real-model SentriFace startup is fail-closed. The production UI and ONNX CLI
inspect the active operating-system policy before loading models or opening the
encrypted data store. The Python loopback socket guard remains a second layer;
it is not accepted as the release boundary by itself.

## Windows

Package SentriFace as a dedicated executable. During elevated installation:

```powershell
.\windows\Install-OfflinePolicy.ps1 -ExecutablePath "C:\Program Files\SentriFace\SentriFace.exe"
```

The installer must remove the rule during uninstall with
`windows\Remove-OfflinePolicy.ps1`. The application rejects rules bound to a
shared Python interpreter and verifies the active rule is enabled, outbound,
blocking, and bound to the exact running executable.

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
