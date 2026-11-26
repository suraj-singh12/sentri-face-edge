"""Disposable test authority environment for the Issue #89 experiments.

* File-backed keyring replacement (same approach as tests/conftest.py, but
  persisted beside the disposable authority so a database can be reopened by a
  later process). It never touches an OS vault.
* Deterministic scripted clock and UUID source. Every fixture step runs inside
  ``Determinism.step(label, at)``: ``utc_now()`` returns ``at`` plus a
  per-step microsecond counter and ``uuid.uuid4()`` returns
  ``uuid5(label, call site, counter)``. Two databases built from the same shared steps
  therefore receive byte-identical identifiers and timestamps for those
  steps, so Database A and Database B' can be compared row-for-row without
  identifier normalization. Steps that exist only in Database B (Event X and
  its consequences) use their own labels, so they can never collide.

No production module is modified; the patches are process-local test seams.
"""
from __future__ import annotations

import importlib.machinery
import json
import os
import sys
import threading
import types
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_KEYRING_FILE = Path(os.environ.get("ISSUE89_KEYRING", "/projects/sandbox/tmp/issue89-keyring.json"))


class _FileKeyring:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def get_password(self, service, username):
        return self._load().get(f"{service}\x00{username}")

    def set_password(self, service, username, password):
        data = self._load()
        data[f"{service}\x00{username}"] = password
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data))

    def delete_password(self, service, username):
        data = self._load()
        data.pop(f"{service}\x00{username}", None)
        self.path.write_text(json.dumps(data))


class KeyringError(Exception):
    pass


class PasswordDeleteError(KeyringError):
    pass


def install_keyring() -> None:
    if "keyring" in sys.modules and getattr(sys.modules["keyring"], "_issue89", False):
        return
    backend = _FileKeyring(_KEYRING_FILE)
    keyring = types.ModuleType("keyring")
    keyring.__spec__ = importlib.machinery.ModuleSpec("keyring", loader=None)
    errors = types.ModuleType("keyring.errors")
    errors.__spec__ = importlib.machinery.ModuleSpec("keyring.errors", loader=None)
    errors.KeyringError = KeyringError
    errors.PasswordDeleteError = PasswordDeleteError
    keyring.errors = errors
    keyring.get_password = backend.get_password
    keyring.set_password = backend.set_password
    keyring.delete_password = backend.delete_password
    keyring._issue89 = True
    sys.modules["keyring"] = keyring
    sys.modules["keyring.errors"] = errors


install_keyring()

_REAL_UUID4 = uuid.uuid4
_REAL_DATETIME = datetime
NAMESPACE = uuid.UUID("8f9a3c1e-0b89-4e89-9a89-000000000089")


class Determinism:
    """Process-global scripted clock + UUID source (thread safe)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.label = None
        self.at = None
        self.uuid_counter = 0
        self.site_counters = {}
        self.tick = 0
        self.install()

    def install(self) -> None:
        import sentriface.models as models

        outer = self

        class _Clock(_REAL_DATETIME):
            @classmethod
            def now(cls, tz=None):  # noqa: D401 - datetime protocol
                return outer.now(tz)

        models.datetime = _Clock
        uuid.uuid4 = self.uuid4

    def now(self, tz=None):
        with self._lock:
            if self.at is None:
                value = _REAL_DATETIME.now(timezone.utc)
            else:
                self.tick += 1
                value = self.at + timedelta(microseconds=self.tick)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    def uuid4(self):
        """UUIDs are keyed by (step label, calling source line, per-line counter).

        Keying by call site keeps identifiers aligned between A and B even when
        a counterfactual step makes extra calls elsewhere (e.g. creating a new
        Person in A where B reuses an existing one)."""
        with self._lock:
            if self.label is None:
                return _REAL_UUID4()
            frame = sys._getframe(1)
            site = f"{Path(frame.f_code.co_filename).name}:{frame.f_lineno}"
            key = (self.label, site)
            self.site_counters[key] = self.site_counters.get(key, 0) + 1
            return uuid.uuid5(NAMESPACE, f"{self.label}#{site}#{self.site_counters[key]}")

    @contextmanager
    def step(self, label: str, at: str):
        with self._lock:
            previous = (self.label, self.at, self.site_counters, self.tick)
            self.label = label
            self.at = _REAL_DATETIME.fromisoformat(at).astimezone(timezone.utc)
            self.site_counters = {}
            self.tick = 0
        try:
            yield self
        finally:
            with self._lock:
                self.label, self.at, self.site_counters, self.tick = previous


DET = Determinism()
