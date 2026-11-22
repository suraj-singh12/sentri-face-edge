"""Response payload builders for the loopback API, re-exported by sentriface.api_server."""
from __future__ import annotations

import hashlib
import json

from dataclasses import asdict
from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from typing import (
    Any,
    Callable,
)
from urllib.parse import parse_qs
from sentriface.api_serializers import embedding_record_payload
from sentriface.backup_service import BackupRecord
from sentriface.engine import FaceEngine
from sentriface.logging_config import sanitize_log_details
from sentriface.models import (
    EmbeddingRecord,
    GraphConnection,
    GraphReadEdge,
    GraphReadFilter,
    GraphReadNode,
    InitGroup,
    InitSession,
    Note,
    Observation,
    PhotoReview,
    Person,
    PersonAssociation,
    PersonChange,
    PersonMatch,
    PersonIntelligence,
    PersonGraphReadModel,
    PersonSummary,
    QualityReport,
    RecognitionDetail,
    RejectedFace,
    Sighting,
    WorldGraphReadModel,
    WorldDetailLevel,
    WorldCollection,
    WorldGraphRequest,
    WorldGraphV2ReadModel,
    WorldReadFilter,
    WorldReadLimits,
)


def _photo_review(review: PhotoReview) -> dict[str, Any]:
    return {
        "review_id": review.review_id,
        "media_id": review.media_id,
        "media_path": review.media_path,
        "source": review.source,
        "status": review.status,
        "observation_id": review.observation_id,
        "completed_operation_id": review.completed_operation_id,
        "created_at": review.created_at,
        "completed_at": review.completed_at,
        "faces": [
            {
                "face_id": face.face_id,
                "staged_face_type": face.staged_face_type,
                "staged_face_id": face.staged_face_id,
                "decision": face.decision,
                "person_id": face.person_id,
                "new_person_key": face.new_person_key,
                "new_person_name": face.new_person_name,
                "new_person_metadata": face.new_person_metadata,
                "notes": face.notes,
                "mentioned_person_ids": list(face.mentioned_person_ids),
                "recognition_detail": face.recognition_detail,
            }
            for face in review.faces
        ],
    }


def _rejected(rejected: RejectedFace, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "source_image": rejected.source_image,
        "box": _box(rejected.face),
        "quality": _quality(rejected.quality),
    }


def _person(person: Person) -> dict[str, Any]:
    lifecycle_status = person.lifecycle_status
    effective_person_id = person.canonical_person_id or person.person_id
    return {
        "person_id": person.person_id,
        "name": person.name,
        "metadata": person.metadata,
        "created_at": person.created_at,
        "deleted_at": person.deleted_at,
        "lifecycle_status": lifecycle_status,
        "canonical_person_id": person.canonical_person_id,
        "effective_person_id": effective_person_id,
        "identity_status": person.identity_status,
        "biometric_status": person.biometric_status,
        "archived": lifecycle_status == "ARCHIVED",
        "deleted": lifecycle_status == "DELETED",
        "merged": lifecycle_status == "MERGED",
        "active": lifecycle_status == "ACTIVE" and person.deleted_at is None,
        "enrollment_status": person.enrollment_status,
        "is_placeholder": person.enrollment_status == "placeholder",
        "notes": person.notes,
        "allowed_actions": _allowed_person_actions(lifecycle_status),
    }


def _person_summary(summary: PersonSummary, engine: FaceEngine | None = None) -> dict[str, Any]:
    embeddings = (
        engine.list_person_embeddings(
            summary.person.person_id,
            include_archived=summary.person.deleted_at is not None,
        )
        if engine
        else []
    )
    return _person_summary_from_embeddings(summary, embeddings)


def _person_summary_from_embeddings(
    summary: PersonSummary,
    embeddings: list[EmbeddingRecord] | tuple[EmbeddingRecord, ...],
) -> dict[str, Any]:
    payload = {
        **_person(summary.person),
        "embedding_count": summary.embedding_count,
        "sighting_count": summary.sighting_count,
        "last_seen_at": summary.last_seen_at,
        "first_seen_at": summary.first_seen_at,
        "frequency_per_30_days": summary.frequency_per_30_days,
        "frequency_label": summary.frequency_label,
        "favorite": bool(summary.person.metadata.get("favorite")),
        "tags": list(summary.person.metadata.get("tags", [])),
        "representative_image": _representative_image(
            embeddings,
            summary.person.metadata.get("representative_embedding_id"),
        ),
    }
    payload["presentation"] = {
        "priority_rank": _priority_rank(summary.person.metadata.get("importance")),
        "priority_label": _priority_label(summary.person.metadata.get("importance")),
        "group_labels": {
            "country": str(summary.person.metadata.get("country") or "Unknown Country"),
            "rank": str(summary.person.metadata.get("rank") or "Unspecified Rank"),
            "priority": f"{_priority_label(summary.person.metadata.get('importance'), long=True)} Priority",
            "frequency": summary.frequency_label,
            "frequent": (
                "Not Seen Yet" if summary.sighting_count == 0
                else "Frequently Seen" if summary.frequency_label in {"Very Frequent", "Frequent"}
                else "Seen Occasionally"
            ),
        },
    }
    return payload


