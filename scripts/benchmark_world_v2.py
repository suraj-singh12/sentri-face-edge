"""Repeatable read-only performance fixture for the World API v2 contract.

The fixture uses validated normalized rows but bypasses production write services so
one million historical observations can be prepared in practical benchmark time.
It does not benchmark writes and must never be used to create product data.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import tracemalloc
from dataclasses import asdict
from pathlib import Path

from sentriface.models import (
    WorldCollection,
    WorldDetailLevel,
    WorldGraphRequest,
    WorldReadLimits,
)
from sentriface.storage.sqlite_store import SQLiteIdentityStore, _world_graph_v2_read


SCENARIOS = {
    "A": (100, 10_000),
    "B": (10_000, 1_000_000),
}
STAMP = "2026-08-01T00:00:00+00:00"


def _seed(store: SQLiteIdentityStore, people: int, observations: int) -> None:
    with store._connect() as conn:
        # Trigger behavior is covered by product tests. Disabling fixture-time
        # triggers avoids measuring a million synthetic write revisions.
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        ).fetchall():
            conn.execute(f'DROP TRIGGER "{str(row[0]).replace(chr(34), chr(34) * 2)}"')
        conn.execute(
            """INSERT INTO operation_journal(
                   operation_id, operation_type, status, actor, source, context,
                   affected_entities, details, created_at, completed_at
               ) VALUES ('world-benchmark-seed', 'benchmark.fixture', 'COMMITTED',
                         '{}', 'benchmark', '{}', '[]', '{}', ?, ?)""",
            (STAMP, STAMP),
        )
        conn.executemany(
            """INSERT INTO persons(
                   person_id, name, metadata, created_at, enrollment_status, notes,
                   lifecycle_status, identity_status, biometric_status
               ) VALUES (?, ?, '{}', ?, 'enrolled', '', 'ACTIVE', 'IDENTIFIED', 'NO_FACE')""",
            ((f"person-{index:05d}", f"Person {index:05d}", STAMP) for index in range(people)),
        )
        batch = 10_000
        for start in range(0, observations, batch):
            stop = min(start + batch, observations)
            conn.executemany(
                """INSERT INTO observations(
                       observation_id, status, observed_at, location, context, source,
                       created_operation_id, created_at, updated_at, finalized_at
                   ) VALUES (?, 'FINALIZED', ?, ?, '{}', 'benchmark',
                             'world-benchmark-seed', ?, ?, ?)""",
                (
                    (
                        f"event-{index:07d}", STAMP,
                        ("HQ" if index % 10 else None), STAMP, STAMP, STAMP,
                    )
                    for index in range(start, stop)
                ),
            )
            conn.executemany(
                """INSERT INTO observation_participants(
                       observation_id, person_id, source, operation_id, created_at
                   ) VALUES (?, ?, 'benchmark', 'world-benchmark-seed', ?)""",
                (
                    (f"event-{index:07d}", f"person-{index % people:05d}", STAMP)
                    for index in range(start, stop)
                ),
            )


def _measure(store: SQLiteIdentityStore, label: str, request: WorldGraphRequest) -> dict[str, object]:
    query_count = 0

    def trace(statement: str) -> None:
        nonlocal query_count
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            query_count += 1

    with store._connect() as conn:
        conn.set_trace_callback(trace)
        started = time.perf_counter()
        model = _world_graph_v2_read(conn, request)
        latency_ms = (time.perf_counter() - started) * 1000
        conn.set_trace_callback(None)
        # Measure allocation separately so tracemalloc's per-allocation hooks do
        # not distort the reported API latency.
        tracemalloc.start()
        _world_graph_v2_read(conn, request)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    payload_bytes = len(json.dumps(asdict(model), default=str, separators=(",", ":")).encode())
    primary = model.pagination.get(request.collection.value) if request.collection else None
    return {
        "read": label,
        "latency_ms": round(latency_ms, 2),
        "sql_query_count": query_count,
        "peak_python_memory_mb": round(peak / 1024 / 1024, 2),
        "payload_bytes": payload_bytes,
        "returned_counts": model.returned_counts,
        "has_more": primary.has_more if primary else model.has_more,
    }


def run(name: str) -> dict[str, object]:
    people, observations = SCENARIOS[name]
    with tempfile.TemporaryDirectory(prefix=f"world-v2-{name.lower()}-") as temp:
        store = SQLiteIdentityStore(Path(temp) / "benchmark.db", embedding_dim=2)
        store.initialize()
        seed_started = time.perf_counter()
        _seed(store, people, observations)
        seed_seconds = time.perf_counter() - seed_started
        overview = _measure(
            store,
            "WORLD_SCOPE",
            WorldGraphRequest(limits=WorldReadLimits(people=25, clusters=10)),
        )
        event = _measure(
            store,
            "EVENT_PARTICIPANTS",
            WorldGraphRequest(
                detail_level=WorldDetailLevel.EVENT,
                focus_type="EVENT",
                focus_id="event-0000000",
            ),
        )
        person = _measure(
            store,
            "PERSON_EVENTS",
            WorldGraphRequest(
                detail_level=WorldDetailLevel.PERSON,
                focus_type="PERSON",
                focus_id="person-00000",
                collection=WorldCollection.EVENTS,
                limits=WorldReadLimits(events=25),
            ),
        )
        return {
            "dataset": name,
            "people": people,
            "observations": observations,
            "fixture_seed_seconds": round(seed_seconds, 2),
            "database_bytes": store.db_path.stat().st_size,
            "reads": [overview, person, event],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("datasets", nargs="*", choices=SCENARIOS, default=list(SCENARIOS))
    args = parser.parse_args()
    print(json.dumps([run(name) for name in args.datasets], indent=2))


if __name__ == "__main__":
    main()
