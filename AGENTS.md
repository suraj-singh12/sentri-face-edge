# SentriFace Edge contributor guidance

## Current baseline and implementation workflow

Batch 3.7 is committed as `555433f082dc39112bd815dddf3a8f35791f2f4b` (schema v34). The verified hardening baseline is `683f3641e3532f08e180fe6c4c4386ac0f798917`, after [Issue #1](https://github.com/suraj-singh12/sentri-face-edge/issues/1) / [PR #8](https://github.com/suraj-singh12/sentri-face-edge/pull/8) completed CI repair. [Hardening CI #40071662474](https://github.com/suraj-singh12/sentri-face-edge/actions/runs/40071662474) passed all five jobs, including unsigned Windows AMD64 packaging. Python 3.12 is the only active target; Python 3.11 is disabled. Batch 4 / World vNext remains planned, not implemented. Green CI and unsigned packaging do not establish production signing or current-artifact installer/model lifecycle acceptance.

GitHub Issues are the durable source for approved implementation work ([roadmap](https://github.com/suraj-singh12/sentri-face-edge/issues/3)); issue priority labels in titles P0/P1/P2/etc. are roadmap priorities, not the repository's historical P0–P14 engineering phases. Before **each feature**, inspect the current code and docs, present a bounded issue review of exact scope, reuse opportunities, tests and material unanswered decisions, then obtain operator agreement. Recommend defaults and resolve the important decisions in one focused review round when practical; do not endlessly reopen trivial implementation choices. If product truth/authority cannot safely be inferred, ask rather than invent.

Once an issue is approved, create a dedicated issue-linked branch (`fix/issue-N-...`, `feature/issue-N-...`, `docs/issue-N-...`), and open a PR targeting **only** `release-v2.0.0-hardening`. Implement a coherent batch with tests, self-review and updates to existing canonical documentation; run relevant automated checks before merging, and do not call red CI green. **Do not merge a PR into the hardening branch until the operator explicitly approves that exact merge.** Never modify, commit, push, merge, cherry-pick or retarget to `main` unless the operator gives separate **explicit permission for that action**. Neither feature completion nor release readiness implies permission to touch `main`. Do not install unattended auto-merge policies. Present a Figma-first design for any substantial UI/interaction refinement **before coding**. Do not silently implement other open issues or commit/tag/push unless authorized.

## Reference Only source authority (Batch 3.7, schema v34)

An embedding is a biometric sample, not identity authority. Different genuine photos independently run inference; Person identity never borrows an earlier vector. Exact-equal serialized vectors may share a stored sample, but each Reference source and Encounter face assignment retains its own identity. Encounter corrections change only their assignments. A sample whose active sources resolve to different canonical Persons is excluded from ordinary recognition; this conflict is derived, not a persisted lifecycle. Reference ownership, active state and cap remain unchanged.

NO_FACE **Add Face** and ENROLLED **Manage Recognition References → Add Reference Only** are two entry points into one operation. Require a cropped image, exactly one detected face and explicit no-reliable-Encounter-context acknowledgment. Preserve GOOD/POOR_ACCEPTED/PROOF_ONLY; proof is not ordinary recognition. Four active source assignments per canonical Person prevent a contextless gallery; retired sources and Encounter samples do not count. Retire/restore append immutable source lifecycle history and never purge media. Archive/delete gate Person eligibility without retiring references. Merge must block above four and preserve raw history. Exact Reference media and Encounter media cannot acquire the opposite role. Reference changes have no occurrence, relationship, recurrence, graph or World meaning. Preserve source authority and lifecycle through the existing encrypted backup/restore; recompute eligibility/conflicts after restore.

## Attach Media draft ownership (Batch 3.7)

Attach uploads belong to their finalized Encounter from scan-session admission, before review planning can succeed or fail. Rejected planning retains that target durably; only targeted Retry or explicit Cancel may continue it. Never turn the failed attachment into general new-Encounter grouping. Retry checks the current Encounter revision; materialized review completion retains its original revision/idempotency contract. Cancel uses existing reference-aware cleanup. Source ownership and P11/live validation share the same contract.

## Product invariants

SentriFace Edge is completely offline. Preserve the loopback-only API, in-process socket guard, OS network policy checks, local model onboarding, encrypted SQLite storage, and local filesystem media model.

SentriFace has one global identity graph. Person Graph and World are read projections of the same graph; neither UI view owns association state. The graph must be rebuildable from authoritative records.

Authoritative identity data is limited to persons, observations/events, accepted participants, saved notes and `@Person` mentions, manual relationship assertions, identity corrections, and merge history. Recognition matches are proposals only. They must not mutate persons, participants, evidence, or graph projections before explicit operator finalisation.

For a multi-face observation/event, persist graph-affecting results only when every detected face has a final decision and the operator explicitly completes the review. The final write, its graph evidence, and its operation-journal entry must commit atomically.

Media provenance uses the existing server-owned registry for independent source admission and P11 checks. Observation membership cannot prove itself. Retained review/session media are valid multi-photo provenance even when accepted vectors reuse earlier enrollment images; saved occurrence-media IDs must belong to the face's own observation. Backup file closure/authentication and restore path/immutability protection remain mandatory.

Standing Manual Associations are unique per effective canonical unordered pair. Merge retires redundant current assertions within its existing transaction/journal without deleting raw rows, rewriting endpoints or losing metadata. Accepted recognition identity must come from the saved operator decision, never an unrelated model proposal; refresh/resume must reload that same decision.

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

## Historical engineering sequence

Follow `docs/IMPLEMENTATION_PLAN.md` for original P0–P14 architectural prerequisites and current batch status, and GitHub Issues for newly planned work. Do not build later-phase UI projections on temporary association state. The original phase P0 migration/version foundation and P1 journaling prerequisite remain important historical dependencies, separate from the roadmap priority P0 CI repair completed in Issue #1.

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
