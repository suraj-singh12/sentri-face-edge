# P11 structured repair authority audit and execution design

Status: **P11-C1 design is frozen; P11C-R01 is implemented; P11C-R02 is not implemented; P11-C is not complete.** P11-A1 corrected and refroze `P11-NOTE-002` after the R02 safety stop. The catalog remains exactly two commands and does not authorize generic repair, operation revert, recovery API/UI, automatic invocation, or P12 work.

## Scope and verified implementation basis

This audit starts only from the executable `INTEGRITY_INVARIANTS` entries whose `future_handling` is `STRUCTURED_REPAIR`. It was checked against schema v28 and the implemented storage, service, trigger, transaction, graph, journal, correction, review-finalisation, merge, and lifecycle paths. Documentation was not treated as implementation proof.

The relevant implementation facts are:

- `persons` stores mutable current lifecycle/canonical/identity/biometric state; merge manifests and journal rows preserve the operations that established historical interpretation.
- canonical resolution is transitive. Normalized merge execution is the only operation that creates a canonical mapping and an immutable merge manifest.
- note revisions and their mention snapshots are immutable. `note_mentions` is the authoritative current occurrence layer and can only transition from active to inactive; reappearance requires a new occurrence.
- `NOTE_REFERENCE` evidence has immutable identity/provenance and can only transition from active to inactive; replacement support must be appended as a new evidence revision.
- graph-affecting authoritative writes, the complete `graph_connections` replacement, revision advancement, and successful journal transition already share a storage transaction in normal note/correction/review/merge paths.
- the journal supports immutable identity/details and append-only `STARTED -> COMMITTED` or `STARTED -> FAILED` history. A failed attempt can be recorded after the failed authoritative transaction rolls back.
- `ReadOnlyIntegrityChecker` is a separate query-only snapshot. It cannot validate uncommitted state on the repair connection, so exact immediate SQL/domain postconditions must run before commit and the full P11-A post-check must run after commit.

## Exact `STRUCTURED_REPAIR` candidate list

No other invariant is admitted to P11-C by this design.

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
| `P11-NOTE-003`: a valid active current occurrence has zero or multiple otherwise coherent active matching evidence rows | `DETERMINISTIC_STRUCTURED_REPAIR` | The occurrence proves exactly one current directed reference. Missing support is appended; duplicate support is retired and replaced with one repair-owned revision. Catalogued as `P11C-R02`. |
| `P11-NOTE-003`: evidence has wrong endpoints/type/direction, a missing source, illegal canonical resolution, or an active-state conflict also reported by `P11-EVIDENCE-001/002` | `MANUAL_REVIEW_ONLY` | Those evidence invariants are registered `MANUAL_REVIEW`. P11-C may not choose which conflicting authoritative row is true or rewrite immutable evidence identity. |
| Latest revision contains a referenced person but no `note_mentions` row exists at all | Outside the current executable finding contract | `P11-NOTE-002` currently iterates existing occurrence rows and does not diagnose a wholly missing occurrence. P11-C1 records this checker coverage gap but does not expand the catalog or synthesize an unreported repair. |

There are **no `OPERATOR_DIRECTED_REPAIR` catalog entries** in P11-C1. In particular, “choose a new canonical target” is normalized merge meaning, not a repair primitive. Allowing it here would create a second merge implementation and contradict old manifests. Choosing identity status or reconstructing note retirement history would introduce domain meaning that the current architecture does not define.

## Fixed repair catalog

Only these repair IDs may be implemented by P11-C. The repair-spec version is `1`; changing their semantic preconditions or mutations requires a new catalog version, not an in-place broadening.

