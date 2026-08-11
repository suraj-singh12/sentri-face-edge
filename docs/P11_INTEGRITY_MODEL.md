# P11 integrity authority model, checker, and graph rebuild

Status: **P11-A and P11-B complete and frozen; P11-C1 design complete; P11C-R01 implemented; P11C-R02 unimplemented; P11-C incomplete.** This document fixes the P11 invariant IDs and authority boundary, records the read-only checker, and defines the explicit deterministic `graph_connections` rebuild. `P11_STRUCTURED_REPAIR_DESIGN.md` records the frozen two-entry catalog and the finding-bound R01 implementation. It does not authorize generic repair, operation revert, recovery UI, or P12 backup/restore work.

## State-authority map

The classification is verified against schema v28, storage writes, services, triggers, migrations, and tests. It is by semantic row/state where a table contains both staged and completed records.

| State / table or object | Class | Authority and rebuild rule |
| --- | --- | --- |
| `persons` stable IDs, profile fields, lifecycle, identity/biometric state, canonical mapping | A — Authoritative | Current identity state and historical nodes. Archive/delete/merge never erase the row. `persons.notes` and legacy merge metadata are compatibility fields. |
| `embeddings` rows and enrollment owner | A — Authoritative | Biometric enrollment and raw ownership. Effective ownership applies corrections then canonical resolution. Linear/HNSW indexes are not authority. |
| `biometric_enrollment_history` | C — Historical / immutable | Immutable accepted-enrollment provenance. |
| finalized `observations`, `observation_media`, raw `observation_participants` | A — Authoritative | Finalized event history, existing-media membership, and accepted-at-the-time raw participants. Draft observations are persistent work in progress, not graph authority. |
| `observation_face_assignments` | C — Historical / immutable | Accepted face-to-event/embedding/original-person provenance. |
| `identity_corrections` | C — Historical / immutable | Ordered append-only transformations. Interpretation applies corrections before canonical resolution. |
| completed `photo_reviews` and `photo_review_faces` | C — Historical / immutable | Explicit final decisions and completion linkage. `IN_PROGRESS` rows/staged sources are D until atomically completed; cancelled rows create no identity/graph truth. |
| `pending_additions`, `init_sessions`, `init_faces`, `init_groups`, exclusions | D — Ephemeral / non-authoritative | Persisted staging/proposal state. It cannot create identity or graph truth before finalization. |
| active and retired `relationship_evidence` | A — Authoritative | Independent evidence provenance/revisions are graph truth. Retirement changes current support without deleting history. A manual assertion is currently its `MANUAL_ASSOCIATION` evidence row; no second manual-assertion table exists. |
| `graph_connections` | B — Derived / rebuildable | Deterministic aggregate of active evidence after canonical resolution and self-edge suppression. It is the P11-A `SAFE_REBUILD` state. |
| `graph_state` revision | B — Derived / rebuildable | Opaque invalidation metadata, not evidence or an operation count. P11-A does not infer a “correct” numeric revision. |
| `notes` identity/lifecycle | A — Authoritative | Stable note identity, owner/subject, and active/retired state. |
| `note_revisions`, `note_revision_mentions` | C — Historical / immutable | Saved content and exact person-ID mention snapshots. Text parsing is never authority. |
| active/retired `note_mentions` | A — Authoritative | Current mention occurrence plus retirement provenance. Active occurrences support current `NOTE_REFERENCE` evidence. |
| `merge_operations`, `merge_affected_items`, `merge_conflict_resolutions` | C — Historical / immutable | Normalized manifest, ownership/action inventory, conflict selection, and inverse data. Later merges may extend the terminal chain beyond the originally selected survivor. |
| `operation_journal`, `operation_journal_status_history` | C — Historical / immutable | Immutable operation identity/details and append-only transitions. History cannot be reconstructed by guessing. |
| local media and durable paths referenced by normalized records | A — Authoritative | Media content is local authority. P11-A checks durable database provenance, not ordinary path readability: protected files and test/reference paths are not plain-file existence claims. |
| `recognition_details`, `person_associations`, `person_operations`, `person_change_history` | C — Historical / compatibility | Retained history. They cannot determine current participants, graph, notes, activity, or analytics. `recognition_details` can be durable media provenance. |
| `persons.notes` mirror and legacy `metadata.merged_into` | C — Historical / compatibility | Migration/compatibility only; normalized notes and canonical columns own current interpretation. |
| linear/HNSW indexes | B — Derived / rebuildable | Replaceable biometric lookup caches from effective active embedding ownership. Outside the P11-A graph checker. |
| sightings, analytics, Person Graph, World entities/clusters/patterns/explanations/rankings | D — Ephemeral / read model | Request-local projections. No World table or cache exists. |
| React layout, pages, filters, camera, selection, hover, retained responses | D — Ephemeral / read model | Presentation state only; never an integrity source. |

