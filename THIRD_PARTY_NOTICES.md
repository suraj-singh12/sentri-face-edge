# Third-party notices

SentriFace Edge uses third-party Python and JavaScript packages. Their license
terms remain those of their respective projects and distributions.

Face detector and recognizer weights are not included and are never downloaded
by SentriFace. Operators must supply compatible ONNX weights, retain model
provenance and license records, and confirm that their commercial and
redistribution rights cover the intended release. Checksum verification protects
installation integrity; it does not grant model rights.
For non-commercial research use, the operator must instead declare and comply
with the applicable model terms. SentriFace records but does not authenticate
any commercial or non-commercial research assertion. A declaration
and checksum verification do not create or grant model rights.

Storage security dependencies include:

- SQLCipher Community Edition, distributed under its open-source BSD-style license;
- `sqlcipher3`, distributed under the MIT License;
- Python `keyring`, distributed under the MIT License;
- Python `argon2-cffi` and its bindings, used for Argon2id password hashing under their applicable upstream licenses;
- Python `cryptography`, used for authenticated file, log, backup, and recovery-key encryption under its applicable upstream licenses.

SentriFace's proprietary license does not replace or restrict those upstream
licenses. Installer and source distributions must retain their required notices.
