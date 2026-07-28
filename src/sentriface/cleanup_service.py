from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


class CleanupService:
    """Durable, conservative cleanup for app-managed files.

    A journal is written before the database mutation that drops references.
    Cleanup then re-checks every live database reference before unlinking.  An
    interrupted cleanup remains in the journal and is retried at startup.
    """

    def __init__(self, data_dir: Path, managed_roots: Iterable[Path]) -> None:
        self.data_dir = data_dir.resolve()
        self.journal_dir = self.data_dir / "cleanup-journal"
        self.managed_roots = tuple(root.resolve() for root in managed_roots)

    def schedule(self, paths: Iterable[str | Path], reason: str) -> Path | None:
        targets = sorted(
            {
                str(resolved)
                for path in paths
                if path
                for resolved in [Path(path).resolve()]
                if self._managed(resolved)
            }
        )
        if not targets:
            return None
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        journal = self.journal_dir / f"{uuid.uuid4()}.json"
        temporary = journal.with_suffix(".tmp")
        payload = {
            "version": 1,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "targets": targets,
        }
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, journal)
        return journal

    def run(
        self,
        journal: Path | None,
        reference_provider: Callable[[], Iterable[str]],
    ) -> bool:
        if journal is None or not journal.exists():
            return True
        payload = json.loads(journal.read_text(encoding="utf-8"))
        protected = {
            Path(path).resolve()
            for path in reference_provider()
            if path
        }
        failures: list[Exception] = []
        for raw_target in payload.get("targets", []):
            target = Path(raw_target).resolve()
            if not self._managed(target):
                continue
            try:
                self._remove_unreferenced(target, protected)
            except OSError as exc:
                failures.append(exc)
        if failures:
            return False
        journal.unlink(missing_ok=True)
        return True

    def retry_all(self, reference_provider: Callable[[], Iterable[str]]) -> int:
        if not self.journal_dir.exists():
            return 0
        completed = 0
        for journal in self.journal_dir.glob("*.json"):
            try:
                completed += int(self.run(journal, reference_provider))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return completed

    def _remove_unreferenced(self, target: Path, protected: set[Path]) -> None:
        if target.is_dir():
            for child in sorted(
                target.rglob("*"),
                key=lambda candidate: len(candidate.parts),
                reverse=True,
            ):
                resolved = child.resolve()
                if child.is_file() and resolved not in protected:
                    child.unlink()
                elif child.is_dir():
                    try:
                        child.rmdir()
                    except OSError:
                        pass
            try:
                target.rmdir()
            except OSError:
                pass
        elif target.exists() and target not in protected:
            target.unlink()

    def _managed(self, path: Path) -> bool:
        return any(path == root or root in path.parents for root in self.managed_roots)
