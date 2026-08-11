# Global identity graph implementation plan

Implement in order. Each phase must preserve offline operation, use additive migrations where possible, keep important writes transactional and journaled, and add upgrade/failure tests before moving on.

Status after P11-A1: P0 through P10 are complete and frozen. P11-A establishes the integrity authority/invariant model and explicit read-only checker; P11-A1 corrected and refroze only `P11-NOTE-002` after the R02 safety stop exposed a historical/current occurrence false positive. P11-B provides deterministic graph rebuild. P11-C1 fixes a two-entry repair catalog, and P11C-R01 is implemented. R02 and P11-D/E remain future work; P11 is not complete.

## P0 Database migration/version foundation — Complete

Refactor the inline version chain in `src/sentriface/storage/sqlite_store.py` into an explicit, testable migration registry without changing runtime domain behavior. Define supported-version policy, schema introspection, transaction boundaries, backup-before-migration, failure recovery, and fixtures for representative old schemas. Exit: fresh install and every supported upgrade reach the same schema; failed/repeated migrations are safe and verified.

## P1 Operation Journal — Complete

Extend the legacy `person_operations` model with a general immutable operation journal while retaining idempotency compatibility. Record actor, operation type, affected entities, before/after or inverse payload, status, and timestamps in the same transaction as each important normalized write. Exit: the journal foundation and status model are available, phase-owned important writes are journaled and retry-safe, and remaining legacy gaps are enumerated rather than speculatively backfilled.

## P2 Identity lifecycle + canonical identity — Complete

Introduce explicit `ACTIVE`, `ARCHIVED`, `DELETED`, and `MERGED` lifecycle states and normalized canonical-resolution/merge-history primitives. Remove physical person erasure from normal lifecycle semantics; provide compatibility mapping from `deleted_at` and `metadata.merged_into`. Exit: archived/deleted/merged source identities resolve correctly while remaining historically queryable.

## P3 Observation/Event model — Complete

Add events/observations, event photos, detected-face review decisions, and accepted participants. Migrate or bridge `recognition_details`; enforce one participant per canonical person per event and allow multiple photos. Exit: event completion is explicit, participant deduplication/self-link rules hold, and existing sightings remain accessible.

## P4 Global graph + relationship evidence engine — Complete

Add normalized evidence records and a rebuildable relationship projection. Keep `CO_OBSERVED`, `NOTE_REFERENCE`, and `MANUAL_ASSOCIATION` evidence distinct, explainable, independently removable, and canonicalized while retaining their observation, note-mention, or manual-assertion provenance. Provide storage/service APIs; do not add final Person Graph/World UI yet. Exit: rebuild is deterministic and produces the same projection as incremental transactional updates.

## P5 Notes/revisions/@Person mentions — Complete

Normalize person and legacy recognition-detail notes, revisions, and exact mention occurrences. Resolve explicit person-ID mentions only on save; diff revisions so removed mentions retire only their evidence. Migrate existing profile/sighting notes and `automatic_mention` associations without inventing provenance that cannot be established. Exit: save/edit/remove/duplicate-name/canonical-resolution cases preserve independent evidence correctly.

## P6 Check Photo/Queue atomic finalisation — Complete

Create one backend finalisation command per photo/event review. Require a final decision for every detected face plus explicit completion; atomically persist identities/participants/details/evidence/journal or nothing. Replace frontend request loops in `useRecognizeController.js` and `useQueueController.js` with the command. Exit: injected failures cannot leave partial identity, event, mention, or graph state.

## Hardening/consolidation pass — Complete

After P6, consolidate production mutation paths behind the storage/service boundary, gate legacy domain writes, strengthen startup domain validation and canonical-aware recognition/index behavior, and retain the existing relationship UI as a compatibility read model. This pass does not add a new domain phase.

## P7 Recognition corrections/Move Face/Add Face — Complete

Model corrections as authoritative, journaled history rather than silent ownership rewrites. Support corrected participant identity, Move Face, and Add Face while retaining original proposal/decision provenance and rebuilding affected projections. Exit: correction paths are atomic and historically explainable; general operation revert remains P11 work.

## P8-A Identity Merge infrastructure foundation — Complete

Add the caller-owned, connection-scoped canonical update primitive; immutable normalized merge manifests, affected-item records, and typed conflict strategies; terminal-survivor validation; and canonical-aware current read models. Do not expose or execute the normalized Merge workflow in this subphase. Exit: the storage/domain primitives can participate in a future single merge transaction without treating legacy merge snapshots as normalized truth.

## P8-B Identity Merge orchestration — Complete

