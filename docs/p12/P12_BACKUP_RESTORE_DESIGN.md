# P12 backup and restore design

Status: **Implemented.** P12 hardens portable backup creation, validation, staged migration, and guarded restore without changing schema, dependencies, the P11 repair/revert whitelist, or the offline security model.

## Authority boundaries

The encrypted SQLite database remains authoritative for persons, enrollment provenance, observations/participants, normalized notes and mention history, relationship evidence, corrections, merges, and the immutable operation journal. Durable referenced media is authority/provenance that must close over the database snapshot. `graph_connections`, graph revision value, vector indexes, World/graph projections, analytics, and layouts are derived. A backup manifest is signed-by-content evidence describing an archive; it is never domain authority and cannot choose a mutation target.

P12 uses four distinct protections:

1. SQLCipher keeps the database encrypted with the source installation master key.
2. Protected media keeps its existing authenticated-encryption contract.
3. The outer portable export is independently authenticated by the export passphrase.
4. The recovery kit separately transports the source master key for another installation.

Portable restore is therefore not key-independent. Format v3 stores only a non-secret SHA-256-derived key identifier. A missing or wrong source recovery-kit key fails during manifest verification, before staged mutation. Keys, recovery codes, passphrases, plaintext media, note content, embeddings, raw journal payloads, SQL, and stack traces never enter the manifest, restore receipt, journal result, or API response.

## Server-owned media registry

`src/sentriface/media_registry.py` is the only authority for durable media binding enumeration and rewrite. Each fixed entry owns its table, stable identity columns, path column, media class, protection expectation, and `RELOCATE` behavior:

| Registry ID | Stable identity | Media class |
| --- | --- | --- |
| `embeddings.source_image` | `embedding_id` | enrollment/face source |
| `embeddings.crop_path` | `embedding_id` | enrollment/face crop |
| `pending_additions.source_image` | `pending_id` | staged enrollment source |
| `pending_additions.crop_path` | `pending_id` | staged enrollment crop |
| `init_faces.source_image` | `init_face_id` | durable initialization source |
| `init_faces.crop_path` | `init_face_id` | durable initialization crop |
| `recognition_details.image_path` | `detail_id` | historical recognition media |
| `observation_media.media_path` | `observation_id`, `media_id` | finalized observation media |
| `photo_reviews.media_path` | `review_id` | persisted review media |

Archived, deleted, merged, corrected, repaired, reverted, and restored histories need no separate entries because they retain the same stable referenced rows. Initialization-session `source_path` is a scan provenance container that may be a directory rather than a media object; after restore it is derived by server code from the restored initialization-face sources. The manifest cannot supply a table, column, SQL fragment, or destination path.

## Portable manifest version 3

The current writer emits `format_version = manifest_version = 3`. The bounded manifest includes:

- backup ID, creation time, application/schema compatibility facts;
- database archive name, size, and SHA-256;
- non-secret storage-key identifier;
- people/enrollment counts;
- journal structural fingerprint and operation/history counts;
- P11-A status, finding invariant IDs, and report fingerprint;
- content-addressed media objects with archive path, ciphertext checksum/size, protection flag, and authenticated plaintext size;
- one stored or missing registry binding for every non-empty durable media reference in the snapshot;
- reference/file/missing counts, completeness, media-closure status, and computed restore eligibility;
- a canonical manifest fingerprint covering every other field.

Verification rejects future or malformed versions, unsafe/archive-traversal paths, extra or duplicate archive entries, duplicate/ambiguous stable bindings, unknown registry IDs, malformed stable identities, absent database rows, path-fingerprint mismatch, missing assets, checksum/size/authentication mismatch, closure/count mismatch, database/schema/FK failure, journal-fingerprint mismatch, P11-A mismatch, or false restore eligibility.

Legacy format v2 may still be imported/exported only when its complete declared original-path set exactly equals the current registry-derived path set in its database. It cannot guess newly registered references. Format v1 remains database-only and non-portable.

## Coherent backup creation

The API operation gate gives backup creation exclusive application access against graph/media-changing requests and the existing maintenance cleanup. The service completes an encrypted SQLite backup first, then enumerates all durable bindings from that immutable snapshot. Each distinct source path is resolved server-side, copied into managed protected storage, content-addressed, authenticated, and compared with its pre-copy device, inode, size, and modification time. Deduplicated media retains every stable row binding.

