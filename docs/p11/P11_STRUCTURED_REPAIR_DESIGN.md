# P11 structured repair authority audit and execution design

Status: **P11-C is complete and frozen: P11C-R01 and P11C-R02 are implemented against the P11-C1/C2A two-command authority model. P11-D is separately complete with one guarded merge-revert subset, and P11-E exposes only these frozen commands through a guarded administrator UI/API.** The first R02 safety stop led P11-A1 to correct `P11-NOTE-002`; the second led P11-C2A to correct `P11-EVIDENCE-001` and shared graph authority while preserving current cardinality validation. Both contradictions remain recorded below. R02 now executes every frozen case without history rewrite. P12 backup/restore does not invoke either repair automatically and does not change the two-command catalog.

## Scope and verified implementation basis

This audit starts only from the executable `INTEGRITY_INVARIANTS` entries whose `future_handling` is `STRUCTURED_REPAIR`. It was checked against schema v28 and the implemented storage, service, trigger, transaction, graph, journal, correction, review-finalisation, merge, and lifecycle paths. Documentation was not treated as implementation proof.

The relevant implementation facts are:

- `persons` stores mutable current lifecycle/canonical/identity/biometric state; merge manifests and journal rows preserve the operations that established historical interpretation.
- canonical resolution is transitive. Normalized merge execution is the only operation that creates a canonical mapping and an immutable merge manifest.
- note revisions and their mention snapshots are immutable. `note_mentions` is the authoritative current occurrence layer and can only transition from active to inactive; reappearance requires a new occurrence.
- `NOTE_REFERENCE` evidence has immutable identity/provenance and can only transition from active to inactive; replacement support must be appended as a new evidence revision. Fully retired evidence remains valid historical provenance even when its source occurrence is current now, provided deactivation operation/time and journal linkage are complete.
- graph-affecting authoritative writes, the complete `graph_connections` replacement, revision advancement, and successful journal transition already share a storage transaction in normal note/correction/review/merge paths.
- the journal supports immutable identity/details and append-only `STARTED -> COMMITTED` or `STARTED -> FAILED` history. A failed attempt can be recorded after the failed authoritative transaction rolls back.
- `ReadOnlyIntegrityChecker` is a separate query-only snapshot. It cannot validate uncommitted state on the repair connection, so exact immediate SQL/domain postconditions must run before commit and the full P11-A post-check must run after commit.

## Exact `STRUCTURED_REPAIR` candidate list

The registry-level candidates remain the four invariants below. P11-C2A additionally admits one subordinate `P11-EVIDENCE-001` finding shape inside R02 only: an otherwise coherent active `NOTE_REFERENCE` whose source occurrence/note is proven inactive. That is not a third repair command and does not admit any other evidence corruption.

| Invariant ID | Registered condition |
| --- | --- |
| `P11-IDENTITY-001` | Person lifecycle, timestamp, identity, biometric, and canonical-field shape is legal. |
| `P11-IDENTITY-003` | A merged chain terminates at a current active, non-deleted canonical person. |
| `P11-NOTE-002` | Existing note/person occurrence groups have the latest-revision-required current active cardinality while valid inactive rows remain historical. |
| `P11-NOTE-003` | Current active non-self mentions have exactly one matching active directed `NOTE_REFERENCE`, and inactive mentions have no active support. |

## Authority classification by actual finding shape

The registry classification identifies candidates, not blanket permission to mutate every row reported under the ID. The implemented checks group several materially different failure shapes under one ID.

