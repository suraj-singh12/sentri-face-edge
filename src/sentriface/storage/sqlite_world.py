"""World read-model queries over the SQLite identity store."""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3

from dataclasses import (
    asdict,
    dataclass,
    replace,
)
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from sentriface.models import (
    WorldCluster,
    WorldCollection,
    WorldDetailLevel,
    WorldDiscovery,
    WorldEvent,
    WorldEvidence,
    WorldExplanation,
    WorldGraphRequest,
    WorldGraphV2ReadModel,
    WorldMediaReference,
    WorldPageState,
    WorldPattern,
    WorldPerson,
    WorldReadFilter,
    WorldReadLimits,
    WorldRelationship,
    utc_now,
)
from sentriface.storage.sqlite_constants import (
    PERSON_LIFECYCLE_STATUSES,
    PERSON_IDENTITY_STATUSES,
    PERSON_BIOMETRIC_STATUSES,
    RELATIONSHIP_EVIDENCE_TYPES,
)
from sentriface.storage.sqlite_helpers import (
    _optional_text,
    _batch_effective_observation_person_ids,
    _graph_allowed_actions,
    _effective_face_assignments,
    _effective_observation_person_ids,
)


_WORLD_FILTERS_VERSION = "world-filters-v1"
_WORLD_CLUSTER_VERSION = "connected-evidence-components-v1"
_WORLD_RANKING_VERSION = "descriptive-salience-v1"
_WORLD_CALCULATION_VERSION = "world-descriptive-v1"
_WORLD_RECENT_WINDOWS = {"LAST_7_DAYS": 7, "LAST_30_DAYS": 30, "LAST_90_DAYS": 90}
_WORLD_MAX_LIMITS = WorldReadLimits(
    people=100, clusters=50, events=100, evidence=100, media=100,
    relationships=200, patterns=25, provenance=200, facets=200,
)


@dataclass(frozen=True)
class _WorldReadContext:
    request: WorldGraphRequest
    revision: str
    as_of: str
    filters: WorldReadFilter
    limits: WorldReadLimits
    level: WorldDetailLevel
    focus_type: str | None
    focus_id: str | None
    collection: WorldCollection
    ranking: str
    scope_fingerprint: str
    offset: int


def _normalize_world_collection(
    level: WorldDetailLevel, collection: WorldCollection | None,
) -> WorldCollection:
    defaults = {
        WorldDetailLevel.WORLD_SCOPE: WorldCollection.PEOPLE,
        WorldDetailLevel.CLUSTER: WorldCollection.MEMBERS,
        WorldDetailLevel.PERSON: WorldCollection.RELATIONSHIPS,
        WorldDetailLevel.EVENT: WorldCollection.PARTICIPANTS,
        WorldDetailLevel.EVIDENCE: WorldCollection.EVIDENCE,
    }
    allowed = {
        WorldDetailLevel.WORLD_SCOPE: {
            WorldCollection.PEOPLE, WorldCollection.CLUSTERS,
            WorldCollection.RELATIONSHIPS, WorldCollection.PATTERNS,
            WorldCollection.LOCATION_FACETS,
            WorldCollection.MOST_FREQUENTLY_SEEN, WorldCollection.MOST_RECENTLY_SEEN,
            WorldCollection.MULTIPLE_LOCATIONS, WorldCollection.LOCATION_SUGGESTIONS,
        },
        WorldDetailLevel.CLUSTER: {WorldCollection.MEMBERS, WorldCollection.RELATIONSHIPS},
        WorldDetailLevel.PERSON: {WorldCollection.RELATIONSHIPS, WorldCollection.EVENTS},
        WorldDetailLevel.EVENT: {
            WorldCollection.PARTICIPANTS, WorldCollection.PROVENANCE,
            WorldCollection.EVIDENCE, WorldCollection.MEDIA,
        },
        WorldDetailLevel.EVIDENCE: {WorldCollection.EVIDENCE, WorldCollection.MEDIA},
    }
    value = collection or defaults[level]
    if value not in allowed[level]:
        raise ValueError(f"Unsupported World collection {value.value} for {level.value}")
    return value


def _world_page_state(
    context: _WorldReadContext,
    collection: WorldCollection,
    total_count: int,
    returned_count: int,
    limit: int,
    *,
    offset: int | None = None,
) -> WorldPageState:
    page_offset = context.offset if offset is None else offset
    if collection != context.collection and returned_count == 0:
        return WorldPageState(
            collection=collection.value,
            total_count=total_count,
            returned_count=0,
            has_more=total_count > 0,
            next_cursor=None,
            truncated=total_count > 0,
            truncation_reason="collection_not_requested",
        )
    has_more = page_offset + returned_count < total_count
    truncation_reason = None
    if has_more:
        truncation_reason = f"backend_limit:{limit}"
    cursor = _world_token(
        "CURSOR", context.revision, context.level.value,
        context.focus_type, context.focus_id, page_offset + returned_count,
        collection=collection.value, as_of=context.as_of,
        scope=context.scope_fingerprint,
    ) if has_more else None
    return WorldPageState(
        collection=collection.value,
        total_count=total_count,
        returned_count=returned_count,
        has_more=has_more,
        next_cursor=cursor,
        truncated=has_more,
        truncation_reason=truncation_reason,
    )


def _world_result(
    context: _WorldReadContext,
    *,
    scope_totals: dict[str, int],
    pagination: dict[str, WorldPageState],
    available_facets: dict[str, object] | None = None,
    people: tuple[WorldPerson, ...] = (),
    clusters: tuple[WorldCluster, ...] = (),
    events: tuple[WorldEvent, ...] = (),
    evidence: tuple[WorldEvidence, ...] = (),
    relationships: tuple[WorldRelationship, ...] = (),
    patterns: tuple[WorldPattern, ...] = (),
    media: tuple[WorldMediaReference, ...] = (),
    discoveries: tuple[WorldDiscovery, ...] = (),
    discovery_context: dict[str, object] | None = None,
) -> WorldGraphV2ReadModel:
    primary = pagination.get(context.collection.value)
    returned_counts = {
        "people": len(people), "clusters": len(clusters), "events": len(events),
        "evidence": len(evidence), "relationships": len(relationships),
        "patterns": len(patterns), "media": len(media),
        "discoveries": len(discoveries),
    }
    facets = {
        "filter_semantics_version": _WORLD_FILTERS_VERSION,
        "ranking_version": _WORLD_RANKING_VERSION,
        "clustering_version": _WORLD_CLUSTER_VERSION,
        "calculation_version": _WORLD_CALCULATION_VERSION,
        "intelligence_extension_version": "world-intelligence-v1",
        **(available_facets or {}),
    }
    return WorldGraphV2ReadModel(
        graph_revision=context.revision,
        as_of=context.as_of,
        generated_at=utc_now(),
        requested_detail_level=context.level,
        returned_detail_level=context.level,
        focus=(
            {"type": context.focus_type, "id": context.focus_id}
            if context.focus_type else None
        ),
        requested_filters=context.request.filters,
        effective_filters=context.filters,
        ranking=context.ranking,
        limits=context.limits,
        scope_totals=scope_totals,
        available_facets=facets,
        returned_counts=returned_counts,
        pagination=pagination,
        truncated=any(page.truncated for page in pagination.values()),
        has_more=primary.has_more if primary else False,
        next_cursor=primary.next_cursor if primary else None,
        expansion_tokens=(),
        people=people, clusters=clusters, events=events, evidence=evidence,
        relationships=relationships, patterns=patterns, media=media,
        discoveries=discoveries, discovery_context=discovery_context or {},
    )


def _world_location_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _world_bounded_state(total: int, returned: int, retrieval: str) -> dict[str, object]:
    return {
        "total_count": total, "returned_count": returned,
        "has_more": returned < total, "truncated": returned < total,
        "retrieval": retrieval,
    }


def _world_recurrence_for_pairs(
    conn: sqlite3.Connection, rows: list[dict], context: _WorldReadContext,
    canonical_map: dict[str, str],
) -> dict[str, dict[str, object]]:
    """Aggregate distinct Encounter support in SQL for a bounded relationship page."""
    pairs = {tuple(sorted((row["source_person_id"], row["target_person_id"]))) for row in rows}
    if not pairs:
        return {}
    _world_register_effective_evidence_function(conn, canonical_map)
    conn.create_function(
        "world_recurrence_pair", 2,
        lambda first, second: int(tuple(sorted((first, second))) in pairs), deterministic=True,
    )
    scope_sql, params = _world_scope_sql(context.filters, evidence=False)
    if context.filters.relationship_type:
        scope_sql += " AND e.relationship_type IN (%s)" % ",".join("?" for _ in context.filters.relationship_type)
        params.extend(context.filters.relationship_type)
    source = "world_effective_evidence_person(e.evidence_type,e.source_entity_type,e.source_entity_id,e.source_person_id)"
    target = "world_effective_evidence_person(e.evidence_type,e.source_entity_type,e.source_entity_id,e.target_person_id)"
    support = conn.execute(
        f"""WITH encounters AS (
            SELECT DISTINCT MIN({source}, {target}) AS first_person,
                   MAX({source}, {target}) AS second_person,
                   o.observation_id AS event_id,
                   COALESCE(o.observed_at, o.created_at) AS occurred_at, o.location
            FROM relationship_evidence e JOIN effective_observations o ON o.observation_id = e.source_entity_id
            WHERE e.active = 1 AND e.evidence_type = 'CO_OBSERVED'
              AND e.source_entity_type = 'OBSERVATION' AND {scope_sql}
              AND world_recurrence_pair({source}, {target}) = 1
        ), numbered AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY first_person, second_person ORDER BY world_time(occurred_at) DESC, event_id) AS position,
                   COUNT(*) OVER (PARTITION BY first_person, second_person) AS total,
                   MIN(world_occurrence(occurred_at) COLLATE world_instant) OVER (PARTITION BY first_person, second_person) AS first_at,
                   MAX(world_occurrence(occurred_at) COLLATE world_instant) OVER (PARTITION BY first_person, second_person) AS latest_at
            FROM encounters
        ) SELECT * FROM numbered WHERE position <= ? ORDER BY first_person, second_person, position""",
        [*params, context.limits.events],
    ).fetchall()
    result = {}
    for row in support:
        relationship_id = f"relationship:{row['first_person']}:{row['second_person']}"
        item = result.setdefault(relationship_id, {
            "count": int(row["total"]), "first_occurrence_at": row["first_at"],
            "latest_occurrence_at": row["latest_at"], "supporting_encounters": [],
        })
        item["supporting_encounters"].append({
            "event_id": str(row["event_id"]), "occurred_at": str(row["occurred_at"]), "location": row["location"],
        })
    return result


