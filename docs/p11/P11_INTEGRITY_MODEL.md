# P11 integrity authority model, checker, and graph rebuild

Status: **P11-A/B/C/D/E are complete and frozen.** Both R01 and R02 are implemented. The two R02 safety stops remain in the architecture record: P11-A1 corrected occurrence history, and P11-C2A corrected dependent evidence-history/shared graph authority without changing normal note/evidence mutations, schema, API, or missing-occurrence coverage. P12 consumes P11-A as the backup/restore semantic gate and P11-B to rebuild untrusted staged graph projection; it does not broaden repair/revert authority.

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
| active and retired `relationship_evidence` | A — Authoritative | Independent evidence provenance/revisions are graph truth. Active rows are current support. Fully deactivated rows are immutable historical provenance and need not mirror a source occurrence that is current again or still current. A manual assertion is currently its `MANUAL_ASSOCIATION` evidence row; no second manual-assertion table exists. |
| `graph_connections` | B — Derived / rebuildable | Deterministic aggregate of active evidence after canonical resolution and self-edge suppression. It is the P11-A `SAFE_REBUILD` state. |
| `graph_state` revision | B — Derived / rebuildable | Opaque invalidation metadata, not evidence or an operation count. P11-A does not infer a “correct” numeric revision. |
| `notes` identity/lifecycle | A — Authoritative | Stable note identity, owner/subject, and active/retired state. |
| `note_revisions`, `note_revision_mentions` | C — Historical / immutable | Saved content and exact person-ID mention snapshots. Text parsing is never authority. |
| active/retired `note_mentions` | A — Authoritative | Active rows are the current occurrence layer. Inactive rows are preserved historical occurrences and remain valid across later remove/re-add cycles when their same-note retirement revision, operation, and timestamp provenance is complete. |
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

## P11-D guarded operation-revert authority

The operation audit classifies actual journaled mutations by whether preserved local state proves a unique history-preserving inverse:

| Journaled operation family | Classification | Reason |
| --- | --- | --- |
| Normalized `identity.merge` with an originally active/unmapped source, complete manifest/journal, no survivor profile/note/biometric mutation, exact current post-state, and no later dependent operation | `SAFE_GUARDED_REVERT` | Raw ownership and evidence were preserved; the only authoritative merge mutation needing reversal is the source lifecycle/canonical interpretation. |
| Any other normalized merge | `NOT_SAFELY_REVERTIBLE` | Archived-source timestamps, survivor conflict selections/note revisions/biometric state, changed entities, or later dependencies prevent a unique inverse without rewriting or guessing. |
| `identity.archive`, `identity.restore`, biometric face delete/restore, identity profile/preferences updates, and active note create/update/profile-save where a normal later command remains legal | `COMPENSATING_OPERATION_ONLY` | The opposite intent is another forward journaled domain operation; the original operation is not marked reverted or erased. |
| Observation/Move Face identity corrections | `COMPENSATING_OPERATION_ONLY` | A later correction may supersede current interpretation, but immutable correction rows are never deleted or inverted. |
| Typed evidence creation/deactivation where current source authority permits new support | `COMPENSATING_OPERATION_ONLY` | Retired evidence is one-way history; a later evidence revision may compensate but old evidence is never reactivated. |
| Review completion, observation finalisation, note retirement, tombstoned identity deletion, R01, R02, and graph rebuild | `NOT_SAFELY_REVERTIBLE` | Reversal would erase accepted/finalized history, reactivate retired rows, recreate a proven integrity defect, or restore known projection drift. |
| Biometric physical purge/purge-expired and any lost local media or authoritative row | `BACKUP_RESTORE_ONLY` | Required content/inverse state no longer exists in live local authority. |

The whitelist contains exactly the first row and uses operation type `identity.merge.revert`. `prepare_revert(operation_id)` requires a clean, untruncated P11-A report and returns an immutable schema-v28 token containing the original operation ID/type/status, fingerprint, affected entities, journal-history fingerprint, lifecycle/graph revisions, source/target state, complete merge/projection fingerprints, and dependency-state fingerprint. Preparation refuses unsupported/already-reverted/non-committed operations, malformed or incomplete history, unsafe merge shapes, changed post-state, ambiguous manifests, and any later operation touching a manifest-affected entity.

