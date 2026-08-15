# SentriFace Edge architecture state

This document is a concise checkpoint of the stable implemented architecture. Detailed rules remain in `AGENTS.md`, `DOMAIN_MODEL.md`, and `p11/P11_INTEGRITY_MODEL.md`; phase scope remains in `IMPLEMENTATION_PLAN.md`.

## P11 integrity, rebuild, repair, revert, and recovery UI complete

P11-A through P11-E are complete and frozen. `ReadOnlyIntegrityChecker` explicitly opens schema-v28 storage read-only/query-only, holds one deferred SQLite snapshot, runs the fixed P11 invariant registry, and returns deterministic bounded factual findings. `GlobalIdentityGraphService.rebuild_projection()` remains the explicit projection-only recovery command for `relationship_evidence → graph_connections`: it reuses normal projection semantics, refuses authoritative `ERROR`/`CRITICAL` ambiguity, replaces drift under `BEGIN IMMEDIATE`, validates before commit, advances the opaque revision only when the projection changes, journals `graph.projection.rebuild`, and runs the checker again after commit.

P11-A1 corrected and refroze `P11-NOTE-002` after R02 safely stopped on an occurrence-history contradiction. P11-C2A then completed the entire note revision → occurrence → `NOTE_REFERENCE` revision → graph audit after a second safety stop exposed the dependent evidence-history contradiction. The checker and shared graph authority now validate retired rows as immutable history, enforce current active occurrence/evidence cardinality separately, and project active evidence only. Valid repeated replacements and add/remove/re-add histories are clean; malformed retirement provenance, stale/duplicate current state, and projection drift remain detected. Wholly missing occurrence groups remain outside coverage. No normal note/evidence mutation, history, schema, API, or UI behavior changed.

P11-C implements exactly the two catalog entries. R01 accepts a typed P11-A token, restores only an otherwise-valid archived terminal survivor under `BEGIN IMMEDIATE`, preserves canonical/merge history, advances the lifecycle visibility revision once, journals atomically, refreshes the derived index, and runs full P11-A. R02 accepts a typed one-note/one-person finding token and deterministically executes one of five plans: append occurrence plus evidence, retire occurrence plus its active evidence, append missing evidence, retire-and-replace duplicate active evidence, or retire exact stale-active evidence. It never reactivates, deletes, retargets, or rewrites history. It validates shared active-only graph authority, updates only the affected directed aggregate, advances revision once for every active-evidence change including canonical collapse, and leaves revision stable for occurrence-only retirement. Every malformed, ambiguous, stale, unrelated, `P11-EVIDENCE-002`, or non-admitted `P11-EVIDENCE-001` state refuses. P11-E delegates only to these typed commands; there is still no startup hook, worker, polling, repair-all behavior, generic repair engine, or new repair.

P11-D adds one explicit whitelist entry, `identity.merge.revert`, for a deliberately narrow normalized-merge shape. Preparation requires clean untruncated P11-A, a complete `STARTED → COMMITTED` original journal and immutable merge manifest, an originally active/unmapped source, no conflict/profile/note/survivor-biometric mutation, the exact current merge post-state, and no later operation touching any manifest-affected entity. Its immutable token binds the original operation/type/status/history, affected entities, lifecycle and graph revisions, complete merge/projection fingerprints, and dependency state. Execution repeats the proof under `BEGIN IMMEDIATE`, restores only the source to a new `ACTIVE` lifecycle state, rebuilds the derived graph with normal authority, validates graph/FKs/history, appends a new committed revert operation, and appends `COMMITTED → REVERTED` to the original journal. Exact retry is idempotent. Unsupported, already-reverted, stale, changed, malformed, dependent, or ambiguous requests perform no mutation. Failed in-transaction attempts roll back source/graph/revisions/journals together and may record a separate bounded failed attempt. No merge manifest, conflict, affected item, evidence, correction, note revision, or old journal detail/history is deleted or rewritten. P11-E exposes only its prepare/execute boundary; there is no generic undo, revert-all, automatic eligibility discovery, startup hook, worker, polling, schema, or dependency change.

