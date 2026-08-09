# SentriFace global identity domain model

## Architectural rule

SentriFace owns one global identity graph. **Person Graph** is an identity-centred projection and **World** is a spatial/temporal projection of the same authoritative records and relationship evidence. They are not separate graphs or stores.

Recognition output is non-authoritative proposal data. Only explicit operator finalisation may create or change persons, observations/events, accepted participants, notes/mentions, relationship evidence, corrections, or merge state. A multi-person review becomes authoritative only after every detected face has a final decision and the review is explicitly completed in one transaction.

## Current authoritative model

### Person and canonical identity

`Person` is a stable historical identity node with one explicit lifecycle state: `ACTIVE`, `ARCHIVED`, `DELETED`, or `MERGED`. Archived and deleted nodes remain in graph history; UI projections render them inactive/non-clickable. A merged source also remains historically addressable.

Raw identity is the person ID stored on the authoritative historical record. Effective identity is that raw ID resolved through the explicit, transitive canonical mapping. A merged source resolves to one active canonical survivor. Current-view reads may group by effective identity, but they do not rewrite the raw owner or participant ID.

Canonical resolution is explicit and transitive. Merge records preserve source, target, actor, time, reason, and affected-record provenance. Merges never delete source history or rewrite away the identity under which evidence was originally recorded.

### Observation/Event

`Observation` (or Event) is the immutable event-history and preferred co-occurrence unit after finalisation. It holds event time/place/context and may reference multiple existing photos without duplicating their media storage. Raw participants retain the originally accepted person IDs. Effective participant reads apply correction history and then canonical resolution, without rewriting the raw participant rows.

Within one event, a canonical person appears at most once as a participant. Repeated recognition across photos or faces must not create duplicate participants or self-links. Rejected/ignored/unknown decisions remain review history but do not become accepted participants.

### Notes and mentions

Notes are revisioned authoritative records. Mentions are explicit saved occurrences referencing person IDs; display-name parsing alone is not authoritative. A saved `@Person` mention becomes directed `NOTE_REFERENCE` evidence only when its note revision is committed. Editing/removing a mention retires only evidence originating from that occurrence/revision. Other mention, co-observation, or manual evidence remains intact.

### Relationship assertions, evidence, and projection

A manual relationship assertion is an authoritative record, not an edge owned by a UI component. Relationship evidence has a stable ID, type, endpoints, provenance source, actor/time, and active/retired state. Required evidence types are:

- `CO_OBSERVED`: derived from accepted participants in one completed event.
- `NOTE_REFERENCE`: derived from a saved note revision and exact mention occurrence.
- `MANUAL_ASSOCIATION`: an operator-created association.

A projected relationship exists while at least one active evidence record supports the canonical pair. Evidence is authoritative; `graph_connections` and graph API results are derived projections. Evidence types never overwrite each other. The projection can be cached, but must be fully rebuildable from authoritative persons, events/participants, note revisions/mentions, manual assertions, corrections, and merge history.

### Corrections and operation journal

Identity corrections (Move Face, Add Face, and effective participant changes) are first-class historical operations. Original review decisions, raw participants, face assignments, and prior evidence revisions remain preserved; corrections append provenance and rebuild only the affected current projections. Every important write has an immutable operation-journal entry with operation/idempotency ID, type, actor, timestamp, affected entities, before/after or inverse data, and status. A graph-affecting write and its journal entry commit in the same SQLite transaction.

Embedding enrollment ownership is raw provenance. Move Face appends ownership corrections rather than rewriting that original owner. The latest ownership correction, followed by terminal canonical resolution, determines effective embedding ownership for recognition, browse ranking, representative-photo selection, deletion, restoration, and subsequent moves.

### Merge foundation and orchestration

P8-A provides the merge infrastructure. A normalized merge manifest links one source identity and its terminal active canonical survivor to the operation journal. Immutable affected-item records describe what is preserved, reinterpreted under canonical ownership, unioned in the current view, or selected. Typed conflict records retain source and target values, the chosen strategy (`KEEP_SOURCE`, `KEEP_TARGET`, `COMBINE`, or `USER_SELECTED`), the selected value, and inverse data.

