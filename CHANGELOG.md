# Changelog

## 2.0.0 - Unreleased

- Batch 3 adds compact finalized Encounter browsing, same-occurrence Attach Media, journaled append-only metadata/participant/Relations corrections, profile media/event integration and normalized Manual Association controls. Schema v32 preserves original history; historical reads retain named deleted people. World scoring/clustering and Windows release acceptance are unchanged.

- Added deliberate `NO_FACE` selection to both review browsers, reused durable Encounter/standalone face-origin history, accepted-poor recognition fallback, a separate proof-only pre-creation duplicate check, and read-only Global/Person Events. Event Note selected IDs remain Encounter→Person references and do not create Person relationship evidence.

- Established the first Encounter foundation on existing observations: Event details and selected-ID Event Note provenance are shared across participants; Event and Person/Sighting forms are separate. Queue new-person fields persist, both review paths support selected-ID Sighting Notes, and Add Face remains independent of Encounters. Schema v29 records GOOD, POOR_ACCEPTED, or PROOF_ONLY on existing embeddings and preserves Queue search policy; proof-only faces remain historical but never match. Large uploads retain one reduced managed historical media object, with transient detector preparation.

- Fixed person profile reads from People and recognition, review person-selection
  state, intentional form scrolling, country search, action and Settings layout,
  and operator-facing Tag terminology; hid developer recognition metrics.
- Fixed macOS source launcher argument parsing and exact-scope development reset
  of read-only model bundles and development Keychain identities.

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
