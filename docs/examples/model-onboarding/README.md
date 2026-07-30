# SentriFace model-onboarding examples

These files show the shape of values requested by the offline model-onboarding
screen. They contain placeholders only and do not grant model rights.

- `research-use.example.json`: reference values for a non-commercial research declaration.
- `commercial-license.example.json`: reference values for supplier-licensed weights.
- `permissive-license.example.json`: reference values for weights under a commercially usable permissive licence.
- `calibration-thresholds.example.json`: an optional threshold file that SentriFace can validate and install after its recognizer hash is replaced.

The three declaration examples are documentation, not import files. Enter their
values into the matching UI fields. Model paths must be absolute paths on the
machine running SentriFace. Replace every value enclosed in angle brackets.

Generate SHA-256 values locally:

- Windows: `Get-FileHash PATH -Algorithm SHA256`
- macOS/Linux: `shasum -a 256 PATH`

Never copy a sample licence reference or hash into a real deployment.