## Severity and future handling

- `CRITICAL`: contradictory authoritative/history state, a non-terminating identity chain, partial visible authoritative mutation, or physical database damage.
- `ERROR`: a definite integrity violation, dangling required reference, or projection drift.
- `WARNING`: suspicious but potentially valid partial/history state. P11-A deliberately has no heuristic warning checks.
- `INFO`: a factual non-corrupt condition worth reporting. P11-A does not emit ordinary aliases, archived/deleted people, or retired evidence as noise.

Future handling is classification only: `SAFE_REBUILD` regenerates purely derived state; `STRUCTURED_REPAIR` would require a future journaled domain command; `MANUAL_REVIEW` forbids guessing; and `UNRECOVERABLE_FROM_LOCAL_STATE` requires backup/restore or external evidence.

## Fixed P11 invariant registry

The executable registry is `sentriface.integrity.INTEGRITY_INVARIANTS`. Every finding contains the stable ID, domain, severity, concrete entity IDs, bounded factual evidence, and future-handling classification.

| ID | Domain / severity | Authoritative condition | Future handling |
| --- | --- | --- | --- |
| `P11-SCHEMA-001` | Schema / Critical | Schema v28 and required tables/checker-critical columns exist. | Unrecoverable from local state |
| `P11-SCHEMA-002` | Schema / Critical | SQLite `integrity_check` succeeds. | Unrecoverable from local state |
| `P11-SCHEMA-003` | Schema / Error | Authoritative foreign keys have no dangling reference. Projection FK drift is graph drift. | Manual review |
| `P11-IDENTITY-001` | Identity / Critical | Lifecycle, timestamps, identity/biometric values, and canonical-field shape are legal. | Structured repair |
| `P11-IDENTITY-002` | Identity / Critical | Canonical targets exist; chains terminate; no cycle/self-map exists. | Manual review |
| `P11-IDENTITY-003` | Identity / Error | Merged chains terminate at a current active, non-deleted canonical person. | Structured repair |
| `P11-CORRECTION-001` | Correction / Critical | Correction type/scope is legal; assignment/ownership chains are continuous. | Manual review |
| `P11-CORRECTION-002` | Correction / Error | Correction-before-canonical interpretation resolves legal identities; observation corrections remain applicable. | Manual review |
| `P11-OBSERVATION-001` | Observation / Error | Finalized observations have timestamps plus raw/effective participants; drafts lack finalization timestamps. | Manual review |
| `P11-OBSERVATION-002` | Observation / Error | Raw keys and current effective participants obey uniqueness/existence rules. | Manual review |
| `P11-OBSERVATION-003` | Observation / Error | Observation media has a non-empty ID and durable database provenance. | Manual review |
| `P11-REVIEW-001` | Review / Critical | Completed decisions, journal result, optional finalized observation, and completion fields agree. | Manual review |
| `P11-EVIDENCE-001` | Evidence / Error | Type/source/direction/raw endpoints/active fields and typed source are coherent. | Manual review |
| `P11-EVIDENCE-002` | Evidence / Error | Active evidence resolves legally and co-observation endpoints remain effective participants. Canonically collapsed self-evidence is legal history. | Manual review |
| `P11-GRAPH-001` | Projection / Error | Stored graph exactly equals the active-evidence aggregate; missing, extra, malformed, wrong-support, and self-edge rows fail. | Safe rebuild |
| `P11-NOTE-001` | Note / Error | Every note has contiguous revisions and valid revision mentions. | Manual review |
| `P11-NOTE-002` | Note / Error | Mention active/retired state agrees with note lifecycle and latest revision. | Structured repair |
| `P11-NOTE-003` | Note / Error | Active non-self mentions have exactly one matching active directed `NOTE_REFERENCE`; inactive mentions are not active support. | Structured repair |
| `P11-MERGE-001` | Merge / Critical | Manifest/journal identity, actor, status, and current transitive source/target terminal resolution agree. | Manual review |
| `P11-MERGE-002` | Merge / Critical | Affected item/action/ownership and conflict selected/inverse JSON are structurally complete. | Manual review |
| `P11-JOURNAL-001` | Journal / Critical | History starts at `STARTED`, follows allowed transitions, and ends at row status. | Manual review |
| `P11-JOURNAL-002` | Journal / Error | Actor/context/affected/details JSON and `completed_at` semantics are valid. | Manual review |
| `P11-JOURNAL-003` | Journal / Critical | Journal-linked authoritative rows belong only to committed/reverted operations; known committed review, merge, observation-correction, and Move Face commands have normalized results. | Manual review |

