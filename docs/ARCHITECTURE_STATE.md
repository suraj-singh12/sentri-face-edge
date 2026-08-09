# SentriFace Edge architecture state

This document is a concise checkpoint of the stable implemented architecture. Detailed rules remain in `AGENTS.md` and `DOMAIN_MODEL.md`; phase scope remains in `IMPLEMENTATION_PLAN.md`.

## Current phase

P10-B Person Graph UI is complete. P0 through P10-A remain frozen; World UI remains a separate future phase.

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

## Known deferred work

- P11 guarded merge/operation revert; normalized merge undo is intentionally not exposed yet.
- P12 backup/restore hardening for normalized authoritative, journal, and projection records.
- P13 fully offline BYOM/model-management work.
- World map/graph rendering and query controls remain deferred, along with later integrity/rebuild/revert, packaging, and release work.