P11-E adds the administrator-only `/api/integrity/*` application/API boundary and an **Integrity & recovery** section under Debug/System. The application layer runs P11-A, emits a versioned bounded DTO that redacts paths, database diagnostics, note content, embeddings, and raw journal payloads, and maps only exact finding shapes to server-signed preparation references. R01, R02, and revert execution require server-generated immutable tokens; graph rebuild preparation is also token-bound while P11-B repeats its own authoritative preflight at execution. All routes explicitly require the existing `recovery` capability and remain available when recognition models are unavailable. The UI renders only backend plans/results, requires a reason plus explicit confirmation, discards stale tokens, retains operation IDs for idempotent retry, distinguishes committed post-check failure, and refreshes from the returned P11-A report. It performs no optimistic domain update, automatic check, polling, worker, scheduler, startup recovery, repair-all, or backup/restore action.

## P12 backup/restore hardening complete

P12 replaces portable format v2 as the current writer with an authority-aware format-v3 manifest. A code-owned media registry enumerates only stable schema bindings for enrollment sources/crops, initialization face sources/crops, historical recognition images, observation media, and persisted photo-review media from the completed SQLite snapshot. Manifests contain registry IDs, stable row identities, content checksums, protection/authentication facts, database/schema/journal/integrity fingerprints, and closure status; they contain no table/column/SQL authority, original filesystem paths, storage key, recovery code, passphrase, note content, or embeddings. Format v2 remains importable only when its legacy path set proves complete closure against the current server registry. Incomplete, malformed, ambiguous, future-format, newer-schema, wrong-key, unauthenticated, or semantically invalid backups are not restorable.

Restore is re-enabled only through administrator capability `database_restore` at `POST /api/backups/restore`. The request accepts backup ID, operation UUID, and bounded reason; actor identity comes from the authenticated session. One exclusive coordinator verifies the archive/manifest/key/database/media/journal/P11-A state, records live intent, creates and verifies a complete safety backup, stages database and media away from live paths, migrates only the staged database through the registered chain, rewrites media through stable registry bindings, authenticates protected media, rebuilds the untrusted graph with P11-B, and requires full P11-A before installation and after reload. The source journal is preserved; the restored timeline appends `graph.projection.rebuild` and `backup.restore`, while the safety backup preserves the displaced live timeline. Sidecar intent and durable receipts coordinate interruption only; they are not domain authority. Failure before confirmed success leaves the old state or restores the verified safety backup, records FAILED in the surviving timeline, and removes newly installed media. No authoritative repair is invoked automatically.

P12 changes no schema or dependency and adds no worker or polling loop. The existing backup/restore UI has only the compatibility changes required to consume server-owned `restorable` eligibility and stop sending `allow_incomplete`.

## Current phase

P10-F World UI and the complete P10 phase are frozen as of 2026-08-11 against the World v2 backend. World is a persistent top-level view with backend-normalized scope controls, authoritative totals/facets, ranked canonical people, revision-bound clusters and memberships, measured patterns, typed relationship pages, bounded finalized-event summaries, effective participants, independent raw provenance, exact evidence detail, and bounded supporting media references. Every semantic level performs a fresh revision/filter-bound read rather than expanding preview data. `EVIDENCE` preserves backend type/direction, raw and current-effective endpoints, source provenance, factual explanation, and explicit media availability; EVENT and EVIDENCE media share an inspection-only preview while retaining distinct origins. Collection pages are replaced rather than concatenated, retained detail is invalidated by lifecycle revision changes, and no continuous polling is used. P0 through P12 are complete; P10 and P11 remain frozen.

The final integration review found P10-FR-01 through P10-FR-04, and the bounded freeze-fix pass corrected all four. The first post-fix runtime gate then exposed one remaining P10-FR-02 validator mismatch for the frozen backend's empty `collection_not_requested` page state; the focused follow-up fixed that mismatch without changing the backend. The complete gate rerun passes focused and full automated verification, fresh empty-database World startup, same-revision deep navigation/Back restoration, direct WORLD_SCOPE → PERSON, and runtime g6 → g7 retained-hierarchy invalidation in light and dark themes. P10-FR-01, P10-FR-02, P10-FR-03, and P10-FR-04 are FIXED.

## Core principles

- The backend owns business logic and durable mutation boundaries.
- The UI renders backend state and sends operator intent; it does not own durable associations.
- The identity graph derives from authoritative relationship evidence.
- Raw identity and event history are preserved rather than rewritten or erased.
- Canonical identity provides the effective current view over raw historical records.
- Recognition results remain proposals until explicit operator finalisation.