| Invariant / finding shape | Class after implementation audit | Decision |
| --- | --- | --- |
| `P11-IDENTITY-001`: lifecycle/deletion timestamp disagreement | `MANUAL_REVIEW_ONLY` | The row does not prove whether the intended current state is active, archived, or deleted. Clearing a timestamp or changing lifecycle could silently replace a completed lifecycle decision. A normal operator transition may later supersede a valid state, but P11-C may not guess the starting truth. |
| `P11-IDENTITY-001`: illegal identity/biometric/lifecycle enum or self-map | `MANUAL_REVIEW_ONLY`, or `UNRECOVERABLE_FROM_LOCAL_STATE` when `P11-SCHEMA-002` also reports the constraint violation | Identity intent is not derivable from embeddings, names, or compatibility fields. Self-maps also conflict with `P11-IDENTITY-002`. Constraint/physical database findings retain their stronger P11-A handling. |
| `P11-IDENTITY-001`: MERGED/canonical-field shape disagreement | `MANUAL_REVIEW_ONLY` | `P11-IDENTITY-002` and often merge-history checks also apply. Creating, clearing, or retargeting a canonical mapping outside normalized merge semantics would rewrite interpretation history. |
| `P11-IDENTITY-003`: terminal survivor is `ARCHIVED`, has a lifecycle timestamp, has no canonical target, and all identity/merge/journal checks are otherwise clean | `DETERMINISTIC_STRUCTURED_REPAIR` | Restoring that terminal survivor to `ACTIVE` is the unique history-preserving way to retain every existing merge mapping and make the chain legal. Catalogued as `P11C-R01`. |
| `P11-IDENTITY-003`: terminal survivor is `DELETED` | `MANUAL_REVIEW_ONLY` | Deleted identities have no normal restore transition. Redirecting sources would contradict immutable merge manifests; reviving deletion belongs, if safe, to guarded P11-D operation-specific work. Missing local inverse/history may make backup/restore the only recovery. |
| `P11-NOTE-002`: an existing note/person occurrence group has wrong current active cardinality against an otherwise valid latest immutable revision snapshot | `DETERMINISTIC_STRUCTURED_REPAIR` | The note status and latest revision uniquely determine whether exactly one current non-self occurrence should exist. Prior inactive occurrences remain valid history; repair retires an excess/stale active occurrence or appends a new occurrence when the existing group has none active. Catalogued as `P11C-R02`. |
| `P11-NOTE-002`: note lifecycle shape is invalid or an inactive occurrence lacks complete retirement provenance | `MANUAL_REVIEW_ONLY`, or `UNRECOVERABLE_FROM_LOCAL_STATE` when structural integrity also fails | The missing operation/time/revision is historical truth. It cannot be filled with a repair timestamp while pretending that timestamp was the original retirement. Existing one-way triggers correctly prevent in-place rewriting. |
| `P11-NOTE-003`: a valid active current occurrence has zero or multiple otherwise coherent active matching evidence rows | `DETERMINISTIC_STRUCTURED_REPAIR` | The occurrence proves exactly one current directed reference. Missing support is appended; duplicate support is retired and replaced with one repair-owned revision. Existing retired revisions remain valid history even though the occurrence stays active. Catalogued as `P11C-R02`. |
| `P11-NOTE-003` plus `P11-EVIDENCE-001`: otherwise coherent active `NOTE_REFERENCE` is sourced by a valid inactive occurrence or retired note | `DETERMINISTIC_STRUCTURED_REPAIR` | The inactive authoritative source proves zero current support. R02 may retire that active evidence row without changing its immutable provenance. This is the only admitted evidence-invariant shape. |
| `P11-NOTE-003`: evidence has wrong endpoints/type/direction, a missing source, illegal canonical resolution, malformed retirement provenance, or any other `P11-EVIDENCE-001/002` conflict | `MANUAL_REVIEW_ONLY` | P11-C may not choose which conflicting authoritative row is true, fabricate retirement history, or rewrite immutable evidence identity. |
| Latest revision contains a referenced person but no `note_mentions` row exists at all | Outside the current executable finding contract | `P11-NOTE-002` currently iterates existing occurrence rows and does not diagnose a wholly missing occurrence. P11-C1 records this checker coverage gap but does not expand the catalog or synthesize an unreported repair. |

There are **no `OPERATOR_DIRECTED_REPAIR` catalog entries** in P11-C1. In particular, “choose a new canonical target” is normalized merge meaning, not a repair primitive. Allowing it here would create a second merge implementation and contradict old manifests. Choosing identity status or reconstructing note retirement history would introduce domain meaning that the current architecture does not define.

## Fixed repair catalog

Only these repair IDs may be implemented by P11-C. The repair-spec version is `1`; changing their semantic preconditions or mutations requires a new catalog version, not an in-place broadening.

| Repair ID | Invariants | Domain | Class |
| --- | --- | --- | --- |
| `P11C-R01-RESTORE-ARCHIVED-CANONICAL-SURVIVOR` | `P11-IDENTITY-003` | Identity lifecycle / merge interpretation | `DETERMINISTIC_STRUCTURED_REPAIR` |
| `P11C-R02-RECONCILE-NOTE-REFERENCE-STATE` | `P11-NOTE-002`, `P11-NOTE-003`, plus only the fixed stale-active-source shape of `P11-EVIDENCE-001` | Notes, mentions, relationship evidence | `DETERMINISTIC_STRUCTURED_REPAIR` |

### `P11C-R01-RESTORE-ARCHIVED-CANONICAL-SURVIVOR`

