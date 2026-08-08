# SentriFace global identity domain model

## Architectural rule

SentriFace owns one global identity graph. **Person Graph** is an identity-centred projection and **World** is a spatial/temporal projection of the same authoritative records and relationship evidence. They are not separate graphs or stores.

Recognition output is non-authoritative proposal data. Only explicit operator finalisation may create or change persons, observations/events, accepted participants, notes/mentions, relationship evidence, corrections, or merge state. A multi-person review becomes authoritative only after every detected face has a final decision and the review is explicitly completed in one transaction.

## Target authoritative model

### Person and canonical identity

`Person` is a stable historical identity node. It has a lifecycle state such as active, archived, or tombstoned. Archived and tombstoned nodes remain in graph history; UI projections render them inactive/non-clickable.

Canonical resolution is explicit and transitive: a merged source remains addressable but resolves to one surviving canonical person. Merge records preserve source, target, actor, time, reason, and affected-record provenance. Merges never delete source history or rewrite away the identity under which evidence was originally recorded.

### Observation/Event

`Observation` (or Event) is the preferred co-occurrence unit. It holds event time/place/context and may reference multiple existing photos without duplicating their media storage. `ObservationParticipant` retains the originally selected person ID; reads also expose its current canonical resolution without rewriting historical ownership.

Within one event, a canonical person appears at most once as a participant. Repeated recognition across photos or faces must not create duplicate participants or self-links. Rejected/ignored/unknown decisions remain review history but do not become accepted participants.

### Notes and mentions

Notes are revisioned authoritative records. A parsed `@Person` mention becomes graph evidence only when its note revision is saved. Editing/removing a mention retires only evidence originating from that mention/revision. Other mention, co-observation, or manual evidence remains intact.

### Relationship assertions, evidence, and projection

A manual relationship assertion is an authoritative record, not an edge owned by a UI component. Relationship evidence has a stable ID, type, endpoints, provenance source, actor/time, and active/retired state. Required evidence types are:

- `CO_OBSERVED`: derived from accepted participants in one completed event.
- `NOTE_REFERENCE`: derived from a saved note revision and exact mention occurrence.
- `MANUAL_ASSOCIATION`: an operator-created association.

A projected relationship exists while at least one active evidence record supports the canonical pair. Evidence types never overwrite each other. The projection can be cached, but must be fully rebuildable from authoritative persons, events/participants, note revisions/mentions, manual assertions, corrections, and merge history.

### Corrections and operation journal

Identity corrections (move face, add face, change a participant decision) are first-class historical operations; they do not silently rewrite provenance. Every important write has an immutable operation-journal entry with operation/idempotency ID, type, actor, timestamp, affected entities, before/after or inverse data, and status. A graph-affecting write and its journal entry commit in the same SQLite transaction.

## Current repository map (schema version 21)

| Concern | Current implementation |
| --- | --- |
| Domain types | `src/sentriface/models.py`: `Person`, `Observation`, `ObservationMedia`, `ObservationParticipant`, `RelationshipEvidence`, `GraphNode`, `GraphConnection`, `GlobalGraphProjection`, plus existing biometric, queue, profile, and legacy-association types |
| Storage boundary | `src/sentriface/contracts.py::IdentityStore` |
| Database and migrations | `src/sentriface/storage/sqlite_store.py`: `SCHEMA_VERSION`, `SQLiteIdentityStore.initialize()`, and the validated `_schema_migrations()` registry through `_migrate_19_to_20`; `_connect()` enables foreign keys and commits/rolls back a connection-scoped transaction |
| Current tables | `persons`, `observations`, `observation_media`, `observation_participants`, normalized `relationship_evidence`, derived `graph_connections`, plus existing biometric, queue, sighting, journal, auth, settings, and legacy `person_associations` tables |
| Application service | `src/sentriface/graph_service.py::GlobalIdentityGraphService` is the single normalized evidence/projection boundary; `src/sentriface/engine.py::FaceEngine` owns it as `graph` alongside existing recognition and identity services |
| Recognition/index | `FaceEngine.recognize()` returns proposals; `linear_index.py`/`hnsw_index.py` are rebuilt from active embeddings and are derived caches |
| API | `src/sentriface/api_server.py`; relevant routes include `/api/recognize`, `/api/recognition-*`, `/api/queue-*`, `/api/person*`, `/api/person-association*`, photo lifecycle, merge/undo, and backups |
| React shell/controllers | `frontend/src/SentriFaceApp.jsx`; `useRecognizeController.js`, `useQueueController.js`, `usePeopleController.js`, `useAppData.js` |
| React views | `frontend/src/views/RecognizeView.jsx`, `QueueView.jsx`, `PeopleView.jsx`; no World view exists |
| Current graph UI | `frontend/src/views/PeopleView.jsx::RelationshipGraphModal` expands neighbor requests; `frontend/src/utils/relationshipGraph.js` stores/layouts client-side nodes and edges for display |
| Backup/offline | `src/sentriface/backup_service.py`, `backup_crypto.py`, `secure_storage.py`, `offline_guard.py`, `os_network_policy.py`; packaging policies under `packaging/` |
| Relevant backend tests | `tests/test_graph_evidence.py`, `test_observations.py`, `test_storage.py`, `test_operation_journal.py`, `test_identity_lifecycle.py`, plus existing engine, queue, person, notes, backup, and offline-packaging tests |
| Relevant frontend tests | `frontend/tests/relationship-graph.test.mjs`, `queue-layout.test.mjs`, `people-layout.test.mjs`, `backend-call-discipline.test.mjs` |