## Domain services

- **Identity/lifecycle:** creates identified people, applies `ACTIVE`, `ARCHIVED`, `DELETED`, and `MERGED` semantics, and resolves canonical identity.
- **Observation:** owns events, media membership, immutable raw participants, effective corrected/canonical participants, and finalised co-observation history.
- **Notes:** owns notes, immutable revisions, explicit person-ID mentions, and mention-derived `NOTE_REFERENCE` evidence.
- **Graph:** owns normalized evidence operations, canonical projection rebuild/validation, and explainable graph reads.
- **Review finalisation:** commits completed multi-face decisions, accepted identity data, observation state, evidence, and journal history atomically.
- **Correction:** records observation identity corrections, Move Face, and Add Face with preserved provenance and affected projection rebuilds.
- **Merge:** `IdentityMergeService` provides read-only preview and normalized execution over the P8-A canonical and manifest primitives. It preserves raw provenance, applies explicit conflict strategies, updates canonical state, rebuilds the graph projection, and coordinates derived-index publication. P11-D can revert only the separately proven no-survivor-mutation/no-dependency subset; all other merge shapes refuse.
- **Intelligence:** `IntelligenceReadService` exposes deduplicated effective sightings, presence/temporal metrics, evidence-derived relationship analytics, and canonical operation-journal activity without adding an authoritative store or mutating the graph.
- **Graph reads:** `GraphReadService` exposes canonical Person Graph and World Graph read models, backend-owned filters, provenance summaries, and durable revision tokens. It reads authoritative evidence and normalized storage, not compatibility associations or frontend state.

## Mutation rules

Only backend application/domain services may mutate authoritative identity state. The UI and recognition pipeline may submit intent or proposals, but they cannot directly create graph truth.

Important mutations require a stable operation/idempotency ID and an operation-journal record. Each graph-affecting authoritative change, its evidence changes, its derived projection update, and its journal transition must commit in one SQLite transaction. Durable graph mutation crosses the `GlobalIdentityGraphService` and storage transaction boundary; React state, recognition scores, queue grouping, and legacy client graph objects are never graph inputs.

## Current authoritative data sources

| Source | Authority |
| --- | --- |
| `persons` plus lifecycle/canonical fields | Raw identity records and current canonical mapping |
| `observations`, media, raw participants, face assignments, and corrections | Event truth and preserved identity-decision history |
| `notes`, `note_revisions`, and saved mention occurrences | Note history and explicit person references |
| `relationship_evidence` | Relationship/graph truth with independent provenance |
| `operation_journal` | Important operation and status history |
| `merge_operations`, affected items, and conflict resolutions | Normalized merge history, affected-item provenance, selected strategies, and inverse data |

`Sighting`, `PresenceAnalytics`, `RelationshipAnalytics`, profile intelligence, `graph_connections`, vector indexes, canonical groupings, and UI graph layouts are derived read models or caches, not authoritative sources.

Compatibility stores are not current truth: `persons.notes` mirrors the latest normalized profile-note revision; `person_operations` is legacy history; `person_associations` is available only for explicit historical/raw reads; and `recognition_details` preserves legacy recognition/photo-detail history. Current profiles, activity, graph relationships, identity resolution, sightings, and presence metrics use normalized sources.

## P9 read behavior

- One current sighting is one finalized observation plus one effective canonical person, regardless of duplicate face detections or media count.
- Corrections determine current effective participation; immutable raw participants and correction operation IDs remain visible as provenance.
- Merge resolution aggregates source observations and embeddings into the canonical survivor without rewriting original ownership or timestamps.
- Presence metrics expose observation count, first/last seen, monthly trend buckets, observed-location counts, and a documented descriptive frequency value/label.
- Relationship analytics read active `relationship_evidence`, including independent type counts and first/last occurrence. Evidence count is reported as strength; no unsupported probability is invented.
- Profile activity comes only from `operation_journal`. No-face identities use the same read models without automatic identity or enrollment creation.
- The backend computes these values. The React People view renders them and retains `recognition_details` only for legacy face/photo-detail presentation.
- `/api/persons` supplies versioned collection statistics, presentation fields, and sort orders. `/api/person` supplies normalized profile notes/mention occurrences, relationship rows, relationship counts, and operation-journal activity.
- `/api/person-relationship-graph` is the bounded, versioned subgraph read contract for the existing relationship modal. It owns graph membership, canonical endpoints, lifecycle state, evidence/counts, breadth-first depth, truncation, and revision metadata; React owns only coordinates and visual interaction state.
- Current identity mutations trigger authoritative People/profile/deleted-face reads. React does not synthesize lifecycle, canonical ownership, embeddings, activity, or aggregate intelligence after a write.