- **Required operator input:** explicit invocation, a fresh operation ID, authenticated actor, selected P11-A finding/terminal person ID, diagnosis fingerprint, and a bounded reason. There is no semantic target choice.
- **Authoritative sources consulted:** schema version; `persons` rows for the terminal and every source/path ending there; normalized `merge_operations`, affected items/conflicts, and their journal rows; the current graph revision; the complete fresh P11-A report.
- **Exact preconditions:** schema is exactly v28; the report is not truncated; every `ERROR`/`CRITICAL` finding is `P11-IDENTITY-003` for this same terminal; `P11-IDENTITY-001/002`, `P11-GRAPH-001`, `P11-MERGE-001/002`, and `P11-JOURNAL-001/002/003` are clean; the terminal row is exactly `ARCHIVED`, has non-null `deleted_at`, has null `canonical_person_id`, and retains the expected lifecycle timestamp; at least one `MERGED` source resolves to it; the exact incoming source/path set and normalized merge/journal operation IDs equal the diagnosed fingerprint; graph revision and person-row fingerprint still match under `BEGIN IMMEDIATE`.
- **Exact mutation:** through a connection-scoped lifecycle helper shared with normal restore semantics, set only the terminal person's current lifecycle to `ACTIVE`, clear `deleted_at`, and set `lifecycle_changed_at` to the repair time. Do not modify any canonical mapping or merge row. Append and commit the repair journal operation in the same transaction.
- **History preserved:** the archived lifecycle operation and all earlier journal transitions remain immutable; every merged source, raw owner, participant, correction, evidence endpoint, manifest, inverse payload, and old target remains unchanged. The repair is an explicit later lifecycle transition, not an edit to the old archive.
- **Journal operation type:** `integrity.repair.canonical-survivor.restore`.
- **Bounded journal result:** repair ID/spec version, invariant IDs, terminal person ID, count and bounded hash of affected merge-source paths, diagnosis fingerprint version/value, before lifecycle summary, after lifecycle summary, graph revision before/after, `changed: true`, and immediate postcondition status. Do not store full paths, whole findings, row dumps, media, or graph edges.
- **Graph/projection consequences:** canonical endpoints and `graph_connections` content do not change. The v28 person lifecycle trigger advances the opaque graph revision exactly once because lifecycle visibility/actions changed. The engine should reuse normal restore's derived vector-index refresh/reconciliation after the database commit; the index remains a cache, not part of authoritative repair proof.
- **Postconditions:** terminal is active/non-deleted/unmapped; every diagnosed source still follows the identical canonical path and now terminates legally; merge manifests still match their journal and terminal resolution; graph projection validation and foreign keys pass; the repair operation is `COMMITTED` with valid history.
- **P11-A checks expected to clear:** every `P11-IDENTITY-003` finding whose terminal is the repaired person.
- **Checks that must remain unchanged:** all other P11 invariant results; `graph_connections`; corrections; observations/participants/media; notes/revisions/mentions; evidence; merge manifests/items/conflicts; every pre-existing journal row/history. Only the terminal current lifecycle fields, `graph_state`, and new repair journal/history rows may change.
- **Retry/idempotency:** the exact same operation ID plus identical repair/request fingerprint returns the prior committed result. A reused ID with different input is rejected. If another operation already restored, merged, archived, or deleted the terminal, a new invocation is stale and refuses; it is not a clean no-op. A `FAILED` attempt is retried only with a new operation ID.
- **Failure behavior:** stale or blocking preconditions refuse before authoritative mutation and may record a bounded `STARTED -> FAILED` attempt. Any in-transaction failure rolls back lifecycle, revision, and the in-transaction journal start together; a separate transaction may then record the failed attempt with `transaction_rolled_back: true`. No automatic retry or second repair follows.
- **P11-D boundary:** `NOT_SAFELY_REVERSIBLE`. Re-archiving the terminal while merged sources still depend on it would deliberately recreate `P11-IDENTITY-003`. The recorded before state is useful audit data, not current authorization to revert.
- **Existing-operation reuse decision:** reuse the connection-scoped field transition, validation, graph-revision trigger, and post-commit index refresh semantics of `identity.restore`. Do not call the public `restore_person()` from inside another transaction, and do not reuse its legacy `person_operations` compatibility write. The repair needs stronger finding/path preconditions and its own operation type.

### `P11C-R02-RECONCILE-NOTE-REFERENCE-STATE`