Orchestrate Merge on the P8-A foundation. Preserve source records and evidence, resolve reads to the canonical survivor, apply explicit conflict strategies, canonicalize projected pairs, prevent self-links, and define safe revert preconditions. The authoritative change, merge manifest, affected items, graph projection update, and operation journal must share one transaction. Exit: the normalized Merge workflow is exposed through the backend boundary; merge chains, archived/deleted identities, notes, events, corrections, and evidence survive intact; and the manifest retains the inverse data needed for guarded P11 revert work.

## P8-C Architecture hardening — Complete

Remove compatibility stores from current-truth decisions without deleting their historical data. Embedding enrollment ownership remains raw provenance while correction history and terminal canonical resolution determine effective ownership. Merge note conflicts append normalized note revisions before refreshing the `persons.notes` mirror. Profile activity reads the global operation journal, current relationship reads use the evidence-derived graph projection, and review/identity request boundaries require an operation ID plus authenticated actor. Exit: `person_associations`, `persons.notes`, `person_operations`, and `recognition_details` are restricted to compatibility, migration, or historical display; none determines current graph, activity, notes, identity, or P9 analytics.

## P9 Intelligence, Sightings, Analytics, and Derived Read Models — Complete

Added a read-only intelligence service and normalized backend models for effective sightings, presence, monthly/location trends, evidence-derived relationship analytics, and profile intelligence. Sightings now come only from finalized observations and corrected/canonical effective participants, collapse duplicate faces within an observation, retain raw provenance, and aggregate merge history under the survivor. People summaries and sort/group fields use backend-provided observation counts, first/last seen, frequency values, and labels; the profile renders normalized sighting rows. Relationship strength and history come only from active `relationship_evidence`, and activity comes only from `operation_journal`. `recognition_details`, `person_associations`, `persons.notes`, and `person_operations` remain compatibility data rather than analytics truth. No-face identities are supported without biometric enrollment. No authoritative table, graph mutation, dependency, or schema migration was added. Exit: photo/embedding deletion cannot erase event participation, corrections move the effective current sighting while preserving raw history, merges union canonical history, and focused plus full regression suites verify the behavior.

## P9.5 Frontend normalization — Complete

Converted React into a rendering and interaction layer over explicit backend read contracts. People collection statistics, intelligence ordering, lifecycle/canonical identity, allowed actions, normalized notes and mention occurrences, relationship rows, and journal activity now arrive from backend services. The existing relationship modal consumes a versioned backend subgraph with canonical endpoints, depth, counts, evidence, lifecycle, and revision metadata; the client computes coordinates only. Identity mutations invalidate and refetch authoritative collections/profiles instead of synthesizing final state. Legacy recognition detail remains available only inside historical face/photo presentation. No P10 Person Graph or World projection was implemented.

## P10-A Graph and World intelligence backend contracts — Complete

Added typed Person Graph and World Graph read models behind `GraphReadService`, versioned loopback APIs, backend-owned temporal/location/lifecycle/profile/frequency/strength filtering, canonical node collapse, evidence-derived provenance summaries, and an opaque durable graph revision token. Schema v27 adds only the singleton revision state and two required read indexes; responses remain uncached and expose no raw evidence or compatibility tables. Exit: frontend consumers can render consistent Person and World projections and detect stale data without reconstructing graph truth.

## P10-B Person Graph UI — Complete

Added a dedicated Person Graph workspace inside People. It consumes only the versioned P10-A Person Graph and revision contracts, renders backend-provided nodes/edges/lifecycle/actions/evidence, and owns only deterministic node coordinates plus pan, zoom, hover, and selection state. Graph revision is an opaque consistency token. In the current offline single-user model, the UI validates it at lifecycle boundaries and after known graph mutations. Continuous polling is intentionally avoided. Opening stores the revision; returning validates once and reuses unchanged state; successful graph mutations invalidate the snapshot; changed, invalidated, and manually refreshed graphs are replaced in full. Node navigation follows backend `allowed_actions`. Empty and large graphs are covered without adding client topology reconstruction. No World UI or backend change was introduced.

## P10-C World Graph architecture and product design review — Complete

Defined World as a scope-first, progressive spatial/temporal projection of the one global identity graph rather than a zoomed-out Person Graph. Canonical people and evidence-derived relationships are primary; backend-computed clusters are ephemeral read-model summaries; finalized events are explicit evidence drill-down; and locations remain filters/facets until a normalized place identity exists. Defined the initial progressive-level concept, unknown-person boundaries, backend filter ownership, contract gaps, scaling limits, and the Person Graph decisions that may or may not be reused. No UI, rendering, backend behavior, schema, dependency, or generated asset changed. Exit: the product model and backend/frontend responsibility boundary are documented before implementation.