## P10-A graph read behavior

- `/api/person-graph` returns one canonical root, its evidence-derived relationships, UI-ready node state, canonical endpoints, evidence-count strength, occurrence bounds, directionality, and summarized provenance.
- `/api/world-graph` version 1 returns the complete canonical node/edge compatibility projection plus summary intelligence. Merged aliases collapse into their survivor; canonical self-edges are suppressed; archived and deleted terminal identities remain historical nodes.
- `/api/graph-revision` exposes the current opaque revision and can compare a client-supplied `current_revision`. Person and World responses carry the same revision and a generated timestamp.
- Filters are backend semantics: inclusive date occurrence bounds, exact case-insensitive observation location, canonical lifecycle/country/rank/priority facets, P9 descriptive frequency threshold, and post-scope evidence-count strength threshold.
- `relationship_evidence` remains the edge source. P10-A does not read `person_associations`, expose raw evidence rows, add layout coordinates, or cache graph responses.
- Schema v27 adds the singleton `graph_state` counter plus indexes for active evidence endpoint/time reads and finalized observation time/location reads. Revision changes share the mutation transaction; committed idempotent retries retain the prior token.

## P10-B Person Graph UI behavior

- The People profile header and association section open a full Person Graph workspace using only `/api/person-graph`.
- React renders backend nodes, endpoints, evidence counts/types, strength, occurrence bounds, provenance summary, lifecycle, biometric state, representative media, and allowed actions without reconstructing relationships.
- `personGraphLayout.js` uses only backend-provided nodes and `root_person_id` for deterministic radial multi-ring coordinates. Edges never determine membership or placement.
- The workspace supports pan, zoom, hover, node/edge selection, evidence inspection, empty graphs, and large node collections. Archived and deleted nodes remain visibly historical.
- Navigation checks backend `allowed_actions`; restricted nodes remain selectable for inspection and show the backend-derived restriction instead of opening another graph.
- Graph revision is an opaque consistency token. In the current offline single-user model, the UI validates it at lifecycle boundaries and after known graph mutations. Continuous polling is intentionally avoided.
- The opening graph read stores its token. Closing retains the read model; returning validates once through `/api/graph-revision`, reuses an unchanged model, and fully reloads a changed model. Successful merge, correction/move-face, archive, delete, restore, finalized review, queue acceptance, and graph-affecting note writes invalidate the retained model. Manual refresh fully reloads it. No mutation patches local nodes or edges.
- No World route, view, request, rendering, or layout was added.

## P10-C World Graph architecture decision

- World is a scope-first, spatial/temporal exploration of the global identity graph, not a zoomed-out Person Graph. Its purpose is to surface significant people, evidence-derived relationships, activity patterns, and their time/place context, then let the operator progressively ask for explanation.
- The initial World experience is Level 0 overview data, followed by Level 1 important people/read-model clusters, Level 2 canonical person relationships, and Level 3 evidence/finalized-event detail. Every response and expansion is bounded and revision-consistent. The backend owns membership, clustering, ranking semantics, canonical collapse, evidence aggregation, filters, totals, and truncation; the frontend owns coordinates, camera, selection, and presentation.
- Canonical people are the only current relationship nodes. Active, archived, and deleted identities remain representable; merged sources remain historical provenance but collapse into their survivor. `NO_FACE` is biometric state, not an unknown node type. `UNIDENTIFIED` is a distinct identity state exposed by World API v2.
- Finalized observations/events are secondary evidence-detail objects and appear only on explicit drill-down. Locations remain filters/facets because the current source is free-text observation metadata and has no stable location identity. Read-model clusters are ephemeral summaries for one query/revision and never authoritative organizations or associations.
- One finalized observation is already the grouped-encounter unit; sightings are derived detail records, not nodes, and no cross-observation encounter group may be inferred. Overview edges aggregate scoped person-pair relationships between summaries, Level 2 edges remain evidence-derived person relationships, and Level 3 may expose finalized-event participation. Each edge states its type and aggregation/strength basis.
- Unresolved and finalized-unknown face decisions are not participants, sightings, nodes, or relationship endpoints. Repeated unknown appearances cannot be linked from recognition similarity. Tracked unknown nodes require a future explicit operator-finalized authoritative entity/lifecycle; until then only aggregate finalized unknown/non-participant decision metadata is permissible, never draft review state.
- Backend filters must support effective date/recent scopes, location facets, lifecycle, identity/biometric state, country, rank, priority, evidence/relationship type, descriptive frequency, and scoped evidence-count strength. Responses echo resolved filters and `as_of`; the UI sends intent and does not recreate semantics.