## Checker architecture and execution

`ReadOnlyIntegrityChecker` is an explicit service-level command object. It accepts a database path and optional encryption key and returns immutable `IntegrityReport`: start/completion timestamps, schema version, graph revision, worst status, checks run, deterministic findings, severity counts, and a truncation flag.

The checker never calls `SQLiteIdentityStore.initialize()`. Plain SQLite opens with `mode=ro`; encrypted storage uses the keyed connector and immediately enables `PRAGMA query_only`. A deferred read transaction establishes one snapshot. Checker statements are `SELECT`, `WITH`, read-only `PRAGMA`, or `BEGIN`. The read-only URI and query-only mode enforce the no-write boundary. On a cleanly closed WAL database SQLite may create a zero-length sidecar while opening it, but no WAL frame, table row, graph revision, journal row, or authoritative database byte is written.

Individual SQL failures become findings and later checks continue when safe. Findings sort by invariant/entity/message/evidence. `max_findings` defaults to 10,000 and sets `findings_truncated` instead of building an unbounded diagnostic payload.

Set-based joins cover foreign keys, finalization, review state, evidence sources, notes, journal linkage, and known results. Evidence is streamed. Canonical people, corrections, effective-participant working sets, and unique expected graph aggregates are request-local memory bounded by normalized person/correction/edge cardinality; no persistent cache or integrity table is created. A 500-person fixture confirms the SQL statement count does not grow with person count (76–86 traced read statements depending on empty-database `integrity_check` internals).

Expected graph state is calculated without mutation. Active evidence is canonically resolved, undirected endpoints are ordered, collapsed self-links are suppressed, and remaining rows group by endpoints/type/direction with exact count, evidence-type set, and latest time. Missing, extra, and unequal stored rows are separately reported.

## P11-B explicit graph projection rebuild

`GlobalIdentityGraphService.rebuild_projection()` is the explicit local service boundary for exceptional graph recovery. It accepts an idempotency/operation ID plus bounded actor, source, reason, and context metadata. It has no HTTP/UI route, startup hook, scheduler, worker, polling loop, or automatic invocation from the checker. Normal domain commands continue to maintain the projection transactionally.

The authoritative input is active and retired `relationship_evidence` interpreted with existing persons/corrections/canonical state. The only domain projection target is `graph_connections`; `graph_state` and the new immutable `graph.projection.rebuild` journal operation are operational bookkeeping. The shared `_expected_graph_connections` function is used by normal projection maintenance, P11-A comparison, validation, and P11-B. It streams evidence after set-based loads of people, observations/participants, corrections/assignments, and note mentions. Its semantics are active-evidence filtering, correction-before-canonical interpretation, canonical collapse, self-edge suppression, directed preservation, undirected normalization, and exact count/type/latest-time aggregation for `CO_OBSERVED`, `NOTE_REFERENCE`, and `MANUAL_ASSOCIATION`.