def _allowed_person_actions(lifecycle_status: str) -> list[str]:
    return {
        "ACTIVE": [
            "OPEN", "EDIT", "EDIT_NOTES", "FAVORITE", "MANAGE_FACES",
            "ARCHIVE", "DELETE", "MERGE",
        ],
        "ARCHIVED": ["VIEW_HISTORY", "RESTORE", "DELETE"],
        "DELETED": ["VIEW_HISTORY"],
        "MERGED": ["VIEW_HISTORY", "OPEN_CANONICAL"],
    }.get(lifecycle_status, [])


def _priority_rank(value: Any) -> int:
    normalized = str(value or "").strip().lower()
    if normalized in {"important", "high"}:
        return 3
    if normalized in {"suspicious", "watch"}:
        return 2
    if normalized in {"regular", "medium"}:
        return 1
    return 0


def _priority_label(value: Any, *, long: bool = False) -> str:
    rank = _priority_rank(value)
    labels = {
        3: ("HIGH", "High"),
        2: ("WATCH", "Watch"),
        1: ("REGULAR", "Regular"),
        0: ("UNSPECIFIED", "Unspecified"),
    }
    return labels[rank][1 if long else 0]


def _people_collection_payload(engine: FaceEngine) -> dict[str, Any]:
    active_summaries = engine.list_persons()
    historical_summaries = engine.list_persons(archived=True)
    active = [_person_summary(item, engine) for item in active_summaries]
    historical = [_person_summary(item, engine) for item in historical_summaries]
    return {
        "contract_version": 1,
        "persons": active,
        "archived_persons": historical,
        "statistics": {
            "active": _people_statistics(active),
            "historical": _people_statistics(historical),
        },
        "sort_orders": {
            "active": _people_sort_orders(active),
            "historical": _people_sort_orders(historical),
        },
    }


def _people_statistics(people: list[dict[str, Any]]) -> dict[str, int]:
    now = datetime.now(timezone.utc)

    def parsed(value: Any) -> datetime | None:
        try:
            result = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
            return result.replace(tzinfo=result.tzinfo or timezone.utc)
        except ValueError:
            return None

    def today(value: Any) -> bool:
        result = parsed(value)
        return bool(result and result.astimezone(timezone.utc).date() == now.date())

    def recent(value: Any) -> bool:
        result = parsed(value)
        return bool(result and 0 <= (now - result.astimezone(timezone.utc)).total_seconds() <= 7 * 86_400)

    return {
        "people_count": len(people),
        "embedding_count": sum(int(item.get("embedding_count") or 0) for item in people),
        "favorite_count": sum(bool(item.get("favorite")) for item in people),
        "with_photos_count": sum(int(item.get("embedding_count") or 0) > 0 for item in people),
        "without_photos_count": sum(int(item.get("embedding_count") or 0) == 0 for item in people),
        "seen_last_7_days_count": sum(recent(item.get("last_seen_at")) for item in people),
        "added_today_count": sum(today(item.get("created_at")) for item in people),
        "archived_today_count": sum(today(item.get("deleted_at")) for item in people),
        "merged_count": sum(item.get("lifecycle_status") == "MERGED" for item in people),
    }


