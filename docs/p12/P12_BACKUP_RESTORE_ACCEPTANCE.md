# P12 backup and restore acceptance

Status: **ACCEPTED — P12 complete.** The restore endpoint is enabled because the required safety gates are implemented and the full backend/frontend/build checks pass.

## Acceptance matrix

| Requirement | Result | Evidence |
| --- | --- | --- |
| Complete authoritative database snapshot | PASS | SQLite backup completes before media enumeration; database checksum, integrity, FKs, schema, counts, journal, and P11-A fingerprints verify. |
| Complete durable-media closure | PASS | Fixed server registry covers every durable schema media column; stable row bindings from the snapshot must exactly match manifest stored/missing bindings. |
| No manifest filesystem/SQL authority | PASS | Manifest contains registry IDs and stable identities only; unknown/duplicate bindings and unsafe/extra archive paths reject. |
| Media capture race detection | PASS | Source device/inode/size/mtime is compared across capture; missing/changed/truncated files prevent restorable closure. |
| Protected-media authentication | PASS | Each captured/staged/installed protected object is authenticated to plaintext with the source key, in addition to ciphertext checksum/size. |
| Secret exclusion and key contract | PASS | Only a non-secret storage-key ID is stored. Wrong/missing source key refuses; passphrase remains outer-archive-only and recovery kit remains separate. |
| Incomplete backup restore | PASS | `restorable` is server-derived; no service/API/UI `allow_incomplete` path exists. |
| Schema compatibility | PASS | Current schema restores; every registered v0-v27 staged path reaches v28; newer/invalid/missing migration states refuse without modifying source/live input. |
| Journal preservation | PASS | Source journal/history is retained, staged P11-B and restore append new operations, safety backup preserves the displaced live timeline. |
| Untrusted graph handling | PASS | Corrupted backup projection is rebuilt deterministically with P11-B and final `P11-GRAPH-001` is clean. |
| P11-A semantic gate | PASS | Snapshot eligibility, staged post-rebuild state, staged post-journal state, and installed state are checked; unrelated authority findings are never auto-repaired. |
| Safety backup | PASS | A complete verified restorable backup of live database/media is mandatory after STARTED and before candidate staging. |
| Half-install prevention | PASS | New media is installed at a unique unreferenced root before atomic database swap; handled failure restores safety state and removes candidate media. |
| Crash/restart recovery | PASS | Sidecar plus surviving immutable journal resolves STARTED to FAILED or republishes a COMMITTED receipt; unresolved state is retained, not guessed. |
| Idempotency/conflict | PASS | Same operation UUID/backup returns committed result; same UUID with another intent refuses without mutation. |
| Authorization/actor | PASS | Route explicitly requires `database_restore`; viewer/operator/custodian/technician are denied; actor is session-derived and spoof fields reject. |
| Recognition independence | PASS | Backup/restore routes bypass model readiness while retaining normal auth/offline guards. |
| No new repair capability | PASS | Restore calls only validation, registered staged migration, P11-B, and P11-A; R01/R02/P11-D never auto-run. |
| Offline/schema/dependency constraints | PASS | Loopback/offline model retained; schema v28 and dependencies unchanged; no new worker or polling loop. |

## Test coverage

Focused backend coverage includes:

- format-v3 metadata, checksum, closure, deduplication, observation/photo-review and all registry binding classes;
- missing/tampered/truncated/concurrently changed media;
- unsafe archive paths, extra entries, unknown/duplicate bindings, omitted closure, and manifest fingerprint tampering;
- protected-media correct/wrong-key authentication and outer export passphrase authentication;
- same-schema export/import/restore and every registered staged schema migration version;
- newer schema refusal and malformed staged candidate rollback;
- graph projection corruption followed by P11-B rebuild and clean P11-A;
- source journal/note history preservation, new restore history, retry, and conflicting operation ID;
- administrator success, all non-administrator role refusal, actor spoof rejection, and operation without recognition models;
- injected exceptions before/after safety backup, staging, migration, media rewrite, graph rebuild, staged integrity, media install, database swap, reload, final integrity, and receipt;
- restart completion when installation committed but receipt publication was interrupted.

Frontend coverage verifies that the existing UI consumes backend `restorable`, sends only backup ID and operation UUID, and contains no incomplete override, client actor, or registry/SQL choice.

## Final gates

- Backend: `.venv/bin/python -m pytest -q` — PASS.
- Frontend: `npm --prefix frontend test` — PASS.
- Production build: `npm --prefix frontend run build` — PASS.
- Whitespace/patch check: `git diff --check` — PASS.

The exact final counts are recorded in the P12 completion report for the implementation run.

## Frozen outcome

- P12 backup/restore: complete.
- Restore endpoint: enabled.
- Incomplete backup restore: impossible through supported service/API/UI paths.
- Schema changed: no.
- Dependencies changed: no.
- Frontend changed: yes, only the required response-contract compatibility adjustment and its focused test.
- P13/P14: not started.
