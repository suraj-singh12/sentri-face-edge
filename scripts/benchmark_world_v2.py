"""Repeatable performance acceptance fixture for the World API v2 contract.

The fixture uses normalized finalized rows but bypasses production write services so
one million historical observations can be prepared in practical benchmark time.
It never creates product data and does not benchmark writes. ``--acceptance`` runs
the P10 freeze matrix; the default keeps the earlier compact smoke benchmark.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import tempfile
import time
import tracemalloc
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from sentriface.models import (
    WorldCollection,
    WorldDetailLevel,
    WorldGraphRequest,
    WorldReadFilter,
    WorldReadLimits,
)
from sentriface.storage.sqlite_store import SQLiteIdentityStore, _world_graph_v2_read


SCENARIOS = {
    "A": (100, 10_000),
    "B": (10_000, 1_000_000),
}
STAMP = "2026-08-01T00:00:00+00:00"
OLD_STAMP = "2025-01-01T00:00:00+00:00"


def _drop_fixture_triggers(conn) -> None:
    for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger'"
    ).fetchall():
        conn.execute(f'DROP TRIGGER "{str(row[0]).replace(chr(34), chr(34) * 2)}"')


def _seed(
    store: SQLiteIdentityStore,
    people: int,
    observations: int,
    *,
    participants_per_event: int = 1,
    relationship_events: int = 0,
    media_events: int = 0,
    merge_count: int = 0,
    correction_count: int = 0,
) -> None:
    with store._connect() as conn:
        _drop_fixture_triggers(conn)
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
                        f"event-{index:07d}",
                        STAMP if index % 2 == 0 else OLD_STAMP,
                        None if index % 10 == 0 else "HQ" if index % 3 else "Field",
                        STAMP, STAMP, STAMP,
                    )
                    for index in range(start, stop)
                ),
            )
            conn.executemany(
                """INSERT INTO observation_participants(
                       observation_id, person_id, source, operation_id, created_at
                   ) VALUES (?, ?, 'benchmark', 'world-benchmark-seed', ?)""",
                (
                    (
                        f"event-{index:07d}",
                        f"person-{(index + participant_offset) % people:05d}",
                        STAMP,
                    )
                    for index in range(start, stop)
                    for participant_offset in range(participants_per_event)
                ),
            )

        evidence_rows = min(relationship_events, observations)
        conn.executemany(
            """INSERT INTO relationship_evidence(
                   evidence_id, evidence_type, source_entity_type, source_entity_id,
                   evidence_revision_id, source_person_id, target_person_id,
                   relationship_type, directionality, active, source,
                   created_operation_id, created_at
               ) VALUES (?, 'CO_OBSERVED', 'OBSERVATION', ?, ?, ?, ?,
                         'CO_OBSERVED_WITH', 'UNDIRECTED', 1, 'benchmark',
                         'world-benchmark-seed', ?)""",
            (
                (
                    f"benchmark-evidence-{index:07d}",
                    f"event-{index:07d}",
                    f"benchmark-evidence-revision-{index:07d}",
                    min(
                        f"person-{index % people:05d}",
                        f"person-{(index + 1) % people:05d}",
                    ),
                    max(
                        f"person-{index % people:05d}",
                        f"person-{(index + 1) % people:05d}",
                    ),
                    STAMP if index % 2 == 0 else OLD_STAMP,
                )
                for index in range(evidence_rows)
            ),
        )
        conn.executemany(
            """INSERT INTO observation_media(
                   observation_id, media_id, media_path, source,
                   operation_id, created_at
               ) VALUES (?, ?, ?, 'benchmark', 'world-benchmark-seed', ?)""",
            (
                (
                    f"event-{index:07d}", f"media-{index:07d}",
                    f"/benchmark/media-{index:07d}.jpg", STAMP,
                )
                for index in range(min(media_events, observations))
            ),
        )

        terminal = f"person-{people - 1:05d}"
        for index in range(min(merge_count, people - 1)):
            conn.execute(
                """UPDATE persons SET canonical_person_id = ?, lifecycle_status = 'MERGED'
                   WHERE person_id = ?""",
                (terminal, f"person-{index:05d}"),
            )
        conn.executemany(
            """INSERT INTO identity_corrections(
                   correction_id, correction_type, observation_id,
                   from_person_id, to_person_id, operation_id, created_at
               ) VALUES (?, 'OBSERVATION_IDENTITY', ?, ?, ?,
                         'world-benchmark-seed', ?)""",
            (
                (
                    f"benchmark-correction-{index:07d}",
                    f"event-{index:07d}",
                    f"person-{index % people:05d}",
                    f"person-{(index + 17) % people:05d}",
                    STAMP,
                )
                for index in range(min(correction_count, observations))
            ),
        )


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _read_once(
    store: SQLiteIdentityStore,
    request: WorldGraphRequest,
    *,
    conn=None,
) -> tuple[object, float, int]:
    selects = 0

    def trace(statement: str) -> None:
        nonlocal selects
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            selects += 1

    def run(active_conn):
        active_conn.set_trace_callback(trace)
        started = time.perf_counter()
        model = _world_graph_v2_read(active_conn, request)
        elapsed = (time.perf_counter() - started) * 1000
        active_conn.set_trace_callback(None)
        return model, elapsed, selects

    if conn is not None:
        return run(conn)
    with store._connect() as active_conn:
        return run(active_conn)


def _measure(
    store: SQLiteIdentityStore,
    label: str,
    request_factory: Callable[[], WorldGraphRequest],
    *,
    cold_repeats: int,
    warm_repeats: int,
    measure_allocation: bool = True,
) -> dict[str, object]:
    cold_latencies: list[float] = []
    model = None
    query_count = 0
    for _ in range(cold_repeats):
        model, elapsed, query_count = _read_once(store, request_factory())
        cold_latencies.append(elapsed)
    warm_latencies: list[float] = []
    with store._connect() as conn:
        for _ in range(warm_repeats):
            model, elapsed, query_count = _read_once(
                store, request_factory(), conn=conn,
            )
            warm_latencies.append(elapsed)
        if measure_allocation:
            tracemalloc.start()
            model = _world_graph_v2_read(conn, request_factory())
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        else:
            peak = None
    payload_bytes = len(
        json.dumps(asdict(model), default=str, separators=(",", ":")).encode()
    )
    return {
        "read": label,
        "cold_definition": "fresh SQLite connection; operating-system file cache not flushed",
        "cold_samples": cold_repeats,
        "warm_samples": warm_repeats,
        "cold_p50_ms": round(statistics.median(cold_latencies), 2),
        "cold_p95_ms": round(_percentile(cold_latencies, 0.95), 2),
        "warm_p50_ms": round(statistics.median(warm_latencies), 2),
        "warm_p95_ms": round(_percentile(warm_latencies, 0.95), 2),
        "sql_statement_count": query_count,
        "peak_python_memory_mb": (
            round(peak / 1024 / 1024, 2) if peak is not None else None
        ),
        "peak_allocation_status": (
            "MEASURED" if peak is not None
            else "NOT_PRACTICAL_DENSE_B_TRACEMALLOC_DISTORTS_RUNTIME"
        ),
        "payload_bytes": payload_bytes,
        "returned_counts": model.returned_counts,
        "primary_collection": model.pagination[model.focus and request_factory().collection.value or request_factory().collection.value].collection if request_factory().collection else None,
        "has_more": model.has_more,
    }


def _cursor_walk(
    store: SQLiteIdentityStore,
    label: str,
    request: WorldGraphRequest,
) -> dict[str, object]:
    pages = 0
    items = 0
    statements = 0
    payload_bytes = 0
    elapsed_ms = 0.0
    cursor = None
    revision = None
    as_of = request.as_of
    expected_total = None
    while True:
        current = WorldGraphRequest(**{
            **request.__dict__, "cursor": cursor, "revision": revision, "as_of": as_of,
        })
        model, elapsed, queries = _read_once(store, current)
        collection = current.collection or {
            WorldDetailLevel.WORLD_SCOPE: WorldCollection.PEOPLE,
            WorldDetailLevel.CLUSTER: WorldCollection.MEMBERS,
            WorldDetailLevel.PERSON: WorldCollection.RELATIONSHIPS,
            WorldDetailLevel.EVENT: WorldCollection.PARTICIPANTS,
            WorldDetailLevel.EVIDENCE: WorldCollection.EVIDENCE,
        }[current.detail_level]
        page = model.pagination[collection.value]
        expected_total = page.total_count if expected_total is None else expected_total
        pages += 1
        items += page.returned_count
        statements += queries
        elapsed_ms += elapsed
        payload_bytes += len(json.dumps(asdict(model), default=str).encode())
        if not page.has_more:
            break
        cursor, revision, as_of = page.next_cursor, model.graph_revision, model.as_of
    return {
        "read": label,
        "pages": pages,
        "returned_items": items,
        "expected_total": expected_total,
        "complete": items == expected_total,
        "elapsed_ms": round(elapsed_ms, 2),
        "sql_statement_count": statements,
        "payload_bytes": payload_bytes,
    }


def _acceptance_profile(
    name: str,
    profile: str,
    *,
    cold_repeats: int,
    warm_repeats: int,
) -> dict[str, object]:
    people, observations = SCENARIOS[name]
    dense = profile == "DENSE_HEAVY"
    measure_allocation = not (name == "B" and dense)
    merge_rows = min(500, max(1, people // 10), max(0, people - 2)) if dense else 0
    correction_rows = min(500, max(1, people // 2), observations) if dense else 0
    with tempfile.TemporaryDirectory(prefix=f"world-v2-{name.lower()}-{profile.lower()}-") as temp:
        store = SQLiteIdentityStore(Path(temp) / "benchmark.db", embedding_dim=2)
        store.initialize()
        seed_started = time.perf_counter()
        _seed(
            store, people, observations,
            participants_per_event=(4 if dense else 1),
            relationship_events=(min(observations, 5_000) if dense else 0),
            media_events=(100 if dense else 0),
            merge_count=merge_rows,
            correction_count=correction_rows,
        )
        seed_seconds = time.perf_counter() - seed_started
        limits = WorldReadLimits(
            people=25, clusters=10, events=25, evidence=25, media=25,
            relationships=25, patterns=10, provenance=25, facets=25,
        )
        reads = [
            _measure(
                store, (
                    "WORLD_SCOPE_UNFILTERED_SPARSE_EVENTS" if not dense
                    else "WORLD_SCOPE_UNFILTERED_DENSE_MULTI_PARTICIPANT_EVENTS"
                ),
                lambda: WorldGraphRequest(limits=limits),
                cold_repeats=cold_repeats, warm_repeats=warm_repeats,
                measure_allocation=measure_allocation,
            ),
            _measure(
                store, "WORLD_SCOPE_DATE_FILTERED",
                lambda: WorldGraphRequest(
                    filters=WorldReadFilter(date_from="2026-01-01T00:00:00+00:00"),
                    limits=limits,
                ),
                cold_repeats=cold_repeats, warm_repeats=warm_repeats,
                measure_allocation=measure_allocation,
            ),
            _measure(
                store, "WORLD_SCOPE_LOCATION_FILTERED",
                lambda: WorldGraphRequest(
                    filters=WorldReadFilter(locations=("HQ",)), limits=limits,
                ),
                cold_repeats=cold_repeats, warm_repeats=warm_repeats,
                measure_allocation=measure_allocation,
            ),
            _measure(
                store, "PERSON_EVENTS",
                lambda: WorldGraphRequest(
                    detail_level=WorldDetailLevel.PERSON,
                    focus_type="PERSON", focus_id=f"person-{people - 1:05d}",
                    collection=WorldCollection.EVENTS, limits=limits,
                ),
                cold_repeats=cold_repeats, warm_repeats=warm_repeats,
                measure_allocation=measure_allocation,
            ),
        ]
        cursor_walks = [
            _cursor_walk(
                store, "LOCATION_FACET_CURSOR_WALK",
                WorldGraphRequest(
                    collection=WorldCollection.LOCATION_FACETS,
                    limits=WorldReadLimits(facets=1),
                ),
            ),
        ]
        if name == "A":
            cursor_walks.insert(0, _cursor_walk(
                store, "PEOPLE_CURSOR_WALK",
                WorldGraphRequest(
                    collection=WorldCollection.PEOPLE,
                    limits=WorldReadLimits(people=100, facets=25),
                ),
            ))

        if dense:
            overview = GraphReadServiceCompat(store).read(WorldGraphRequest(
                collection=WorldCollection.CLUSTERS, limits=limits,
            ))
            cluster_id = overview.clusters[0].cluster_id
            relationship_overview = GraphReadServiceCompat(store).read(WorldGraphRequest(
                collection=WorldCollection.RELATIONSHIPS, limits=limits,
            ))
            relationship_id = relationship_overview.relationships[0].relationship_id
            event_id = "event-0000000"
            event_evidence = GraphReadServiceCompat(store).read(WorldGraphRequest(
                detail_level=WorldDetailLevel.EVENT,
                focus_type="EVENT", focus_id=event_id,
                collection=WorldCollection.EVIDENCE, limits=limits,
            ))
            evidence_id = event_evidence.evidence[0].evidence_id
            dynamic = [
                ("CLUSTER_MEMBERS", lambda: WorldGraphRequest(
                    detail_level=WorldDetailLevel.CLUSTER,
                    focus_type="CLUSTER", focus_id=cluster_id,
                    collection=WorldCollection.MEMBERS, limits=limits,
                )),
                ("PERSON_RELATIONSHIPS_MERGE_HEAVY", lambda: WorldGraphRequest(
                    detail_level=WorldDetailLevel.PERSON,
                    focus_type="PERSON", focus_id=f"person-{people - 1:05d}",
                    collection=WorldCollection.RELATIONSHIPS, limits=limits,
                )),
                ("PERSON_EVENTS_CORRECTION_HEAVY", lambda: WorldGraphRequest(
                    detail_level=WorldDetailLevel.PERSON,
                    focus_type="PERSON", focus_id=f"person-{people - 1:05d}",
                    collection=WorldCollection.EVENTS, limits=limits,
                )),
                ("EVENT_EVIDENCE", lambda: WorldGraphRequest(
                    detail_level=WorldDetailLevel.EVENT,
                    focus_type="EVENT", focus_id=event_id,
                    collection=WorldCollection.EVIDENCE, limits=limits,
                )),
                ("EVENT_MEDIA", lambda: WorldGraphRequest(
                    detail_level=WorldDetailLevel.EVENT,
                    focus_type="EVENT", focus_id=event_id,
                    collection=WorldCollection.MEDIA, limits=limits,
                )),
                ("EVIDENCE_DETAIL", lambda: WorldGraphRequest(
                    detail_level=WorldDetailLevel.EVIDENCE,
                    focus_type="EVIDENCE", focus_id=evidence_id,
                    collection=WorldCollection.EVIDENCE, limits=limits,
                )),
                ("EVIDENCE_MEDIA", lambda: WorldGraphRequest(
                    detail_level=WorldDetailLevel.EVIDENCE,
                    focus_type="EVIDENCE", focus_id=evidence_id,
                    collection=WorldCollection.MEDIA, limits=limits,
                )),
            ]
            reads.extend(
                _measure(
                    store, label, factory,
                    cold_repeats=cold_repeats, warm_repeats=warm_repeats,
                    measure_allocation=measure_allocation,
                )
                for label, factory in dynamic
            )
            if name == "A":
                cursor_walks.append(_cursor_walk(
                    store, "CLUSTER_MEMBER_CURSOR_WALK",
                    WorldGraphRequest(
                        detail_level=WorldDetailLevel.CLUSTER,
                        focus_type="CLUSTER", focus_id=cluster_id,
                        collection=WorldCollection.MEMBERS,
                        limits=WorldReadLimits(people=100),
                    ),
                ))
            cursor_walks.append(_cursor_walk(
                    store, "EVENT_EVIDENCE_CURSOR_WALK",
                    WorldGraphRequest(
                        detail_level=WorldDetailLevel.EVENT,
                        focus_type="EVENT", focus_id=event_id,
                        collection=WorldCollection.EVIDENCE,
                        limits=WorldReadLimits(evidence=1),
                    ),
                ))
        return {
            "dataset": name,
            "profile": profile,
            "people": people,
            "observations": observations,
            "participants_per_event": 4 if dense else 1,
            "relationship_evidence_rows": min(observations, 5_000) if dense else 0,
            "merge_rows": merge_rows,
            "correction_rows": correction_rows,
            "fixture_seed_seconds": round(seed_seconds, 2),
            "database_bytes": store.db_path.stat().st_size,
            "reads": reads,
            "cursor_walks": cursor_walks,
        }


class GraphReadServiceCompat:
    """Tiny benchmark-only adapter that avoids importing the application service."""

    def __init__(self, store: SQLiteIdentityStore) -> None:
        self.store = store

    def read(self, request: WorldGraphRequest):
        with self.store._connect() as conn:
            return _world_graph_v2_read(conn, request)


def run_smoke(name: str) -> dict[str, object]:
    people, observations = SCENARIOS[name]
    with tempfile.TemporaryDirectory(prefix=f"world-v2-{name.lower()}-") as temp:
        store = SQLiteIdentityStore(Path(temp) / "benchmark.db", embedding_dim=2)
        store.initialize()
        seed_started = time.perf_counter()
        _seed(store, people, observations)
        seed_seconds = time.perf_counter() - seed_started
        read = _measure(
            store, "WORLD_SCOPE",
            lambda: WorldGraphRequest(limits=WorldReadLimits(people=25, clusters=10)),
            cold_repeats=1, warm_repeats=1,
        )
        return {
            "dataset": name,
            "people": people,
            "observations": observations,
            "fixture_seed_seconds": round(seed_seconds, 2),
            "database_bytes": store.db_path.stat().st_size,
            "reads": [read],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("datasets", nargs="*", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--acceptance", action="store_true")
    parser.add_argument("--cold-repeats", type=int, default=3)
    parser.add_argument("--warm-repeats", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.cold_repeats < 1 or args.warm_repeats < 1:
        raise SystemExit("repeat counts must be positive")
    if args.acceptance:
        results = [
            _acceptance_profile(
                name, profile,
                cold_repeats=args.cold_repeats,
                warm_repeats=args.warm_repeats,
            )
            for name in args.datasets
            for profile in ("SPARSE", "DENSE_HEAVY")
        ]
    else:
        results = [run_smoke(name) for name in args.datasets]
    payload = json.dumps({
        "benchmark": "P10_WORLD_V2_ACCEPTANCE" if args.acceptance else "P10_WORLD_V2_SMOKE",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": results,
    }, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