P8-B adds a read-only preview and one normalized execution command through the backend service boundary. Canonical survivor rules reject self-maps, missing targets, cycles, deleted identities, and inactive survivors. Execution applies explicit conflict strategies, writes the manifest and canonical mapping, rebuilds and validates the graph projection, publishes canonical index ownership, and commits the journal atomically. Raw ownership and provenance remain unchanged while effective reads resolve to the survivor. Merge undo remains gated for the guarded P11 revert phase.

### P9 intelligence and sightings read models

A current `Sighting` is a derived `(finalized observation, effective canonical person)` pair. It is not a stored identity record and does not own a face, embedding, or recognition-detail row. Repeated accepted faces for one effective person within the same observation collapse to one sighting. Draft observations and recognition proposals never appear. Raw accepted participant IDs, media membership, correction operation IDs, original timestamps, location/context, and source remain attached as provenance while the current person is resolved through corrections and terminal canonical identity.

`PresenceAnalytics` derives observation count, first/last seen, monthly counts, observed locations, and a descriptive 30-day frequency from those sightings. Frequency is appearances divided by the observed span in 30-day units (with a one-unit minimum); its labels are descriptive buckets, not probabilities. A photo or embedding deletion does not remove an authoritative finalized observation, an identity correction moves the effective current sighting while preserving the raw participant, and a merge unions source history under the canonical survivor.

`RelationshipAnalytics` reads active `relationship_evidence` directly and resolves endpoints canonically. It reports evidence counts by type, co-observation count, first/last evidence time, directionality, raw evidence provenance, and an evidence-count strength basis. It does not assign a probabilistic confidence or mutate `graph_connections`. Profile intelligence combines lifecycle/canonical state, current embedding count, the presence read model, evidence-derived relationships, and canonical operation-journal activity. A confidence summary explicitly reports that no probabilistic identity confidence is available from normalized authoritative records.

These models are calculated by the backend read boundary and returned by the API. They introduce no new authoritative table or cache. No-face identities participate normally because sightings, notes, activity, and relationship evidence do not require an embedding.

## Current repository map (schema version 26)

| Concern | Current implementation |
| --- | --- |
| Domain types | `src/sentriface/models.py`: `Person`, `Note`, `NoteRevision`, `Observation`, `ObservationMedia`, `ObservationParticipant`, `RelationshipEvidence`, `GraphNode`, `GraphConnection`, `GlobalGraphProjection`, plus existing biometric, queue, profile, and legacy-association types |
| Storage boundary | `src/sentriface/contracts.py::IdentityStore` |
| Database and migrations | `src/sentriface/storage/sqlite_store.py`: `SCHEMA_VERSION`, `SQLiteIdentityStore.initialize()`, and the validated `_schema_migrations()` registry through `_migrate_25_to_26`; `_connect()` enables foreign keys and commits/rolls back a connection-scoped transaction |
| Current tables | `persons`, `notes`, `note_revisions`, `note_revision_mentions`, `note_mentions`, `observations`, `observation_media`, historical `observation_participants`, immutable `observation_face_assignments`, `identity_corrections`, `biometric_enrollment_history`, normalized `merge_operations`, `merge_affected_items`, and `merge_conflict_resolutions`, revisioned `relationship_evidence`, derived `graph_connections`, plus existing biometric, queue, sighting, journal, auth, settings, and legacy `person_associations` tables |
| Application service | `src/sentriface/graph_service.py::GlobalIdentityGraphService` is the single normalized evidence/projection boundary; `src/sentriface/engine.py::FaceEngine` owns it as `graph` alongside existing recognition and identity services |
| Correction service | `src/sentriface/correction_service.py::IdentityCorrectionService` centralizes P7 observation correction, Move Face, and Add Face commands and routes graph-affecting work through `GlobalIdentityGraphService` |
| Merge service | `src/sentriface/merge_service.py::IdentityMergeService` is the P8-B preview/execution boundary and coordinates transactional storage execution with derived-index publication/reconciliation |
| Intelligence service | `src/sentriface/intelligence_service.py::IntelligenceReadService` is the read-only P9 boundary for canonical sightings, presence/temporal metrics, evidence-derived relationship analytics, and profile intelligence |
| Recognition/index | `FaceEngine.recognize()` returns proposals; `linear_index.py`/`hnsw_index.py` are rebuilt from active embeddings and are derived caches |
| API | `src/sentriface/api_server.py`; P9/P9.5 enrich `/api/persons` and `/api/person`, expose `/api/person-sightings` and `/api/person-intelligence`, and add the bounded versioned `/api/person-relationship-graph` read contract; recognition, queue, merge, lifecycle, and backup routes retain their prior boundaries |
| React shell/controllers | `frontend/src/SentriFaceApp.jsx`; `useRecognizeController.js`, `useQueueController.js`, `usePeopleController.js`, `useAppData.js` |
| React views | `frontend/src/views/RecognizeView.jsx`, `QueueView.jsx`, `PeopleView.jsx`; no World view exists |
| Current graph UI | `frontend/src/views/PeopleView.jsx::RelationshipGraphModal` renders the backend relationship-subgraph contract; `frontend/src/utils/relationshipGraph.js` converts backend-provided depth bands into coordinates only |
| Backup/offline | `src/sentriface/backup_service.py`, `backup_crypto.py`, `secure_storage.py`, `offline_guard.py`, `os_network_policy.py`; packaging policies under `packaging/` |
| Relevant backend tests | `tests/test_graph_evidence.py`, `test_observations.py`, `test_storage.py`, `test_operation_journal.py`, `test_identity_lifecycle.py`, `test_merge_foundation.py`, `test_identity_merge_orchestration.py`, plus existing engine, queue, person, notes, backup, and offline-packaging tests |
| Relevant frontend tests | `frontend/tests/relationship-graph.test.mjs`, `queue-layout.test.mjs`, `people-layout.test.mjs`, `backend-call-discipline.test.mjs` |

