from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import Iterator


@dataclass
class MetricsCollector:
    timings_ms: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        start = perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (perf_counter() - start) * 1000.0
            self.timings_ms[name] = self.timings_ms.get(name, 0.0) + elapsed_ms

    def increment(self, name: str, amount: int = 1) -> None:
        self.counts[name] = self.counts.get(name, 0) + amount

    def snapshot(self) -> dict:
        return {
            "timings_ms": {key: round(value, 3) for key, value in sorted(self.timings_ms.items())},
            "counts": dict(sorted(self.counts.items())),
        }

