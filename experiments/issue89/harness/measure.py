"""Measurement battery: database rows, physical media, backend reads, World,
recognition and integrity. Every measurement is read-only with respect to the
authority (recognize-batch does not stage reviews; integrity/check is a read).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import quote, urlencode

from .app import KIT, App
from .env import DET

MEASURE_AT = "2026-05-31T12:00:00+00:00"
PROBE_DIR_NAME = "probes"


def _canon(value):
    if isinstance(value, (bytes, memoryview)):
        return "blob:" + hashlib.sha256(bytes(value)).hexdigest()[:16]
    return value


def db_rows(app: App) -> dict[str, list[str]]:
    """Every row of every table (sorted, authority prefix normalized)."""
    root = str(app.data_dir)
    tables = {}
    with app.store._connect() as conn:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for name in names:
            cursor = conn.execute(f"SELECT * FROM main.{name}")  # physical rows, never TEMP shadows
            columns = [d[0] for d in cursor.description]
            rows = []
            for row in cursor.fetchall():
                record = {c: _canon(v) for c, v in zip(columns, row)}
                rows.append(json.dumps(record, sort_keys=True, default=str).replace(root, "<AUTH>"))
            tables[name] = sorted(rows)
        tables["__schema__"] = sorted(
            json.dumps([t, n, s], default=str) for t, n, s in conn.execute(
                "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
    return tables


def files(app: App) -> dict[str, str]:
    """Managed media/crop objects -> plaintext SHA-256 (decrypted with the authority key)."""
    from sentriface.secure_files import read_protected_bytes
    key = app.engine.config.storage_key
    result = {}
    for sub in ("uploads", "faces", "restored-media"):
        base = app.data_dir / sub
        if not base.exists():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            try:
                data = read_protected_bytes(path, key)
            except Exception:
                data = path.read_bytes()
            result[str(path.relative_to(app.data_dir))] = hashlib.sha256(data).hexdigest()
    return result


def eligibility(app: App) -> list[dict]:
    from sentriface.storage.sqlite_helpers import _eligible_source_samples
    with app.store._connect() as conn:
        samples = _eligible_source_samples(conn)
        names = dict(conn.execute("SELECT person_id, name FROM persons").fetchall())
    out = []
    for sample in samples:
        item = dict(sample) if isinstance(sample, dict) else {k: getattr(sample, k) for k in dir(sample) if not k.startswith("_") and not callable(getattr(sample, k))}
        item = {k: _canon(v) for k, v in item.items() if k != "vector"}
        out.append(item)
    root = str(app.data_dir)
    return sorted((json.dumps(o, sort_keys=True, default=str).replace(root, "<AUTH>") for o in out))


def _people(app: App) -> dict[str, str]:
    with app.store._connect() as conn:
        return {name: pid for pid, name in conn.execute("SELECT person_id, name FROM persons ORDER BY name, created_at")}


def _events(app: App) -> dict[str, str]:
    with app.store._connect() as conn:
        rows = conn.execute("SELECT observation_id, context FROM observations").fetchall()
    return {json.loads(c or "{}").get("occasion") or oid: oid for oid, c in rows}


def _get(app: App, path: str):
    """One read = one clock slot, so as_of/read timestamps do not depend on how
    many clock calls earlier reads happened to make. Authority root normalized."""
    with DET.step("measure.read", MEASURE_AT):
        status, payload = app.request("GET", path, expect=None)
    text = json.dumps(payload, default=str).replace(str(app.data_dir), "<AUTH>")
    return status, json.loads(text)


def api_reads(app: App) -> dict[str, object]:
    out: dict[str, object] = {}
    get = lambda path: _get(app, path)  # noqa: E731
    people, events = _people(app), _events(app)
    out["persons"] = get("/api/persons")
    out["deleted-faces"] = get("/api/deleted-faces")
    out["pending"] = get("/api/pending")
    out["queue-sessions"] = get("/api/queue-sessions")
    out["graph-revision"] = get("/api/graph-revision")
    for name, pid in people.items():
        for suffix, path in {
            "raw": f"/api/person?person_id={pid}&view=raw&include_archived=1",
            "effective": f"/api/person?person_id={pid}",
            "sightings": f"/api/person-sightings?person_id={pid}",
            "intelligence": f"/api/person-intelligence?person_id={pid}",
            "graph": f"/api/person-graph?person_id={pid}",
            "relationship-graph": f"/api/person-relationship-graph?person_id={pid}&limit=60",
            "neighbors": f"/api/person-association-neighbors?person_id={pid}&include_archived=1&limit=30",
            "events-participant": f"/api/encounters?participant_id={pid}",
            "events-mentioned": f"/api/encounters?mentioned_person_id={pid}",
            "events-person": f"/api/encounters?person_id={pid}",
        }.items():
            out[f"person[{name}].{suffix}"] = get(path)
    out["events"] = get("/api/encounters")
    page, cursor, pages = 0, None, []
    while page < 20:
        result = get("/api/encounters?limit=2" + (f"&cursor={quote(cursor)}" if cursor else ""))
        status, payload = result
        pages.append(result)
        cursor = payload.get("next_cursor") if isinstance(payload, dict) else None
        page += 1
        if not cursor:
            break
    out["events.pages(limit=2)"] = pages
    for location in ("Delhi", "Pune", "Mumbai", "Goa"):
        out[f"events.search[{location}]"] = get(f"/api/encounters?search={location}")
        out[f"events.location[{location}]"] = get(f"/api/encounters?location={location}")
    out["events.date[2026-03]"] = get("/api/encounters?date_from=2026-03-01&date_to=2026-03-31")
    for occasion, oid in events.items():
        out[f"event[{occasion}]"] = get(f"/api/encounter?observation_id={oid}")
    out.update(world(app, people, events))
    return out


def _world_query(**params):
    base = {"version": "2", "level": "WORLD_SCOPE", "ranking": "SALIENCE", "people_limit": "25", "cluster_limit": "10",
            "relationship_limit": "50", "pattern_limit": "10", "facet_limit": "100", "missing_location": "INCLUDE"}
    base.update(params)
    items = []
    for key, value in base.items():
        for v in (value if isinstance(value, list) else [value]):
            items.append((key, v))
    return "/api/world-graph?" + urlencode(items)


def world(app: App, people: dict, events: dict) -> dict:
    out = {}
    get = lambda path: _get(app, path)  # noqa: E731
    views = {
        "connections": {"view": "CURRENT"},
        "explore": {"view": "EXPLORE", "evidence_type": ["CO_OBSERVED"], "min_relationship_strength": "2", "include_below_threshold": "true"},
        "explore-all-1": {"view": "EXPLORE", "evidence_type": ["CO_OBSERVED", "NOTE_REFERENCE", "MANUAL_ASSOCIATION"], "min_relationship_strength": "1", "include_below_threshold": "true"},
    }
    for vname, view in views.items():
        for collection in ("PEOPLE", "CLUSTERS", "RELATIONSHIPS", "PATTERNS"):
            out[f"world.{vname}.{collection}"] = get(_world_query(collection=collection, **view))
        for period in ("7", "30", "90"):
            for collection in ("MOST_FREQUENTLY_SEEN", "MULTIPLE_LOCATIONS"):
                out[f"world.{vname}.{collection}[{period}]"] = get(_world_query(collection=collection, discovery_period_days=period, **view))
        out[f"world.{vname}.MOST_RECENTLY_SEEN"] = get(_world_query(collection="MOST_RECENTLY_SEEN", **view))
        out[f"world.{vname}.LOCATION_SUGGESTIONS"] = get(_world_query(collection="LOCATION_SUGGESTIONS", location_query="del", **view))
        status, scope = out[f"world.{vname}.CLUSTERS"]
        if status != 200:
            continue
        binding = {"revision": scope["graph_revision"], "as_of": scope["as_of"]}
        for cluster in scope.get("clusters", []) or []:
            cid = cluster.get("cluster_id")
            label = ",".join(sorted(p["display_name"] for p in cluster.get("member_preview", []))) or cid
            for collection in ("MEMBERS", "RELATIONSHIPS"):
                out[f"world.{vname}.cluster[{label}].{collection}"] = get(
                    _world_query(level="CLUSTER", focus_type="CLUSTER", focus_id=cid, collection=collection, **view, **binding))
        for name, pid in people.items():
            for collection in ("RELATIONSHIPS", "EVENTS"):
                out[f"world.{vname}.person[{name}].{collection}"] = get(_world_query(level="PERSON", focus_type="PERSON", focus_id=pid,
                                                                                    collection=collection, event_limit="25", **view, **binding))
        if vname == "explore-all-1":
            for occasion, oid in events.items():
                for collection in ("PARTICIPANTS", "PROVENANCE", "EVIDENCE", "MEDIA"):
                    out[f"world.{vname}.event[{occasion}].{collection}"] = get(_world_query(
                        level="EVENT", focus_type="EVENT", focus_id=oid, collection=collection, provenance_limit="100",
                        evidence_limit="25", media_limit="25", **view, **binding))
            status, rels = out[f"world.{vname}.RELATIONSHIPS"]
            for rel in (rels.get("relationships") or []) if status == 200 else []:
                rid = rel.get("relationship_id")
                label = "|".join(sorted([str(rel.get("source_display_name") or rel.get("source_person_id")), str(rel.get("target_display_name") or rel.get("target_person_id"))]))
                out[f"world.{vname}.relationship[{label}].EVIDENCE"] = get(_world_query(
                    level="EVIDENCE", focus_type="RELATIONSHIP", focus_id=rid, collection="EVIDENCE", evidence_limit="25",
                    media_limit="25", **view, **binding))
    return out


def recognition(app: App, probes: list[str]) -> dict:
    """Genuine ONNX recognition of held-out probe photos (no staging writes)."""
    probe_dir = app.data_dir.parent / PROBE_DIR_NAME
    probe_dir.mkdir(exist_ok=True)
    for name in probes:
        target = probe_dir / f"{name}.jpg"
        if not target.exists():
            target.write_bytes((KIT / f"{name}.jpg").read_bytes())
    out = {}
    original = app.index_backend or "linear"
    for backend in ("linear", "hnsw"):
        app.use_index(backend)
        for quality_only in (True, False):
            with DET.step("measure.recognize", MEASURE_AT):
                result = app.post("/api/recognize-batch", {"path": str(probe_dir), "quality_only": quality_only})
            rows = []
            for item in result["batch"]:
                for face in item["faces"]:
                    rows.append({"probe": Path(item["image"]).stem, "decision": face.get("decision"),
                                 "matches": [{"name": m["name"], "score": round(m["score"], 6), "classification": m["classification"],
                                              "embeddings_matched": m.get("embeddings_matched")} for m in face["matches"]]})
            out[f"{backend}.quality_only={quality_only}"] = sorted(rows, key=lambda r: r["probe"])
    app.use_index(original)
    return out


def integrity(app: App) -> dict:
    report = app.post("/api/integrity/check")
    findings = report.get("findings") or report.get("issues") or []
    return {"status": report.get("status") or report.get("overall_status"), "raw": report, "findings": findings}


def cluster_aliases(api: dict) -> dict:
    """Revision-bound cluster IDs -> member-name labels (from untruncated previews)."""
    aliases = {}
    def walk(value):
        if isinstance(value, dict):
            if str(value.get("cluster_id", "")).startswith("cluster:") and value.get("member_preview") and not (value.get("member_preview_state") or {}).get("truncated"):
                aliases[value["cluster_id"]] = "<C:" + ",".join(sorted(p["display_name"] for p in value["member_preview"])) + ">"
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
    walk(api)
    return aliases


def measure_all(app: App, probes: list[str]) -> dict:
    with DET.step("measure", MEASURE_AT):
        api = api_reads(app)
        return {"db": db_rows(app), "files": files(app), "eligibility": eligibility(app), "api": api,
                "cluster_aliases": cluster_aliases(api), "recognition": recognition(app, probes), "integrity": integrity(app)}
