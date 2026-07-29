# Similarity calibration requirement

Production ONNX startup is fail-closed unless `calibration.json` is stored beside
`recognizer.onnx`. Generate its thresholds from a representative validation set
for the exact recognizer and the deployment's target false-match rate.

```json
{
  "recognizer_sha256": "64 lowercase hex characters",
  "representative_dataset": "name/version and population description",
  "target_false_match_rate": 0.0001,
  "thresholds": {
    "possible": 0.0,
    "likely": 0.0,
    "strong": 0.0
  }
}
```

Do not copy example threshold values into production. Record dataset provenance,
subgroup coverage, evaluation date, score distributions, and the selected operating
point in release evidence. Recalibrate whenever the recognizer or target population
changes.