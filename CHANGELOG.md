# Changelog

## 0.1.0 - Unreleased

- Added an offline ONNX face-recognition runtime and React localhost UI.
- Added reviewed enrollment, recognition follow-ups, people lifecycle, queue
  scanning, idempotent mutations, and portable backup/restore.
- Added backend-owned Strong/Likely/Maybe/Unknown confidence policy.
- Added cancellable inference, request-scoped metrics, synchronized linear/HNSW
  indexes, atomic index publication, and linear fallback.
- Added durable file cleanup, SQLite lock handling, migration backups, restore
  rollback, request limits, localhost validation, and browser-origin hardening.
- Added post-login research/commercial model onboarding, local path and checksum
  validation, in-process ONNX activation, and automatic return to setup when model
  files are missing or changed.
- Added per-machine local signup/login, Argon2id password hashing, viewer/operator/
  custodian/technician/administrator roles, backend and CLI authorization, account
  lockout/auditing, and OS-custodian administrator recovery.
- Added machine-profile diagnostics, SQLCipher live-database encryption, authenticated
  managed-file and persistent-log encryption, and OS-vault key custody.
- Added user-configured disaster recovery kits, automatic encrypted external backups,
  recovery-key restoration, and rejection of network-backed recovery destinations.
- Added process-wide non-loopback socket blocking and runtime reporting for the
  fully offline, loopback-only security posture.
- Added reproducible wheel packaging with the compiled UI, verified model setup,
  platform-specific data paths, and Windows/macOS/Linux CI.
