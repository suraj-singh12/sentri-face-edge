# SentriFace Edge architecture state

This document is a concise checkpoint of the stable implemented architecture. Detailed rules remain in `AGENTS.md` and `DOMAIN_MODEL.md`; phase scope remains in `IMPLEMENTATION_PLAN.md`.

## Current phase

P8-A Merge infrastructure, P8-B Merge orchestration, and P8-C Architecture hardening are complete. P9 Sightings metrics and People sort/group is the next planned phase.

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

`graph_connections`, vector indexes, canonical groupings, and UI graph layouts are derived read models or caches, not authoritative sources.

Compatibility stores are not current truth: `persons.notes` mirrors the latest normalized profile-note revision; `person_operations` is legacy history; `person_associations` is available only for explicit historical/raw reads; and `recognition_details` preserves legacy sighting history. Current profiles, activity, graph relationships, and identity resolution use normalized sources.

## Known deferred work

- P9 sightings metrics and People sort/group improvements based on accepted event participation.
- P9 replacement of legacy `recognition_details` sighting counts with accepted-participant metrics.
- P11 guarded merge/operation revert; normalized merge undo is intentionally not exposed yet.
- P12 backup/restore hardening for normalized authoritative, journal, and projection records.
- P13 fully offline BYOM/model-management work.
- P10 and later graph UI, integrity/rebuild/revert, packaging, and release work remain governed by the implementation plan.