- **Required operator input:** explicit invocation, a fresh operation ID, authenticated actor, selected note/finding IDs, diagnosis fingerprint, and a bounded reason. The operator does not choose mention or evidence truth.
- **Authoritative sources consulted:** the note row; complete ordered immutable revisions; the latest `note_revision_mentions` snapshot; all current/retired `note_mentions` for the note; all `NOTE_REFERENCE` evidence sourced by those occurrences; referenced `persons` and canonical state; relevant journal operation IDs; graph revision; the complete fresh P11-A report.
- **Exact preconditions:** schema is exactly v28; report is not truncated; `P11-NOTE-001`, schema, identity/correction, `P11-EVIDENCE-002`, merge, and journal invariants are clean; `P11-EVIDENCE-001` is clean except for the exact stale-active `NOTE_REFERENCE`/inactive-source rows selected for this note; every allowed `P11-NOTE-002/003` finding belongs to the selected note; any `P11-GRAPH-001` finding is a consequence of this same note-reference state; note status/retirement shape is legal; revision numbering is contiguous and the latest revision ID/number and mention snapshot match diagnosis; every inactive occurrence has complete existing retirement provenance; every evidence row has coherent immutable type/source/endpoints/direction/lifecycle and legal journal linkage apart from the selected active/source-state conflict; fully retired evidence is accepted as history and is not required to mirror current occurrence state; exact note, revision, occurrence, evidence, canonical-state, and graph-revision fingerprints still match under `BEGIN IMMEDIATE`.
- **Allowed finding shapes:** (1) an existing occurrence group has an active occurrence absent from the latest active non-self snapshot; (2) an existing occurrence group is required by the latest snapshot but has zero active occurrences; (3) a valid desired active occurrence has zero matching active evidence; (4) a valid desired active occurrence has more than one matching active evidence; (5) an active self occurrence or an active occurrence on a retired note has no conflicting active evidence; (6) an otherwise coherent active `NOTE_REFERENCE` is sourced by a valid inactive occurrence or retired note and is reported by the exact stale-active-source shape of `P11-EVIDENCE-001`. A wholly missing occurrence group with no finding, malformed retirement provenance, multiple active occurrences created through structural corruption, or any other `P11-EVIDENCE-001/002` finding is not allowed.
- **Exact mutation:** compute the desired current raw person-ID set from the immutable latest revision when the note is active, excluding the raw owner. Retire undesired active occurrences using the current repair operation/revision/time and retire only their active `NOTE_REFERENCE` evidence. Where a desired occurrence has only retired history, append one new active occurrence tied to the existing latest revision and the repair operation; never reactivate an old row. For each desired active occurrence with zero or multiple matching active evidence rows, retire every active duplicate and append exactly one new directed `REFERENCES`/`NOTE_REFERENCE` evidence revision owned by this repair operation. Recompute authority with the shared projection function, replace only the affected directed relationship aggregate, and validate the complete projection. Do not add an occurrence that P11-A did not diagnose as missing.
- **History preserved:** note content and every revision/mention snapshot remain immutable; retired occurrences/evidence remain present; existing occurrence/evidence identity and creation provenance are never changed; old journal records are not amended. New current state is represented only by repair-owned appended rows and one-way retirements.
- **Journal operation type:** `integrity.repair.note-reference.reconcile`.
- **Bounded journal result:** repair ID/spec version, invariant IDs, note ID, latest revision ID/number, diagnosis fingerprint version/value, counts of occurrences/evidence appended and retired, bounded affected ID lists or hashes, graph revision before/after, connection counts before/after, `changed: true`, and immediate postcondition status. Never store note content, full revision history, full finding evidence, or graph edges.
- **Graph/projection consequences:** active note evidence changes are maintained in the same transaction using shared expected-projection semantics. Replace the derived projection and advance the opaque revision exactly once whenever the active evidence set changes, including canonically collapsed evidence that is visible in provenance but suppressed as a self-edge. A self-occurrence-only retirement with no evidence need not advance graph revision. No self-edge may be inserted.
- **Postconditions:** the selected note's existing occurrence layer exactly matches the diagnosed latest active non-self snapshot for the handled persons; each desired active occurrence has exactly one coherent active matching evidence row; inactive/undesired occurrences have none; projection and foreign keys pass; the repair operation is `COMMITTED` with valid status history.
- **P11-A checks expected to clear:** all selected note findings under `P11-NOTE-002` and `P11-NOTE-003`, the exact selected stale-active-source `P11-EVIDENCE-001` findings, plus only the `P11-GRAPH-001` drift caused by those repaired evidence rows.
- **Checks that must remain unchanged:** `P11-NOTE-001`, all non-selected `P11-EVIDENCE-001` results, `P11-EVIDENCE-002`, and every unrelated invariant; all note revisions and revision mentions; persons/canonical state; observations, participants, corrections, non-note evidence, merge history, and pre-existing journal history. Unrelated note/mention/evidence rows must be byte-for-byte unchanged.
- **Retry/idempotency:** the exact same operation ID plus identical request fingerprint returns the prior committed result. A reused ID with different input is rejected. A new invocation after any note revision, retirement, mention/evidence transition, merge/correction affecting endpoints, or graph revision change refuses as stale. Clean state under a new operation ID is not silently journaled as a repair no-op. A `FAILED` attempt requires a new operation ID.
- **Failure behavior:** any stale/unsafe shape refuses without authoritative mutation. Insert, retirement, projection, revision, immediate validation, or journal failures roll back together; a bounded failure attempt may be appended only after rollback. No failed post-check launches another repair.
- **P11-D boundary:** `NOT_SAFELY_REVERSIBLE`. Occurrence/evidence retirement is one-way and reverting a deterministic reconciliation would recreate a known invariant violation. P11-D must not reinterpret this repair as permission to edit immutable note history.
- **Existing-operation reuse decision:** extract/reuse the connection-scoped occurrence/evidence append/retire and shared graph validation primitives used by `update_note()` and `retire_note()`. Do not invoke either public normal command: appending a fake note revision would rewrite semantic history, while `retire_note()` changes the note lifecycle rather than reconciling its current occurrence layer.

## Finding-bound precondition model

P11-C needs no distributed lock or generic optimistic-locking framework. One diagnosis token plus exact local row fingerprints is sufficient.

Each invocation carries a typed `RepairPrecondition` equivalent containing:

- repair ID and repair-spec version;
- schema version (`28` for this catalog);
- diagnosis fingerprint version and SHA-256 value;
- invariant IDs and sorted affected entity IDs from the selected findings;
- graph revision when the repair can affect graph/World-visible state;
- exact domain state: lifecycle/canonical/deletion values and merge-path operation IDs for R01, or note status/latest revision/mention snapshot plus occurrence/evidence states and relevant operation IDs for R02;
- a bounded reason plus authenticated actor and fresh operation ID outside the fingerprinted database state.

The diagnosis fingerprint is SHA-256 over canonical JSON containing the checker contract tag (initially `p11-a-schema28-repair-fingerprint-v1`), repair ID/spec version, sorted selected findings (`invariant_id`, message code/text, entity IDs, factual evidence), schema version, graph revision when applicable, and the repair-specific state summary. It is a stale-state guard, not new authority and is not stored in a new table.

After `BEGIN IMMEDIATE`, the command re-reads and compares every repair-specific row/state field, not merely the hash. The hash makes the request bounded and auditable; explicit comparisons provide the actual safety proof. Any later merge, correction, note revision, evidence retirement/creation, lifecycle transition, or relevant journal change causes refusal. The command never restores diagnosed stale state over newer authority.

## Explicit invocation and common execution boundary

