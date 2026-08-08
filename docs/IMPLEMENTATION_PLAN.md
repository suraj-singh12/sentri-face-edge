# Global identity graph implementation plan

Implement in order. Each phase must preserve offline operation, use additive migrations where possible, keep important writes transactional and journaled, and add upgrade/failure tests before moving on.

## P0 Database migration/version foundation

Refactor the inline version chain in `src/sentriface/storage/sqlite_store.py` into an explicit, testable migration registry without changing runtime domain behavior. Define supported-version policy, schema introspection, transaction boundaries, backup-before-migration, failure recovery, and fixtures for representative old schemas. Exit: fresh install and every supported upgrade reach the same schema; failed/repeated migrations are safe and verified.

## P1 Operation Journal

Replace/extend `person_operations` with a general immutable operation journal while retaining idempotency compatibility. Record actor, operation type, affected entities, before/after or inverse payload, status, and timestamps in the same transaction as each important write. Exit: all existing graph/identity-affecting writes are journaled and retry-safe; gaps are enumerated and tested.

## P2 Identity lifecycle + canonical identity

Introduce explicit active/archived/tombstoned lifecycle and normalized canonical-resolution/merge-history primitives. Remove physical person erasure from normal lifecycle semantics; provide compatibility mapping from `deleted_at` and `metadata.merged_into`. Exit: archived/tombstoned/merged source identities resolve correctly while remaining historically queryable.

## P3 Observation/Event model

Add events/observations, event photos, detected-face review decisions, and accepted participants. Migrate or bridge `recognition_details`; enforce one participant per canonical person per event and allow multiple photos. Exit: event completion is explicit, participant deduplication/self-link rules hold, and existing sightings remain accessible.

## P4 Global graph + relationship evidence engine

Add normalized evidence records and a rebuildable relationship projection. Keep `CO_OBSERVATION`, `NOTE_MENTION`, and `MANUAL_ASSERTION` distinct, explainable, independently removable, and canonicalized. Provide storage/service APIs; do not add final Person Graph/World UI yet. Exit: rebuild is deterministic and produces the same projection as incremental transactional updates.

## P5 Notes/revisions/@Person mentions

Normalize person/event notes, revisions, and exact mention occurrences. Parse mentions only on save; diff revisions so removed mentions retire only their evidence. Migrate existing profile/sighting notes and `automatic_mention` associations without inventing provenance that cannot be established. Exit: save/edit/remove/duplicate-name/merge cases preserve independent evidence correctly.

## P6 Check Photo/Queue atomic finalisation

Create one backend finalisation command per photo/event review. Require a final decision for every detected face plus explicit completion; atomically persist identities/participants/details/evidence/journal or nothing. Replace frontend request loops in `useRecognizeController.js` and `useQueueController.js` with the command. Exit: injected failures cannot leave partial identity, event, mention, or graph state.

## P7 Recognition corrections/Move Face/Add Face

Model corrections as authoritative, journaled history rather than silent ownership rewrites. Support corrected participant identity, Move Face, and Add Face while retaining original proposal/decision provenance and rebuilding affected projections. Exit: correction/revert paths are atomic and historically explainable.

## P8 Identity Merge

Move merge to normalized canonical identity and merge history. Preserve source records and evidence, resolve reads to the survivor, canonicalize projected pairs, prevent self-links, and define safe revert preconditions. Exit: merge chains, archived/tombstoned identities, notes, events, corrections, and evidence survive merge/revert intact.

## P9 Sightings metrics + People sort/group

Compute sightings, last seen, frequency, and grouping from accepted event participation rather than embedding-linked detail counts. Update People APIs/controllers with stable canonical/lifecycle semantics. Exit: metrics remain stable across photo deletion, face move, and merge according to documented rules.

## P10 Person Graph + World

Build both as projections of the same global graph API/evidence engine. Person Graph is identity-centred; World filters/aggregates the same observations and nodes by place/time. Archived/tombstoned nodes remain visible where historically relevant but inactive/non-clickable. Exit: neither view owns association state, and both explain edge evidence consistently.

## P11 Integrity checker + graph rebuild + operation revert

Add offline integrity checks for canonical chains, event decisions/participants, evidence sources, projection drift, self-links, file references, and journal linkage. Add transactional graph rebuild and supported operation reverts using journal/inverse data. Exit: corruption/drift is reported without inference; rebuild is idempotent and reverts are guarded/audited.

## P12 Backup/Restore

Extend `backup_service.py` manifests, verification, path rewriting, recovery checks, and compatibility rules for all new authoritative/journal/projection records. Prefer rebuilding derived graph/index state after restore. Exit: encrypted portable backup round trips preserve history/provenance and reject incompatible/newer schemas safely.

## P13 BYOM model manager

Build on `model_setup.py` and existing local upload/install routes to manage fully offline operator-supplied detector/recognizer bundles, hash-bound calibration, compatibility, activation, and rollback. Models and recognition remain proposal generators only. Exit: no download/network dependency and no model activation can mutate authoritative identity data.

## P14 Windows packaging/licensing

Complete Windows packaging, executable-bound offline policy, local licensing/activation rules, upgrades, data-path permissions, backup/recovery UX, and signed release verification. Exit: packaged Windows operation remains offline and passes migration, recovery, security, and licensing acceptance tests.

## Cross-phase gates

- Preserve `FaceEngine`, `IdentityStore`, SQLite, loopback API, React controllers/views, derived vector indexes, and backup services where reasonable.
- Do not use recognition proposals, temporary queue groups, or frontend graph objects as authoritative inputs.
- Every graph-affecting change and its journal entry share one transaction.
- Add tests for failure rollback, idempotent retries, canonical merge chains, evidence independence, participant deduplication, no self-links, archived/tombstoned rendering data, rebuild equivalence, and zero non-loopback network access.