## P10-D World Intelligence read-model decision

- World is an intelligence system over one normalized identity environment. Authoritative World entities are canonical people and finalized observations/events. Person relationships and event participation are authoritative-record projections. Clusters, patterns, salience/ranking, aggregate edges, trends, and explanations are derived, revision-bound read objects.
- Clusters are deterministic groups over the scoped evidence-derived person graph. They have an algorithm/version, parameters, member set, revision-bound ID, and evidence-based membership explanation. They are not organizations or durable entities; location/time similarity alone cannot create membership.
- The supported detail model is Level 0 `WORLD_SCOPE`, Level 1 `CLUSTER`, Level 2 `PERSON`, Level 3 `EVENT`, and Level 4 `EVIDENCE`. These are semantic backend request levels, not frontend zoom states. Events and evidence appear on focused drill-down, not in initial topology.
- Evidence, photos, notes, sightings, detections, embeddings, locations/time buckets, journal entries, proposals, and pattern cards are never topology nodes. Event-to-event edges are excluded until an authoritative event-link model exists. Cluster-to-cluster edges are explicitly aggregate counts, not assertions about every member.
- Initial intelligence is limited to deterministic activity change, relationship change, emerging evidence-based clusters, recurring time/location context, and data-quality limitations. Every pattern declares subjects, windows, baseline, metrics, thresholds, sample sufficiency, calculation version, supporting counts, and evidence expansion. Intent, affiliation, risk, sentiment, causation, demographics, prediction, identity confidence, and opaque AI summaries are prohibited.
- Structured explanations separate factual factors from derived calculations. Relationships explain evidence counts/types and occurrence bounds; clusters explain qualifying member edges and grouping rules; people separate explicit priority from computed activity/connection/recency factors; patterns show current and baseline values, windows, thresholds, and limitations.
- Backend filter order is normative: scope events/evidence; resolve canonical identities and suppress self-links; apply eligible-person state/profile filters; aggregate/threshold relationships; then compute clusters, patterns, salience, ranking, and facets. Requested and effective filters, `as_of`, missing-location policy, and semantics version are echoed.
- The minimum contract is `/api/world-graph` version 2 with level, typed focus, filters, ranking intent, limits, and revision-bound cursor/expansion tokens. A common envelope carries typed people/clusters/events/patterns/edges, explanations, scope totals/facets, algorithm versions, counts, and truncation. Separate overview/cluster/person/event routes are not justified yet.
- All responses are capped. Small scopes may return a complete bounded Level 2 graph; 10,000-person scopes start with server-aggregated Level 0/1 data and lazy expansion; 100,000-observation histories require indexed server-side aggregation and on-demand event/evidence pages. Derived caches remain optional, measured, revision-keyed, and rebuildable.

## P10-E World API v2 implementation