No repair may run at startup, after checker execution, periodically, in a worker, through polling, or merely because a finding exists. There is no “repair all” command.

The implemented flow is fixed:

```text
explicit P11-A report
    -> operator selects one catalogued repair/finding group
    -> service validates request and preflight report
    -> BEGIN IMMEDIATE
       -> revalidate exact preconditions
       -> create STARTED journal row
       -> perform one typed repair mutation
       -> maintain deterministic projection/revision
       -> validate targeted postconditions, projection, FKs, and journal linkage
       -> transition journal to COMMITTED
       -> COMMIT
    -> run a fresh full P11-A post-check
    -> return result or prominently report post-check failure
```

The implemented service/store boundary is one explicit structured-repair service delegating only to typed SQLite R01 and R02 commands. It does not accept table names, SQL fragments, arbitrary field/value patches, open-ended invariant IDs, cross-note batches, or repair-all input.

The current journal represents both safe catalog operations. The implementation uses the private connection-scoped `_begin_journal_operation()` and `_transition_journal_operation()` pattern; public `begin_operation()`/normal domain methods are not composed because they open and commit their own connections. This keeps each typed repair inside one caller-owned transaction rather than adding a second transaction around public calls.

For both entries, the immutable initial journal details contain the repair ID/spec version, selected invariant IDs, bounded operator reason, diagnosis fingerprint version/value, and repair-specific before-state fingerprint. `affected_entities` contains only the terminal/source person IDs for R01 or the note, occurrence, evidence, and endpoint person IDs for R02, subject to a fixed count cap plus a hash/count summary when the set is larger. The `COMMITTED` transition result contains the bounded after-state summary and immediate validation result defined in the catalog entry. It never replaces the initial details or changes any older operation. The same request fingerprint is used to distinguish an exact idempotent retry from operation-ID misuse.

If a transaction fails after `STARTED`, the in-transaction start rolls back with authority. As in P11-B/correction/merge patterns, a separate transaction may create the same operation identity as a durable `STARTED -> FAILED` attempt, provided no authoritative repair rows survived. Refused preconditions may also be recorded as `FAILED`. The failure payload is bounded and includes repair ID, diagnosis fingerprint, refusal/error code, error type, and `transaction_rolled_back`; it excludes raw rows and unbounded findings.

The post-commit P11-A report must be untruncated. Success requires the targeted findings to be absent, no new `CRITICAL`/`ERROR`, deterministic projection validity, and valid journal state. Because the read-only checker uses a separate connection, an unexpected post-commit failure cannot roll back an already committed repair or change its journal status to `FAILED`. It is surfaced as a post-check error; no automatic repair or journal rewrite follows.

## Conflict, retry, and supersession rules

- the same committed operation ID and identical request fingerprint returns its immutable committed result;
- the same operation ID with a different repair, entity set, or fingerprint is rejected;
- a `FAILED`/`ROLLED_BACK` operation ID is never reused for success;
- a new operation ID against already-clean or otherwise changed state refuses as stale rather than manufacturing a repair no-op;
- later lifecycle, merge, correction, note revision, mention transition, evidence transition, or relevant journal state always wins over the old diagnosis; P11-C never writes the diagnosed snapshot back;
- multiple findings may be handled together only where one fixed catalog command explicitly defines the group: all paths to one archived terminal for R01, or safe findings for one note for R02. There is no cross-person/cross-note batch repair.

## Explicit refusal and recovery boundaries

P11-C must stop and report when:

- any non-permitted `ERROR`/`CRITICAL` finding is present or the report is truncated;
- identity fields disagree without a unique current meaning;
- a terminal survivor is deleted rather than archived;
- a proposed repair would clear/repoint a canonical mapping or contradict a merge manifest;
- note lifecycle or retirement provenance is incomplete;
- immutable evidence endpoints/type/direction disagree with the occurrence, or `P11-EVIDENCE-001` has any shape other than the exact selected stale-active/inactive-source conflict;
- a wholly missing note occurrence has no current P11-A finding;
- the expected result requires deleting rows, mutating a note revision, rewriting an old journal/result, or fabricating operation/time/actor provenance;
- a normal domain operation's meaning would be redefined to fit recovery.

`UNRECOVERABLE_FROM_LOCAL_STATE` remains reserved for loss or contradiction that local authority cannot resolve, including physical/constraint database damage reported by schema invariants and missing historical truth not recoverable from immutable records. The operator must use verified backup/restore or external evidence; P11-C does not reconstruct it.

## P11C-R01 implementation record

`StructuredRepairService.prepare_restore_archived_canonical_survivor()` explicitly obtains a fresh, untruncated P11-A report and returns an `ArchivedCanonicalSurvivorRepairPrecondition`. The token binds repair/spec and fingerprint versions, `P11-IDENTITY-003`, sorted finding entity IDs, terminal ID, schema v28, graph revision, exact lifecycle/deletion/canonical/timestamp state, every resolving merge source/path, supporting merge operation IDs and manifest fingerprint, and a relevant-operation fingerprint. It refuses clean state, any other `ERROR`/`CRITICAL`, deleted/mapped/non-terminal targets, malformed/cyclic/dangling paths, incomplete merge/journal support, or diagnosis/state disagreement without writing a journal row.

