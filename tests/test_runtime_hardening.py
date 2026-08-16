from __future__ import annotations

import os
import signal
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sentriface.api_server import (
    EngineBusyError,
    OperationGate,
    _install_shutdown_signal_handlers,
)
from sentriface.runtime_hardening import (
    InstanceLock,
    RuntimeReadinessError,
    cleanup_managed_temporaries,
    validate_managed_storage,
)
from sentriface.secure_files import write_protected_bytes
from sentriface.secure_storage import StorageSecurityError, validate_recovered_master_key
from sentriface.storage.sqlite_store import SQLiteIdentityStore


class RuntimeHardeningTest(unittest.TestCase):
    def test_second_instance_is_refused_and_release_is_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = InstanceLock(root).acquire()
            try:
                with self.assertRaisesRegex(RuntimeReadinessError, "already owns"):
                    InstanceLock(root).acquire()
            finally:
                first.release()
            replacement = InstanceLock(root).acquire()
            replacement.release()
            self.assertFalse((root / ".sentriface.instance.lock").exists())

    def test_storage_readiness_rejects_disk_pressure_and_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "data"
            with self.assertRaisesRegex(RuntimeReadinessError, "free space"):
                validate_managed_storage(
                    root,
                    (root / "faces",),
                    minimum_free_bytes=100,
                    disk_usage=lambda _: SimpleNamespace(free=99),
                )
            outside = Path(temporary) / "outside"
            outside.mkdir()
            models = root / "models"
            models.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeReadinessError, "symbolic"):
                validate_managed_storage(root, (models,), minimum_free_bytes=0)

    def test_storage_readiness_refuses_unwritable_managed_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch(
            "sentriface.runtime_hardening.tempfile.mkstemp",
            side_effect=PermissionError("denied"),
        ):
            root = Path(temporary) / "data"
            with self.assertRaisesRegex(RuntimeReadinessError, "not writable"):
                validate_managed_storage(root, (root / "faces",), minimum_free_bytes=0)

    def test_recovered_key_is_authenticated_before_it_can_replace_live_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_protected_bytes(root / "face.jpg", b"biometric", b"a" * 32)
            validate_recovered_master_key(root, b"a" * 32)
            with self.assertRaisesRegex(StorageSecurityError, "incompatible"):
                validate_recovered_master_key(root, b"b" * 32)

    def test_cleanup_removes_only_old_recognized_temporary_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / ".staging-old"
            keep = root / "authoritative.json"
            old.mkdir()
            keep.write_text("keep", encoding="utf-8")
            age = time.time() - (2 * 24 * 60 * 60)
            os.utime(old, (age, age))
            self.assertEqual(cleanup_managed_temporaries((root,)), 1)
            self.assertTrue(keep.exists())

    def test_shutdown_gate_rejects_new_operations_and_drains_existing(self) -> None:
        gate = OperationGate()
        gate.begin_shutdown()
        with self.assertRaisesRegex(EngineBusyError, "shutting down"):
            with gate.shared():
                pass
        self.assertTrue(gate.wait_for_idle(0.01))

    def test_shutdown_waits_for_an_interrupted_operation_boundary(self) -> None:
        gate = OperationGate()
        entered = threading.Event()
        release = threading.Event()

        def operation() -> None:
            with gate.shared():
                entered.set()
                release.wait(2)

        thread = threading.Thread(target=operation)
        thread.start()
        self.assertTrue(entered.wait(1))
        gate.begin_shutdown()
        self.assertFalse(gate.wait_for_idle(0.01))
        release.set()
        thread.join(2)
        self.assertTrue(gate.wait_for_idle(0.1))

    def test_sqlite_connections_apply_production_durability_pragmas(self) -> None:
        statements: list[str] = []

        class Connection:
            def execute(self, sql):
                statements.append(sql)
                return self

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        store = SQLiteIdentityStore(Path("authority.db"))
        with patch("sentriface.storage.sqlite_store.connect_database", return_value=Connection()):
            with store._connect():
                pass
        self.assertIn("PRAGMA foreign_keys=ON", statements)
        self.assertIn("PRAGMA busy_timeout=30000", statements)
        self.assertIn("PRAGMA synchronous=FULL", statements)

    def test_sigint_and_sigterm_install_the_same_shutdown_path(self) -> None:
        handlers = {}
        server = SimpleNamespace(
            log_event=lambda *args, **kwargs: None,
            graceful_shutdown=lambda: calls.append("shutdown"),
        )
        calls: list[str] = []
        with patch("sentriface.api_server.signal.getsignal", return_value="previous"), patch(
            "sentriface.api_server.signal.signal",
            side_effect=lambda signum, handler: handlers.setdefault(signum, handler),
        ), patch("sentriface.api_server.threading.Thread") as thread:
            thread.return_value.start.side_effect = lambda: thread.call_args.kwargs["target"]()
            previous = _install_shutdown_signal_handlers(server)
            self.assertEqual(set(previous), {signal.SIGINT, signal.SIGTERM})
            handlers[signal.SIGINT](signal.SIGINT, None)
            self.assertEqual(calls, ["shutdown"])

        calls.clear()
        handlers.clear()
        with patch("sentriface.api_server.signal.getsignal", return_value="previous"), patch(
            "sentriface.api_server.signal.signal",
            side_effect=lambda signum, handler: handlers.setdefault(signum, handler),
        ), patch("sentriface.api_server.threading.Thread") as thread:
            thread.return_value.start.side_effect = lambda: thread.call_args.kwargs["target"]()
            _install_shutdown_signal_handlers(server)
            handlers[signal.SIGTERM](signal.SIGTERM, None)
            self.assertEqual(calls, ["shutdown"])


if __name__ == "__main__":
    unittest.main()
