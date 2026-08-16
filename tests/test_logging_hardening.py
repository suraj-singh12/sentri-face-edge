from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sentriface.logging_config import (
    ENCRYPTED_LOG_MAGIC,
    EncryptedLogSink,
    redact_log_text,
    sanitize_log_details,
)


class LoggingHardeningTest(unittest.TestCase):
    def test_sensitive_fields_and_filesystem_paths_are_redacted(self) -> None:
        details = sanitize_log_details({
            "token": "secret-token",
            "note_contents": "private note",
            "embedding": [0.1, 0.2],
            "error": "failed at /Users/example/private/file.db",
            "endpoint": "/api/models/status",
        })
        encoded = str(details)
        self.assertNotIn("secret-token", encoded)
        self.assertNotIn("private note", encoded)
        self.assertNotIn("0.1", encoded)
        self.assertNotIn("/Users/example", encoded)
        self.assertEqual(details["endpoint"], "/api/models/status")
        self.assertNotIn("hunter2", redact_log_text("password=hunter2"))

    def test_encrypted_log_rotation_and_retention_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sentriface.sflog"
            sink = EncryptedLogSink(path, b"k" * 32, max_bytes=180, retention=2)
            for index in range(20):
                sink.write(f"event-{index}-" + ("x" * 80))
            archives = list(path.parent.glob("sentriface-*-*.sflog"))
            self.assertLessEqual(len(archives), 2)
            self.assertEqual(path.read_bytes()[: len(ENCRYPTED_LOG_MAGIC)], ENCRYPTED_LOG_MAGIC)
            for archive in archives:
                self.assertEqual(
                    archive.read_bytes()[: len(ENCRYPTED_LOG_MAGIC)], ENCRYPTED_LOG_MAGIC,
                )


if __name__ == "__main__":
    unittest.main()
