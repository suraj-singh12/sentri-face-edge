# SentriFace Edge agent handoff

This is the shortest safe path for an engineer or coding agent taking over the
`pre-packaging` branch. It is an orientation guide, not a replacement for the
normative rules in the repository-root `AGENTS.md`.

## Current checkpoint

- Application version: `2.0.0` (`src/sentriface/_version.py`).
- Database schema: v28 (`SQLiteIdentityStore`).
- P0 through P14 source implementation is complete.
- P10 through P13 are frozen.
- Unsigned Windows 11 x64 packaging acceptance passed.
- Production release acceptance is still incomplete: rebuild from a clean exact
  `v2.0.0` tag, re-run the release gates, then Authenticode-sign and timestamp
  the executable and installer.
- The runtime is offline and loopback-only. Do not weaken the application socket
  guard, OS network-policy checks, or localhost request validation.

## Read in this order

1. `AGENTS.md` — non-negotiable product, authority, transaction, and test rules.
2. `docs/ARCHITECTURE_STATE.md` — what is implemented now and what remains.
3. `docs/IMPLEMENTATION_PLAN.md` — phase sequence and completed exit gates.
4. `docs/DOMAIN_MODEL.md` — normative identity, evidence, lifecycle, and graph rules.
5. `docs/ARCHITECTURE_EXPLANATION.md` — rationale and rejected alternatives.
6. The relevant frozen phase record under `docs/p10`, `docs/p11`, `docs/p12`, or
   `docs/p14` before changing that area.

Historical files and pre-optimization benchmark artifacts are evidence, not
current authority. `src/sentriface/ui_static/` is generated from `frontend/` and
must not be edited by hand.

## Architectural map

| Concern | Primary implementation |
| --- | --- |
| Domain records | `src/sentriface/models.py` |
| Storage contract | `src/sentriface/contracts.py::IdentityStore` |
| SQLCipher store and migrations | `src/sentriface/storage/sqlite_store.py::SQLiteIdentityStore` |
| Recognition/application boundary | `src/sentriface/engine.py::FaceEngine` |
| Loopback API, auth, and route policy | `src/sentriface/api_server.py` |
| Identity lifecycle and merge | `src/sentriface/{identity_service,merge_service,revert_service}.py` |
| Evidence graph and read models | `src/sentriface/{graph_service,graph_read_service,intelligence_service}.py` |
| Integrity and recovery | `src/sentriface/{integrity,structured_repair_service,integrity_recovery_service}.py` |
| Backup/restore and media closure | `src/sentriface/{backup_service,media_registry}.py` |
| Model authority and runtime activation | `src/sentriface/{model_bundle,model_activation,model_setup}.py` |
| Runtime/offline hardening | `src/sentriface/{runtime_hardening,offline_guard,os_network_policy}.py` |
| Licensing | `src/sentriface/licensing/` |
| React shell and controllers | `frontend/src/SentriFaceApp.jsx`, `frontend/src/hooks/` |
| React views | `frontend/src/views/` |
| Windows release build | `build_release.ps1`, `installer/SentriFaceEdge.iss`, `packaging/windows/` |

## Authority rules to keep in mind

- Recognition output is a proposal. Only explicit operator finalisation creates
  identity, participant, evidence, or graph truth.
- Multi-face review is all-or-nothing: every face needs a final decision before
  the operator completes the review.
- Graph edges are derived from independently retained evidence. Removing one
  evidence record must not remove an edge supported by other evidence.
- Corrections and merges preserve raw history. Archive and delete are lifecycle
  states; merge sources resolve to a surviving canonical identity.
- Important writes use an operation/idempotency ID. A graph-affecting authority
  change, its evidence/projection change, and its journal transition commit in
  one SQLite transaction.
- The React application renders backend truth; it does not maintain durable
  identity associations or reconstruct graph semantics.

## Local development

Use Python 3.11 or 3.12. For a fast synthetic development run:

```bash
python -m pip install -e ".[test]"
sentriface-ui --runtime dev --data-dir data
```

Open `http://127.0.0.1:8765`. The development runtime exercises application
workflows but produces synthetic face results. Real ONNX source setup and model
licensing steps are documented in the root `README.md` and `models/MODELS.md`.

The normal verification gate is:

```bash
python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

Run focused tests first while developing. Migration, graph, backup/restore,
runtime-hardening, licensing, and packaging work has additional mandatory gates
in `AGENTS.md`, the phase acceptance documents, and `packaging/README.md`.

## Release and support boundary

- `src/sentriface/_version.py::APP_VERSION` is the release version authority.
- Production release mode requires a clean tree at exact tag `v<version>`.
- Model weights and private signing/license keys must never enter release artifacts.
- Windows uninstall intentionally preserves per-user data, models, backups,
  recovery material, logs, license state, and the OS-vault key.
- `tools/wipe_clean_this_machine_installation_and_data.py` and credential cleanup
  scripts are destructive test/support utilities. Read `tools/dangerous_scripts.md`
  before using them; never run them on a machine containing required data.
- A packaged Windows startup failure now displays a native error dialog as well
  as the diagnostic console message, while retaining fail-closed startup.

## Before handing off again

1. Keep `docs/ARCHITECTURE_STATE.md` and `docs/IMPLEMENTATION_PLAN.md` consistent.
2. Update `docs/README.md` when adding, moving, or superseding a document.
3. Record operator-visible changes in `CHANGELOG.md`.
4. Preserve historical acceptance records rather than rewriting them as current.
5. Report the branch, changed files, tests run, and any remaining release gate.
