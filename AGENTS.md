# SentriFace Edge contributor guidance

## Product invariants

SentriFace Edge is completely offline. Preserve the loopback-only API, in-process socket guard, OS network policy checks, local model onboarding, encrypted SQLite storage, and local filesystem media model.

SentriFace has one global identity graph. Person Graph and World are read projections of the same graph; neither UI view owns association state. The graph must be rebuildable from authoritative records.

Authoritative identity data is limited to persons, observations/events, accepted participants, saved notes and `@Person` mentions, manual relationship assertions, identity corrections, and merge history. Recognition matches are proposals only. They must not mutate persons, participants, evidence, or graph projections before explicit operator finalisation.

For a multi-face observation/event, persist graph-affecting results only when every detected face has a final decision and the operator explicitly completes the review. The final write, its graph evidence, and its operation-journal entry must commit atomically.

Relationships retain provenance. `CO_OBSERVED`, Person/Sighting Note `NOTE_REFERENCE`, and `MANUAL_ASSOCIATION` are separate evidence types. Selected Event Note IDs are structured Encounter→Person mentions on the observation; they create no relationship evidence or World effect. Literal unselected `@Name` is inert in every note scope. Removing one evidence record must not remove a relationship supported by other evidence. Deduplicate event participants by canonical person and never create self-links.

Archive and delete are identity states, not historical erasure. Archived people remain graph nodes but are inactive/non-clickable in graph projections. Their historical People profile remains reachable for authorized Restore. Deleted people are tombstoned and remain historically represented. A merge preserves both identities, all history and provenance; the source resolves to the surviving canonical identity.

## Existing architecture to preserve where reasonable

- Domain dataclasses: `src/sentriface/models.py`
- Storage protocol: `src/sentriface/contracts.py::IdentityStore`
- SQLite implementation and inline schema migrations: `src/sentriface/storage/sqlite_store.py::SQLiteIdentityStore`
- Application/service boundary: `src/sentriface/engine.py::FaceEngine`
- Loopback HTTP API and authorization: `src/sentriface/api_server.py`
- React application: `frontend/src/SentriFaceApp.jsx`, controllers in `frontend/src/hooks/`, views in `frontend/src/views/`
- Vector indexes are derived caches: `src/sentriface/components/linear_index.py` and `hnsw_index.py`
- Portable backup/restore: `src/sentriface/backup_service.py`

Keep SQL writes behind the storage/service boundary. Do not let React components directly maintain durable association state. Prefer additive, versioned migrations and compatibility reads over broad rewrites.

## Implementation sequence

Follow `docs/IMPLEMENTATION_PLAN.md` in order. Do not build later-phase UI projections on temporary association state. P0 must establish the migration/version foundation before domain feature work; P1 journaling must precede new graph-affecting writes.

## Transaction and journal rules

- Use one SQLite transaction for each graph-affecting operation.
- Require an idempotency/operation ID for important writes.
- Write the operation journal in the same transaction as the authoritative change.
- Never derive durable evidence from unsaved UI state or recognition proposals.
- Treat graph edges as a projection of evidence; rebuild and integrity checks must be possible without recognition inference.
- File cleanup may be coordinated outside SQLite, but database state and journal intent must remain recoverable and testable under failure.

## Verification

Run focused tests while developing, then the full relevant suites:

```bash
python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

Migration work must test fresh databases, every supported upgrade path, rollback on failure, repeat startup/idempotence, foreign keys, backup-before-migration, and preservation of archived/tombstoned/merged history. Graph work must test evidence independence, canonical resolution, event participant deduplication, no self-links, atomic multi-face finalisation, rebuild equivalence, and offline operation.

Do not edit generated `src/sentriface/ui_static/` assets by hand; rebuild them from `frontend/` only when a UI phase requires it.

## Windows release boundary

For the current 2.0.0 release state, read `docs/AGENT_HANDOFF.md` and
`docs/p14/P14_RELEASE_ACCEPTANCE.md` before changing release tooling or claiming
acceptance. The unsigned pre-tag installer is an engineering candidate. Historical
installer lifecycle results belong to an earlier artifact and do not verify the
current one. A canonical release requires the exact `rc-v<version>` or
`release-v<version>` tag, verified executable and installer signatures, and the
current artifact's lifecycle and model acceptance on a disposable Windows host.

Windows source development uses `run.ps1` and `%LOCALAPPDATA%\SentriFace-Dev`.
Preserve its separation from `%LOCALAPPDATA%\SentriFace` and the exact-scope
development credential reset. Treat `tools/wipe_clean_this_machine_installation_and_data.py`
as destructive. Never execute it on a machine with required product data; use
a disposable fixture for release acceptance.