def _world_location_suggestions_read(
    conn: sqlite3.Connection, context: _WorldReadContext,
) -> WorldGraphV2ReadModel:
    query_text = _world_location_text(context.request.location_query)
    query = query_text.casefold()
    rows = []
    total = 0
    if len(query_text) >= 3:
        conn.create_function("world_location_text", 1, _world_location_text, deterministic=True)
        conn.create_function("world_location_key", 1, lambda value: _world_location_text(value).casefold(), deterministic=True)
        rows = conn.execute(
            """WITH locations AS (
                SELECT world_location_key(location) AS key,
                       MIN(world_location_text(location)) AS value,
                       COUNT(*) AS event_count
                FROM effective_observations
                WHERE status = 'FINALIZED' AND world_location_key(location) <> ''
                  AND INSTR(world_location_key(location), ?) > 0
                GROUP BY world_location_key(location)
            ) SELECT *, COUNT(*) OVER () AS total FROM locations
              ORDER BY key, value LIMIT ? OFFSET ?""",
            (query, context.limits.facets, context.offset),
        ).fetchall()
        total = int(rows[0]["total"]) if rows else 0
    values = [{"value": str(row["value"]), "count": int(row["event_count"])} for row in rows]
    return _world_result(
        context, scope_totals={"locations": total},
        pagination={context.collection.value: _world_page_state(
            context, context.collection, total, len(values), context.limits.facets,
        )},
        available_facets={"locations": values, "minimum_query_characters": 3},
    )


def _world_has_event_scope(filters: WorldReadFilter) -> bool:
    return bool(
        filters.date_from or filters.date_to or filters.locations
        or filters.missing_location != "INCLUDE"
    )


def _world_degree(
    people_rows: dict[str, sqlite3.Row], relationships: list[dict],
) -> dict[str, dict[str, int]]:
    degree = {
        person_id: {"relationships": 0, "evidence": 0} for person_id in people_rows
    }
    for item in relationships:
        if not item.get("qualifies_for_cluster", True):
            continue
        for person_id in (item["source_person_id"], item["target_person_id"]):
            if person_id in degree:
                degree[person_id]["relationships"] += 1
                degree[person_id]["evidence"] += int(item["evidence_count"])
    return degree


def _world_explanation_scope(context: _WorldReadContext) -> dict[str, object]:
    return {
        "as_of": context.as_of,
        "date_from": context.filters.date_from,
        "date_to": context.filters.date_to,
        "recent_activity": context.filters.recent_activity,
        "locations": list(context.filters.locations),
        "missing_location": context.filters.missing_location,
        "filter_semantics_version": _WORLD_FILTERS_VERSION,
    }


def _normalize_world_limits(value: WorldReadLimits) -> WorldReadLimits:
    values = {}
    for name in WorldReadLimits.__dataclass_fields__:
        requested = int(getattr(value, name))
        if requested < 1:
            raise ValueError(f"World {name} limit must be at least 1")
        values[name] = min(requested, int(getattr(_WORLD_MAX_LIMITS, name)))
    return WorldReadLimits(**values)