## P10-D World Intelligence read-model architecture review — Complete

Defined World as a backend-owned intelligence system over canonical people, finalized events, normalized evidence, and journaled history. Classified clusters, patterns, salience, ranking, explanations, and aggregate edges as deterministic revision-bound read objects; excluded unsupported topology and speculative inference; separated five semantic detail levels from frontend zoom; defined normative filter ordering and structured explanation contracts; selected a single bounded `/api/world-graph` version 2 route; and set scaling/cursor/cache boundaries. No UI, backend behavior, schema, dependency, or generated asset changed. Exit: the entity, intelligence, explanation, filter, read-contract, scale, and frontend/backend ownership decisions are explicit enough to implement and test without inventing semantics.

## P10-E Bounded World read and expansion contract — Complete and frozen

Implemented `/api/world-graph?version=2` as a typed, bounded, revision-consistent backend projection while preserving version 1. Added the five semantic detail levels, typed focus, effective filters/facets, deterministic ranking factors, revision-bound cursors and cluster identities, canonical people/historical IDs, finalized event detail, bounded evidence provenance, evidence-derived relationships, deterministic explained clusters, measured data-quality patterns, scope/returned totals, and hard response caps. Existing normalized truth is queried directly; no World table, cache, dependency, frontend code, or generated asset was added. Schema v28 only refines shared revision invalidation so World-visible person fields advance it while unrelated metadata does not; finalized single-participant events now advance revision transactionally. Exit: focused tests cover contract validation, normalization, caps/pagination/stale revisions, merge collapse/no self-links, lifecycle/biometric state, evidence provenance/type filters, deterministic cluster explanations, finalized-event gating, missing location, non-speculative patterns, and relevant/irrelevant revision inputs.

Final stabilization completed: every response is held to one revision-bound SQLite snapshot; relationship projection and evidence expansion share correction-before-canonical endpoint semantics; self-edge/cross-edge leakage is suppressed; and evidence counts equal supporting scoped rows. The full documented navigation is backend-owned, including overview relationships, cluster ranking/activity, person cluster membership, independent event participants/provenance/evidence/media, exact evidence media, and reference-only media. All bounded collections and dynamic location facets report truthful page state. Partial neighbour analytics are explicitly `NOT_LOADED`. Evidence and empty-person read paths are constant-query for bounded pages, reducing the recorded diagnostics from 78 to 17 and 1,004 to at most 6 statements respectively. The Python invariant/full suites and frontend test/build checks pass.

The final consolidated artifact, `docs/P10_WORLD_BENCHMARK_RESULTS_POST_OPT.json`, records Dataset A/B sparse/dense cold/warm p50/p95, SQL counts, payloads, returned counts, and cursor walks. Dense-B allocation tracing remains explicitly unavailable because instrumentation distorts runtime; product latency is measured without it. The former dense observation×alias adjustments, focused-person event scans, repeated complete-World facet pages, and recursive cluster scoped counts were replaced with bounded participant-first or collection-specific reads without changing semantics. P10-PERF-01 through P10-PERF-05 pass. No cache, materialized view, background work, dependency, index, schema, or frontend feature was added.

## P10-F World UI — Complete and frozen

P10-F1 adds World as a persistent first-class top-level view and renders only frozen `WORLD_SCOPE` authority: normalized effective scope controls, backend totals/facets, ranked canonical people, revision-bound cluster summaries, measured patterns, typed relationship pages, truthful analytics availability, page/truncation state, and structured factual explanations. P10-F2 adds a backend-requested `CLUSTER` workspace with factual cluster explanation, independently bounded member and relationship collections, page replacement, selected-member navigation intent, relationship inspection, and stale revision/cluster recovery to an authoritative `WORLD_SCOPE` reload. P10-F3 adds fresh `PERSON` entry from WORLD_SCOPE and CLUSTER, a compact scoped identity/intelligence header, backend-provided cluster memberships, independently bounded relationship and finalized-event summary pages, factual relationship inspection, event navigation intent, origin-aware return navigation, and stale person/canonical recovery. P10-F4 adds a fresh `EVENT` read from PERSON, finalized observation context, independently bounded effective participant, raw provenance, evidence-summary, and media-reference pages, backend raw-to-effective interpretation, retained PERSON return state, and stale event recovery. P10-F5 adds a fresh `EVIDENCE` read from EVENT, explicit raw versus current-effective endpoints, typed/directed factual provenance and explanation, independent bounded Evidence → Media reads, truthful unavailable/requested-empty/not-requested/truncated states, and shared inspection-only media preview with explicit EVENT or EVIDENCE origin. The controller replaces immutable bounded responses, validates retained state at navigation boundaries, invalidates after known graph mutations, and performs no polling or page concatenation. Layout, selection, interaction state, and visual presentation remain client concerns; identity, participation, provenance, evidence/media membership, filters, ranking, intelligence, explanations, pagination, and revision ownership remain backend concerns. P10-FR-01 through P10-FR-04 are fixed, including the follow-up acceptance of the frozen empty `collection_not_requested` page state. The final post-fix integration/runtime gate passes, so P10-F1 through P10-F5 and P10 as a whole are frozen.