`execute_revert(precondition, operation_id, actor, reason)` repeats the complete classification under `BEGIN IMMEDIATE`. It starts a new journal operation, changes only the merge source from `MERGED` to a new `ACTIVE` lifecycle state with no canonical target, deterministically replaces/validates the graph projection, validates foreign keys and byte-stable merge/survivor history, appends `COMMITTED → REVERTED` to the original journal, commits the new revert operation, refreshes the derived index, and runs full P11-A. The source lifecycle trigger and normal projection replacement advance the graph revision under existing rules. Exact committed retry is idempotent; a reused or failed ID cannot acquire new meaning.

Refusal performs zero mutation. Failure after the new `STARTED` entry, source mutation, graph update, immediate validation, or final journal transitions rolls the whole authoritative transaction back; only a separate bounded `STARTED → FAILED` attempt may remain. Original journal identity/details/transitions and all merge manifests/items/conflicts remain immutable; only the legal appended `REVERTED` transition is added after a successful separate revert operation. No evidence, correction, note revision, participant, observation, or historical row is deleted, reactivated, retargeted, or rewritten.

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
| `P11-OBSERVATION-003` | Observation / Error | Observation media has a non-empty ID and independent registry-owned source provenance; saved accepted-face occurrence-media IDs belong to their own observation. | Manual review |
| `P11-REVIEW-001` | Review / Critical | Completed decisions, journal result, optional finalized observation, and completion fields agree. | Manual review |
| `P11-EVIDENCE-001` | Evidence / Error | Type/source/direction/raw endpoints/lifecycle provenance and typed source are coherent. An active `NOTE_REFERENCE` requires an active occurrence on an active note; a fully retired evidence revision remains valid history regardless of whether that occurrence is current now. | Manual review |
| `P11-EVIDENCE-002` | Evidence / Error | Active evidence resolves legally and co-observation endpoints remain effective participants. Canonically collapsed self-evidence is legal history. | Manual review |
| `P11-GRAPH-001` | Projection / Error | Stored graph exactly equals the active-evidence aggregate; missing, extra, malformed, wrong-support, and self-edge rows fail. | Safe rebuild |
| `P11-NOTE-001` | Note / Error | Every note has contiguous revisions and valid revision mentions. | Manual review |
| `P11-NOTE-002` | Note / Error | For each existing note/person occurrence group, active cardinality is exactly one when the active latest revision requires that non-self person and zero otherwise. Retired historical occurrences remain valid with complete same-note retirement provenance. A latest-revision person with no occurrence rows remains outside current coverage. | Structured repair for the already-frozen R02 shapes only |
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

Expected graph state is calculated without mutation. Only active evidence is canonically resolved, undirected endpoints are ordered, collapsed self-links are suppressed, and remaining rows group by endpoints/type/direction with exact count, evidence-type set, and latest time. Retired evidence is validated as history but never projected. For `NOTE_REFERENCE`, the shared authority validates per-row provenance plus current active cardinality per occurrence; it does not require every historical revision to mirror current source state. Missing, extra, and unequal stored rows are separately reported.

### P11-A1 note-occurrence correction and refreeze

The original `P11-NOTE-002` implementation compared every occurrence row independently with membership in the latest revision. That was incorrect for append/retire history: after mention, removal, and later re-mention, it demanded that both the retired historical occurrence and the new current occurrence be active. The normal note domain correctly never reactivates or deletes historical rows.

The refrozen checker first validates each occurrence's own state. Active rows have no retirement fields. Inactive historical rows require a retirement revision belonging to the same note at or after their creation revision, plus retirement operation and timestamp. It then groups only existing occurrence rows by raw note/person identity and compares current active cardinality with the immutable latest revision: one active occurrence for a required active non-self mention, otherwise none. Inactive historical rows do not contribute to current cardinality. No row ID or timestamp ordering is used to select a current occurrence.

