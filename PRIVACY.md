# SentriFace Edge privacy and local data

SentriFace Edge processes recognition images locally. It does not contain
telemetry, analytics, advertising, or a cloud synchronization service.

The application stores sensitive biometric-related information, including:

- source images and face crops accepted into the library;
- numerical face embeddings used for matching;
- names and optional person/event metadata;
- recognition history, deletion history, and operation receipts;
- local account names, Argon2id password hashes, roles, login state, and authentication audit records;
- portable backups containing the database and referenced image files.

By default these files live in the current user's SentriFace application-data
directory. The exact path is shown in the Debug/Profile view and can be changed
with `--data-dir` or `SENTRIFACE_DATA_DIR`.

SentriFace encrypts the live SQLite database with SQLCipher and encrypts managed
images, face crops, backup assets, and persistent log records with authenticated
AES-256-GCM. A random per-installation master key is stored in the current
operating-system user's credential vault. Existing managed plaintext data is
migrated before the recognition engine opens it. Files created afterward are encrypted,
but migration cannot guarantee forensic erasure of old plaintext blocks previously
written to an SSD or filesystem snapshot.

Local account passwords are never stored or logged in plaintext. Account records and
authentication audit entries reside inside the encrypted SQLCipher database. Browser
authentication uses an HttpOnly cookie; SentriFace does not persist the session secret in browser JavaScript storage.

This protects copied or stolen application files. It does not protect against
malware or a person already operating as the same unlocked OS user, because that
user can ask the operating-system vault to release the key. Full-disk encryption
and a locked, dedicated OS account remain recommended.

The UI exports portable copies as password-encrypted `.sfbackup.enc` files. A
configured disaster-recovery destination receives automatic encrypted exports
and a recovery kit containing only a passphrase-wrapped master key. The one-time
recovery code is not written to application files and cannot be recovered by
SentriFace if both the operator's copy and OS vault are lost.

"Erase from live library" removes the active face and linked sightings only
after creating a verified safety backup. That new backup, older managed backups,
and exported files can retain recovery copies. Complete erasure therefore also
requires deliberately deleting every relevant managed and exported backup.

SentriFace has no built-in model-download operation. The `sentriface-models`
command accepts only local, checksum-verified, operator-supplied weights. It records
the operator's declared commercial, research, or permissive usage basis against the
exact model hashes. SentriFace does not upload or authenticate license documents,
grant third-party model rights, or remove the operator's responsibility for model
licensing and lawful biometric processing.

Only enroll people and process images when you have the necessary permission
and a lawful basis for biometric processing in your jurisdiction.
