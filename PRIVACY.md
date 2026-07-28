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

Application data and `.sfbackup` exports are not encrypted by SentriFace.
Protect the operating-system account and disk, and handle exported backups as
sensitive files. A soft-deleted person or face can remain in the database and
backups until it is permanently purged and older backups are removed.

The only built-in network operation other than the localhost UI is the explicit
`sentriface-models` command, which downloads pinned model files from the
InsightFace GitHub release location. Recognition and library data are not sent
with that request.

Only enroll people and process images when you have the necessary permission
and a lawful basis for biometric processing in your jurisdiction.