Coverage remains deliberately unchanged when the latest revision mentions a person for whom no `note_mentions` occurrence row exists: `P11-NOTE-002` still emits no finding. `P11-NOTE-003` is unchanged and continues to require exactly one matching active directed `NOTE_REFERENCE` only for a current active non-self occurrence. Regression tests prove valid remove/re-add cycles are clean, malformed provenance and wrong active cardinality still fail, historical evidence stays inactive, and the frozen R02 append/retire result can theoretically clear its finding without rewriting history.

### P11-C2A consolidated note/evidence/graph authority model

P11-C2A proved the lifecycle model from the one-way schema triggers and normal storage commands. `note_revisions` and `note_revision_mentions` are immutable snapshots. A `note_mentions` row has immutable identity/creation provenance and may only transition active → inactive; re-add creates another occurrence. A `relationship_evidence` row likewise has immutable identity/source/endpoints/creation provenance and may only transition active → inactive; replacement support is another evidence revision. Therefore retired rows describe completed history, while active-row cardinality describes current truth.

Authority is split as follows:

| Layer | Historical authority | Current authority | Derived current state |
| --- | --- | --- | --- |
| Note | every immutable ordered revision and exact `note_revision_mentions` snapshot | latest revision plus note lifecycle | rendered current note |
| Occurrence | every occurrence row and its creation/retirement provenance | active rows per existing raw note/person group | none |
| `NOTE_REFERENCE` | every evidence revision and its creation/deactivation provenance | active evidence rows per current occurrence | effective/canonical endpoints |
| Graph | raw historical evidence remains queryable | current active evidence only | `graph_connections` aggregate and opaque graph revision |

Current cardinality ownership is intentionally non-overlapping. `P11-NOTE-002` requires one active occurrence for each existing group required by an active latest revision and zero otherwise. `P11-NOTE-003` requires one matching active directed `REFERENCES`/`NOTE_REFERENCE` row for each active non-self occurrence on an active note and zero active rows for every other occurrence. `P11-EVIDENCE-001` validates each evidence row's type, source, endpoints, direction, relationship type, and lifecycle provenance; it rejects active evidence without a current active source but does not reinterpret a fully retired row as current support. `P11-EVIDENCE-002` validates only current active evidence under correction-before-canonical resolution and retains legal canonical self-collapse as suppressed history. `P11-GRAPH-001` owns exact stored-versus-expected projection equality.

The complete state table is:

| Latest revision / note | Occurrence history in an existing group | Expected active occurrence | Validity / owner |
| --- | --- | ---: | --- |
| active note mentions A | one active | 1 | valid — `P11-NOTE-002` |
| active note mentions A | retired + newer active, or several retired + one active | 1 | valid; retired rows remain history |
| active note mentions A | retired rows only | 1 | invalid current cardinality — `P11-NOTE-002` |
| active note mentions A | duplicate active | 1 | invalid current cardinality — `P11-NOTE-002` |
| active note does not mention A | retired rows only | 0 | valid history |
| active note does not mention A | stale active row | 0 | invalid current cardinality — `P11-NOTE-002` |
| retired note | all occurrences retired | 0 | valid history |
| any | inactive row missing same-note retirement revision/operation/time | as above | invalid row provenance — `P11-NOTE-002` |
| active note mentions A | no occurrence group ever existed | not evaluated | preserved checker-coverage boundary |

| Source occurrence/note | Evidence history | Expected active `NOTE_REFERENCE` | Validity / owner |
| --- | --- | ---: | --- |
| active non-self occurrence on active note | one active | 1 | valid |
| active non-self occurrence on active note | retired + newer active, or many retired + one active | 1 | valid; retired revisions remain history |
| active non-self occurrence on active note | retired only / zero active | 1 | invalid current cardinality — `P11-NOTE-003` |
| active non-self occurrence on active note | duplicate active | 1 | invalid current cardinality — `P11-NOTE-003` |
| inactive occurrence or retired note | retired evidence only | 0 | valid history |
| inactive occurrence or retired note | stale active evidence | 0 | invalid source/current state — `P11-EVIDENCE-001`, cardinality consequence in `P11-NOTE-003` |
| any | retired row with missing deactivation operation/time or non-committed journal linkage | unchanged | invalid provenance — `P11-EVIDENCE-001` and/or `P11-JOURNAL-003` |
| any | missing source, wrong endpoints, wrong source/type, non-directed, or non-`REFERENCES` note evidence | unchanged | invalid row provenance — `P11-EVIDENCE-001` |