Every rebuild first runs the full P11-A checker. A report containing only `P11-GRAPH-001` errors is classified `PROJECTION_DRIFT` and may proceed. Any other `ERROR`/`CRITICAL` finding, or a truncated report, is `BLOCKED`: the graph and revision are untouched, a bounded `FAILED` journal attempt records the refusal, and the caller receives `GraphProjectionRebuildRefused`. Authority is recomputed after `BEGIN IMMEDIATE`, so a change between preflight and the write snapshot also aborts rather than being guessed.

Inside one SQLite write transaction, P11-B computes expected and stored signatures. A true equality is a committed journaled no-op: no graph rows are replaced and the opaque revision is unchanged. Drift uses deterministic delete-plus-insert of the complete expected projection, validates exact equality before advancing revision, advances once only when semantic projection changed, and commits the journal result atomically. The bounded result records revision before/after, active evidence, expected/stored edge counts, added/removed signature counts, preflight status, and postcheck status; it never stores edge payloads. Retrying the same committed operation ID returns the same result. Failed insertion, validation, or revision advancement rolls back the old projection and revision, then records the existing `STARTED → FAILED` lifecycle in a separate transaction.

After commit, P11-A runs again. Its successful result proves `P11-GRAPH-001` and all other invariants pass at that new read snapshot. An unexpected post-commit finding raises `GraphProjectionPostcheckError` prominently and never starts another repair.

Current-schema startup is validation-only for graph drift. It reports/refuses an inconsistent projection and directs the operator to explicit P11-B; it does not replace rows or advance revision. The supported schema-v26-to-v27 upgrade retains a one-time transactional derived-projection normalization because v27 introduced `graph_state`; this is migration backfill, not current-schema automatic repair.

Tests directly corrupt disposable databases to cover missing/extra/wrong-direction/wrong-support/stale-retired/self rows, all evidence directionality families, correction then merge, merge then correction, no-op retries, authoritative refusal, and failures after deletion/before insertion, validation, and revision advancement. Snapshots prove persons, embeddings/enrollment history, observations/media/participants/assignments, corrections, evidence, notes/revisions/mentions, and merge manifests/items/conflicts are unchanged; pre-existing journal rows/history are unchanged and only the rebuild operation is appended. A 400-evidence fixture produces 400 expected edges using eight or fewer projection read statements, demonstrating fixed query shape without N+1 behavior or a new cache/index.

## Explicit limits and non-ambiguities

- Raw historical IDs, archived/deleted persons, merged sources, transitive merge chains, retired evidence, and canonically collapsed self-evidence are valid.
- A manual association has no separate assertion table in v28; its immutable `MANUAL_ASSOCIATION` evidence row is the assertion authority.
- Media has no universal content hash/normalized media table. P11-A proves durable database provenance but cannot call an arbitrary protected/reference path corrupt without redefining semantics.
- The journal has heterogeneous legacy/current operation types. P11-A checks the state machine, JSON, normalized operation FKs, and known phase-owned result links. It does not infer current person state from an old lifecycle operation because later valid operations may supersede it.
- `graph_state.revision` has no authoritative expected numeric value. P11-A reports it and validates projection content; it does not guess a missing increment.
- SQLite cannot prove an absent authoritative record once existed. Such findings are manual/unrecoverable; P11-A never synthesizes it.

These are architectural boundaries, not P11-A blockers. They constrain later repair/recovery design.

## Remaining P11 sequence

1. **P11-A — Read-only integrity checker:** complete.
2. **P11-B — Deterministic graph projection rebuild:** complete; explicit preflight-gated, atomic, journaled, revision-aware replacement with no authority rewrite.
3. **P11-C1 — Structured repair authority audit/catalog/design:** complete and frozen. The only commands admitted are restoring an otherwise-valid archived terminal merge survivor and reconciling diagnosed note occurrence/reference state from immutable revision authority.
4. **P11-C2 / R01:** implemented as explicit Python/service invocation with typed finding preconditions, in-transaction revalidation, immutable repair journaling, shared lifecycle mutation, exact projection/revision validation, and full P11-A post-check. **R02 remains unimplemented.**
5. **P11-D — Revert execution:** future; operation-specific preconditions/inverse data and atomic journaled execution.
6. **P11-E — Integrity/recovery UI and acceptance:** future; explicit invocation and factual reports, no polling/background scan.
