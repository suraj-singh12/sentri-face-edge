# SentriFace Edge

**Offline, CPU-first face recognition and evidence-based identity management.**

SentriFace Edge helps operators review local photographs, identify people, confirm who appears in an Encounter, and explore the supporting history and relationships. Recognition results are **suggestions**; operator decisions and recorded evidence determine durable identity and Encounter history. The application is designed to run locally without cloud recognition services.

## What it does

- **Recognize and review:** Detect faces in photographs, assess quality, suggest matches and review grouped images.
- **Manage people:** Maintain identity profiles, authorized reference photographs, lifecycle history and controlled merges.
- **Record Encounters:** Confirm participants, preserve source media, location and time, and make auditable corrections.
- **Investigate evidence:** Inspect People, Events, Person Graph and World relationships with their supporting records.
- **Keep data under local control:** Encrypted storage, role-based permissions, offline operation, recovery and backup tools.

The application uses Python, React, ONNX Runtime CPU, SQLite/SQLCipher and a local image store. No GPU or external recognition API is required.

## Get started

**Requirements:** Git and **Python 3.12**. The supported source workflow runs on macOS and Windows; Linux has a source-development path. Node.js is needed when rebuilding/testing the frontend, not for an ordinary source launch.

```bash
git clone https://github.com/suraj-singh12/sentri-face-edge.git
cd sentri-face-edge
./run.sh                 # macOS / Linux source mode
```

On Windows, use `./run.ps1` from PowerShell instead. Open **http://127.0.0.1:8765** and create the first local administrator.

The default source launch uses **synthetic recognition** for development and does not establish real face-identification performance.

For genuine recognition, supply appropriately licensed SCRFD/ArcFace-compatible ONNX models through the existing Model Setup process, then launch `./run.sh onnx` or `./run.ps1 onnx`. SentriFace does **not** bundle or grant rights to model weights. See the [source-development guide](docs/DEVELOPMENT_MODE.md) and [model policy](models/MODELS.md) for platform-specific steps, admission requirements and data isolation.

## Testing and QA

```bash
python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

The reusable QA foundation includes isolated test data, real-photo fixture validation, a browser/ONNX acceptance journey, independent People/Events/World checks and failure evidence. Its complete setup and command are in [Development Mode — QA Foundation](docs/DEVELOPMENT_MODE.md#qa-foundation-17). QA Foundation acceptance was demonstrated on macOS in [draft PR #23](https://github.com/suraj-singh12/sentri-face-edge/pull/23); this work is **not yet merged** into the hardening branch.

## Documentation

| Read | Purpose |
| --- | --- |
| [Project overview](docs/PROJECT_OVERVIEW.md) | Product concepts, capabilities and workflows |
| [Development mode](docs/DEVELOPMENT_MODE.md) | Source setup, genuine ONNX admission, QA and troubleshooting |
| [Documentation map](docs/README.md) | Canonical architecture, domain and maintenance reading order |
| [Contributor rules](AGENTS.md) | Required engineering, security and GitHub workflow |
| [Privacy](PRIVACY.md) · [Security](SECURITY.md) | Data handling and security boundaries |
| [Release acceptance](docs/p14/P14_RELEASE_ACCEPTANCE.md) · [Changelog](CHANGELOG.md) | Release qualification and changes |

**Release status:** The 2.0.0 Windows installer is an **unsigned engineering candidate**, not a verified signed production release. Source-mode acceptance does not replace packaged installer qualification.

## License

Proprietary software. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md).