- `/api/world-graph?version=2` accepts the five semantic detail levels, typed focus, normalized World filters, deterministic ranking intent, hard per-object limits, `as_of`, revision, and revision-bound cursor. Version 1 remains unchanged for compatibility.
- The backend returns typed people, ephemeral evidence-connected clusters, finalized events, bounded provenance evidence, evidence-derived relationships, and qualified descriptive patterns in one revision-consistent envelope. It owns scope totals/facets, effective filters, ordering, clustering, explanations, truncation, pagination, and expansion identity.
- `WORLD_SCOPE` pages ranked people and bounded cluster/pattern summaries; `CLUSTER` expands one revision-bound component; `PERSON` returns a bounded scoped relationship neighbourhood without Person Graph layout assumptions; `EVENT` returns finalized observation detail; `EVIDENCE` returns bounded source provenance. No level is a UI zoom threshold.
- Clustering uses deterministic connected components over qualifying scoped evidence relationships and requires at least two members. Explanations expose algorithm/version, parameters, member/relationship/evidence counts, types, and occurrence bounds. The initial pattern surface is limited to measured missing-location data quality. There is no intent, affiliation, organization, risk, prediction, anomaly, or hidden-AI conclusion.
- Existing normalized persons, finalized observations/participants/corrections, active relationship evidence, notes/mentions, merge history, and operation provenance remain authoritative. World has no table or cache. SQL performs evidence/event scoping and aggregation; event/evidence detail is always bounded and lazy.
- The shared opaque revision now covers finalized events even when no relationship edge is created. Schema v28 only narrows the existing person metadata trigger so unrelated metadata does not invalidate World; it adds no World truth. Revision-bound cursors reject stale or mismatched snapshots.
- Frontend responsibility remains limited to future rendering, layout, interaction state, and request intent. No World route, view, visualization, React logic, or generated frontend asset was added.

## World scaling and compatibility assessment

- `/api/world-graph` version 1 is sufficient only for a small Level 2 person-to-person projection. It already has canonical nodes, evidence summaries, filters, revision, generation time, and counts, but returns the complete matching graph.
- Version 2 implements the P10-D object, explanation, scope, filter, hard-bound, and pagination rules. Evidence/event detail is lazy and bounded. Version 1 remains compatibility-only.
- Revision-input tests cover finalized event visibility, relationship evidence, canonical/lifecycle/profile changes, stale cursor rejection, and irrelevant draft/tag metadata writes.
- Version 1 still walks complete graph inputs and is unsuitable for medium/large World loading. Version 2 bounds serialized objects, pushes event/evidence scoping and pair aggregation into SQL, pages every selected collection, and dispatches focused person/event/evidence requests without global ranking or clustering. Global work is restricted to overview and cluster resolution.
- No cache or dependency was added. Exact-scale acceptance shows the remaining dense work is bounded, set-based, and approximately scale-driven; no cache, materialized authority, worker, index, schema change, or new dependency is required for the P10 contract.

## P10-E readiness history and 2026-08-11 freeze review

The implemented hardening correctly deduplicates `(finalized observation, terminal canonical person)` before activity, ranking, patterns, and totals. Directed relationship aggregation preserves a single consistent direction. Explanation objects state calculation scope, method, strongest factors, thresholds/samples where applicable, and limitations; ranking objects state intent, reason, scoped metrics, position, deterministic tie-break, and that values are ordering measurements rather than confidence. The 2026-08-10 freeze review reopened the correctness and contract gates described below.

Progressive reads use explicit collection intent. `WORLD_SCOPE` owns global summaries; `CLUSTER` independently pages members or relationships; `PERSON` independently pages relationships or finalized event summaries; `EVENT` independently pages effective participants, evidence, or media references; and `EVIDENCE` is a bounded provenance read. Implemented collection pages expose total/returned counts, `has_more`, a scope/revision/collection-bound cursor, and truncation reason. Raw/effective participant provenance is an explicit mapping. Focused person/event/evidence reads do not execute global ranking or clustering, and person event summaries batch their participant/evidence/media counts instead of issuing one query per event. The freeze findings below supersede the earlier claim that every unrequested child is fully lazy.

The reproducible `scripts/benchmark_world_v2.py` fixture measures single local reads; latency is measured without allocation instrumentation and Python peak allocation is measured in a separate repeated read. The fixture uses normalized finalized rows but bypasses production writes solely to seed scale. Results on 2026-08-09:

| Dataset/read | Latency | SQL reads | Peak Python allocation | Payload | Pagination |
| --- | ---: | ---: | ---: | ---: | --- |
| A: 100 people / 10,000 observations, `WORLD_SCOPE` | 24.99 ms | 7 | 0.16 MiB | 66,004 bytes | 25 people, `has_more=true` |
| A, `PERSON/EVENTS` | 3.63 ms | 13 | 0.17 MiB | 49,020 bytes | 25 events, `has_more=true` |
| A, focused `EVENT/PARTICIPANTS` | 2.16 ms | 13 | 0.02 MiB | 3,826 bytes | complete |
| B: 10,000 people / 1,000,000 observations, `WORLD_SCOPE` | 2,008.12 ms | 5 | 8.74 MiB | 66,050 bytes | 25 people, `has_more=true` |
| B, `PERSON/EVENTS` | 36.61 ms | 11 | 4.97 MiB | 49,020 bytes | 25 events, `has_more=true` |
| B, focused `EVENT/PARTICIPANTS` | 18.43 ms | 13 | 2.15 MiB | 3,826 bytes | complete |

