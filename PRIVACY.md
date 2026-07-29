# SentriFace Edge privacy and local data

SentriFace Edge processes recognition images locally. It does not contain
telemetry, analytics, advertising, or a cloud synchronization service.

The application stores sensitive biometric-related information, including:

- source images and face crops accepted into the library;
- numerical face embeddings used for matching;
- names and optional person/event metadata;
- recognition history, deletion history, and operation receipts;
- portable backups containing the database and referenced image files.

By default these files live in the current user's SentriFace application-data
directory. The exact path is shown in the Debug/Profile view and can be changed
with `--data-dir` or `SENTRIFACE_DATA_DIR`.

Application data and managed backups are not encrypted at rest by SentriFace. Use operating-system disk encryption and account controls.
The UI exports new portable copies as password-encrypted `.sfbackup.enc` files.
Their authenticated encryption protects the exported file during transfer and
storage, but does not encrypt the live library or managed safety backups. A lost
passphrase cannot be recovered by SentriFace.

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