## Current semantics and compatibility boundaries

- `persons` now has explicit `lifecycle_status`, `canonical_person_id`, `identity_status`, `biometric_status`, and `lifecycle_changed_at`. Existing live rows migrate to `ACTIVE`; legacy archived rows remain historical, and valid `metadata.merged_into` sources migrate to `MERGED` mappings.
- Ordinary archive, restore, and delete paths now use atomic lifecycle transitions plus the global operation journal. The compatibility `permanently_delete_person()` entry point tombstones as `DELETED` and retains linked history; the former destructive implementation remains isolated as the storage-only `physically_purge_person()` exceptional capability.
- `observations`, `observation_media`, and `observation_participants` provide draft events, existing-media membership, and canonical-aware participant deduplication while retaining original person IDs. Standalone domain finalisation remains gated; P6 review completion is the exposed atomic finalisation path.
- Existing `recognition_details` rows remain unchanged and accessible. Their nullable `observation_id` remains the compatibility bridge; migration does not invent or backfill events from ambiguous legacy rows.
- `photo_reviews` and `photo_review_faces` hold non-authoritative staged face decisions. `SQLiteIdentityStore.complete_photo_review()` is the single P6 transaction that creates accepted identities/embeddings, finalizes the observation and media/participants, saves review notes, records co-observation evidence, rebuilds/validates the projection, commits one `review.complete` journal operation, and only then marks the review complete. `FaceEngine` gates the legacy per-face pending/Queue confirmation paths.
- Completed P6 reviews also retain immutable face-to-observation assignments. P7 corrections leave original review decisions and `observation_participants` untouched, append `identity_corrections`, expose effective participants on current reads, retire only the affected observation's active co-observation evidence, and create a new evidence revision before rebuilding the global projection.
- Profile notes retain immutable revisions and explicit person-ID mention snapshots. Active mention occurrences own directed `NOTE_REFERENCE` evidence; edit or retirement deactivates only evidence from that occurrence. Merge conflict resolution appends a survivor note revision in the merge transaction. `persons.notes` is refreshed only afterward as a compatibility mirror; profile reads use normalized notes.
- Legacy profile and recognition-detail note text migrates into revision history without parsing `@` text or fabricating mention records/evidence. Existing legacy `automatic_mention` associations are not promoted when their exact note provenance cannot be established.
- Queue confirmation routes selected faces through the same P6 `review.complete` transaction boundary; the controller sends one intent for the selected group subset rather than maintaining durable participant or graph state.
- Check Photo stages decisions and sends one explicit `/api/photo-review-complete` intent after every face has a final decision.
- `relationship_evidence` now retains every immutable raw participant pair and source provenance for `CO_OBSERVED`, `NOTE_REFERENCE`, and `MANUAL_ASSOCIATION`; only finalized-observation evidence is produced in P4. Canonical resolution and self-edge suppression happen only in the replaceable `graph_connections` projection.
- Legacy `person_associations` remains unchanged for historical/raw compatibility. Current profile and relationship-graph reads use the normalized `graph_connections` projection. Legacy rows are not speculatively copied into evidence when accurate provenance cannot be established.
- `_create_note_associations()` remains only for explicit-ID legacy compatibility paths; name matching no longer infers new associations. Normal profile-note saves use the global graph service and normalized evidence instead.
- Removing a current association deletes the whole row even if multiple underlying reasons should support the relationship.
- The current Relationship Graph UI reads canonical neighbors from the evidence-derived `graph_connections` projection. Person Graph/World UI expansion remains P10.
- The P2 canonical resolver and constrained `MERGED` mapping are present. P8-B exposes normalized merge preview and execution through `IdentityMergeService`, `FaceEngine`, and the loopback API. Undo remains gated for P11.
- P8-A provides the caller-owned, connection-scoped canonical update primitive and immutable normalized `merge_operations` / `merge_affected_items` manifests linked to the global operation journal. P8-B executes those primitives in one transaction; legacy merge snapshots are not imported as normalized truth.
- Merge execution preserves source-owned embeddings, recognition history, raw participants, corrections, notes/revisions/mentions, evidence, and prior operation history. It changes the source lifecycle/canonical mapping, applies selected survivor profile values, rebuilds the derived graph projection, and publishes canonical index ownership. A failed transaction leaves no manifest or canonical/profile/graph change and records a durable failed attempt under a non-reusable operation ID.
- Identity, embedding, note, and observation read models retain raw IDs while exposing current canonical resolution. Observation APIs now separate immutable raw participants from corrected/canonical effective participants, and existing raw note mentions remain editable after their referenced identity becomes merged while new mentions remain active-only.
- Move Face appends current embedding-ownership and affected face-assignment corrections and recalculates only affected observations. It does not rewrite raw embedding enrollment ownership. Historical `photo_review_faces`, `recognition_details`, base participants, and inactive evidence revisions retain their original person IDs. The former destructive reassignment remains private as `_legacy_move_embedding()` with no production caller.
- Add Face uses a completed staged review targeting one active existing identity. It creates no person, observation, participant, or graph evidence, records immutable enrollment history, and atomically transitions the existing identity to `ENROLLED`.
- `operation_journal` is the current activity authority and profile activity resolves affected person entities canonically. `person_operations` remains unchanged only for historical compatibility and legacy idempotency; it is not merged into the current activity feed because its rows lack reliable actor and lifecycle data.
- Storage methods are generally transaction-scoped through `_connect()`. Normalized review, correction, and merge commands provide their phase-owned atomic boundaries; remaining legacy workflows that span several engine/API calls are not implicitly atomic.
- Current sightings and People metrics use finalized observations plus corrected/canonical effective participants. `recognition_details` remains available only as legacy recognition/photo-detail history and cannot determine sightings, presence, relationship strength, or identity.
- The People UI renders backend-provided sighting counts, first/last seen values, frequency values/labels, and normalized sighting rows. It no longer derives sightings or frequency from recognition details or client time calculations.

## Projection rules

Graph rebuild reads only authoritative durable records, resolves endpoints through canonical identity, groups active evidence by unordered canonical pair, drops self-links, and retains evidence details for explanation. Archived/tombstoned persons remain nodes with inactive presentation state. Recognition scores, temporary queue grouping, frontend state, and vector-index contents are never graph inputs.