## P11 Integrity / rebuild / repair / revert — In progress

P11-A is complete. `docs/P11_INTEGRITY_MODEL.md` records the verified authority map, fixed invariant registry, restrained severity/future-handling model, and explicit `ReadOnlyIntegrityChecker`. It checks schema/SQLite/FKs, identity and canonical chains, corrections, observations/media/reviews, evidence and graph projection equivalence, notes/mentions, merge manifests/inverse structure, and journal transitions/results from one query-only snapshot. It creates no journal row and performs no mutation.

P11-B is complete. The existing graph service command now performs explicit recovery only: full P11-A preflight; refusal on authoritative ambiguity; one `BEGIN IMMEDIATE` snapshot; shared deterministic projection calculation; no-op comparison; complete derived replacement and in-transaction validation; one revision advance only on change; bounded immutable journal result; and post-commit P11-A verification. Current-schema startup no longer silently repairs projection drift. There is no schema, dependency, HTTP/API, frontend, worker, polling, vector-index, structured-repair, or revert change.

P11-C1 authority audit/catalog/execution design is complete and frozen. The executable registry contributes exactly four candidates, but implementation inspection admits only two fixed repair commands. P11C-R01 now implements restoration of an otherwise-valid archived terminal merge survivor with a finding-bound typed token, exact `BEGIN IMMEDIATE` revalidation, a shared archived-to-active primitive, immutable journal, unchanged merge/canonical/graph-edge state, one lifecycle revision advance, and full P11-A post-check. The note occurrence/`NOTE_REFERENCE` reconciliation R02 remains design-only. Generic repair, canonical retargeting, lifecycle/identity guessing, missing-history reconstruction, automatic invocation, and revert remain rejected.

P11-A1 records the required safety-stop correction before R02 resumes. The former row-by-row `P11-NOTE-002` rule incorrectly expected a retired occurrence to reactivate when its person appeared in a later revision. The refrozen rule validates occurrence provenance individually, then requires current active cardinality per existing note/person group. It preserves append/retire history and the wholly-missing-group coverage boundary, leaves NOTE-003 unchanged, and changes no note-domain mutation code.

Remaining order: implement only P11C-R02 from the fixed catalog; P11-D guarded operation revert; P11-E integrity/recovery UI and final acceptance. Exit for all of P11 remains: corruption/drift is reported without inference, rebuild is idempotent, supported repair/revert is guarded and audited, and authority is never reconstructed by guessing.

## P12 Backup/Restore — Future

Extend `backup_service.py` manifests, verification, path rewriting, recovery checks, and compatibility rules for all new authoritative/journal/projection records. Prefer rebuilding derived graph/index state after restore. Exit: encrypted portable backup round trips preserve history/provenance and reject incompatible/newer schemas safely.

## P13 BYOM model manager — Future

Build on `model_setup.py` and existing local upload/install routes to manage fully offline operator-supplied detector/recognizer bundles, hash-bound calibration, compatibility, activation, and rollback. Models and recognition remain proposal generators only. Exit: no download/network dependency and no model activation can mutate authoritative identity data.

## P14 Windows packaging/licensing — Future

Complete Windows packaging, executable-bound offline policy, local licensing/activation rules, upgrades, data-path permissions, backup/recovery UX, and signed release verification. Exit: packaged Windows operation remains offline and passes migration, recovery, security, and licensing acceptance tests.

## Cross-phase gates

- Preserve `FaceEngine`, `IdentityStore`, SQLite, loopback API, React controllers/views, derived vector indexes, and backup services where reasonable.
- Do not use recognition proposals, temporary queue groups, or frontend graph objects as authoritative inputs.
- Every graph-affecting change and its journal entry share one transaction.
- Add tests for failure rollback, idempotent retries, canonical merge chains, evidence independence, participant deduplication, no self-links, archived/tombstoned rendering data, rebuild equivalence, and zero non-loopback network access.