| Repair ID | Invariants | Domain | Class |
| --- | --- | --- | --- |
| `P11C-R01-RESTORE-ARCHIVED-CANONICAL-SURVIVOR` | `P11-IDENTITY-003` | Identity lifecycle / merge interpretation | `DETERMINISTIC_STRUCTURED_REPAIR` |
| `P11C-R02-RECONCILE-NOTE-REFERENCE-STATE` | `P11-NOTE-002`, `P11-NOTE-003` | Notes, mentions, relationship evidence | `DETERMINISTIC_STRUCTURED_REPAIR` |

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
- **Exact preconditions:** schema is exactly v28; report is not truncated; `P11-NOTE-001`, schema, identity/correction, evidence, merge, and journal invariants are clean; every allowed `P11-NOTE-002/003` finding belongs to the selected note; any `P11-GRAPH-001` finding is a consequence of this same note-reference state; note status/retirement shape is legal; revision numbering is contiguous and the latest revision ID/number and mention snapshot match diagnosis; every inactive occurrence has complete existing retirement provenance; every evidence row has coherent immutable type/source/endpoints/direction and legal journal linkage; exact note, revision, occurrence, evidence, canonical-state, and graph-revision fingerprints still match under `BEGIN IMMEDIATE`.
- **Allowed finding shapes:** (1) an existing occurrence group has an active occurrence absent from the latest active non-self snapshot; (2) an existing occurrence group is required by the latest snapshot but has zero active occurrences; (3) a valid desired active occurrence has zero matching active evidence; (4) a valid desired active occurrence has more than one matching active evidence; (5) an active self occurrence or an active occurrence on a retired note has no conflicting active evidence. A wholly missing occurrence group with no finding, malformed retirement provenance, multiple active occurrences created through structural corruption, or any `P11-EVIDENCE-001/002` finding is not allowed.
- **Exact mutation:** compute the desired current raw person-ID set from the immutable latest revision when the note is active, excluding the raw owner. Retire undesired active occurrences using the current repair operation/revision/time and retire only their active `NOTE_REFERENCE` evidence. Where a desired occurrence has only retired history, append one new active occurrence tied to the existing latest revision and the repair operation; never reactivate an old row. For each desired active occurrence with zero or multiple matching active evidence rows, retire every active duplicate and append exactly one new directed `REFERENCES`/`NOTE_REFERENCE` evidence revision owned by this repair operation. Rebuild/validate `graph_connections` with the shared projection functions. Do not add an occurrence that P11-A did not diagnose as missing.
- **History preserved:** note content and every revision/mention snapshot remain immutable; retired occurrences/evidence remain present; existing occurrence/evidence identity and creation provenance are never changed; old journal records are not amended. New current state is represented only by repair-owned appended rows and one-way retirements.
- **Journal operation type:** `integrity.repair.note-reference.reconcile`.
- **Bounded journal result:** repair ID/spec version, invariant IDs, note ID, latest revision ID/number, diagnosis fingerprint version/value, counts of occurrences/evidence appended and retired, bounded affected ID lists or hashes, graph revision before/after, connection counts before/after, `changed: true`, and immediate postcondition status. Never store note content, full revision history, full finding evidence, or graph edges.
- **Graph/projection consequences:** active note evidence changes are maintained in the same transaction using shared expected-projection semantics. Replace the derived projection and advance the opaque revision exactly once whenever the active evidence set changes, including canonically collapsed evidence that is visible in provenance but suppressed as a self-edge. A self-occurrence-only retirement with no evidence need not advance graph revision. No self-edge may be inserted.
- **Postconditions:** the selected note's existing occurrence layer exactly matches the diagnosed latest active non-self snapshot for the handled persons; each desired active occurrence has exactly one coherent active matching evidence row; inactive/undesired occurrences have none; projection and foreign keys pass; the repair operation is `COMMITTED` with valid status history.
- **P11-A checks expected to clear:** all selected note findings under `P11-NOTE-002` and `P11-NOTE-003`, plus only the `P11-GRAPH-001` drift caused by those repaired evidence rows.
- **Checks that must remain unchanged:** `P11-NOTE-001`, `P11-EVIDENCE-001/002`, and every unrelated invariant; all note revisions and revision mentions; persons/canonical state; observations, participants, corrections, non-note evidence, merge history, and pre-existing journal history. Unrelated note/mention/evidence rows must be byte-for-byte unchanged.
- **Retry/idempotency:** the exact same operation ID plus identical request fingerprint returns the prior committed result. A reused ID with different input is rejected. A new invocation after any note revision, retirement, mention/evidence transition, merge/correction affecting endpoints, or graph revision change refuses as stale. Clean state under a new operation ID is not silently journaled as a repair no-op. A `FAILED` attempt requires a new operation ID.
- **Failure behavior:** any stale/unsafe shape refuses without authoritative mutation. Insert, retirement, projection, revision, immediate validation, or journal failures roll back together; a bounded failure attempt may be appended only after rollback. No failed post-check launches another repair.
- **P11-D boundary:** `NOT_SAFELY_REVERSIBLE`. Occurrence/evidence retirement is one-way and reverting a deterministic reconciliation would recreate a known invariant violation. P11-D must not reinterpret this repair as permission to edit immutable note history.
- **Existing-operation reuse decision:** extract/reuse the connection-scoped occurrence/evidence append/retire and shared graph validation primitives used by `update_note()` and `retire_note()`. Do not invoke either public normal command: appending a fake note revision would rewrite semantic history, while `retire_note()` changes the note lifecycle rather than reconciling its current occurrence layer.

## Finding-bound precondition model

P11-C needs no distributed lock or generic optimistic-locking framework. One diagnosis token plus exact local row fingerprints is sufficient.

The future invocation must carry a `RepairPrecondition` equivalent containing:

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

The future flow is fixed:

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

The implemented service/store boundary is one explicit structured-repair service delegating to a typed SQLite R01 command. It does not accept table names, SQL fragments, arbitrary field/value patches, an open-ended invariant ID, or R02 input. R02 may extend this same bounded service later without creating a generic engine.