| Active support after canonical resolution | Expected graph | R02 revision effect |
| --- | --- | --- |
| `NOTE_REFERENCE` only, distinct effective endpoints | directed `REFERENCES` edge | advance once when active evidence changes |
| `NOTE_REFERENCE` plus `CO_OBSERVED` and/or `MANUAL_ASSOCIATION` | independent typed support remains aggregated | advance once; retiring note support cannot erase other types |
| endpoints collapse canonically | no self-edge; raw evidence remains | advance once for active-evidence provenance change even if projection stays empty |
| retired `NOTE_REFERENCE` only | no note-derived edge | no retired row contributes |
| correction → merge or merge → correction | correction applies to observation authority before canonical resolution; note raw endpoints use canonical resolution | exact shared projection remains rebuildable |

The scoped contradiction register is closed:

1. The former `P11-NOTE-002` row-by-row latest-membership rule rejected valid retired occurrences. P11-A1 corrected it to current group cardinality.
2. The former `P11-EVIDENCE-001` equality `evidence.active == occurrence.active && note.active` rejected valid retired evidence revisions attached to a current occurrence. P11-C2A now applies current-source compatibility only to active evidence; retired rows retain strict provenance validation.
3. The shared `_expected_graph_connections` repeated the same row equality and blocked normal projection validation, P11-B authority calculation, and the frozen R02 replacement result. It now validates historical rows independently, enforces current `NOTE_REFERENCE` cardinality per occurrence, and projects only active evidence.
4. The former frozen R02 precondition rejected every `P11-EVIDENCE-001` finding, yet a stale active `NOTE_REFERENCE` on a proven inactive occurrence necessarily owns that finding and was explicitly required in the R02 case matrix. The refrozen model admits only that exact stale-active/inactive-source shape inside R02; all malformed source/type/endpoint/direction/retirement and all `P11-EVIDENCE-002` findings still refuse.
5. Removing the old equality without a replacement cardinality guard would have allowed the generic evidence-deactivation path to commit an unsupported active occurrence. The shared authority now rejects that intermediate/final state, so normal mutation safety is unchanged.

`P11-NOTE-003` and `P11-EVIDENCE-002` contained no history/current contradiction and were not weakened. `CO_OBSERVED` source/finalization/effective-participant rules and `MANUAL_ASSOCIATION` lifecycle/projection rules remain unchanged. Evidence retirement proof in schema v28 is the inactive flag together with non-null `deactivated_operation_id` and `deactivated_at`, foreign-key linkage, and a committed/reverted journal result; there is no replacement-link column to invent. Occurrence retirement additionally requires a same-note retirement revision at or after creation plus operation and timestamp.

## P11-C structured repair execution

R01 and R02 are the complete whitelist. R02 preparation is finding-bound to one existing note/person group and deterministically selects one of five frozen plans. Execution revalidates the full token under `BEGIN IMMEDIATE`, appends or retires occurrence/evidence rows without reactivation or deletion, validates with shared active-only graph authority, maintains only the affected directed aggregate, and advances graph revision once exactly when active evidence changes. A canonical self-collapse still advances because provenance changed; occurrence-only retirement without evidence does not. The committed repair and its journal share the transaction, and a full untruncated P11-A post-check is mandatory.

R02 refuses wholly missing groups, multiple active occurrences, ambiguous multi-plan states, incomplete occurrence/evidence retirement provenance, wrong type/source/endpoints/direction, any `P11-EVIDENCE-002`, invalid correction/canonical state, unrelated blocking findings, stale fingerprints/revisions/journals, and graph drift outside the selected relationship key. Valid retired occurrence and evidence revisions remain byte-for-byte unchanged. `CO_OBSERVED` and `MANUAL_ASSOCIATION` evidence is never selected or mutated.

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

## P11-E integrity and recovery presentation

