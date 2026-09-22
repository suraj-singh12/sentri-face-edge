# Changelog

## 2.0.0 - Unreleased

- Completed P0-P14 source implementation through schema v28, including the
  global evidence-derived identity graph, World, integrity/recovery,
  authority-aware backup/restore, runtime hardening, offline licensing, and
  Windows x64 packaging.
- Historical unsigned Windows 11 x64 installer lifecycle acceptance passed for
  an earlier artifact. The current 2.0.0 unsigned pre-tag candidate passed source,
  build, inspection, and packaged runtime checks. Production release remains
  pending verified signatures, current-artifact installer/model lifecycle
  acceptance on a disposable Windows host, and a clean exact-tag rebuild.
- Added a native packaged-Windows startup error dialog while retaining
  fail-closed startup and console diagnostics.
- Added documented Windows test-credential and complete-machine cleanup tools.
- Added a repository-local Windows source launcher with isolated development
  data and credentials, synthetic and real-ONNX modes, and a fail-closed reset.
- Added controlled non-exportable Windows code-signing identity creation,
  explicit trust-store onboarding, exact certificate validation, and distinct
  signed/unsigned pre-tag artifact naming.
- Improved release dependency evidence by falling back to standard package
  license classifiers when direct license fields are absent.

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