## Current semantics and conflicts to resolve

- `persons` now has explicit `lifecycle_status`, `canonical_person_id`, `identity_status`, `biometric_status`, and `lifecycle_changed_at`. Existing live rows migrate to `ACTIVE`; legacy archived rows remain historical, and valid `metadata.merged_into` sources migrate to `MERGED` mappings.
- Ordinary archive, restore, and delete paths now use atomic lifecycle transitions plus the global operation journal. The compatibility `permanently_delete_person()` entry point tombstones as `DELETED` and retains linked history; the former destructive implementation remains isolated as the storage-only `physically_purge_person()` exceptional capability.
- `observations`, `observation_media`, and `observation_participants` now provide draft events, existing-media membership, and canonical-aware participant deduplication while retaining original person IDs. Standalone domain finalisation is gated; the low-level P3 primitive remains private until P6 supplies atomic review finalisation plus evidence recording.
- Existing `recognition_details` rows remain unchanged and accessible. Their nullable `observation_id` is the compatibility bridge for later atomic P6 workflow integration; P3 does not invent or backfill events from ambiguous legacy rows.
- Queue identity confirmation is atomic per selected group subset in `confirm_init_faces_atomic()`, but `useQueueController.js::confirmQueueFollowup()` then creates one `/api/recognition-followup` write per accepted face. There is no explicit all-faces-final event completion transaction, so identity, sighting, mention, and future graph writes can partially commit.
- Check Photo similarly performs identity confirmation and recognition follow-up as separate API operations in `useRecognizeController.js`.
- `relationship_evidence` now retains every immutable raw participant pair and source provenance for `CO_OBSERVED`, `NOTE_REFERENCE`, and `MANUAL_ASSOCIATION`; only finalized-observation evidence is produced in P4. Canonical resolution and self-edge suppression happen only in the replaceable `graph_connections` projection.
- Legacy `person_associations` remains unchanged for compatibility with the current UI. Its manual/automatic rows are not speculatively copied into normalized evidence before P5 and the later manual-association owning phase can establish accurate provenance.
- `_create_note_associations()` creates an association when saved notes contain a mention, but it does not reconcile removed mentions. A manual link can overwrite an automatic mention's origin, losing independent provenance.
- Removing a current association deletes the whole row even if multiple underlying reasons should support the relationship.
- The current Relationship Graph UI still reads legacy `person_associations`, but the backend global graph now has explainable evidence queries, canonical neighbor/global projection reads, deterministic rebuild, and projection validation. Person Graph/World UI adoption remains P10.
- The P2 canonical resolver and constrained `MERGED` mapping are present. Public merge and undo-merge workflows are gated until P8; the private legacy implementation remains only for compatibility with existing merge history and tests.
- Face move similarly rewrites embedding and sighting ownership; it journals a result but does not preserve a normalized correction history/provenance chain.
- `person_operations` remains unchanged as the legacy idempotency/result table because its rows lack reliable actor and lifecycle data. New work uses the global `operation_journal` API; existing writes are not speculatively backfilled or automatically bridged, so important legacy paths remain unjournaled until their owning phase adopts the API.
- Storage methods are generally transaction-scoped through `_connect()`, which is a useful foundation, but workflows spanning several engine/API calls are not atomic.
- Sightings metrics count `recognition_details` joined through live embeddings; archive/delete/merge/move behavior can therefore change counts rather than report stable event participation.

## Projection rules

Graph rebuild reads only authoritative durable records, resolves endpoints through canonical identity, groups active evidence by unordered canonical pair, drops self-links, and retains evidence details for explanation. Archived/tombstoned persons remain nodes with inactive presentation state. Recognition scores, temporary queue grouping, frontend state, and vector-index contents are never graph inputs.