The current journal can represent both safe catalog operations. The private connection-scoped `_begin_journal_operation()` and `_transition_journal_operation()` pattern is suitable; public `begin_operation()`/normal domain methods cannot be composed because they open and commit their own connections. Future implementation therefore needs connection-scoped typed helpers, not a second transaction around public calls.

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
- immutable evidence endpoints/type/direction disagree with the occurrence;
- a wholly missing note occurrence has no current P11-A finding;
- the expected result requires deleting rows, mutating a note revision, rewriting an old journal/result, or fabricating operation/time/actor provenance;
- a normal domain operation's meaning would be redefined to fit recovery.

`UNRECOVERABLE_FROM_LOCAL_STATE` remains reserved for loss or contradiction that local authority cannot resolve, including physical/constraint database damage reported by schema invariants and missing historical truth not recoverable from immutable records. The operator must use verified backup/restore or external evidence; P11-C does not reconstruct it.

## P11C-R01 implementation record

`StructuredRepairService.prepare_restore_archived_canonical_survivor()` explicitly obtains a fresh, untruncated P11-A report and returns an `ArchivedCanonicalSurvivorRepairPrecondition`. The token binds repair/spec and fingerprint versions, `P11-IDENTITY-003`, sorted finding entity IDs, terminal ID, schema v28, graph revision, exact lifecycle/deletion/canonical/timestamp state, every resolving merge source/path, supporting merge operation IDs and manifest fingerprint, and a relevant-operation fingerprint. It refuses clean state, any other `ERROR`/`CRITICAL`, deleted/mapped/non-terminal targets, malformed/cyclic/dangling paths, incomplete merge/journal support, or diagnosis/state disagreement without writing a journal row.

`StructuredRepairService.restore_archived_canonical_survivor()` requires that typed token, a fresh operation ID, authenticated actor, and bounded reason. The store reruns P11-A, enters `BEGIN IMMEDIATE`, compares the complete precondition again, starts `integrity.repair.canonical-survivor.restore`, invokes the shared connection-scoped archived-to-active lifecycle primitive, and immediately validates lifecycle, canonical paths, immutable merge state, byte-identical `graph_connections`, projection equivalence, foreign keys, and an exactly-one graph revision advance before committing the journal result and mutation together.

The only domain mutation is `persons.lifecycle_status: ARCHIVED -> ACTIVE`, `deleted_at -> NULL`, and a new `lifecycle_changed_at`. Canonical mappings, merge manifests/items/conflicts, corrections, observations/participants/media, note history/mentions, relationship evidence, graph connections, legacy person-operation history, and prior journal/history rows are unchanged. The archived transition remains visible in its original lifecycle journal/person-operation record; the repair adds its own immutable journal history. The lifecycle trigger advances the graph revision once as the existing invalidation rule requires, but R01 neither rewrites the projection nor invokes P11-B rebuild.

After commit the service refreshes the derived recognition index and runs full P11-A. It returns `postcheck_status: PASS` only when the selected finding is absent, the report is untruncated, and no `CRITICAL`/`ERROR` remains. An unexpected failure is surfaced without an automatic repair or journal rewrite. An exact committed operation-ID/fingerprint retry returns the committed result; a new ID against clean/stale state refuses; failed IDs cannot be reused and retry requires a fresh diagnosis and operation ID. Transaction failures roll authority and revision back before a bounded separate `STARTED -> FAILED` attempt is recorded. R01 remains `NOT_SAFELY_REVERSIBLE` and exposes no inverse.

R02 remains design-only. No recovery API/UI, startup hook, scheduler, worker, polling, repair-all path, or revert has been added.

### P11-A1 safety-stop resolution

The first R02 implementation attempt correctly stopped before mutation because the old checker treated every historical occurrence as expected-active whenever its person reappeared in the latest revision. A normal mention → remove → re-mention sequence therefore produced a false `P11-NOTE-002` against the retired first occurrence, and the frozen append-new-occurrence repair could never pass post-check.

P11-A1 corrected only the checker: existing occurrence rows are now grouped by note/person; valid inactive rows remain historical; and latest revision authority determines required current active cardinality for the group. Wholly missing groups remain undiagnosed. NOTE-003 and all note mutation helpers are unchanged. The original stop remains part of the architecture record; R02 may restart only against this refrozen contract.

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
- wrong endpoint/type/direction, incomplete retirement provenance, `P11-EVIDENCE-001/002`, wholly missing occurrence, later note revision, later evidence retirement, correction, and merge all refuse.

R01 has focused success, refusal, idempotency, rollback, postcondition, history, transitive-path, correction/evidence, graph-revision, and mutation-boundary coverage. R02 tests remain future. Run focused repair tests first, then `python -m pytest -q`, `npm --prefix frontend test`, and `npm --prefix frontend run build`.

## P11-D boundary

No revert behavior is designed or implemented here. Both catalog entries are `NOT_SAFELY_REVERSIBLE`: reverting either would recreate the inconsistency the deterministic repair proved. Recorded before-state fingerprints are audit/precondition material only. P11-D may independently analyze earlier lifecycle/merge operations, but it may not mutate these repair operations, reinterpret their journal history, reactivate retired rows, or use this document as authorization for a generic inverse engine.