`StructuredRepairService.restore_archived_canonical_survivor()` requires that typed token, a fresh operation ID, authenticated actor, and bounded reason. The store reruns P11-A, enters `BEGIN IMMEDIATE`, compares the complete precondition again, starts `integrity.repair.canonical-survivor.restore`, invokes the shared connection-scoped archived-to-active lifecycle primitive, and immediately validates lifecycle, canonical paths, immutable merge state, byte-identical `graph_connections`, projection equivalence, foreign keys, and an exactly-one graph revision advance before committing the journal result and mutation together.

The only domain mutation is `persons.lifecycle_status: ARCHIVED -> ACTIVE`, `deleted_at -> NULL`, and a new `lifecycle_changed_at`. Canonical mappings, merge manifests/items/conflicts, corrections, observations/participants/media, note history/mentions, relationship evidence, graph connections, legacy person-operation history, and prior journal/history rows are unchanged. The archived transition remains visible in its original lifecycle journal/person-operation record; the repair adds its own immutable journal history. The lifecycle trigger advances the graph revision once as the existing invalidation rule requires, but R01 neither rewrites the projection nor invokes P11-B rebuild.

After commit the service refreshes the derived recognition index and runs full P11-A. It returns `postcheck_status: PASS` only when the selected finding is absent, the report is untruncated, and no `CRITICAL`/`ERROR` remains. An unexpected failure is surfaced without an automatic repair or journal rewrite. An exact committed operation-ID/fingerprint retry returns the committed result; a new ID against clean/stale state refuses; failed IDs cannot be reused and retry requires a fresh diagnosis and operation ID. Transaction failures roll authority and revision back before a bounded separate `STARTED -> FAILED` attempt is recorded. R01 remains `NOT_SAFELY_REVERSIBLE` and exposes no inverse.

## P11C-R02 implementation record

`StructuredRepairService.prepare_note_reference_reconciliation(note_id, referenced_person_id)` runs fresh untruncated P11-A and returns a `NoteReferenceReconciliationPrecondition` for exactly one existing note/person occurrence group. The token fixes one of five plan values: `APPEND_OCCURRENCE_AND_EVIDENCE`, `RETIRE_OCCURRENCE_AND_EVIDENCE`, `APPEND_EVIDENCE`, `REPLACE_DUPLICATE_ACTIVE_EVIDENCE`, or `RETIRE_STALE_EVIDENCE`. It binds the selected findings, schema, note owner/status, complete latest revision mention snapshot, note revision/history hash, occurrence and evidence histories, retirement provenance, canonical paths, exact graph projection/revision, and relevant journal state. Wholly missing groups, multiple active occurrences, two simultaneously applicable plans, malformed history, any `P11-EVIDENCE-002`, and every non-admitted `P11-EVIDENCE-001` refuse.

`reconcile_note_reference_state()` repeats the full classification under `BEGIN IMMEDIATE`, creates `integrity.repair.note-reference.reconcile`, and performs only the frozen append/retire transition. Appended IDs are deterministic for the fresh operation ID and are included in bounded journal entities. Existing inactive rows are never reactivated, deleted, retargeted, or rewritten. Duplicate active evidence is retired in full before one repair-owned replacement is appended. The shared expected-projection builder validates all evidence; only the one affected directed relationship aggregate is maintained, and the complete projection is immediately compared with shared authority.

Every active-evidence-set change advances graph revision once, including canonical self-collapse; occurrence-only retirement with no evidence change leaves revision stable. Immediate validation proves immutable revisions/mention snapshots, pre-existing retired history, unrelated occurrences/evidence—including `CO_OBSERVED` and `MANUAL_ASSOCIATION`—persons, corrections, observations, merges, and prior journals are unchanged; verifies NOTE-002/003 cardinality, evidence lifecycle, graph equality, foreign keys, and transaction-local journal state; then commits `STARTED -> COMMITTED`. Failures roll the entire mutation/projection/revision/start back and record a bounded separate `FAILED` attempt. Exact committed retry returns its result; changed reuse, failed-ID reuse, stale state, and a new ID against clean state refuse. The service then runs mandatory full P11-A and reports unexpected post-check failure without a second repair or journal rewrite.

R02 remains one typed service command. P11-E delegates to it only after its existing preparation succeeds; it added no new R02 plan, startup hook, scheduler, worker, polling, repair-all path, or revert. P11-C remains complete and frozen; P11-D is separate and cannot invert R02.

### P11-A1 safety-stop resolution

The first R02 implementation attempt correctly stopped before mutation because the old checker treated every historical occurrence as expected-active whenever its person reappeared in the latest revision. A normal mention → remove → re-mention sequence therefore produced a false `P11-NOTE-002` against the retired first occurrence, and the frozen append-new-occurrence repair could never pass post-check.

P11-A1 corrected only the checker: existing occurrence rows are now grouped by note/person; valid inactive rows remain historical; and latest revision authority determines required current active cardinality for the group. Wholly missing groups remain undiagnosed. NOTE-003 and all note mutation helpers are unchanged. The original stop remains part of the architecture record; P11-C2A below supersedes the incomplete occurrence-only refreeze with the consolidated chain contract.

### P11-C2A second safety stop and consolidated refreeze

