# Recognition model policy

SentriFace does not bundle or download face-recognition weights.

SentriFace sells model-independent recognition software, not model weights or model
rights. Operators supply their own detector and recognizer, choose the legal basis
for their intended use, and remain responsible for model licensing and biometric
processing. SentriFace records that assertion but does not authenticate it or grant
third-party rights.

Install local files with SHA-256 verification:

```text
sentriface-models \
  --detector-source path/to/licensed-detector.onnx \
  --detector-sha256 <64-hex-digest> \
  --recognizer-source path/to/licensed-recognizer.onnx \
  --recognizer-sha256 <64-hex-digest> \
  --usage-basis commercial-license \
  --authorized-by "Customer Administrator" \
  --organization "Customer Organization" \
  --licensor "Model Supplier" \
  --license-reference "Agreement or invoice reference" \
  --accept-model-responsibility
```

For non-commercial research only, use `--usage-basis
noncommercial-research`, `--authorized-by`, and
`--accept-model-responsibility`. The UI then displays a persistent research-only
warning. A permissively licensed model instead uses `--usage-basis
permissive-license --license-name <license>`.

The command writes `model-usage.json` beside the installed models. That local
record binds the operator's assertion to both SHA-256 hashes. SentriFace refuses
to start the ONNX runtime if the declaration is missing, incomplete, based on
older terms, or no longer matches either model.

SentriFace does not upload or authenticate license documents. False declarations
do not create model rights and may violate the SentriFace terms. Compatibility
does not imply affiliation, endorsement, or sublicensing. Replacing either model
requires a new declaration; replacing the recognizer also requires re-embedding
enrolled faces and recalibration.

The command installs `detector.onnx` and `recognizer.onnx`. Keep the supplier's
license, invoice, model card, provenance, and redistribution terms with release
records. Calibrate similarity thresholds on a representative validation dataset
for the exact installed recognizer and target false-match rate.
