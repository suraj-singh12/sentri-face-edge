from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, TypeVar

from sentriface.config import RuntimeConfig

T = TypeVar("T")


class BackgroundWorker:
    """Single-worker executor to keep i3-class systems responsive."""

    def __init__(self, config: RuntimeConfig) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=config.max_workers,
            thread_name_prefix="sentriface",
        )

    def submit(self, task: Callable[[], T]) -> Future[T]:
        return self._executor.submit(task)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)

