# SentriFace Edge

SentriFace Edge is a CPU-first, fully offline face identification engine. It is designed for low-end Windows x86 machines first, including i3-class CPUs without a GPU.

The project goal is simple: keep the face system modular and controllable without turning it into a pile of local web services.

## Core Shape

```text
UI
-> App Controller
-> Face Engine
   -> Detector
   -> Aligner
   -> Embedder
   -> Matcher / Index
   -> SQLite Identity Store
   -> Filesystem Image Store
```

The first scaffold uses deterministic placeholder components so the storage, workflows, and contracts can run immediately. Real ONNX models will plug into the same interfaces.

## CPU-First Defaults

Target runtime stack:

```text
Inference: ONNX Runtime CPU
Detector:  det_500m.onnx
Embedder:  w600k_r50.onnx
Search:    hnswlib for larger galleries, linear cosine for tiny galleries
DB:        SQLite
Images:    filesystem paths, not DB blobs
```

For an i3 system:

- Load models once and reuse them.
- Keep processing in a single background worker by default.
- Resize images before detection.
- Cache embeddings and never re-encode unchanged images.
- Store multiple good embeddings per person.
- Use strict thresholds before adding embeddings to an identity.

SentriFace assesses the machine at startup and maps it to a runtime tier:

```text
low    -> 1 worker, batch size 1, smaller image edge, small-model preference
medium -> 2 workers, batch size 2, hnswlib-ready vector index
high   -> 3 workers, batch size 4, larger preprocessing batches
```

For i3-class systems, the goal is not to max out the CPU. The goal is to keep
the UI responsive while recognition happens in the background.

Check the selected profile:

```bash
PYTHONPATH=src python3 -m sentriface.cli profile
```

Use JSON output for future UI integration:

```bash
PYTHONPATH=src python3 -m sentriface.cli --json profile
```

Run with development placeholders:

```bash
PYTHONPATH=src python3 -m sentriface.cli --runtime dev recognize path/to/image.jpg
```

Run with real CPU ONNX components after placing models on disk:

```bash
python -m pip install -r requirements-runtime.txt
python scripts/fetch_models.py

PYTHONPATH=src python3 -m sentriface.cli \
  --runtime onnx \
  --detector-model models/det_500m.onnx \
  --recognizer-model models/w600k_r50.onnx \
  recognize path/to/image.jpg
```

The ONNX path is CPU-only by default and uses the selected hardware profile to
limit ONNX Runtime threads.

Enroll a person from the first detected face:

```bash
PYTHONPATH=src python3 -m sentriface.cli \
  --runtime onnx \
  enroll "Person Name" path/to/image.jpg
```

Queue a face for review instead of immediately updating the DB:

```bash
PYTHONPATH=src python3 -m sentriface.cli --runtime onnx queue-add path/to/image.jpg
PYTHONPATH=src python3 -m sentriface.cli --runtime onnx pending
PYTHONPATH=src python3 -m sentriface.cli --runtime onnx confirm-existing PENDING_ID PERSON_ID
PYTHONPATH=src python3 -m sentriface.cli --runtime onnx confirm-new PENDING_ID "Person Name"
PYTHONPATH=src python3 -m sentriface.cli --runtime onnx reject-pending PENDING_ID
```

Face additions are quality-gated before they enter the pending queue. The engine
checks detector confidence, face size, blur, brightness, crop validity, and
landmark availability.

Possible quality states:

```text
good -> safe to queue/enroll
warn -> accepted, but reasons are shown
bad  -> rejected by default
```

Force a bad-quality face only when you intentionally want it:

```bash
PYTHONPATH=src python3 -m sentriface.cli --runtime onnx queue-add path/to/image.jpg --force-bad-quality
```

## Workflows

### Init_Add

```text
images -> detect -> encode -> cluster -> user confirms groups -> save identities
```

### Add

```text
image -> detect -> encode -> top 3 candidates -> pending suggestion -> user confirms -> save embedding
```

### Recognize

```text
image -> detect -> encode -> search -> top 3 -> show identity or unknown
```

## Storage

```text
data/
  sentriface.db
  faces/
    person_id/
      crop files
  index/
    face_index.bin
models/
  detector.onnx
  recognizer.onnx
```

SQLite stores metadata, embedding records, thresholds, and paths. Original images and face crops live on disk when needed.

The SQLite database uses `PRAGMA user_version` for schema versioning. Newer
database versions are rejected clearly instead of being opened unsafely by older
app builds.

## Run Checks

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```