def _world_datetime(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid World {label}: {value}") from exc


def _world_stored_datetime(value: str) -> datetime | None:
    """Legacy storage accepts arbitrary text; unknown time is not creation time.

    Only malformed/out-of-range source dates are tolerated. Request validation
    continues to call the strict parser directly.
    """
    try:
        return _world_datetime(value, "occurrence")
    except ValueError:
        return None


def _normalize_world_filters(value: WorldReadFilter, as_of: datetime) -> WorldReadFilter:
    def choices(items: tuple[str, ...], *, upper: bool = False) -> tuple[str, ...]:
        result = {(str(item).strip().upper() if upper else str(item).strip()) for item in items if str(item).strip()}
        return tuple(sorted(result, key=str.casefold))

    recent = _optional_text(value.recent_activity)
    if recent:
        recent = recent.upper()
        if recent not in _WORLD_RECENT_WINDOWS:
            raise ValueError(f"Unsupported recent activity preset: {recent}")
        if value.date_from or value.date_to:
            raise ValueError("Recent activity cannot be combined with absolute World dates")
        date_from = (as_of - timedelta(days=_WORLD_RECENT_WINDOWS[recent])).isoformat()
        date_to = as_of.isoformat()
    else:
        date_from, date_to = _optional_text(value.date_from), _optional_text(value.date_to)
        if date_from:
            start = _world_datetime(date_from, "date_from")
            date_from = start.isoformat()
        if date_to:
            end = _world_datetime(date_to, "date_to")
            if len(str(value.date_to).strip()) == 10:
                end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
            date_to = end.isoformat()
    if date_from and date_to and _world_datetime(date_from, "date_from") > _world_datetime(date_to, "date_to"):
        raise ValueError("World date_from must be earlier than or equal to date_to")
    missing = str(value.missing_location or "INCLUDE").strip().upper()
    if missing not in {"INCLUDE", "EXCLUDE", "ONLY"}:
        raise ValueError(f"Unsupported missing-location behavior: {missing}")
    lifecycle = choices(value.lifecycle, upper=True)
    identity = choices(value.identity_state, upper=True)
    biometric = choices(value.biometric_state, upper=True)
    evidence = choices(value.evidence_type, upper=True)
    unsupported = set(lifecycle) - PERSON_LIFECYCLE_STATUSES
    if unsupported:
        raise ValueError(f"Unsupported World lifecycle filter: {sorted(unsupported)[0]}")
    if set(identity) - PERSON_IDENTITY_STATUSES:
        raise ValueError("Unsupported World identity-state filter")
    if set(biometric) - PERSON_BIOMETRIC_STATUSES:
        raise ValueError("Unsupported World biometric-state filter")
    if set(evidence) - RELATIONSHIP_EVIDENCE_TYPES:
        raise ValueError("Unsupported World evidence-type filter")
    if value.min_relationship_strength is not None and (
        type(value.min_relationship_strength) is not int or value.min_relationship_strength < 1
    ):
        raise ValueError("World minimum relationship strength must be a positive integer")
    activity = choices(value.activity, upper=True)
    if set(activity) - {"NONE", "LOW", "MEDIUM", "HIGH"}:
        raise ValueError("Unsupported World activity filter")
    pattern_type = choices(value.pattern_type, upper=True)
    if set(pattern_type) - {"DATA_QUALITY"}:
        raise ValueError("Unsupported World pattern-type filter")
    return WorldReadFilter(
        date_from=date_from, date_to=date_to, recent_activity=recent,
        locations=choices(value.locations), missing_location=missing,
        lifecycle=lifecycle, identity_state=identity, biometric_state=biometric,
        country=choices(value.country), rank=choices(value.rank), priority=choices(value.priority),
        evidence_type=evidence, relationship_type=choices(value.relationship_type, upper=True),
        min_relationship_strength=(int(value.min_relationship_strength) if value.min_relationship_strength is not None else None),
        activity=activity, pattern_type=pattern_type,
    )


def _normalize_world_focus(
    level: WorldDetailLevel, focus_type: str | None, focus_id: str | None,
) -> tuple[str | None, str | None]:
    if level == WorldDetailLevel.WORLD_SCOPE:
        if focus_type or focus_id:
            raise ValueError("WORLD_SCOPE does not accept focus")
        return None, None
    expected = {
        WorldDetailLevel.CLUSTER: {"CLUSTER"},
        WorldDetailLevel.PERSON: {"PERSON"},
        WorldDetailLevel.EVENT: {"EVENT"},
        WorldDetailLevel.EVIDENCE: {"RELATIONSHIP", "EVENT", "PERSON", "EVIDENCE"},
    }[level]
    normalized_type = str(focus_type or "").strip().upper()
    normalized_id = str(focus_id or "").strip()
    if normalized_type not in expected or not normalized_id:
        raise ValueError(f"{level.value} requires a typed focus")
    return normalized_type, normalized_id


def _world_people_scope(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    canonical_map: dict[str, str] | None = None,
) -> tuple[
    dict[str, sqlite3.Row], dict[str, tuple[str, ...]], dict[str, str],
]:
    rows = conn.execute(
        """SELECT person_id, name, metadata, lifecycle_status,
                  canonical_person_id, identity_status, biometric_status
           FROM persons ORDER BY person_id"""
    ).fetchall()
    resolved = canonical_map or _world_canonical_map(conn, rows)
    aliases: dict[str, list[str]] = {}
    canonical_rows: dict[str, sqlite3.Row] = {}
    for row in rows:
        raw_id = str(row["person_id"])
        canonical_id = resolved[raw_id]
        if raw_id != canonical_id:
            aliases.setdefault(canonical_id, []).append(raw_id)
            continue
        metadata = json.loads(row["metadata"] or "{}")
        def match(field: str, choices: tuple[str, ...]) -> bool:
            return not choices or str(metadata.get(field) or "").casefold() in {item.casefold() for item in choices}
        if filters.lifecycle and str(row["lifecycle_status"]) not in filters.lifecycle:
            continue
        if filters.identity_state and str(row["identity_status"]) not in filters.identity_state:
            continue
        if filters.biometric_state and str(row["biometric_status"]) not in filters.biometric_state:
            continue
        if not (match("country", filters.country) and match("rank", filters.rank) and match("importance", filters.priority)):
            continue
        canonical_rows[canonical_id] = row
    return (
        canonical_rows,
        {key: tuple(sorted(value)) for key, value in aliases.items()},
        resolved,
    )


def _world_canonical_map(
    conn: sqlite3.Connection, rows: list[sqlite3.Row] | None = None,
) -> dict[str, str]:
    person_rows = rows or conn.execute(
        "SELECT person_id, canonical_person_id FROM persons ORDER BY person_id"
    ).fetchall()
    parent = {
        str(row["person_id"]): (
            str(row["canonical_person_id"]) if row["canonical_person_id"] else None
        ) for row in person_rows
    }
    resolved: dict[str, str] = {}
    for person_id in parent:
        chain: list[str] = []
        current = person_id
        while parent.get(current):
            if current in chain:
                raise RuntimeError(f"Canonical identity cycle detected: {person_id}")
            chain.append(current)
            current = str(parent[current])
        if current not in parent:
            raise RuntimeError(f"Canonical identity target is unavailable: {current}")
        resolved[person_id] = current
        for alias in chain:
            resolved[alias] = current
    return resolved


def _world_scope_sql(filters: WorldReadFilter, *, evidence: bool) -> tuple[str, list[object]]:
    clauses = ["o.status = 'FINALIZED'"]
    params: list[object] = []
    occurrence = "COALESCE(o.observed_at, o.created_at)"
    if filters.date_from:
        clauses.append(f"world_time({occurrence}) >= world_time(?)")
        params.append(filters.date_from)
    if filters.date_to:
        clauses.append(f"world_time({occurrence}) <= world_time(?)")
        params.append(filters.date_to)
    if filters.locations:
        clauses.append("LOWER(TRIM(COALESCE(o.location, ''))) IN (%s)" % ",".join("?" for _ in filters.locations))
        params.extend(item.casefold() for item in filters.locations)
    if filters.missing_location == "EXCLUDE":
        clauses.append("TRIM(COALESCE(o.location, '')) <> ''")
    elif filters.missing_location == "ONLY":
        clauses.append("TRIM(COALESCE(o.location, '')) = ''")
    if evidence and filters.evidence_type:
        clauses.append("e.evidence_type IN (%s)" % ",".join("?" for _ in filters.evidence_type))
        params.extend(filters.evidence_type)
    if evidence and filters.relationship_type:
        clauses.append("e.relationship_type IN (%s)" % ",".join("?" for _ in filters.relationship_type))
        params.extend(filters.relationship_type)
    return " AND ".join(clauses), params


def _world_register_effective_evidence_function(
    conn: sqlite3.Connection,
    canonical_map: dict[str, str],
):
    """Match graph projection semantics for regenerated active evidence.

    Corrections retire and regenerate co-observation evidence atomically. Replaying
    old identity corrections over its current endpoints loses explicitly re-added
    participants and misinterprets valid forward/reverse histories as cycles.
    """
    def effective_person(
        evidence_type: object,
        source_entity_type: object,
        source_entity_id: object,
        raw_person_id: object,
    ) -> str:
        return canonical_map[str(raw_person_id)]

    conn.create_function(
        "world_effective_evidence_person", 4, effective_person, deterministic=True,
    )
    return effective_person


def _world_relationship_scope(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    eligible_ids: set[str],
    *,
    canonical_map: dict[str, str] | None = None,
    focus_person_id: str | None = None,
    include_below_threshold: bool = False,
) -> list[dict]:
    resolved = canonical_map or _world_canonical_map(conn)
    evidence_person = _world_register_effective_evidence_function(conn, resolved)
    scope_sql, scope_params = _world_scope_sql(filters, evidence=False)
    evidence_clauses: list[str] = []
    evidence_params: list[object] = []
    if filters.evidence_type:
        evidence_clauses.append("e.evidence_type IN (%s)" % ",".join("?" for _ in filters.evidence_type))
        evidence_params.extend(filters.evidence_type)
    if filters.relationship_type:
        evidence_clauses.append("e.relationship_type IN (%s)" % ",".join("?" for _ in filters.relationship_type))
        evidence_params.extend(filters.relationship_type)
    if focus_person_id:
        evidence_clauses.append(
            "(world_effective_evidence_person(e.evidence_type, e.source_entity_type, "
            "e.source_entity_id, e.source_person_id) = ? OR "
            "world_effective_evidence_person(e.evidence_type, e.source_entity_type, "
            "e.source_entity_id, e.target_person_id) = ?)"
        )
        evidence_params.extend([focus_person_id, focus_person_id])
    non_observation_clauses = ["e.evidence_type <> 'CO_OBSERVED'"]
    non_observation_params: list[object] = []
    if filters.date_from:
        non_observation_clauses.append("world_time(e.created_at) >= world_time(?)")
        non_observation_params.append(filters.date_from)
    if filters.date_to:
        non_observation_clauses.append("world_time(e.created_at) <= world_time(?)")
        non_observation_params.append(filters.date_to)
    non_observation_allowed = not filters.locations and filters.missing_location != "EXCLUDE"
    evidence_prefix = (" AND " + " AND ".join(evidence_clauses)) if evidence_clauses else ""
    rows = conn.execute(
        f"""
        SELECT e.source_person_id, e.target_person_id, e.evidence_type,
               e.source_entity_type, e.source_entity_id,
               e.relationship_type, e.directionality, o.location,
               COUNT(*) AS evidence_count,
               MIN(world_occurrence(CASE WHEN e.evidence_type = 'CO_OBSERVED' THEN COALESCE(o.observed_at, o.created_at) ELSE e.created_at END) COLLATE world_instant) AS first_at,
               MAX(world_occurrence(CASE WHEN e.evidence_type = 'CO_OBSERVED' THEN COALESCE(o.observed_at, o.created_at) ELSE e.created_at END) COLLATE world_instant) AS last_at
        FROM relationship_evidence e
        LEFT JOIN effective_observations o ON e.evidence_type = 'CO_OBSERVED'
             AND e.source_entity_type = 'OBSERVATION' AND o.observation_id = e.source_entity_id
        WHERE e.active = 1{evidence_prefix} AND (
            (e.evidence_type = 'CO_OBSERVED' AND {scope_sql})
            OR ({' AND '.join(non_observation_clauses)} AND ? = 1)
        )
        GROUP BY e.source_person_id, e.target_person_id, e.evidence_type,
                 e.source_entity_type, e.source_entity_id,
                 e.relationship_type, e.directionality
        """,
        [*evidence_params, *scope_params, *non_observation_params, int(non_observation_allowed)],
    ).fetchall()
    aggregates: dict[tuple[str, str], dict] = {}
    for row in rows:
        source = evidence_person(
            row["evidence_type"], row["source_entity_type"],
            row["source_entity_id"], row["source_person_id"],
        )
        target = evidence_person(
            row["evidence_type"], row["source_entity_type"],
            row["source_entity_id"], row["target_person_id"],
        )
        if source == target or source not in eligible_ids or target not in eligible_ids:
            continue
        pair = tuple(sorted((source, target)))
        item = aggregates.setdefault(pair, {
            "relationship_id": f"relationship:{pair[0]}:{pair[1]}",
            "source_person_id": pair[0], "target_person_id": pair[1],
            "directionality": "UNDIRECTED", "directions": {}, "relationship_types": set(),
            "note_directions": {},
            "evidence_type_counts": {}, "evidence_count": 0,
            "first_occurrence_at": None, "last_occurrence_at": None,
        })
        count = int(row["evidence_count"])
        item["evidence_count"] += count
        item["evidence_type_counts"][str(row["evidence_type"])] = item["evidence_type_counts"].get(str(row["evidence_type"]), 0) + count
        item["relationship_types"].add(str(row["relationship_type"]))
        direction_key = (
            "UNDIRECTED" if str(row["directionality"]) == "UNDIRECTED"
            else f"{source}->{target}"
        )
        item["directions"][direction_key] = (
            item["directions"].get(direction_key, 0) + count
        )
        if row["evidence_type"] == "NOTE_REFERENCE":
            item["note_directions"][direction_key] = item["note_directions"].get(direction_key, 0) + count
        if row["first_at"] is not None:
            item["first_occurrence_at"] = min(item["first_occurrence_at"] or row["first_at"], row["first_at"], key=lambda value: _world_datetime(value, "occurrence"))
        if row["last_at"] is not None:
            item["last_occurrence_at"] = max(item["last_occurrence_at"] or row["last_at"], row["last_at"], key=lambda value: _world_datetime(value, "occurrence"))
    result = []
    for item in aggregates.values():
        if not item["evidence_count"]:
            continue
        item["qualifies_for_cluster"] = item["evidence_count"] >= (filters.min_relationship_strength or 1)
        if not item["qualifies_for_cluster"] and not include_below_threshold:
            continue
        item["relationship_types"] = tuple(sorted(item["relationship_types"]))
        directions = item.pop("directions")
        if set(directions) == {"UNDIRECTED"}:
            item["directionality"] = "UNDIRECTED"
        elif "UNDIRECTED" not in directions and len(directions) == 1:
            item["source_person_id"], item["target_person_id"] = next(iter(directions)).split("->", 1)
            item["directionality"] = "DIRECTED"
        else:
            item["directionality"] = "MIXED"
        item["direction_counts"] = dict(sorted(directions.items()))
        result.append(item)
    return sorted(result, key=lambda item: (-item["evidence_count"], item["relationship_id"]))


def _world_scoped_event_people(conn: sqlite3.Connection, filters: WorldReadFilter) -> set[str]:
    scope, params = _world_scope_sql(filters, evidence=False)
    cte = _world_effective_participant_cte(conn, scope)
    return {str(row[0]) for row in conn.execute(f"{cte} SELECT DISTINCT person_id FROM effective", params)}


def _world_activity_counts(
    conn: sqlite3.Connection, eligible_ids: set[str], filters: WorldReadFilter,
) -> dict[str, int]:
    scope, params = _world_scope_sql(filters, evidence=False)
    cte = _world_effective_participant_cte(conn, scope)
    return {str(row[0]): int(row[1]) for row in conn.execute(
        f"{cte} SELECT person_id, COUNT(*) FROM effective GROUP BY person_id", params,
    ) if str(row[0]) in eligible_ids}


def _world_full_scope_event_statistics(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    canonical_map: dict[str, str],
    *,
    location_offset: int = 0,
    location_limit: int = 100,
) -> dict[str, object]:
    """Fast exact aggregation when every terminal canonical identity is eligible."""
    scope_sql, params = _world_scope_sql(filters, evidence=False)
    conn.create_aggregate(
        "world_overview_statistics", 3, _WorldOverviewStatisticsAggregate,
    )
    if not _world_use_participant_first_overview(conn, filters):
        aggregate_from = """effective_observations o
            CROSS JOIN observation_participants p"""
    else:
        aggregate_from = """observation_participants p
                 INDEXED BY sqlite_autoindex_observation_participants_1
            CROSS JOIN effective_observations o"""
    row = conn.execute(
        f"""SELECT world_overview_statistics(
                       p.person_id, o.observation_id, o.location
                   ) AS payload
            FROM {aggregate_from}
            WHERE {scope_sql} AND p.observation_id = o.observation_id""",
        params,
    ).fetchone()
    payload = json.loads(str(row["payload"] or "{}"))
    activity: dict[str, int] = {}
    for raw_person_id, count in payload.get("activity", {}).items():
        canonical_id = canonical_map[str(raw_person_id)]
        activity[canonical_id] = (
            activity.get(canonical_id, 0) + int(count)
        )
    location_counts: dict[str, dict[str, object]] = {}
    for stored_location, event_count in payload.get("locations", {}).items():
        raw_location = str(stored_location or "").strip()
        location_key = raw_location.casefold()
        item = location_counts.setdefault(
            location_key,
            {"value": raw_location or "MISSING", "count": 0},
        )
        item["count"] = int(item["count"]) + int(event_count)
        if raw_location and raw_location < str(item["value"]):
            item["value"] = raw_location
    locations = sorted(
        location_counts.values(),
        key=lambda item: (-int(item["count"]), str(item["value"]).casefold()),
    )
    total = sum(int(item["count"]) for item in locations)
    missing = next(
        (int(item["count"]) for item in locations if item["value"] == "MISSING"), 0,
    )

    correction_sources = {
        str(row[0]) for row in conn.execute(
            """SELECT DISTINCT from_person_id FROM identity_corrections
               WHERE correction_type IN ('OBSERVATION_IDENTITY', 'FACE_ASSIGNMENT')
               UNION SELECT person_id FROM encounter_participant_revisions"""
        ).fetchall()
    }
    affected_ids = {
        raw_id for raw_id, canonical_id in canonical_map.items()
        if raw_id != canonical_id
    } | correction_sources
    if not affected_ids:
        return {
            "activity": activity,
            "locations": locations[location_offset:location_offset + location_limit],
            "location_total_count": len(locations),
            "total": total, "missing": missing,
        }

    candidates = _world_register_effective_person_function(conn, canonical_map)
    del candidates
    conn.create_function(
        "world_canonical_person", 1,
        lambda person_id: canonical_map[str(person_id)], deterministic=True,
    )
    placeholders = ",".join("?" for _ in affected_ids)
    effective_adjustments = " UNION ALL ".join(
        f"""SELECT 'EFFECTIVE', world_effective_person(p.observation_id, p.person_id),
                   COUNT(DISTINCT p.observation_id)
            FROM {source} p JOIN affected_events a USING(observation_id)
            GROUP BY world_effective_person(p.observation_id, p.person_id)"""
        for source in _world_participant_sources(conn)
    )
    adjustments = conn.execute(
        f"""WITH affected_events AS MATERIALIZED (
                SELECT DISTINCT p.observation_id
                FROM observation_participants p
                     INDEXED BY idx_observation_participants_person
                CROSS JOIN effective_observations o
                WHERE p.person_id IN ({placeholders})
                  AND o.observation_id = p.observation_id
                  AND {scope_sql}
            )
            SELECT 'NAIVE' AS kind, world_canonical_person(p.person_id) AS person_id,
                   COUNT(*) AS count
            FROM observation_participants p JOIN affected_events a USING(observation_id)
            GROUP BY world_canonical_person(p.person_id)
            UNION ALL
            {effective_adjustments}""",
        [*sorted(affected_ids), *params],
    ).fetchall()
    for row in adjustments:
        person_id, count = str(row["person_id"]), int(row["count"])
        if not person_id:
            continue
        activity[person_id] = activity.get(person_id, 0) + (
            count if str(row["kind"]) == "EFFECTIVE" else -count
        )
    return {
        "activity": activity,
        "locations": locations[location_offset:location_offset + location_limit],
        "location_total_count": len(locations),
        "total": total, "missing": missing,
    }


def _world_use_participant_first_overview(
    conn: sqlite3.Connection, filters: WorldReadFilter,
) -> bool:
    """Use the sequential participant scan only for an unrestricted sparse scope."""
    if _world_has_event_scope(filters):
        return False
    multi_participant = conn.execute(
        """SELECT 1
           FROM observation_participants
                INDEXED BY sqlite_autoindex_observation_participants_1
           GROUP BY observation_id
           HAVING COUNT(*) > 1
           LIMIT 1"""
    ).fetchone()
    return multi_participant is None


class _WorldOverviewStatisticsAggregate:
    """One-pass activity/location aggregation over observation-grouped input."""

    def __init__(self) -> None:
        self.activity: dict[str, int] = {}
        self.locations: dict[str, int] = {}
        self.last_observation_id: str | None = None

    def step(
        self, person_id: object, observation_id: object, location: object,
    ) -> None:
        raw_person_id = str(person_id)
        self.activity[raw_person_id] = self.activity.get(raw_person_id, 0) + 1
        current_observation_id = str(observation_id)
        # Both supported plans keep all participants for an observation
        # consecutive: observations are the outer loop for filtered scopes,
        # while the unfiltered plan scans the (observation_id, person_id)
        # participant primary-key index in order.
        if current_observation_id != self.last_observation_id:
            stored_location = "" if location is None else str(location)
            self.locations[stored_location] = self.locations.get(stored_location, 0) + 1
            self.last_observation_id = current_observation_id

    def finalize(self) -> str:
        return json.dumps(
            {"activity": self.activity, "locations": self.locations},
            sort_keys=True, separators=(",", ":"),
        )


def _world_activity_bucket(count: int) -> str:
    if count == 0:
        return "NONE"
    if count <= 2:
        return "LOW"
    if count <= 9:
        return "MEDIUM"
    return "HIGH"


def _world_rank_people(
    rows: dict[str, sqlite3.Row], activity: dict[str, int], degree: dict[str, dict[str, int]], ranking: str,
) -> list[str]:
    def priority_value(row: sqlite3.Row) -> int:
        metadata = json.loads(row["metadata"] or "{}")
        return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(
            str(metadata.get("importance") or "").casefold(), 0,
        )
    def key(person_id: str):
        row = rows[person_id]
        if ranking == "DISPLAY_NAME":
            return (str(row["name"]).casefold(), person_id)
        if ranking == "RECENT_ACTIVITY":
            return (-activity.get(person_id, 0), str(row["name"]).casefold(), person_id)
        if ranking == "EVIDENCE_COUNT":
            return (-degree.get(person_id, {}).get("evidence", 0), str(row["name"]).casefold(), person_id)
        return (
            -priority_value(row), -activity.get(person_id, 0),
            -degree.get(person_id, {}).get("evidence", 0),
            str(row["name"]).casefold(), person_id,
        )
    return sorted(rows, key=key)


def _world_person(
    person_id: str,
    row: sqlite3.Row,
    aliases: tuple[str, ...],
    event_count: int | None,
    degree: dict[str, int] | None,
    context: _WorldReadContext,
    *,
    rank_position: int | None = None,
    selected_by_focus: bool = False,
) -> WorldPerson:
    metadata = json.loads(row["metadata"] or "{}")
    priority = metadata.get("importance")
    analytics_loaded = event_count is not None and degree is not None
    relationships = degree.get("relationships", 0) if degree is not None else None
    evidence_records = degree.get("evidence", 0) if degree is not None else None
    factors = (
        {"factor": "explicit_priority", "value": priority, "kind": "OPERATOR_ASSERTED"},
        {"factor": "finalized_event_count", "value": event_count, "kind": "MEASURED" if analytics_loaded else "NOT_LOADED"},
        {"factor": "relationship_count", "value": relationships, "kind": "MEASURED" if analytics_loaded else "NOT_LOADED"},
        {"factor": "evidence_count", "value": evidence_records, "kind": "MEASURED" if analytics_loaded else "NOT_LOADED"},
    )
    ranking_reasons = {
        "SALIENCE": "Ordered by operator priority, finalized events, evidence count, then display name.",
        "RECENT_ACTIVITY": "Ordered by finalized-event count in the explicit effective time window.",
        "EVIDENCE_COUNT": "Ordered by active authoritative relationship-evidence count in scope.",
        "DISPLAY_NAME": "Ordered by normalized display name.",
    }
    ranking_reason = (
        "Requested person focus; global ranking was not used to select this object."
        if selected_by_focus else ranking_reasons[context.ranking]
    )
    ranking_payload = {
        "applied": not selected_by_focus,
        "intent": context.ranking,
        "rank_position": rank_position,
        "ranking_reason": ranking_reason,
        "metrics": {
            "finalized_events": event_count,
            "relationships": relationships,
            "evidence_records": evidence_records,
            "operator_priority": priority,
        },
        "metrics_state": "LOADED" if analytics_loaded else "NOT_LOADED",
        "deterministic_tie_break": (
            ["operator_priority", "finalized_events", "evidence_records", "display_name", "canonical_person_id"]
            if context.ranking == "SALIENCE" else
            ["finalized_events", "display_name", "canonical_person_id"]
            if context.ranking == "RECENT_ACTIVITY" else
            ["evidence_records", "display_name", "canonical_person_id"]
            if context.ranking == "EVIDENCE_COUNT" else
            ["display_name", "canonical_person_id"]
        ),
        "value_semantics": "deterministic_ordering_not_confidence",
    }
    return WorldPerson(
        canonical_person_id=person_id,
        historical_person_ids=aliases,
        display_name=str(row["name"]),
        lifecycle_state=str(row["lifecycle_status"]),
        identity_state=str(row["identity_status"]),
        biometric_state=str(row["biometric_status"]),
        display={"country": metadata.get("country"), "rank": metadata.get("rank")},
        intelligence_summary={
            "relationship_count": relationships,
            "relationship_evidence_count": evidence_records,
            "activity_bucket": (_world_activity_bucket(event_count) if event_count is not None else None),
        },
        importance_indicators=factors,
        activity_summary={
            "finalized_event_count": event_count,
            "activity_bucket": (_world_activity_bucket(event_count) if event_count is not None else None),
            "state": "LOADED" if analytics_loaded else "NOT_LOADED",
        },
        ranking=ranking_payload,
        allowed_actions=_graph_allowed_actions(str(row["lifecycle_status"])),
        explanation=WorldExplanation(
            summary=ranking_reason,
            basis_type="PERSON_RANKING",
            factual_factors=factors,
            derived_factors=({"factor": "ranking_intent", "value": context.ranking},),
            calculation_version=_WORLD_RANKING_VERSION,
            evidence_count=(evidence_records if analytics_loaded else None),
            evidence_expansion_token=None,
            calculation_scope=_world_explanation_scope(context),
            strongest_factors=factors[:3],
            method="deterministic_lexicographic_ordering",
            limitations=("No probabilistic importance or identity confidence is calculated.",),
        ),
        analytics_state="LOADED" if analytics_loaded else "NOT_LOADED",
    )


def _world_clusters(
    revision: str,
    scope_fingerprint: str,
    relationships: list[dict],
    people_rows: dict[str, sqlite3.Row],
    activity: dict[str, int],
    preview_limit: int,
    context: _WorldReadContext,
) -> list[WorldCluster]:
    adjacency: dict[str, set[str]] = {}
    by_pair = {}
    for item in relationships:
        if not item.get("qualifies_for_cluster", True):
            continue
        source, target = item["source_person_id"], item["target_person_id"]
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)
        by_pair[tuple(sorted((source, target)))] = item
    components: list[set[str]] = []
    remaining = set(adjacency)
    while remaining:
        seed = min(remaining)
        component, frontier = set(), [seed]
        while frontier:
            current = frontier.pop()
            if current in component:
                continue
            component.add(current)
            frontier.extend(sorted(adjacency.get(current, set()) - component, reverse=True))
        remaining -= component
        if len(component) >= 2:
            components.append(component)
    result = []
    for members in components:
        ordered = tuple(sorted(members))
        member_edges = [item for pair, item in by_pair.items() if set(pair) <= members]
        evidence_count = sum(int(item["evidence_count"]) for item in member_edges)
        type_counts: dict[str, int] = {}
        for item in member_edges:
            for evidence_type, count in item["evidence_type_counts"].items():
                type_counts[evidence_type] = type_counts.get(evidence_type, 0) + int(count)
        digest = hashlib.sha256(
            json.dumps(
                [revision, scope_fingerprint, _WORLD_CLUSTER_VERSION, ordered],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()[:20]
        cluster_id = f"cluster:{digest}"
        preview_ids = sorted(
            ordered, key=lambda person_id: (-activity.get(person_id, 0), str(people_rows[person_id]["name"]).casefold(), person_id),
        )[:preview_limit]
        strongest = tuple({
            "relationship_id": item["relationship_id"],
            "source_person_id": item["source_person_id"],
            "target_person_id": item["target_person_id"],
            "evidence_count": item["evidence_count"],
            "evidence_types": sorted(item["evidence_type_counts"]),
        } for item in member_edges[:3])
        location_factor = {
            "factor": "location_context_role",
            "value": {
                "locations": list(context.filters.locations),
                "missing_location": context.filters.missing_location,
                "membership_basis": False,
            },
            "kind": "SCOPE_LIMITATION",
        }
        explanation = WorldExplanation(
            summary=f"{len(ordered)} people are connected by {evidence_count} scoped evidence records.",
            basis_type="EVIDENCE_CONNECTED_COMPONENT",
            factual_factors=(
                {"factor": "member_count", "value": len(ordered)},
                {"factor": "qualifying_relationship_count", "value": len(member_edges)},
                {"factor": "evidence_count", "value": evidence_count},
            ),
            derived_factors=(
                {"factor": "algorithm", "value": _WORLD_CLUSTER_VERSION},
                location_factor,
            ),
            calculation_version=_WORLD_CLUSTER_VERSION,
            evidence_types=tuple(sorted(type_counts)),
            evidence_count=evidence_count,
            first_occurrence_at=min((item["first_occurrence_at"] for item in member_edges if item["first_occurrence_at"] is not None), default=None, key=lambda value: _world_datetime(value, "occurrence")),
            last_occurrence_at=max((item["last_occurrence_at"] for item in member_edges if item["last_occurrence_at"] is not None), default=None, key=lambda value: _world_datetime(value, "occurrence")),
            evidence_expansion_token=None,
            calculation_scope=_world_explanation_scope(context),
            strongest_factors=strongest,
            method="connected_components_over_scoped_evidence_relationships",
            threshold={"minimum_members": 2, "minimum_relationship_strength": context.filters.min_relationship_strength or 1},
            sample={"member_count": len(ordered), "qualifying_relationship_count": len(member_edges)},
            limitations=(
                "Location and context restrict or describe scope but never create membership.",
                "A cluster is a revision-bound read object, not an organization or affiliation.",
            ),
        )
        result.append(WorldCluster(
            cluster_id=cluster_id, graph_revision=revision, member_ids=ordered,
            member_count=len(ordered),
            member_preview=tuple({"canonical_person_id": person_id, "display_name": str(people_rows[person_id]["name"])} for person_id in preview_ids),
            grouping_algorithm="EVIDENCE_CONNECTED_COMPONENT",
            algorithm_version=_WORLD_CLUSTER_VERSION,
            parameters={"minimum_members": 2, "qualifying_edge": "relationship_after_effective_filters"},
            evidence_basis={
                "relationship_count": len(member_edges),
                "evidence_count": evidence_count,
                "evidence_type_counts": dict(sorted(type_counts.items())),
                "strongest_relationships": list(strongest),
                "strongest_relationships_total_count": len(member_edges),
                "strongest_relationships_returned_count": len(strongest),
                "strongest_relationships_truncated": len(strongest) < len(member_edges),
                "location_context_role": "scope_only_not_membership",
            },
            explanation=explanation,
            activity_summary={
                "member_event_contributions": sum(activity.get(person_id, 0) for person_id in ordered),
                "active_member_count": sum(1 for person_id in ordered if activity.get(person_id, 0) > 0),
                "measurement": "deduplicated_person_event_contributions",
            },
            member_preview_state={
                "total_count": len(ordered),
                "returned_count": len(preview_ids),
                "has_more": len(preview_ids) < len(ordered),
                "truncated": len(preview_ids) < len(ordered),
                "truncation_reason": (
                    f"backend_preview_limit:{preview_limit}"
                    if len(preview_ids) < len(ordered) else None
                ),
            },
            expansion_token=None,
        ))
    ordered_result = sorted(
        result,
        key=lambda item: (
            -item.member_count,
            -int(item.evidence_basis["evidence_count"]),
            -int(item.activity_summary["member_event_contributions"]),
            item.cluster_id,
        ),
    )
    return [replace(item, ranking={
        "intent": "CLUSTER_SCOPE_SALIENCE",
        "rank_position": index + 1,
        "measurements": {
            "member_count": item.member_count,
            "evidence_count": item.evidence_basis["evidence_count"],
            "member_event_contributions": item.activity_summary["member_event_contributions"],
        },
        "deterministic_tie_break": [
            "member_count", "evidence_count", "member_event_contributions", "cluster_id",
        ],
        "reason": "Ordered by member count, evidence count, member event contributions, then cluster ID.",
        "value_semantics": "deterministic_ordering_not_confidence",
    }) for index, item in enumerate(ordered_result)]


def _world_relationship_models(
    conn: sqlite3.Connection, rows: list[dict], context: _WorldReadContext,
    canonical_map: dict[str, str],
) -> tuple[WorldRelationship, ...]:
    recurrence = _world_recurrence_for_pairs(conn, rows, context, canonical_map)
    models = []
    for row in rows:
        summary = recurrence.get(row["relationship_id"], {
            "count": 0, "first_occurrence_at": None, "latest_occurrence_at": None,
            "supporting_encounters": [],
        })
        summary["supporting_encounters_state"] = _world_bounded_state(
            int(summary["count"]), len(summary["supporting_encounters"]), "RELATIONSHIP_EVIDENCE_COLLECTION",
        )
        summary["measurement"] = "distinct_finalized_encounter_canonical_unordered_pair"
        models.append(_world_relationship({**row, "encounter_recurrence": summary}, context))
    return tuple(models)


def _world_relationship(
    item: dict, context: _WorldReadContext,
) -> WorldRelationship:
    explanation = WorldExplanation(
        summary=f"Supported by {item['evidence_count']} active authoritative evidence records in scope.",
        basis_type="EVIDENCE_COUNT_IN_SCOPE",
        factual_factors=(
            {"factor": "canonical_endpoints", "value": [item["source_person_id"], item["target_person_id"]]},
            {"factor": "evidence_type_counts", "value": dict(sorted(item["evidence_type_counts"].items()))},
            {"factor": "directionality", "value": item["directionality"]},
        ),
        calculation_version=_WORLD_CALCULATION_VERSION,
        evidence_types=tuple(sorted(item["evidence_type_counts"])), evidence_count=item["evidence_count"],
        first_occurrence_at=item["first_occurrence_at"], last_occurrence_at=item["last_occurrence_at"],
        evidence_expansion_token=None,
        calculation_scope=_world_explanation_scope(context),
        strongest_factors=(
            {"factor": "evidence_type_counts", "value": dict(sorted(item["evidence_type_counts"].items()))},
            {"factor": "occurrence_window", "value": {"first": item["first_occurrence_at"], "last": item["last_occurrence_at"]}},
        ),
        method="active_authoritative_evidence_count_after_scope",
        threshold={"minimum_evidence_count": context.filters.min_relationship_strength or 1},
        sample={"evidence_count": item["evidence_count"]},
        limitations=("Strength is a descriptive evidence count, not confidence or risk.",),
    )
    return WorldRelationship(
        relationship_id=item["relationship_id"], source_person_id=item["source_person_id"],
        target_person_id=item["target_person_id"], directionality=item["directionality"],
        relationship_types=item["relationship_types"], evidence_count=item["evidence_count"],
        evidence_type_counts=dict(sorted(item["evidence_type_counts"].items())),
        first_occurrence_at=item["first_occurrence_at"], last_occurrence_at=item["last_occurrence_at"],
        strength_basis="EVIDENCE_COUNT_IN_SCOPE", explanation=explanation,
        evidence_expansion_token=None,
        selected_evidence_strength=int(item["evidence_count"]),
        qualifies_for_cluster=item.get("qualifies_for_cluster", True),
        direction_counts=item["direction_counts"],
        note_reference_direction_counts=dict(sorted(item["note_directions"].items())),
        encounter_recurrence=item["encounter_recurrence"],
    )


def _world_participant_sources(conn: sqlite3.Connection) -> tuple[str, ...]:
    """Read-only corrected membership overlay; ordinary reads retain indexed SQL.

    Only amended Encounters need the correction interpreter. No per-Encounter
    callback, persisted projection, or recognition state participates in this read.
    """
    changed = [str(row[0]) for row in conn.execute(
        "SELECT observation_id FROM identity_corrections WHERE observation_id IS NOT NULL "
        "AND correction_type IN ('FACE_ASSIGNMENT', 'OBSERVATION_IDENTITY') "
        "UNION SELECT observation_id FROM encounter_participant_revisions"
    )]
    if not changed:
        return ("observation_participants",)
    raw: dict[str, set[str]] = {oid: set() for oid in changed}
    for row in conn.execute(
        "SELECT observation_id, person_id FROM observation_participants "
        "WHERE observation_id IN (SELECT value FROM json_each(?))", (json.dumps(changed),),
    ):
        raw[str(row[0])].add(str(row[1]))
    effective, _ = _batch_effective_observation_person_ids(
        conn, set(changed), raw, lambda pid: pid, selected_observations_only=True,
    )
    rows = [[oid, pid] for oid in changed for pid in sorted(effective[oid])]
    # SQL literals contain only encoded stored identifiers, escaped as SQL text.
    ids = json.dumps(changed).replace("'", "''")
    values = json.dumps(rows).replace("'", "''")
    return (
        f"(SELECT observation_id, person_id FROM observation_participants "
        f"WHERE observation_id NOT IN (SELECT value FROM json_each('{ids}')))",
        f"(SELECT json_extract(value, '$[0]') AS observation_id, "
        f"json_extract(value, '$[1]') AS person_id FROM json_each('{values}'))",
    )


def _world_participant_source(conn: sqlite3.Connection) -> str:
    sources = _world_participant_sources(conn)
    return sources[0] if len(sources) == 1 else "(" + " UNION ALL ".join(
        f"SELECT * FROM {source}" for source in sources
    ) + ")"



def _world_effective_participant_cte(conn: sqlite3.Connection, scope_sql: str) -> str:
    source = _world_participant_source(conn)
    return f"""
        WITH RECURSIVE identity_map(person_id, canonical_person_id) AS (
            SELECT person_id, person_id FROM persons WHERE canonical_person_id IS NULL
            UNION ALL
            SELECT p.person_id, m.canonical_person_id
            FROM persons p JOIN identity_map m ON p.canonical_person_id = m.person_id
        ), effective(observation_id, person_id) AS (
            SELECT DISTINCT p.observation_id, m.canonical_person_id
            FROM effective_observations o JOIN {source} p USING(observation_id)
            JOIN identity_map m ON m.person_id = p.person_id
            WHERE {scope_sql}
        )
    """


def _world_scoped_event_count(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    eligible_person_ids: set[str],
    *,
    canonical_map: dict[str, str] | None = None,
) -> int:
    if not eligible_person_ids:
        return 0
    resolved = canonical_map or _world_canonical_map(conn)
    candidates = _world_register_effective_person_function(
        conn, resolved, focus_person_ids=eligible_person_ids,
    )
    if not candidates:
        return 0
    source = _world_participant_source(conn)
    participant_index = "INDEXED BY idx_observation_participants_person" if source == "observation_participants" else ""
    scope_sql, params = _world_scope_sql(filters, evidence=False)
    placeholders = ",".join("?" for _ in candidates)
    return int(conn.execute(
        f"""SELECT COUNT(DISTINCT p.observation_id)
            FROM {source} p
                 {participant_index}
            CROSS JOIN effective_observations o
            WHERE p.person_id IN ({placeholders})
              AND o.observation_id = p.observation_id
              AND {scope_sql}
              AND world_effective_person_in_scope(
                      p.observation_id, p.person_id
                  ) = 1""",
        [*sorted(candidates), *params],
    ).fetchone()[0])


def _world_person_event_count(
    conn: sqlite3.Connection,
    person_id: str,
    filters: WorldReadFilter,
    *,
    canonical_map: dict[str, str] | None = None,
) -> int:
    resolved = canonical_map or _world_canonical_map(conn)
    candidates = _world_register_effective_person_function(conn, resolved, person_id)
    if not candidates:
        return 0
    membership_sql, params = _world_person_event_membership_sql(
        conn, filters, candidates, person_id,
    )
    return int(conn.execute(
        f"SELECT COUNT(DISTINCT p.observation_id) {membership_sql}", params,
    ).fetchone()[0])


def _world_person_events(
    conn: sqlite3.Connection,
    person_id: str,
    filters: WorldReadFilter,
    offset: int,
    limit: int,
    *,
    canonical_map: dict[str, str] | None = None,
    known_total: int | None = None,
) -> tuple[int, list[sqlite3.Row]]:
    resolved = canonical_map or _world_canonical_map(conn)
    candidates = _world_register_effective_person_function(conn, resolved, person_id)
    if not candidates:
        return 0, []
    membership_sql, params = _world_person_event_membership_sql(
        conn, filters, candidates, person_id,
    )
    total = known_total if known_total is not None else _world_person_event_count(
        conn, person_id, filters, canonical_map=resolved,
    )
    rows = conn.execute(
        f"""SELECT DISTINCT o.* {membership_sql}
            ORDER BY world_time(COALESCE(o.observed_at, o.created_at)) DESC, o.observation_id
            LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    ).fetchall()
    return total, rows


def _world_person_event_membership_sql(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    candidates: set[str],
    person_id: str,
) -> tuple[str, list[object]]:
    """Return the shared participant-first focused-event membership predicate."""
    source = _world_participant_source(conn)
    participant_index = "INDEXED BY idx_observation_participants_person" if source == "observation_participants" else ""
    scope_sql, scope_params = _world_scope_sql(filters, evidence=False)
    placeholders = ",".join("?" for _ in candidates)
    return (
        f"""FROM {source} p
               {participant_index}
            CROSS JOIN effective_observations o
            WHERE p.person_id IN ({placeholders})
              AND o.observation_id = p.observation_id
              AND {scope_sql}
              AND world_effective_person(p.observation_id, p.person_id) = ?""",
        [*sorted(candidates), *scope_params, person_id],
    )


def _world_register_effective_person_function(
    conn: sqlite3.Connection,
    canonical_map: dict[str, str],
    focus_person_id: str | None = None,
    *,
    focus_person_ids: set[str] | None = None,
) -> set[str]:
    def effective_person(observation_id: object, raw_person_id: object) -> str:
        return canonical_map[str(raw_person_id)]

    conn.create_function("world_effective_person", 2, effective_person, deterministic=True)
    if focus_person_id is not None and focus_person_ids is not None:
        raise ValueError("World effective-person focus must be singular or a set")
    target_ids = (
        set(focus_person_ids) if focus_person_ids is not None
        else {focus_person_id} if focus_person_id is not None
        else None
    )
    if target_ids is None:
        return set(canonical_map)
    candidates = {
        raw_id for raw_id, canonical_id in canonical_map.items()
        if canonical_id in target_ids
    }
    if focus_person_ids is not None:
        conn.create_function(
            "world_effective_person_in_scope", 2,
            lambda observation_id, raw_person_id: int(
                effective_person(observation_id, raw_person_id) in target_ids
            ),
            deterministic=True,
        )
    return candidates


def _world_event_row(
    conn: sqlite3.Connection, event_id: str, filters: WorldReadFilter,
) -> sqlite3.Row:
    scope_sql, params = _world_scope_sql(filters, evidence=False)
    row = conn.execute(
        f"SELECT o.* FROM effective_observations o WHERE {scope_sql} AND o.observation_id = ?",
        [*params, event_id],
    ).fetchone()
    if row is None:
        raise KeyError("World event is unavailable in the effective scope")
    return row


def _world_event_participant_mapping(
    conn: sqlite3.Connection, event_id: str,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    raw_rows = conn.execute(
        "SELECT person_id FROM observation_participants WHERE observation_id = ? ORDER BY person_id",
        (event_id,),
    ).fetchall()
    corrections = conn.execute(
        """SELECT from_person_id, to_person_id, operation_id
           FROM identity_corrections
           WHERE observation_id = ? AND correction_type = 'OBSERVATION_IDENTITY'
           ORDER BY created_at, rowid""",
        (event_id,),
    ).fetchall()
    canonical_map = _world_canonical_map(conn)
    participants, provenance = _world_participant_mapping(
        [str(row["person_id"]) for row in raw_rows], corrections, canonical_map,
    )
    amended = conn.execute(
        "SELECT 1 FROM encounter_participant_revisions WHERE observation_id = ? "
        "UNION ALL SELECT 1 FROM identity_corrections WHERE observation_id = ? "
        "AND correction_type = 'FACE_ASSIGNMENT' LIMIT 1", (event_id, event_id),
    ).fetchone()
    if amended:
        assignments = _effective_face_assignments(conn, event_id)
        if assignments:
            represented = {item["original_person_id"] for item in assignments}
            _, untouched = _world_participant_mapping(
                [str(row["person_id"]) for row in raw_rows if str(row["person_id"]) not in represented],
                corrections, canonical_map,
            )
            face_operations: dict[str, list[str]] = {}
            for row in conn.execute(
                "SELECT face_assignment_id, operation_id FROM identity_corrections "
                "WHERE observation_id = ? AND correction_type = 'FACE_ASSIGNMENT' "
                "ORDER BY created_at, rowid", (event_id,),
            ):
                face_operations.setdefault(str(row[0]), []).append(str(row[1]))
            origins = list(untouched)
            for assignment in assignments:
                _, mapped = _world_participant_mapping(
                    [assignment["current_person_id"]], corrections, canonical_map,
                )
                item = dict(mapped[0])
                operations = face_operations.get(assignment["assignment_id"], [])
                item.update(raw_person_id=assignment["original_person_id"],
                    face_assignment_id=assignment["assignment_id"],
                    correction_operation_ids=list(dict.fromkeys([*operations, *item["correction_operation_ids"]])))
                if operations:
                    item["relationship_to_effective_identity"] = "CORRECTED_PARTICIPANT"
                origins.append(item)
            provenance = tuple(origins)
        presence_revisions: dict[str, sqlite3.Row] = {}
        for row in conn.execute(
            "SELECT person_id, disposition, operation_id FROM encounter_participant_revisions "
            "WHERE observation_id = ? ORDER BY created_at, rowid", (event_id,),
        ):
            presence_revisions[str(row["person_id"])] = row
        revision_origins = []
        for pid, revision in presence_revisions.items():
            if revision["disposition"] != "PRESENT":
                continue
            _, mapped = _world_participant_mapping([pid], [], canonical_map)
            revision_origins.append({**mapped[0],
                "relationship_to_effective_identity": "CORRECTED_PARTICIPANT",
                "correction_operation_ids": [str(revision["operation_id"])],
                "participant_revision_operation_ids": [str(revision["operation_id"])]})
        provenance = (*provenance, *revision_origins)
        participants = tuple({"person_id": pid} for pid in _effective_observation_person_ids(conn, event_id))
        provenance = tuple({**item, "effective_participation": item["effective_person_id"] in {p["person_id"] for p in participants}} for item in provenance)
    return participants, provenance


def _world_participant_mapping(
    raw_ids: list[str],
    corrections: list[sqlite3.Row],
    canonical_map: dict[str, str],
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    effective_ids: set[str] = set()
    provenance: list[dict[str, object]] = []
    for raw_id in sorted(raw_ids):
        current = raw_id
        correction_ids: list[str] = []
        for correction in corrections:
            if str(correction["from_person_id"]) == current:
                current = str(correction["to_person_id"])
                correction_ids.append(str(correction["operation_id"]))
        effective_id = canonical_map[current]
        effective_ids.add(effective_id)
        relationship = (
            "CORRECTED_PARTICIPANT" if correction_ids else
            "MERGED_SOURCE" if raw_id != effective_id else
            "ORIGINAL_IDENTITY"
        )
        provenance.append({
            "raw_person_id": raw_id,
            "effective_person_id": effective_id,
            "relationship_to_effective_identity": relationship,
            "correction_operation_ids": correction_ids,
        })
    participants = tuple({"person_id": person_id} for person_id in sorted(effective_ids))
    return participants, tuple(provenance)


def _world_event_batch_data(
    conn: sqlite3.Connection,
    event_rows: list[sqlite3.Row],
    canonical_map: dict[str, str],
) -> dict[str, tuple[
    tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]],
    dict[str, object],
    int,
]]:
    event_ids = [str(row["observation_id"]) for row in event_rows]
    if not event_ids:
        return {}
    placeholders = ",".join("?" for _ in event_ids)
    raw_by_event: dict[str, list[str]] = {event_id: [] for event_id in event_ids}
    for row in conn.execute(
        f"""SELECT observation_id, person_id FROM observation_participants
            WHERE observation_id IN ({placeholders}) ORDER BY observation_id, person_id""",
        event_ids,
    ).fetchall():
        raw_by_event[str(row["observation_id"])].append(str(row["person_id"]))
    corrections_by_event: dict[str, list[sqlite3.Row]] = {
        event_id: [] for event_id in event_ids
    }
    for row in conn.execute(
        f"""SELECT observation_id, from_person_id, to_person_id, operation_id
            FROM identity_corrections
            WHERE correction_type = 'OBSERVATION_IDENTITY'
              AND observation_id IN ({placeholders})
            ORDER BY observation_id, created_at, rowid""",
        event_ids,
    ).fetchall():
        corrections_by_event[str(row["observation_id"])].append(row)
    evidence_by_event: dict[str, dict[str, int]] = {event_id: {} for event_id in event_ids}
    for row in conn.execute(
        f"""SELECT source_entity_id, evidence_type, COUNT(*) AS count
            FROM relationship_evidence
            WHERE active = 1 AND source_entity_type = 'OBSERVATION'
              AND source_entity_id IN ({placeholders})
            GROUP BY source_entity_id, evidence_type""",
        event_ids,
    ).fetchall():
        evidence_by_event[str(row["source_entity_id"])][str(row["evidence_type"])] = int(row["count"])
    media_by_event = {event_id: 0 for event_id in event_ids}
    for row in conn.execute(
        f"""SELECT observation_id, COUNT(*) AS count FROM observation_media
            WHERE observation_id IN ({placeholders}) GROUP BY observation_id""",
        event_ids,
    ).fetchall():
        media_by_event[str(row["observation_id"])] = int(row["count"])
    revised_events = {str(row[0]) for row in conn.execute(
        f"SELECT observation_id FROM encounter_participant_revisions WHERE observation_id IN ({placeholders}) UNION SELECT observation_id FROM identity_corrections WHERE correction_type = 'FACE_ASSIGNMENT' AND observation_id IN ({placeholders})", [*event_ids, *event_ids])}
    return {
        event_id: (
            _world_event_participant_mapping(conn, event_id) if event_id in revised_events else _world_participant_mapping(
                raw_by_event[event_id], corrections_by_event[event_id], canonical_map,
            ),
            {
                "total_count": sum(evidence_by_event[event_id].values()),
                "evidence_type_counts": dict(sorted(evidence_by_event[event_id].items())),
            },
            media_by_event[event_id],
        )
        for event_id in event_ids
    }


def _world_context_summary(payload: str) -> dict[str, object]:
    context = json.loads(payload or "{}")
    allowed = (
        "occasion", "event_type", "description", "category",
        "time_precision", "start_time", "end_time", "event_notes",
    )
    values = {
        key: str(context[key]) for key in allowed
        if context.get(key) is not None and str(context[key]).strip()
    }
    return {"available": bool(values), **values}


def _world_event_evidence_summary(
    conn: sqlite3.Connection, event_id: str,
) -> dict[str, object]:
    rows = conn.execute(
        """SELECT evidence_type, COUNT(*) AS count
           FROM relationship_evidence
           WHERE active = 1 AND source_entity_type = 'OBSERVATION'
             AND source_entity_id = ?
           GROUP BY evidence_type ORDER BY evidence_type""",
        (event_id,),
    ).fetchall()
    counts = {str(row["evidence_type"]): int(row["count"]) for row in rows}
    return {"total_count": sum(counts.values()), "evidence_type_counts": counts}


def _world_event_evidence_count(
    conn: sqlite3.Connection, event_id: str, filters: WorldReadFilter,
) -> int:
    total, _ = _world_evidence_page(conn, filters, "EVENT", event_id, 0, 1)
    return total


def _world_event_media_count(conn: sqlite3.Connection, event_id: str) -> int:
    return int(conn.execute(
        "SELECT COUNT(*) FROM observation_media WHERE observation_id = ?", (event_id,),
    ).fetchone()[0])


def _world_event_media_page(
    conn: sqlite3.Connection, event_id: str, offset: int, limit: int,
    *, supporting_evidence_id: str | None = None,
) -> tuple[int, tuple[WorldMediaReference, ...]]:
    total = _world_event_media_count(conn, event_id)
    event = conn.execute(
        "SELECT COALESCE(observed_at, created_at) AS occurred_at FROM effective_observations WHERE observation_id = ? AND status = 'FINALIZED'",
        (event_id,),
    ).fetchone()
    if event is None:
        raise KeyError("World event is unavailable")
    rows = conn.execute(
        """SELECT media_id, media_path, source FROM observation_media
           WHERE observation_id = ? ORDER BY created_at, media_id LIMIT ? OFFSET ?""",
        (event_id, limit, offset),
    ).fetchall()
    return total, tuple(WorldMediaReference(
        media_id=str(row["media_id"]),
        media_reference=_optional_text(row["media_path"]),
        source=_optional_text(row["source"]),
        occurred_at=str(event["occurred_at"]),
        supporting_event_id=event_id,
        supporting_evidence_id=supporting_evidence_id,
    ) for row in rows)


def _world_event_from_row(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    participant_offset: int,
    participant_limit: int,
    provenance_offset: int,
    provenance_limit: int,
    context: _WorldReadContext,
    prepared: tuple[
        tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]],
        dict[str, object],
        int,
    ] | None = None,
) -> WorldEvent:
    event_id = str(row["observation_id"])
    if prepared is None:
        all_participants, provenance = _world_event_participant_mapping(conn, event_id)
        evidence_summary = _world_event_evidence_summary(conn, event_id)
        media_count = _world_event_media_count(conn, event_id)
    else:
        (all_participants, provenance), evidence_summary, media_count = prepared
    participants = all_participants[
        participant_offset:participant_offset + participant_limit
    ]
    page_provenance = provenance[
        provenance_offset:provenance_offset + provenance_limit
    ]
    occurred_at = str(row["observed_at"] if row["observed_at"] is not None else row["created_at"])
    known_occurrence = occurred_at if _world_stored_datetime(occurred_at) is not None else None
    return WorldEvent(
        event_id=event_id,
        finalized_at=str(row["finalized_at"]),
        occurred_at=occurred_at,
        location=_optional_text(row["location"]),
        context_summary=_world_context_summary(str(row["context"] or "{}")),
        source=_optional_text(row["source"]),
        participants=participants,
        participant_provenance=page_provenance,
        participant_summary={
            "total_count": len(all_participants), "returned_count": len(participants),
            "has_more": participant_offset + len(participants) < len(all_participants),
            "provenance_total_count": len(provenance),
            "provenance_returned_count": len(page_provenance),
            "participants_state": "LOADED" if participant_limit else "NOT_REQUESTED",
            "provenance_state": "LOADED" if provenance_limit else "NOT_REQUESTED",
        },
        evidence_summary=evidence_summary,
        media_summary={"total_count": media_count, "retrieval": "EVENT_MEDIA_COLLECTION"},
        explanation=WorldExplanation(
            summary=f"Finalized event with {len(all_participants)} effective canonical participants.",
            basis_type="FINALIZED_OBSERVATION",
            factual_factors=(
                {"factor": "finalization_state", "value": "FINALIZED"},
                {"factor": "participant_count", "value": len(all_participants)},
                {"factor": "evidence_count", "value": evidence_summary["total_count"]},
                {"factor": "media_count", "value": media_count},
                {"factor": "location", "value": _optional_text(row["location"])},
            ),
            calculation_version=_WORLD_CALCULATION_VERSION,
            evidence_types=tuple(sorted(evidence_summary["evidence_type_counts"])),
            evidence_count=int(evidence_summary["total_count"]),
            first_occurrence_at=known_occurrence,
            last_occurrence_at=known_occurrence,
            calculation_scope=_world_explanation_scope(context),
            strongest_factors=(
                {"factor": "participant_count", "value": len(all_participants)},
                {"factor": "evidence_count", "value": evidence_summary["total_count"]},
            ),
            method="finalized_observation_summary",
            sample={"participant_count": len(all_participants)},
            limitations=("Media and evidence details are retrieved through separate bounded collections.",),
        ),
    )


def _world_evidence_page(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    focus_type: str | None,
    focus_id: str | None,
    offset: int,
    limit: int,
) -> tuple[int, list[WorldEvidence]]:
    canonical_map = _world_canonical_map(conn)
    effective_person = _world_register_effective_evidence_function(conn, canonical_map)
    effective_source = (
        "world_effective_evidence_person(e.evidence_type, e.source_entity_type, "
        "e.source_entity_id, e.source_person_id)"
    )
    effective_target = (
        "world_effective_evidence_person(e.evidence_type, e.source_entity_type, "
        "e.source_entity_id, e.target_person_id)"
    )
    clauses = [
        "e.active = 1",
        "(e.evidence_type <> 'CO_OBSERVED' OR o.status = 'FINALIZED')",
    ]
    params: list[object] = []
    if focus_type == "RELATIONSHIP":
        parts = str(focus_id).split(":")
        if len(parts) != 3 or parts[0] != "relationship":
            raise ValueError("Invalid World relationship focus")
        first, second = sorted(parts[1:])
        if first == second or first not in canonical_map.values() or second not in canonical_map.values():
            raise ValueError("Invalid World relationship focus")
        clauses.append(
            f"(({effective_source} = ? AND {effective_target} = ?) OR "
            f"({effective_source} = ? AND {effective_target} = ?))"
        )
        params.extend([first, second, second, first])
    elif focus_type == "EVENT":
        clauses.append("e.source_entity_type = 'OBSERVATION' AND e.source_entity_id = ?")
        params.append(focus_id)
    elif focus_type == "PERSON":
        canonical_id = canonical_map.get(str(focus_id))
        if canonical_id is None:
            raise KeyError("World person is unavailable")
        clauses.append(f"({effective_source} = ? OR {effective_target} = ?)")
        params.extend([canonical_id, canonical_id])
    elif focus_type == "EVIDENCE":
        clauses.append("e.evidence_id = ?")
        params.append(focus_id)
    if filters.evidence_type:
        clauses.append("e.evidence_type IN (%s)" % ",".join("?" for _ in filters.evidence_type))
        params.extend(filters.evidence_type)
    if filters.relationship_type:
        clauses.append("e.relationship_type IN (%s)" % ",".join("?" for _ in filters.relationship_type))
        params.extend(filters.relationship_type)
    occurrence = "CASE WHEN e.evidence_type = 'CO_OBSERVED' THEN COALESCE(o.observed_at, o.created_at) ELSE e.created_at END"
    if filters.date_from:
        clauses.append(f"world_time({occurrence}) >= world_time(?)")
        params.append(filters.date_from)
    if filters.date_to:
        clauses.append(f"world_time({occurrence}) <= world_time(?)")
        params.append(filters.date_to)
    if filters.locations:
        clauses.append("e.evidence_type = 'CO_OBSERVED'")
        clauses.append("LOWER(TRIM(COALESCE(o.location, ''))) IN (%s)" % ",".join("?" for _ in filters.locations))
        params.extend(item.casefold() for item in filters.locations)
    if filters.missing_location == "EXCLUDE":
        clauses.append("e.evidence_type = 'CO_OBSERVED' AND TRIM(COALESCE(o.location, '')) <> ''")
    elif filters.missing_location == "ONLY":
        clauses.append("(e.evidence_type <> 'CO_OBSERVED' OR TRIM(COALESCE(o.location, '')) = '')")
    where = " AND ".join(clauses)
    joined = "relationship_evidence e LEFT JOIN effective_observations o ON e.evidence_type = 'CO_OBSERVED' AND o.observation_id = e.source_entity_id"
    total = int(conn.execute(f"SELECT COUNT(*) FROM {joined} WHERE {where}", params).fetchone()[0])
    rows = conn.execute(
        f"SELECT e.*, o.location AS encounter_location, {occurrence} AS effective_occurred_at FROM {joined} "
        f"WHERE {where} ORDER BY world_time({occurrence}) DESC, e.evidence_id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    observation_ids = sorted({
        str(row["source_entity_id"]) for row in rows
        if str(row["evidence_type"]) == "CO_OBSERVED"
        and str(row["source_entity_type"]) == "OBSERVATION"
    })
    media_counts: dict[str, int] = {}
    if observation_ids:
        placeholders = ",".join("?" for _ in observation_ids)
        media_counts = {
            str(row["observation_id"]): int(row["count"])
            for row in conn.execute(
                f"""SELECT observation_id, COUNT(*) AS count FROM observation_media
                    WHERE observation_id IN ({placeholders}) GROUP BY observation_id""",
                observation_ids,
            ).fetchall()
        }
    result = []
    for row in rows:
        source = effective_person(
            row["evidence_type"], row["source_entity_type"],
            row["source_entity_id"], row["source_person_id"],
        )
        target = effective_person(
            row["evidence_type"], row["source_entity_type"],
            row["source_entity_id"], row["target_person_id"],
        )
        occurred_at = str(row["effective_occurred_at"])
        known_occurrence = occurred_at if _world_stored_datetime(occurred_at) is not None else None
        supporting = ({
            "source_entity_type": str(row["source_entity_type"]),
            "source_entity_id": str(row["source_entity_id"]),
            "evidence_revision_id": str(row["evidence_revision_id"]),
        },)
        raw_endpoints = (str(row["source_person_id"]), str(row["target_person_id"]))
        effective_endpoints = (source, target)
        is_observation = (
            str(row["evidence_type"]) == "CO_OBSERVED"
            and str(row["source_entity_type"]) == "OBSERVATION"
        )
        media_count = media_counts.get(str(row["source_entity_id"]), 0) if is_observation else 0
        directionality = str(row["directionality"])
        explanation = WorldExplanation(
            summary=(
                f"{row['evidence_type']} evidence records an authoritative "
                f"{directionality.lower()} relationship fact from {row['source_entity_type']}."
            ),
            basis_type="AUTHORITATIVE_EVIDENCE_PROVENANCE",
            factual_factors=(
                {"factor": "raw_endpoints", "value": list(raw_endpoints)},
                {"factor": "effective_endpoints", "value": list(effective_endpoints)},
                {"factor": "directionality", "value": directionality},
                {"factor": "authoritative_source", "value": {
                    "type": str(row["source_entity_type"]),
                    "id": str(row["source_entity_id"]),
                }},
            ),
            calculation_version=_WORLD_CALCULATION_VERSION,
            evidence_types=(str(row["evidence_type"]),), evidence_count=1,
            first_occurrence_at=known_occurrence, last_occurrence_at=known_occurrence,
            method="terminal_canonical_resolution_of_current_evidence",
            sample={"evidence_items": 1},
            limitations=(
                "This evidence is descriptive provenance, not confidence, risk, or inferred intent.",
            ),
        )
        result.append(WorldEvidence(
            evidence_id=str(row["evidence_id"]),
            provenance={
                "created_operation_id": str(row["created_operation_id"]),
                "source": row["source"],
                "canonical_endpoints": [source, target],
                "raw_endpoints": list(raw_endpoints),
                "encounter_location": row["encounter_location"],
            },
            evidence_type=str(row["evidence_type"]), supporting_references=supporting,
            occurred_at=occurred_at,
            explanation_links=(
                (f"relationship:{min(source, target)}:{max(source, target)}",)
                if source != target else ()
            ),
            active=bool(row["active"]),
            directionality=directionality,
            effective_endpoints=effective_endpoints, raw_endpoints=raw_endpoints,
            occurrence_bounds={"first": known_occurrence, "last": known_occurrence},
            explanation=explanation,
            media_summary={
                "total_count": media_count,
                "availability": "AVAILABLE" if is_observation else "UNAVAILABLE",
                "retrieval": "EVIDENCE_MEDIA_COLLECTION",
                "reason": None if is_observation else "evidence_source_has_no_authoritative_media",
            },
        ))
    return total, result


def _world_facets(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    people_rows: dict[str, sqlite3.Row],
    relationships: list[dict],
    activity: dict[str, int],
    eligible_person_ids: set[str],
    *,
    location_facets: list[dict[str, object]] | None = None,
    pattern_count: int = 0,
) -> dict[str, object]:
    def facet(values: list[str]) -> list[dict[str, object]]:
        counts: dict[str, int] = {}
        for value in values:
            normalized = value.strip() or "MISSING"
            counts[normalized] = counts.get(normalized, 0) + 1
        return [
            {"value": value, "count": count}
            for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
        ]

    metadata = {
        person_id: json.loads(row["metadata"] or "{}")
        for person_id, row in people_rows.items()
    }
    evidence_counts: dict[str, int] = {}
    for relationship in relationships:
        for evidence_type, count in relationship["evidence_type_counts"].items():
            evidence_counts[evidence_type] = evidence_counts.get(evidence_type, 0) + int(count)
    return {
        "locations": (
            location_facets if location_facets is not None
            else _world_location_facets_effective(conn, filters, eligible_person_ids)
        ),
        "lifecycle": facet([str(row["lifecycle_status"]) for row in people_rows.values()]),
        "identity_state": facet([str(row["identity_status"]) for row in people_rows.values()]),
        "biometric_state": facet([str(row["biometric_status"]) for row in people_rows.values()]),
        "country": facet([str(value.get("country") or "") for value in metadata.values()]),
        "rank": facet([str(value.get("rank") or "") for value in metadata.values()]),
        "priority": facet([str(value.get("importance") or "") for value in metadata.values()]),
        "activity": facet([_world_activity_bucket(activity.get(person_id, 0)) for person_id in people_rows]),
        "evidence_type": [
            {"value": value, "count": count}
            for value, count in sorted(evidence_counts.items())
        ],
        "pattern_type": (
            [{"value": "DATA_QUALITY", "count": pattern_count}]
            if pattern_count else []
        ),
    }


def _world_location_facets_effective(
    conn: sqlite3.Connection,
    filters: WorldReadFilter,
    eligible_person_ids: set[str],
) -> list[dict]:
    if not eligible_person_ids:
        return []
    location_filters = WorldReadFilter(
        date_from=filters.date_from, date_to=filters.date_to,
        recent_activity=filters.recent_activity, missing_location="INCLUDE",
    )
    scope_sql, params = _world_scope_sql(location_filters, evidence=False)
    cte = _world_effective_participant_cte(conn, scope_sql)
    placeholders = ",".join("?" for _ in eligible_person_ids)
    rows = conn.execute(
        f"""{cte}, eligible_events AS (
                SELECT DISTINCT observation_id FROM effective
                WHERE person_id IN ({placeholders})
            )
            SELECT CASE WHEN TRIM(COALESCE(o.location, '')) = '' THEN 'MISSING'
                         ELSE TRIM(o.location) END AS value, COUNT(*) AS count
            FROM eligible_events e JOIN effective_observations o USING(observation_id)
            GROUP BY LOWER(TRIM(COALESCE(o.location, '')))
            ORDER BY count DESC, value LIMIT 100""",
        [*params, *sorted(eligible_person_ids)],
    ).fetchall()
    return [{"value": str(row["value"]), "count": int(row["count"])} for row in rows]


def _world_token(
    kind: str, revision: str, level: str, focus_type: str | None, focus_id: str | None, offset: int,
    *, collection: str | None = None, as_of: str | None = None, scope: str | None = None,
) -> str:
    payload = json.dumps({
        "kind": kind, "revision": revision, "level": level,
        "focus_type": focus_type, "focus_id": focus_id, "offset": offset,
        "collection": collection, "as_of": as_of, "scope": scope,
    }, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _world_decode_cursor(
    token: str | None, revision: str, level: WorldDetailLevel,
    focus_type: str | None, focus_id: str | None, collection: WorldCollection,
    as_of: str, scope: str,
) -> int:
    if not token:
        return 0
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid World cursor") from exc
    expected = {
        "kind": "CURSOR", "revision": revision, "level": level.value,
        "focus_type": focus_type, "focus_id": focus_id,
        "collection": collection.value, "as_of": as_of, "scope": scope,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("World cursor does not match the current revision, level, focus, collection, as_of, or scope")
    offset = payload.get("offset")
    if not isinstance(offset, int) or offset < 0:
        raise ValueError("Invalid World cursor offset")
    return offset


def _world_cursor_as_of(token: str | None) -> str | None:
    if not token:
        return None
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid World cursor") from exc
    if payload.get("kind") != "CURSOR":
        raise ValueError("Invalid World cursor")
    return _optional_text(payload.get("as_of"))


def _world_scope_fingerprint(
    filters: WorldReadFilter, ranking: str, limits: WorldReadLimits,
) -> str:
    payload = json.dumps(
        {"filters": asdict(filters), "ranking": ranking, "limits": asdict(limits),
         "chronology": "utc-microseconds-unknown-v2"},
        sort_keys=True, separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def _world_filter_fingerprint(filters: WorldReadFilter) -> str:
    payload = json.dumps(asdict(filters), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:24]
