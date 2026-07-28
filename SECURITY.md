# Security

SentriFace Edge is designed as a single-user, localhost-only application. It is
not a multi-user network service and must not be exposed through a reverse
proxy, port-forwarding rule, or non-loopback bind.

Security controls include:

- loopback-only binding and Host-header validation;
- rejection of state-changing requests from non-local browser origins;
- restrictive browser security headers;
- request, upload, image-dimension, and backup-import limits;
- managed-path validation for media and cleanup operations;
- checksummed portable backups and model downloads;
- database migration backups and rollback-oriented restore handling.

The local database, images, embeddings, logs, and backup exports are not
encrypted by the application. Use operating-system disk encryption and account
access controls when the threat model includes another user or physical access.

Report suspected vulnerabilities privately to the repository maintainers.
Include the SentriFace version, operating system, reproduction steps, and
whether any real biometric data was involved. Do not attach real face images,
database files, or backup archives to a public issue.