P11-E is complete as a bounded application/API/UI layer over the frozen P11-A/B/C/D services. `IntegrityRecoveryApplication` never serializes `IntegrityReport` or `IntegrityFinding` directly. Its versioned DTO caps findings, entity identifiers, evidence facts, operation summaries, and results; removes filesystem/database paths, SQLite/SQL diagnostics, stack traces, note content, embeddings, actors, secrets, and raw journal data; and reports only factual status/timestamps/schema/graph revision/severity/invariant/domain/message plus server-owned action hints.

Action hints do not mirror `future_handling`. Isolated `P11-GRAPH-001` drift can prepare P11-B; exact `P11-IDENTITY-003` terminal groups can request R01 preparation; exact existing note/person `P11-NOTE-002/003` groups can request R02 preparation; and recent normalized merges are merely `PREPARATION_REQUIRED` until P11-D proves one operation safe. Every preparation invokes the existing service. Signed report/action references prevent the client from selecting another finding target, and signed wrappers preserve the exact typed R01/R02/revert precondition. Execution requests contain only token, fresh operation UUID, and bounded reason; unknown fields reject. P11-B retains its independent fresh P11-A execution preflight.

All `/api/integrity/*` routes explicitly require the existing `recovery` capability, which remains administrator-only, and use the authenticated server-side actor. They bypass recognition-model readiness without bypassing session, origin, host, or capability checks. Stale/tampered/refused requests return a typed conflict with `committed: false`; a failed post-commit checker remains `committed: true` with `postcheck_failed_after_commit`. The Debug/System panel is manually invoked and replaces its state only from backend responses. There is no polling, background check, startup mutation, worker, scheduler, optimistic graph/identity patch, repair-all, arbitrary repair ID, whitelist expansion, or schema change.

P12 invokes the checker on the completed backup snapshot, on the staged candidate after migration/path rewrite/P11-B, and on installed state after reload. A format-v3 backup is restore-eligible only when P11-A is clean, except isolated `P11-GRAPH-001` projection drift may be retained in the backup because the staged projection is explicitly untrusted and must be rebuilt before the candidate can pass. Every authoritative P11 finding refuses restore; P12 never invokes R01, R02, P11-D, or any other repair automatically. Normal current-schema startup remains validation-only. Disposable staged migration may carry projection drift only as far as the mandatory P11-B rebuild; relationship evidence and all other authority validation remain strict.

## Completed P11 sequence

1. **P11-A / P11-A1 / P11-C2A — Read-only integrity semantics:** complete and refrozen after correcting occurrence history, evidence revision history, and shared graph-authority current-cardinality semantics.
2. **P11-B — Deterministic graph projection rebuild:** complete; explicit preflight-gated, atomic, journaled, revision-aware replacement with no authority rewrite.
3. **P11-C1 — Structured repair authority audit/catalog/design:** complete and frozen. The only commands admitted are restoring an otherwise-valid archived terminal merge survivor and reconciling diagnosed note occurrence/reference state from immutable revision authority.
4. **P11-C2 / R01 and R02:** complete as explicit Python/service invocation with typed finding preconditions, in-transaction revalidation, immutable repair journaling, append/retire-only history preservation, exact projection/revision validation, rollback/idempotency rules, and full P11-A post-check. The whitelist remains exactly two.
5. **P11-D — Revert execution:** complete; one operation-specific normalized-merge subset with immutable preconditions, conservative dependency refusal, atomic graph/journal execution, rollback tests, and P11-A post-check.
6. **P11-E — Integrity/recovery UI and acceptance:** complete; administrator-only explicit checks, bounded factual DTOs, signed preparation tokens, typed refusal/post-check outcomes, manually confirmed execution, and no polling/background scan.

## Batch 3.6 provenance interpretation

The read-only checker and write admission share `media_registry` source lookup, excluding observation membership as its own proof. Retained multi-photo review/session references are valid independently of embedding reuse, correction generations or Person lifecycle. Enrollment images and later occurrence media are distinct provenance. Physical asset closure/authentication remains the existing backup verifier's responsibility; its checks are not disabled. Rebuild and restore consume this checker unchanged at their safety boundaries.
