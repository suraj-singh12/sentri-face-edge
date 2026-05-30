# SentriFace Model Choice

Default CPU/i3 model pair:

```text
Detector:   det_500m.onnx
Recognizer: w600k_r50.onnx
```

Place them as:

```text
models/det_500m.onnx
models/w600k_r50.onnx
```

Then run:

```bash
PYTHONPATH=src python3 -m sentriface.cli \
  --runtime onnx \
  --detector-model models/det_500m.onnx \
  --recognizer-model models/w600k_r50.onnx \
  recognize path/to/image.jpg
```

## Why This Pair

`det_500m.onnx` is the lightweight SCRFD detector. It keeps detection cheap on
i3-class CPUs.

`w600k_r50.onnx` is the stronger ArcFace-style recognizer. Recognition quality
matters more than detector size once a face is found, and this model gives a
better accuracy balance than the tiny MobileFaceNet recognizer.

This is a deliberate hybrid:

```text
small detector + strong recognizer
```

That is the best first choice for low-resource offline recognition without
making the system feel slow.

## Source

These filenames are from the InsightFace model zoo bundles. A convenient way to
obtain them is from the official InsightFace release/model zoo packages:

- `buffalo_s` contains `det_500m.onnx`
- `buffalo_l` or `buffalo_m` contains `w600k_r50.onnx`

Check model license terms before commercial use. InsightFace code is permissive,
but pretrained model weights can have separate restrictions.