def _people_sort_orders(people: list[dict[str, Any]]) -> dict[str, list[str]]:
    def text(item: dict[str, Any], key: str) -> str:
        return str(item.get("metadata", {}).get(key) or "").casefold()

    def timestamp(value: Any) -> float:
        try:
            return datetime.fromisoformat(str(value or "").replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0

    def ordered(key: Callable[[dict[str, Any]], Any]) -> list[str]:
        return [item["person_id"] for item in sorted(people, key=key)]

    name_key = lambda item: str(item.get("name") or "").casefold()
    return {
        "name": ordered(name_key),
        "country": ordered(lambda item: (text(item, "country"), name_key(item))),
        "rank": ordered(lambda item: (text(item, "rank"), name_key(item))),
        "priority": ordered(lambda item: (-item["presentation"]["priority_rank"], name_key(item))),
        "sightings": ordered(lambda item: (-int(item.get("sighting_count") or 0), name_key(item))),
        "frequency": ordered(lambda item: (-float(item.get("frequency_per_30_days") or 0), name_key(item))),
        "seen": ordered(lambda item: (-timestamp(item.get("last_seen_at")), name_key(item))),
        "frequent": ordered(lambda item: (-float(item.get("frequency_per_30_days") or 0), name_key(item))),
        "newest": ordered(lambda item: (-timestamp(item.get("created_at")), name_key(item))),
    }


def _person_association(
    association: PersonAssociation,
    current_person_id: str,
    person_summaries: dict[str, PersonSummary],
    engine: FaceEngine,
) -> dict[str, Any]:
    associated_person_id = (
        association.target_person_id
        if association.source_person_id == current_person_id
        else association.source_person_id
    )
    summary = person_summaries.get(associated_person_id)
    if summary is None:
        raise RuntimeError("An associated person record is unavailable")
    return {
        "association_id": association.association_id,
        "source_person_id": association.source_person_id,
        "target_person_id": association.target_person_id,
        "relationship_type": association.relationship_type,
        "created_at": association.created_at,
        "updated_at": association.updated_at,
        "created_by": association.created_by,
        "association_origin": association.association_origin,
        "person": _person_summary(summary, engine),
    }


def _graph_connection_association(
    connection: GraphConnection,
    current_person_id: str,
    person_summaries: dict[str, PersonSummary],
    engine: FaceEngine,
) -> dict[str, Any]:
    associated_person_id = (
        connection.target_person_id
        if connection.source_person_id == current_person_id
        else connection.source_person_id
    )
    summary = person_summaries.get(associated_person_id)
    if summary is None:
        raise RuntimeError("A graph person record is unavailable")
    return {
        "association_id": (
            f"graph:{connection.source_person_id}:{connection.target_person_id}:"
            f"{connection.relationship_type}:{connection.directionality}"
        ),
        "source_person_id": connection.source_person_id,
        "target_person_id": connection.target_person_id,
        "relationship_type": connection.relationship_type,
        "created_at": connection.last_evidence_at,
        "updated_at": connection.last_evidence_at,
        "created_by": "Normalized evidence",
        "association_origin": "+".join(connection.evidence_types),
        "evidence_count": connection.evidence_count,
        "person": _person_summary(summary, engine),
    }


def _embedding(record: EmbeddingRecord) -> dict[str, Any]:
    return embedding_record_payload(record)


def _note_record(note: Note) -> dict[str, Any]:
    return {
        "note_id": note.note_id,
        "raw_owner_person_id": note.owner_person_id,
        "canonical_owner_person_id": note.canonical_owner_person_id or note.owner_person_id,
        "content": note.content,
        "revision_number": note.revision_number,
        "raw_mentioned_person_ids": list(note.mentioned_person_ids),
        "effective_mentioned_person_ids": list(note.effective_mentioned_person_ids),
        "status": note.status,
    }


def _profile_note_record(
    note: Note | None,
    person_summaries: dict[str, PersonSummary],
    engine: FaceEngine,
) -> dict[str, Any]:
    if note is None:
        return {
            "note_id": None,
            "content": "",
            "revision_number": 0,
            "mentioned_person_ids": [],
            "mentions": [],
        }
    mentions = []
    for raw_person_id in note.mentioned_person_ids:
        effective_person_id = engine.resolve_canonical_person_id(raw_person_id)
        summary = person_summaries.get(effective_person_id) or person_summaries.get(raw_person_id)
        person_payload = _person_summary(summary, engine) if summary is not None else None
        mentions.append({
            "occurrence_id": f"{note.note_id}:{raw_person_id}",
            "raw_person_id": raw_person_id,
            "effective_person_id": effective_person_id,
            "display_name": person_payload["name"] if person_payload else raw_person_id,
            "person": person_payload,
        })
    return {
        "note_id": note.note_id,
        "content": note.content,
        "revision_number": note.revision_number,
        "mentioned_person_ids": list(note.mentioned_person_ids),
        "effective_mentioned_person_ids": list(note.effective_mentioned_person_ids),
        "mentions": mentions,
    }


def _person_relationships(
    intelligence: PersonIntelligence,
    person_summaries: dict[str, PersonSummary],
    engine: FaceEngine,
) -> list[dict[str, Any]]:
    relationships = []
    for item in intelligence.relationships:
        summary = person_summaries.get(item.person_id)
        if summary is None:
            raise RuntimeError("A related person record is unavailable")
        relationships.append({
            "relationship_id": (
                f"relationship:{item.source_person_id}:{item.target_person_id}:"
                f"{item.relationship_type}:{item.directionality}"
            ),
            "person_id": item.person_id,
            "source_person_id": item.source_person_id,
            "target_person_id": item.target_person_id,
            "relationship_type": item.relationship_type,
            "directionality": item.directionality,
            "evidence_count": item.evidence_count,
            "evidence_type_counts": item.evidence_type_counts,
            "co_observation_count": item.co_observation_count,
            "first_evidence_at": item.first_evidence_at,
            "last_evidence_at": item.last_evidence_at,
            "presentation_label": _relationship_label(item.evidence_type_counts),
            "person": _person_summary(summary, engine),
            "manual_evidence": [{"evidence_id": evidence.evidence_id, "created_at": evidence.created_at}
                                for evidence in item.evidence if evidence.evidence_type == "MANUAL_ASSOCIATION"],
        })
    return relationships


def _relationship_label(evidence_counts: dict[str, int] | set[str] | tuple[str, ...]) -> str:
    types = set(evidence_counts)
    if len(types) > 1:
        return "Multiple evidence types"
    if "NOTE_REFERENCE" in types:
        return "Mention-linked"
    if "CO_OBSERVED" in types:
        return "Co-observed"
    if "MANUAL_ASSOCIATION" in types:
        return "Manually linked"
    return "Related"


def _graph_filters_from_query(query: str) -> GraphReadFilter:
    values = parse_qs(query)

    def one(key: str) -> str | None:
        value = values.get(key, [None])[0]
        return str(value).strip() if value is not None and str(value).strip() else None

    def many(key: str) -> tuple[str, ...]:
        result: list[str] = []
        for value in values.get(key, []):
            result.extend(item.strip() for item in str(value).split(",") if item.strip())
        return tuple(result)

    def number(key: str, caster):
        value = one(key)
        if value is None:
            return None
        try:
            return caster(value)
        except ValueError as exc:
            raise ValueError(f"Invalid graph filter: {key}") from exc

    return GraphReadFilter(
        date_from=one("date_from"),
        date_to=one("date_to"),
        location=one("location"),
        lifecycle=many("lifecycle"),
        country=many("country"),
        rank=many("rank"),
        priority=many("priority"),
        min_frequency=number("min_frequency", float),
        min_relationship_strength=number("min_relationship_strength", int),
    )


def _graph_filter_payload(filters: GraphReadFilter) -> dict[str, Any]:
    return {
        "date_from": filters.date_from,
        "date_to": filters.date_to,
        "location": filters.location,
        "lifecycle": list(filters.lifecycle),
        "country": list(filters.country),
        "rank": list(filters.rank),
        "priority": list(filters.priority),
        "min_frequency": filters.min_frequency,
        "min_relationship_strength": filters.min_relationship_strength,
    }


def _graph_read_node_payload(node: GraphReadNode) -> dict[str, Any]:
    return {
        "person_id": node.person_id,
        "canonical_person_id": node.canonical_person_id,
        "effective_person_id": node.canonical_person_id,
        "display_name": node.display_name,
        "lifecycle_status": node.lifecycle_status,
        "biometric_status": node.biometric_status,
        "representative_media_reference": node.representative_media_reference,
        "allowed_actions": list(node.allowed_actions),
        "state_indicator": node.state_indicator,
        "historical_person_ids": list(node.historical_person_ids),
        "summary_intelligence": node.summary_intelligence,
    }


def _graph_read_edge_payload(edge: GraphReadEdge) -> dict[str, Any]:
    return {
        "edge_id": f"graph:{edge.source_person_id}:{edge.target_person_id}",
        "source": edge.source_person_id,
        "target": edge.target_person_id,
        "source_person_id": edge.source_person_id,
        "target_person_id": edge.target_person_id,
        "connected_person_id": edge.connected_person_id,
        "canonical_endpoints": {
            "source_person_id": edge.canonical_source_person_id,
            "target_person_id": edge.canonical_target_person_id,
        },
        "relationship_strength": edge.relationship_strength,
        "evidence_count": edge.evidence_count,
        "evidence_types": list(edge.evidence_types),
        "first_occurrence": edge.first_occurrence_at,
        "last_occurrence": edge.last_occurrence_at,
        "directionality": edge.directionality,
        "relationship_types": list(edge.relationship_types),
        "relationship_type_summary": edge.relationship_type_summary,
        "strength_basis": edge.strength_basis,
        "provenance_summary": edge.provenance_summary,
    }


def _person_graph_read_payload(model: PersonGraphReadModel) -> dict[str, Any]:
    return {
        "contract": "sentriface.person-graph",
        "contract_version": 1,
        "graph_revision": model.graph_revision,
        "generated_at": model.generated_at,
        "requested_person_id": model.requested_person_id,
        "root_person_id": model.root_person_id,
        "root_requested_state": model.root_requested_state,
        "filters": _graph_filter_payload(model.filters),
        "nodes": [_graph_read_node_payload(item) for item in model.nodes],
        "edges": [_graph_read_edge_payload(item) for item in model.edges],
        "node_count": len(model.nodes),
        "edge_count": len(model.edges),
    }


def _world_graph_read_payload(model: WorldGraphReadModel) -> dict[str, Any]:
    return {
        "contract": "sentriface.world-graph",
        "contract_version": 1,
        "graph_revision": model.graph_revision,
        "generated_at": model.generated_at,
        "filters": _graph_filter_payload(model.filters),
        "nodes": [_graph_read_node_payload(item) for item in model.nodes],
        "edges": [_graph_read_edge_payload(item) for item in model.edges],
        "node_count": len(model.nodes),
        "edge_count": len(model.edges),
    }


def _world_graph_v2_request_from_query(query: str) -> WorldGraphRequest:
    values = parse_qs(query)

    def one(key: str) -> str | None:
        value = values.get(key, [None])[0]
        return str(value).strip() if value is not None and str(value).strip() else None

    def many(key: str) -> tuple[str, ...]:
        result: list[str] = []
        for value in values.get(key, []):
            result.extend(item.strip() for item in str(value).split(",") if item.strip())
        return tuple(result)

    def integer(key: str, default: int) -> int:
        value = one(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"Invalid World limit: {key}") from exc

    level_text = (one("level") or "WORLD_SCOPE").upper()
    below = one("include_below_threshold") or "false"
    if below.lower() not in {"true", "false"}:
        raise ValueError("include_below_threshold must be true or false")
    try:
        level = WorldDetailLevel(level_text)
    except ValueError as exc:
        raise ValueError(f"Unsupported World detail level: {level_text}") from exc
    return WorldGraphRequest(
        detail_level=level,
        collection=(WorldCollection(one("collection").upper()) if one("collection") else None),
        focus_type=one("focus_type"), focus_id=one("focus_id"),
        filters=WorldReadFilter(
            date_from=one("date_from"), date_to=one("date_to"),
            recent_activity=one("recent_activity"), locations=many("location"),
            missing_location=one("missing_location") or "INCLUDE",
            lifecycle=many("lifecycle"), identity_state=many("identity_state"),
            biometric_state=many("biometric_state"), country=many("country"),
            rank=many("rank"), priority=many("priority"),
            evidence_type=many("evidence_type"), relationship_type=many("relationship_type"),
            min_relationship_strength=(integer("min_relationship_strength", 1) if one("min_relationship_strength") else None),
            activity=many("activity"), pattern_type=many("pattern_type"),
        ),
        ranking=one("ranking") or "SALIENCE",
        limits=WorldReadLimits(
            people=integer("people_limit", 25), clusters=integer("cluster_limit", 10),
            events=integer("event_limit", 25), evidence=integer("evidence_limit", 25),
            media=integer("media_limit", 25),
            relationships=integer("relationship_limit", 50), patterns=integer("pattern_limit", 10),
            provenance=integer("provenance_limit", 100),
            facets=integer("facet_limit", 100),
        ),
        cursor=one("cursor"), revision=one("revision"), as_of=one("as_of"),
        view=one("view") or "CURRENT",
        include_below_threshold=below.lower() == "true",
        discovery_period_days=integer("discovery_period_days", 30),
        location_query=one("location_query"),
    )


def _world_graph_v2_payload(model: WorldGraphV2ReadModel) -> dict[str, Any]:
    # Normalize tuple-backed immutable models into their JSON array representation.
    payload = json.loads(json.dumps(asdict(model)))
    def remove_dormant_tokens(value: Any) -> None:
        if isinstance(value, dict):
            for key in (
                "expansion_tokens", "expansion_token", "evidence_expansion_token",
            ):
                value.pop(key, None)
            for child in value.values():
                remove_dormant_tokens(child)
        elif isinstance(value, list):
            for child in value:
                remove_dormant_tokens(child)

    remove_dormant_tokens(payload)
    payload.update({
        "contract": "sentriface.world-graph",
        "contract_version": 2,
        "filter_semantics_version": "world-filters-v1",
        "ranking_version": "descriptive-salience-v1",
        "clustering_version": "connected-evidence-components-v1",
        "calculation_version": "world-descriptive-v1",
    })
    return payload


def _person_relationship_graph(
    engine: FaceEngine,
    requested_person_id: str,
    *,
    limit: int,
) -> dict[str, Any]:
    root = engine.get_effective_person(requested_person_id)
    if root is None:
        raise KeyError("This person no longer exists")
    projection = engine.get_global_graph_projection()
    nodes_by_id = {node.person_id: node for node in projection.nodes}
    root_id = root.person_id
    if root_id not in nodes_by_id:
        raise RuntimeError("The requested person is missing from the graph projection")

    adjacency: dict[str, set[str]] = {person_id: set() for person_id in nodes_by_id}
    for connection in projection.connections:
        adjacency.setdefault(connection.source_person_id, set()).add(connection.target_person_id)
        adjacency.setdefault(connection.target_person_id, set()).add(connection.source_person_id)

    selected_ids: list[str] = []
    depths = {root_id: 0}
    queue = [root_id]
    while queue and len(selected_ids) < limit:
        person_id = queue.pop(0)
        selected_ids.append(person_id)
        for neighbor_id in sorted(adjacency.get(person_id, set())):
            if neighbor_id in depths:
                continue
            depths[neighbor_id] = depths[person_id] + 1
            queue.append(neighbor_id)

    selected = set(selected_ids)
    summaries = {
        item.person.person_id: item
        for item in [*engine.list_persons(), *engine.list_persons(archived=True)]
    }
    nodes = []
    for person_id in selected_ids:
        graph_node = nodes_by_id[person_id]
        summary = summaries.get(person_id)
        person_payload = _person_summary(summary, engine) if summary is not None else {
            "person_id": person_id,
            "name": graph_node.name,
            "lifecycle_status": graph_node.lifecycle_status,
            "canonical_person_id": graph_node.canonical_person_id,
            "effective_person_id": graph_node.canonical_person_id or person_id,
            "allowed_actions": _allowed_person_actions(graph_node.lifecycle_status),
            "representative_image": "",
            "metadata": {},
            "is_placeholder": True,
        }
        nodes.append({
            **person_payload,
            "layout": {"depth": depths[person_id]},
        })

    edges = [
        {
            "edge_id": (
                f"graph:{item.source_person_id}:{item.target_person_id}:"
                f"{item.relationship_type}:{item.directionality}"
            ),
            "source_person_id": item.source_person_id,
            "target_person_id": item.target_person_id,
            "relationship_type": item.relationship_type,
            "directionality": item.directionality,
            "evidence_count": item.evidence_count,
            "evidence_types": list(item.evidence_types),
            "last_evidence_at": item.last_evidence_at,
            "presentation_label": _relationship_label(item.evidence_types),
        }
        for item in projection.connections
        if item.source_person_id in selected and item.target_person_id in selected
    ]
    revision_payload = {
        "nodes": [
            [item["person_id"], item["canonical_person_id"], item["lifecycle_status"]]
            for item in nodes
        ],
        "edges": [
            [item["edge_id"], item["evidence_count"], item["last_evidence_at"]]
            for item in edges
        ],
    }
    graph_revision = hashlib.sha256(
        json.dumps(revision_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "contract": "sentriface.relationship-subgraph",
        "contract_version": 1,
        "graph_revision": graph_revision,
        "requested_person_id": requested_person_id,
        "root_person_id": root_id,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "truncated": len(selected_ids) < len(nodes_by_id) and bool(queue),
        "limit": limit,
    }


def _observation_record(observation: Observation) -> dict[str, Any]:
    return {
        "observation_id": observation.observation_id,
        "status": observation.status,
        "observed_at": observation.observed_at,
        "location": observation.location,
        "context": observation.context,
        "source": observation.source,
    }


def _sighting_record(sighting: Sighting) -> dict[str, Any]:
    observed_at = sighting.observed_at
    date, separator, time = observed_at.partition("T")
    media = [
        {
            "media_id": item.media_id,
            "media_path": item.media_path,
            "source": item.source,
        }
        for item in sighting.media
    ]
    return {
        "sighting_id": sighting.sighting_id,
        "detail_id": sighting.sighting_id,
        "observation_id": sighting.observation_id,
        "canonical_person_id": sighting.canonical_person_id,
        "observed_at": observed_at,
        "date": date,
        "time": time if separator else "",
        "location": sighting.location,
        "place_seen": sighting.location or "",
        "context": sighting.context,
        "event_occasion": str(sighting.context.get("occasion") or ""),
        "source": sighting.source,
        "added_by": str(sighting.context.get("added_by") or ""),
        "finalized_at": sighting.finalized_at,
        "media": media,
        "image_path": next((item["media_path"] for item in media if item["media_path"]), None),
        "raw_participant_person_ids": list(sighting.raw_participant_person_ids),
        "effective_participant_person_ids": list(sighting.effective_participant_person_ids),
        "correction_operation_ids": list(sighting.correction_operation_ids),
        "provenance": {
            "basis": "finalized observation accepted participation",
            "raw_participants_preserved": True,
            "canonical_resolution_applied": True,
        },
    }


def _person_intelligence(intelligence: PersonIntelligence) -> dict[str, Any]:
    presence = intelligence.presence
    return {
        "requested_person_id": intelligence.requested_person_id,
        "canonical_person_id": intelligence.canonical_person_id,
        "lifecycle_status": intelligence.lifecycle_status,
        "canonical_lifecycle_status": intelligence.canonical_lifecycle_status,
        "biometric_status": intelligence.biometric_status,
        "embedding_count": intelligence.embedding_count,
        "confidence_summary": intelligence.confidence_summary,
        "relationship_count": len({item.person_id for item in intelligence.relationships}),
        "presence": {
            "observation_count": presence.observation_count,
            "first_seen_at": presence.first_seen_at,
            "last_seen_at": presence.last_seen_at,
            "frequency_per_30_days": presence.frequency_per_30_days,
            "frequency_label": presence.frequency_label,
            "timeline": [
                {"period": item.period, "count": item.count}
                for item in presence.timeline
            ],
            "locations": [
                {
                    "location": item.location,
                    "count": item.count,
                    "last_observed_at": item.last_observed_at,
                }
                for item in presence.locations
            ],
            "provenance": list(presence.provenance),
        },
        "relationships": [
            {
                "person_id": item.person_id,
                "source_person_id": item.source_person_id,
                "target_person_id": item.target_person_id,
                "relationship_type": item.relationship_type,
                "directionality": item.directionality,
                "evidence_count": item.evidence_count,
                "evidence_type_counts": item.evidence_type_counts,
                "first_evidence_at": item.first_evidence_at,
                "last_evidence_at": item.last_evidence_at,
                "co_observation_count": item.co_observation_count,
                "strength": {
                    "basis": "active normalized evidence count",
                    "count": item.evidence_count,
                    "probability": None,
                },
                "evidence": [
                    {
                        "evidence_id": evidence.evidence_id,
                        "evidence_type": evidence.evidence_type,
                        "source_entity_type": evidence.source_entity_type,
                        "source_entity_id": evidence.source_entity_id,
                        "raw_source_person_id": evidence.source_person_id,
                        "raw_target_person_id": evidence.target_person_id,
                        "created_at": evidence.created_at,
                        "source": evidence.source,
                    }
                    for evidence in item.evidence
                ],
            }
            for item in intelligence.relationships
        ],
        "activity": list(intelligence.activity),
        "provenance": list(intelligence.provenance),
    }


def _deleted_embedding(record: dict[str, Any]) -> dict[str, Any]:
    purge_after = str(record.get("purge_after") or "")
    try:
        deadline = datetime.fromisoformat(purge_after)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        seconds_remaining = max(0, (deadline - datetime.now(timezone.utc)).total_seconds())
        days_remaining = max(0, int((seconds_remaining + 86_399) // 86_400))
    except ValueError:
        days_remaining = 0
    return {
        "embedding_id": record["embedding_id"],
        "person_id": record["person_id"],
        "person_name": record["name"],
        "person_lifecycle_status": record["person_lifecycle_status"],
        "canonical_person_id": record["canonical_person_id"],
        "person_archived": record["person_lifecycle_status"] == "ARCHIVED",
        "person_deleted": record["person_lifecycle_status"] == "DELETED",
        "person_merged": record["person_lifecycle_status"] == "MERGED",
        "quality_score": record["quality_score"],
        "source_image": record["source_image"],
        "crop_path": record["crop_path"],
        "created_at": record["created_at"],
        "deleted_at": record["deleted_at"],
        "purge_after": purge_after,
        "days_remaining": days_remaining,
        "sighting_count": record["sighting_count"],
    }


def _recognition_detail(
    detail: RecognitionDetail,
    canonical_person_id: str | None = None,
) -> dict[str, Any]:
    return {
        "detail_id": detail.detail_id,
        "embedding_id": detail.embedding_id,
        "person_id": detail.person_id,
        "raw_person_id": detail.person_id,
        "canonical_person_id": canonical_person_id or detail.person_id,
        "image_id": detail.image_id,
        "image_path": detail.image_path,
        "name": detail.name,
        "decision": detail.decision,
        "date": detail.seen_date,
        "time": detail.seen_time,
        "place_seen": detail.place_seen,
        "individual_count": detail.individual_count,
        "event_occasion": detail.event_occasion,
        "rank": detail.rank,
        "country": detail.country,
        "importance": detail.importance,
        "added_by": detail.added_by,
        "notes": detail.notes,
        "created_at": detail.created_at,
    }


def _person_change(change: PersonChange) -> dict[str, Any]:
    return {
        "change_id": change.change_id,
        "person_id": change.person_id,
        "previous_name": change.previous_name,
        "new_name": change.new_name,
        "previous_rank": change.previous_rank,
        "new_rank": change.new_rank,
        "previous_country": change.previous_country,
        "new_country": change.new_country,
        "previous_importance": change.previous_importance,
        "new_importance": change.new_importance,
        "previous_status": change.previous_status,
        "new_status": change.new_status,
        "previous_notes": change.previous_notes,
        "new_notes": change.new_notes,
        "editor_name": change.editor_name,
        "created_at": change.created_at,
    }


def _representative_init_face(group: InitGroup):
    if not group.faces:
        return None
    return max(group.faces, key=lambda face: face.quality.score)


def _init_session_summary(session: InitSession, groups: list[InitGroup]) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "source_path": session.source_path,
        "status": session.status,
        "target_observation_id": session.target_observation_id,
        "expected_encounter_revision": session.expected_encounter_revision,
        "created_at": session.created_at,
        "group_count": len(groups),
        "face_count": sum(len(group.faces) for group in groups),
        "pending_count": sum(1 for group in groups if group.status == "pending" and group.faces),
        "skipped_count": sum(1 for group in groups if group.status == "skipped" and group.faces),
    }


def _filtered_matches(matches: list[PersonMatch], excluded_person_ids: set[str]) -> list[PersonMatch]:
    if not excluded_person_ids:
        return matches
    return [match for match in matches if match.person_id not in excluded_person_ids]


def _group_matches_from_face_matches(
    face_matches: list[list[PersonMatch]],
    top_k: int,
) -> list[PersonMatch]:
    best_by_person: dict[str, PersonMatch] = {}
    for matches in face_matches:
        for match in matches:
            current = best_by_person.get(match.person_id)
            if current is None or match.score > current.score:
                best_by_person[match.person_id] = match
    group_matches = sorted(best_by_person.values(), key=lambda match: match.score, reverse=True)
    return group_matches[:top_k]


def _representative_image(
    embeddings: list[EmbeddingRecord],
    representative_embedding_id: str | None = None,
) -> str | None:
    if representative_embedding_id:
        for record in embeddings:
            if record.embedding_id == representative_embedding_id:
                return record.crop_path or record.source_image
    for record in embeddings:
        if record.crop_path:
            return record.crop_path
    for record in embeddings:
        if record.source_image:
            return record.source_image
    return None


def _available_image_path(*candidates: str | None) -> str | None:
    """Prefer the first image that is still available, then a stable fallback.

    Queue crops should normally exist, but an interrupted cleanup or manually
    moved data must not make a whole group look empty when its source upload is
    still readable.
    """
    paths = [candidate for candidate in candidates if candidate]
    for candidate in paths:
        if Path(candidate).is_file():
            return candidate
    return paths[0] if paths else None


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _box(face) -> dict[str, Any]:
    return {
        "x": face.box.x,
        "y": face.box.y,
        "width": face.box.width,
        "height": face.box.height,
        "confidence": face.box.confidence,
        "quality_score": face.quality_score,
        "crop_path": face.crop_path,
    }


def _quality(report: QualityReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {"status": report.status.value, "score": report.score, "reasons": list(report.reasons)}


def _sanitize_log_details(details: dict[str, Any]) -> dict[str, Any]:
    """Keep production events useful without retaining image/vector payloads."""
    sanitized = sanitize_log_details(details)
    return sanitized if isinstance(sanitized, dict) else {}


def _backup(record: BackupRecord) -> dict[str, Any]:
    return {
        "backup_id": record.backup_id,
        "created_at": record.created_at,
        "size_bytes": record.size_bytes,
        "people_count": record.people_count,
        "embedding_count": record.embedding_count,
        "verified": record.verified,
        "reason": record.reason,
        "operation_id": record.operation_id,
        "format_version": record.format_version,
        "portable": record.portable,
        "complete": record.complete,
        "file_count": record.file_count,
        "missing_file_count": record.missing_file_count,
        "reference_count": record.reference_count,
        "restorable": record.restorable,
        "integrity_status": record.integrity_status,
    }
