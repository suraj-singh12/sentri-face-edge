# Security

SentriFace Edge is designed as a single-machine, localhost-only application with
local accounts and roles. It is not a network service and must not be exposed
through a reverse proxy, port-forwarding rule, or non-loopback bind.

Security controls include:

- IPv4 loopback-only binding, Host-header validation, a process-wide outbound socket guard, and rejection of UNC or mapped-network filesystem paths at runtime entry points;
- fail-closed production ONNX startup unless an active OS policy blocks non-loopback outbound traffic for the exact packaged application boundary;
- rejection of state-changing requests from non-local browser origins;
- a per-launch browser secret on every API/media request, strict matching of the actual SentriFace origin, and HttpOnly SameSite account sessions;
- Argon2id password hashing, persistent login lockout, backend-enforced roles, session revocation, and authentication audit records;
- restrictive browser security headers;
- request, upload, image-dimension, and backup-import limits;
- managed-path validation for media and cleanup operations;
- checksummed portable backups and local operator-supplied model installations;
- post-login, administrator-only local model onboarding with SHA-256 verification, hash-bound calibration, and fail-closed recognition when setup files are missing or changed;
- password-based authenticated encryption for exported `.sfbackup.enc` files;
- database migration backups and rollback-oriented restore handling;
- SQLCipher encryption for the live database and authenticated encryption for managed media, backups, and persistent logs;
- OS-vault protection for the per-installation master key and recovery-code-wrapped external recovery kits.

SentriFace refuses non-loopback binds and blocks Python socket name resolution,
connects, and datagrams to non-loopback destinations. The packaged runtime has no
intentional telemetry, updater, model downloader, remote asset, or cloud-recognition
path. OS-level tunnels, proxies, remote desktop, malware, and independently loaded
native code remain outside an application's absolute control. A remote filesystem already
mounted by the operating system can also be indistinguishable from local storage on
Unix-like systems. Do not mount network storage into SentriFace paths, and validate
installers with outbound firewall rules enabled.

Encrypted storage makes copied database, account records, password hashes, and biometric
files unusable without the per-installation key. The application never stores plaintext
passwords. An operating-system custodian who can unlock the installation key can use the
explicit `sentriface-admin-reset` recovery command; this boundary is audited and is why
SentriFace roles do not replace OS account security.

It does not defend against code already running as the same
unlocked OS user. Operating-system disk encryption and account access controls
remain defense-in-depth requirements.

Report suspected vulnerabilities privately to the repository maintainers.
Include the SentriFace version, operating system, reproduction steps, and
whether any real biometric data was involved. Do not attach real face images,
database files, or backup archives to a public issue.

The scripts documented in `tools/dangerous_scripts.md` are destructive local
support utilities, not normal uninstall steps. Removing the OS-vault storage
credential can make encrypted SentriFace data permanently inaccessible.