Query restructuring removed repeated overview scans, applies sparse correction/merge adjustments to direct scoped aggregates, and reduced focused Dataset B person-event reads from the diagnostic 23.7 seconds/134 statements to about 37 ms/11 statements. The overview SQL pass combined activity and location counting, removed runtime SQL location normalization, and combined canonical/person projection reads. On 2026-08-10 an adaptive unfiltered sparse path was added: it scans the covering participant primary-key index first only when no multi-participant observation exists, while dense and filtered scopes retain observation-first traversal. In an alternating same-connection p50 comparison, the 10,000-person/1,000,000-single-participant-observation overview improved from 3,257.85 ms to 2,273.42 ms; a 100,000-observation/1,000,000-participant dense overview remained effectively unchanged at 613.86 ms versus 613.96 ms. These are diagnostic p50 results, not the required full cold/warm p50/p95 matrix.

The stabilization pass closed every recorded correctness and contract finding. World v2 reads now use one explicit SQLite snapshot beginning with the revision read. Effective evidence endpoints share correction-before-canonical resolution across projection and expansion, exact relationship predicates prevent self-edge/cross-edge leakage, and evidence counts agree with complete supporting cursor walks. The backend supplies bounded overview relationships, cluster ranking/activity, person cluster membership, exact evidence-to-media navigation, independent raw participant provenance, paged location facets, explicit unrequested children, and `NOT_LOADED` neighbour analytics. Expansion-token compatibility fields are absent from active JSON. Evidence materialization is batched: the representative 25-item EVENT page fell from 78 to 17 statements including event summaries, and the empty 1,000-person evidence read is at most 6 instead of 1,004.

The final mandatory matrix completed on 2026-08-11 in `docs/p10/benchmarks/P10_WORLD_BENCHMARK_RESULTS_POST_OPT.json` using three cold and five warm samples per read. Dataset B dense warm p50 improved from 206.09 seconds to 15.73 seconds for unfiltered overview, 111.06 seconds to 12.92 seconds for date filtering, 128.07 seconds to 11.51 seconds for location filtering, 415.76 seconds to 1.13 seconds for person events, 418.79 seconds to 1.00 second for correction-heavy person events, 209.27 seconds to 0.41 second for person relationships, and 248.93 seconds to 24.18 seconds for cluster members. The three-page location-facet walk improved from 674.42 seconds to 53.06 seconds. Corresponding Dataset A/B SQL counts remain constant, payloads and returned collections remain bounded, and every cursor walk completes exactly. Dense-B Python allocation is explicitly `NOT_PRACTICAL_DENSE_B_TRACEMALLOC_DISTORTS_RUNTIME`; product latency remains separately measured. P10-PERF-01 through P10-PERF-05 pass without a cache, materialized view, worker, dependency, index, schema, or frontend change.

## Person Graph reuse boundary

- Reuse the opaque revision token, immutable replacement model, canonical/lifecycle semantics, backend `allowed_actions`, evidence-count strength, occurrence/provenance explanations, and the rule that React owns only presentation/interaction.
- Do not reuse the person-centred radial membership model, complete-graph loading assumption, homogeneous person-node schema, client-only full-response refresh strategy, or the assumption that edge weight alone communicates importance. World requires scope-first levels, typed summary/detail objects, server-side ranking/clustering, bounded expansion, and density-aware presentation.
- P10-F1 `WORLD_SCOPE`, P10-F2 `CLUSTER`, P10-F3 `PERSON`, P10-F4 `EVENT`, and P10-F5 `EVIDENCE`/supporting media are frozen against the additive v2 contract. The final integration/adversarial gate verified the full chain without granting the frontend canonical, topology, ranking, cluster, evidence, media, filter, or truncation authority.

## Known deferred work

- P13 fully offline BYOM/model-management work.
- Packaging and release work remain deferred; P13 has not started.
