# SentriFace Edge architecture state

This document is a concise checkpoint of the stable implemented architecture. Detailed rules remain in `AGENTS.md` and `DOMAIN_MODEL.md`; phase scope remains in `IMPLEMENTATION_PLAN.md`.

## Current phase

P10-D World Intelligence read-model architecture review is complete. P0 through P10-B remain frozen; P10-C and P10-D are documentation-only decisions. The bounded World backend contract and World UI remain separate future phases.

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
- **Merge:** `IdentityMergeService` provides read-only preview and normalized execution over the P8-A canonical and manifest primitives. It preserves raw provenance, applies explicit conflict strategies, updates canonical state, rebuilds the graph projection, and coordinates derived-index publication. Undo remains deferred to guarded P11 revert work.
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
- `/api/world-graph` returns the complete canonical node/edge projection plus summary intelligence. Merged aliases collapse into their survivor; canonical self-edges are suppressed; archived and deleted terminal identities remain historical nodes.
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
- Canonical people are the only current relationship nodes. Active, archived, and deleted identities remain representable; merged sources remain historical provenance but collapse into their survivor. `NO_FACE` is biometric state, not an unknown node type. `UNIDENTIFIED` is distinct identity state and is currently missing from `GraphReadNode`/the API payload.
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

## World contract gap and scaling assessment

- `/api/world-graph` version 1 is sufficient only for a small Level 2 person-to-person projection. It already has canonical nodes, evidence summaries, filters, revision, generation time, and counts, but returns the complete matching graph.
- Before World UI, the version 2 backend read contract must implement the P10-D object, explanation, pattern, scope, and pagination rules. Evidence/event detail must be lazy and bounded.
- P10-E must prove that its revision token advances for every authoritative input used by World. An uncovered input must be excluded or placed under a broader backend-owned snapshot revision before revision-bound cursors are safe.
- The current SQLite read walks all persons, observations, active evidence, sightings, and embeddings and constructs full node intelligence before returning. This is acceptable around 100 people but is not an appropriate initial-load path for 10,000 people or 100,000+ observations. Existing indexes help but do not make the current all-record materialization bounded.
- The first performance step is query bounding and server-side scoping, not a new cache or dependency. For medium data, overview/cluster reads, stable pagination, and lazy expansion are required. For large observation histories, evidence/event detail must be queried on demand and aggregation should be pushed into indexed SQL where measurements show it is needed. Derived caches remain optional, rebuildable optimizations only.

## Person Graph reuse boundary

- Reuse the opaque revision token, immutable replacement model, canonical/lifecycle semantics, backend `allowed_actions`, evidence-count strength, occurrence/provenance explanations, and the rule that React owns only presentation/interaction.
- Do not reuse the person-centred radial membership model, complete-graph loading assumption, homogeneous person-node schema, client-only full-response refresh strategy, or the assumption that edge weight alone communicates importance. World requires scope-first levels, typed summary/detail objects, server-side ranking/clustering, bounded expansion, and density-aware presentation.
- No World UI is safe to start against contract version 1 beyond disposable prototyping. Implement and test the bounded World read contract first; then the UI can safely render it without acquiring graph semantics.

## Known deferred work

- P11 guarded merge/operation revert; normalized merge undo is intentionally not exposed yet.
- P12 backup/restore hardening for normalized authoritative, journal, and projection records.
- P13 fully offline BYOM/model-management work.
- The bounded World read/expansion contract and then World rendering/query controls remain deferred, along with later integrity/rebuild/revert, packaging, and release work.