The second R02 implementation attempt also correctly stopped before mutation. The frozen duplicate/missing-evidence reconciliation retires historical/current active revisions and appends one repair-owned current revision for the same occurrence. The former `P11-EVIDENCE-001` and shared `_expected_graph_connections` implementation compared every evidence revision's `active` flag to the occurrence's current state. It therefore called a retired historical revision corrupt as soon as its source occurrence remained or became current, making the frozen replacement operation impossible.

P11-C2A audited the entire immutable revision → occurrence history → evidence revision history → effective endpoint → graph projection chain before changing semantics. The consolidated result is:

- `P11-NOTE-002` owns active occurrence cardinality for each existing raw note/person group and validates occurrence retirement provenance;
- `P11-NOTE-003` owns active `NOTE_REFERENCE` cardinality per occurrence;
- `P11-EVIDENCE-001` owns each row's type/source/endpoint/direction/relationship/lifecycle provenance and requires current source compatibility only for active evidence;
- `P11-EVIDENCE-002` owns active effective resolution and remains unchanged;
- shared graph authority validates those current cardinalities, retains retired rows as history, and aggregates only active evidence;
- `P11-GRAPH-001` owns exact derived-table equality;
- deactivation proof is the schema-v28 operation ID plus timestamp, foreign-key linkage, and committed/reverted journal status. No replacement-link column exists, so none is guessed.

The old equality was not merely removed. Shared graph authority now checks exactly one matching active evidence row for each current active non-self occurrence and zero for inactive/self/retired-note occurrences. This preserves normal transactional safety: the generic evidence-deactivation command still rolls back if it would leave a current occurrence unsupported. `CO_OBSERVED` and `MANUAL_ASSOCIATION` validation/projection semantics are unchanged.

#### Frozen R02 reachability matrix

| Case | Before: exact allowed P11-A findings | Frozen R02 action | After authority/history | Graph and revision | Expected targeted findings after |
| --- | --- | --- | --- | --- | --- |
| 1. Latest snapshot requires A; existing group has only retired rows | `P11-NOTE-002` | append a new occurrence at the existing latest revision; append one active evidence revision | old occurrences/evidence stay retired; one new current pair | current edge appears; advance once | none |
| 2. Latest snapshot excludes A; one stale occurrence is active | `P11-NOTE-002`, plus `P11-NOTE-003` only if its current evidence cardinality is also wrong | retire the stale occurrence and only its active note evidence | creation provenance unchanged; retirement is repair-owned | note support disappears; advance once if evidence changed, otherwise unchanged | none |
| 3. Current occurrence exists; active evidence is missing | `P11-NOTE-003` and corresponding `P11-GRAPH-001` drift when the stored edge remains | append one repair-owned evidence revision | prior retired evidence stays retired | edge/current support restored; advance once | none |
| 4. Current occurrence has duplicate active evidence revisions | `P11-NOTE-003` and aggregate `P11-GRAPH-001` drift | retire every active duplicate; append exactly one repair-owned evidence revision | all duplicates remain as retired history | exact count/latest time rebuilt; advance once | none |
| 5. Occurrence/note is inactive but evidence is stale active | `P11-EVIDENCE-001`, `P11-NOTE-003`, and graph drift; admitted only when other row provenance is coherent and preconditions classify the fixed shape | retire stale active evidence; append nothing | occurrence and all evidence are retired history | note support removed; advance once | none |
| 6. Several historical evidence replacements already exist | only the case-specific current-cardinality finding; retired rows produce no finding | act only on current active rows and append when required | every older evidence revision remains retired | active-only aggregate; advance once when active evidence changes | none |
| 7. Same pair also has `CO_OBSERVED` or `MANUAL_ASSOCIATION` | note finding(s) only, plus exact aggregate drift if present | reconcile only `NOTE_REFERENCE` | other evidence rows byte-identical | relationship remains if other support exists; advance once for note evidence change | none |
| 8. Effective endpoints canonically self-collapse | note finding(s); no self-edge is expected | same append/retire action on raw non-self provenance | raw evidence remains explainable | projection remains self-edge-free; advance once when evidence changes | none |
| 9. Correction then merge exists | note finding(s) only; correction/evidence/merge invariants clean | reconcile raw note occurrence/evidence against current canonical map | correction/merge/note revision history unchanged | correction applies only to observation evidence before canonical resolution; exact graph rebuilt; advance once if evidence changes | none |
| 10. Merge then correction exists | same as case 9 | same fixed reconciliation after fresh fingerprint/revalidation | all transformations preserved | same deterministic active-only result | none |

The matrix first proved reachability and now exactly matches the implemented plans. Focused R02 tests prove full P11-A cleanliness, repeated replacements, independent evidence support, canonical collapse, both correction/merge orders, rollback and retry behavior, and P11-B rebuild regression. A wholly missing occurrence group still has no `P11-NOTE-002/003` finding and remains outside R02 authorization.

## Test plan

Implementation is not authorized complete until every catalog entry has focused tests plus the relevant full suites.

### Common matrix for both entries

