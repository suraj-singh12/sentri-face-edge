# SentriFace model choice

Default CPU/i3 model pair:

```text
Detector:   det_500m.onnx
Recognizer: w600k_r50.onnx
```

Install and verify them with:

```bash
sentriface-models
```

By default they are stored in the platform-specific SentriFace data directory.
Use `SENTRIFACE_MODEL_DIR` or `--models-dir` to choose another location.

## Why this pair

`det_500m.onnx` is the lightweight SCRFD detector. It keeps detection cheap on
i3-class CPUs.

`w600k_r50.onnx` is the stronger ArcFace-style recognizer. Recognition quality
matters more than detector size once a face is found, and this model gives a
better accuracy balance than a tiny recognizer.

This is a deliberate hybrid:

```text
small detector + strong recognizer
```

## Source and terms

The files come from official InsightFace release/model-zoo archives:

- `buffalo_s` contains `det_500m.onnx`.
- `buffalo_l` contains `w600k_r50.onnx`.

The `sentriface-models` command verifies the exact expected byte size and
SHA-256 digest before atomically installing either file. SentriFace does not
bundle these weights in its Python wheel.

Review the current InsightFace model terms before commercial or redistributed
use. Pretrained model weights can have terms separate from the source code.