Missing media is recorded factually, never fabricated. A missing or concurrently replaced/truncated file makes `media_closure_status = INCOMPLETE`, `complete = false`, and `restorable = false`. The directory can remain a verified diagnostic backup, but restore has no override. Final metadata is written and re-verified only after database, journal, P11-A, assets, bindings, and closure agree.

## Authoritative validation path

`BackupService.verify_backup()` is the one archive-directory validation path used by create, list, export, import, safety backup, and restore. For format v3 it proves:

1. manifest version/canonical fingerprint and source-key compatibility;
2. database checksum, SQLite integrity, foreign keys, schema/count facts;
3. journal structural fingerprint;
4. safe unique media objects and authenticated protected contents;
5. exact server-registry stable-binding closure;
6. completeness and restore-eligibility truth;
7. P11-A semantic fingerprint.

A clean P11-A report is required except isolated `P11-GRAPH-001` projection drift. That one state may be archived as `PROJECTION_DRIFT` and restore-eligible because the imported projection is never trusted and must be rebuilt. Any authoritative error/critical finding or truncated report makes the backup non-restorable.

## Guarded staged restore

`restore_backup()` is serialized by the service lock and the exclusive API operation gate. Its order is:

1. validate backup ID, UUID operation identity, archive/manifest/key/schema/closure and free space;
2. reject conflicting operation identity or return the durable committed receipt/idempotent journal result;
3. append a live `backup.restore` STARTED intent with bounded facts and write a versioned sidecar;
4. create, verify, and protect a complete restorable safety backup of current live database and media;
5. copy the candidate database/media to unique non-live staging locations;
6. migrate only the staged database through the contiguous registered migration chain;
7. rewrite every media reference by registry ID and stable row identity;
8. authenticate staged media and verify closure;
9. run P11-B on the staged database with a restore-derived operation UUID;
10. require clean staged P11-A and closure again;
11. append and commit `backup.restore` in the staged source timeline;
12. install unique media, atomically replace the database, and reload the store/vector cache;
13. require final P11-A and live media closure;
14. publish the durable result receipt and remove intent.

The staged migration validator accepts projection drift only because P11-B immediately follows; foreign keys, lifecycle/canonical state, relationship evidence, and all other domain validation remain strict. Newer schemas and missing/failed migration steps refuse. The imported archive is never modified.

## Graph and history

Imported `graph_connections` and graph revision are not authority. P11-B replaces the projection from active relationship evidence under its existing transactional/journal/revision rules. P11-A must then report `P11-GRAPH-001` clean. Vector indexes are reloaded afterward as derived caches; recognition models are not required for backup, validation, or restore.

The source database's existing journal rows and status history are preserved. The restored timeline appends the P11-B rebuild and one `backup.restore` STARTED-to-COMMITTED operation. The displaced live timeline is not merged into it; the complete safety backup preserves it. If installation does not succeed, the surviving old/safety timeline transitions its STARTED restore to FAILED. Journal and receipt facts are bounded to backup/manifest/schema/safety/database/media/graph/integrity/result identifiers and fingerprints.

## Crash and rollback coordination

Media is installed first into a new unique path that the live database does not yet reference. Only a fully verified staged database is then atomically moved over the live database. Thus a process interruption yields either the old database referencing old media or the committed candidate referencing fully installed new media.

The sidecar records only coordination state, operation/backup identifiers, manifest fingerprint, restore token, safety-backup ID, and unique final media root. On startup, the surviving immutable journal decides recovery:

- COMMITTED plus clean P11-A/media closure republishes a missing receipt and removes intent;
- STARTED means the old timeline survived, so it is marked FAILED and orphaned unique media is removed;
- an unverifiable state retains the sidecar and reports `UNRESOLVED` for explicit attention.

Handled failures after database replacement restore the verified safety database, reload the engine, remove installed candidate media, and mark the surviving attempt FAILED. If safety rollback itself fails, the typed result is explicitly indeterminate; it is never reported as safely rolled back.

## API boundary

`POST /api/backups/restore` explicitly requires administrator-only `database_restore`, works without recognition models, and accepts only `backup_id`, `operation_id`, and optional bounded `reason`. Actor comes only from the authenticated session. Paths, actors, incomplete overrides, SQL/table/column selectors, and arbitrary options are rejected. Typed results distinguish `REFUSED`, `ROLLED_BACK`, `COMMITTED`, operation conflict, and the exceptional indeterminate committed-postcheck state.

No backup/restore command exists under `/api/recovery/*`; that namespace remains recovery-kit/disaster-readiness configuration. P12 adds no automatic restore, polling, worker, scheduler, or new UI workflow.