- clean database refuses an unbound repair request;
- exact target finding and clean preconditions succeed;
- selected findings clear and no new `CRITICAL`/`ERROR` appears;
- immutable/raw history and pre-existing journal rows remain unchanged;
- one new operation has valid `STARTED -> COMMITTED` history and bounded payloads;
- graph revision behavior matches the catalog entry exactly;
- stale diagnosis fingerprint, schema, graph revision, entity state, and operation references refuse;
- a later valid merge/correction/revision/evidence/lifecycle mutation supersedes diagnosis and causes refusal;
- injected failure at journal start, domain mutation, projection write, revision advance, immediate validation, journal commit, and SQLite commit rolls authoritative state back;
- failure-attempt journaling contains no authoritative result rows and requires a new retry ID;
- exact committed retry returns the prior result; changed request reuse rejects;
- snapshots prove no unrelated-table or unrelated-entity mutation;
- post-check failure is surfaced and never launches another repair;
- operation cannot be invoked through startup, worker, polling, or a generic repair-all path.

### R01-specific tests

- one and multiple merged paths ending at the archived terminal;
- transitive chain preservation and unchanged manifests/inverse data;
- terminal lifecycle becomes active with canonical mapping unchanged;
- graph content remains byte-for-byte equal and graph revision advances once;
- derived index refresh sees the restored active canonical owner;
- deleted terminal, mapped terminal, missing timestamp, malformed path, stale later merge, and conflicting lifecycle change all refuse;
- attempting the inverse would recreate `P11-IDENTITY-003` and is not exposed.

### R02-specific tests

- active occurrence removed from latest snapshot is retired with its evidence;
- inactive occurrence present in latest snapshot produces a new occurrence/evidence without reactivating history;
- missing evidence is appended; duplicate active evidence is all retired and replaced by one repair-owned revision;
- active self occurrence and retired-note/no-active-evidence safe shape;
- note revisions and revision mentions are byte-for-byte unchanged;
- unrelated evidence types and occurrences remain independent;
- projection aggregation/direction/count/latest-time and canonical self-edge suppression remain correct;
- wrong endpoint/type/direction, incomplete retirement provenance, any non-admitted `P11-EVIDENCE-001` shape, any `P11-EVIDENCE-002`, wholly missing occurrence, later note revision, later evidence retirement, correction, and merge all refuse.

R01 and R02 have focused success, refusal, idempotency, rollback, postcondition, history, correction/merge, evidence-independence, graph-revision, post-check, and mutation-boundary coverage. The complete backend suite plus frontend test/build gates pass before P11-C is marked complete.

## P11-D boundary

P11-D is complete without changing either repair. Both catalog entries remain `NOT_SAFELY_REVERSIBLE`: reverting either would recreate the inconsistency the deterministic repair proved. Recorded repair before-state fingerprints remain audit/precondition material only; P11-D cannot mutate these repairs, reinterpret their journal history, or reactivate retired rows.

The independent journal audit classified only a restricted normalized `identity.merge` as `SAFE_GUARDED_REVERT`: the source was originally active/unmapped; manifest and journal are complete; no conflict, target profile/note revision, or survivor biometric-current-state change occurred; current source/target/graph state exactly matches the merge result; and no later operation touches any manifest-affected entity. Every other merge shape refuses. Archive/restore, profile/note updates, face delete/restore, corrections, and source-proven evidence changes use later forward compensating operations where legal. Finalisation, note retirement, tombstone deletion, R01/R02, and graph rebuild are not safely reversible. Physical purge/lost authority is backup/restore-only.

The `OperationRevertPrecondition` binds the original operation/type/status/history, fingerprint, affected entities, relevant lifecycle and graph revisions, exact source/target state, merge/projection fingerprints, and dependency state. Execution uses `BEGIN IMMEDIATE`, repeats every explicit comparison, starts a new `identity.merge.revert`, restores only source lifecycle/canonical interpretation, rebuilds and validates the projection, appends the original operation's legal `COMMITTED → REVERTED` transition, commits the new operation, refreshes the derived index, and runs P11-A. Failures at journal start, mutation, graph update, validation, or before commit roll authority and both journal transitions back before a separate bounded failed attempt is recorded. Refusal mutates nothing. P11-E exposes this exact preparation/execution path but does not discover eligibility automatically; recent merges remain unassessed until selected. There is no generic inversion, revert-all, startup invocation, worker, polling, schema, or dependency change.

## P11-E exposure boundary

The `/api/integrity/repairs/r01/*`, `/api/integrity/repairs/r02/*`, and `/api/integrity/reverts/*` routes accept only server-signed preparation material. Report tokens bind an exact backend-provided action/target; prepared tokens wrap the complete existing immutable dataclass and are decoded back into that type before delegation. The frontend never supplies a repair ID, person/note target, field patch, SQL fragment, plan value, canonical decision, graph state, or reversibility judgment. Unknown JSON fields reject.

The UI plan contains only bounded affected identifiers, exact existing plan meaning, graph revision, expected changes, and explicit history guarantees. It requires a reason and confirmation phrase, holds one operation UUID across uncertain retry, discards a stale token, and replaces its report only with a returned P11-A DTO. A committed operation whose separate post-check fails is reported as committed, never rewritten or labelled rolled back. The repair catalog, transaction/journal rules, immutable-history guarantees, failure behavior, post-check rules, and P11-D whitelist are unchanged. No automatic recovery, polling, worker, scheduler, or startup repair exists. P12 consumes only P11-A/P11-B during staged restore; authoritative repair findings refuse rather than triggering R01 or R02.
