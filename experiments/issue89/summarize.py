"""Produce the per-scenario Measure | A | B | B' | Equivalent? tables from saved measurements.

    python -m experiments.issue89.summarize > experiments/issue89/evidence/TABLES.md
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from .build import RUNS, load
from .harness import compare


def _rows(m, table):
    return [json.loads(r) for r in m["db"].get(table, [])]


def _api(m, key):
    value = m["api"].get(key)
    return value[1] if isinstance(value, (list, tuple)) and value and value[0] == 200 else None


def metrics(m) -> dict:
    out = {}
    persons = _rows(m, "persons")
    out["Persons by lifecycle"] = dict(sorted(Counter(p["lifecycle_status"] for p in persons).items()))
    out["ENROLLED / NO_FACE (active)"] = dict(sorted(Counter(p["biometric_status"] for p in persons if p["lifecycle_status"] == "ACTIVE").items()))
    obs = [o for o in _rows(m, "observations") if o["status"] == "FINALIZED"]
    out["Finalized Events (rows)"] = len(obs)
    events = _api(m, "events")
    out["Events list (API)"] = len(events["events"]) if events else None
    out["Effective participants (rows)"] = len(_rows(m, "observation_participants"))
    sightings, seen = 0, {}
    people = _api(m, "persons") or {}
    for p in people.get("persons", []):
        seen[p["name"]] = (str(p.get("first_seen_at"))[:10], str(p.get("last_seen_at"))[:10], p.get("frequency_per_30_days"))
    for key in m["api"]:
        if key.endswith(".sightings"):
            s = _api(m, key)
            sightings += len(s["sightings"]) if s else 0
    out["Sightings (sum over People)"] = sightings
    out["First/last seen, freq/30d"] = "; ".join(f"{k} {v[0]}→{v[1]} f{v[2]}" for k, v in sorted(seen.items()))
    out["Event media refs (observation_media)"] = len(_rows(m, "observation_media"))
    files = m["files"]
    out["Physical files (uploads/objects, faces, other)"] = (sum(1 for f in files if f.startswith("uploads/objects")),
                                                            sum(1 for f in files if f.startswith("faces/")),
                                                            sum(1 for f in files if not f.startswith(("uploads/objects", "faces/"))))
    emb = _rows(m, "embeddings")
    out["Face samples by state"] = dict(sorted(Counter(e["recognition_state"] for e in emb).items()))
    out["Recognition-eligible samples"] = len(m["eligibility"])
    rec = m["recognition"]["linear.quality_only=True"]
    out["Recognition top-1 (probe→name score)"] = "; ".join(f"{r['probe'].split('-')[0]}→{r['matches'][0]['name'] if r['matches'] else '-'} {r['matches'][0]['score']:.3f}" if r["matches"] else f"{r['probe']}→-" for r in rec)
    def ranked(key):
        return [(r["probe"], [(x["name"], round(x["score"], 4)) for x in r["matches"]]) for r in m["recognition"][key]]
    out["Linear == HNSW ranking (4 d.p.)"] = all(ranked(f"linear.quality_only={q}") == ranked(f"hnsw.quality_only={q}") for q in (True, False))
    notes = _rows(m, "notes")
    out["Notes by scope (active)"] = dict(sorted(Counter(n["subject_type"] for n in notes if n["status"] == "ACTIVE").items()))
    out["Active structured mentions"] = sum(1 for x in _rows(m, "note_mentions") if x["active"])
    out["Event Note selected mentions"] = sum(len(json.loads(o["context"] or "{}").get("event_mentioned_person_ids") or []) for o in obs)
    ev = _rows(m, "relationship_evidence")
    out["Active evidence by type"] = dict(sorted(Counter(e["evidence_type"] for e in ev if e["active"]).items()))
    out["Graph connections (projection rows)"] = len(_rows(m, "graph_connections"))
    rg = _api(m, "person[Alder].relationship-graph")
    out["Person Graph edges (Alder view)"] = rg.get("edge_count") if rg else None
    for view in ("connections", "explore"):
        clusters = _api(m, f"world.{view}.CLUSTERS")
        names = []
        for c in (clusters or {}).get("clusters", []):
            names.append("{" + ",".join(sorted(p["display_name"] for p in c.get("member_preview", []))) + "}")
        out[f"World {view} clusters"] = " ".join(sorted(names))
        rels = _api(m, f"world.{view}.RELATIONSHIPS")
        out[f"World {view} relationships"] = len((rels or {}).get("relationships", []))
    for key, label in (("world.connections.MOST_FREQUENTLY_SEEN[30]", "Discoveries: frequent (30d)"),
                       ("world.connections.MOST_RECENTLY_SEEN", "Discoveries: most recent"),
                       ("world.connections.MULTIPLE_LOCATIONS[90]", "Discoveries: multiple locations (90d)")):
        d = _api(m, key)
        out[label] = "; ".join(f"{x['display_name']}:{x['count']}" for x in (d or {}).get("discoveries", []))
    for loc in ("Delhi", "Goa", "Mumbai", "Pune"):
        s = _api(m, f"events.search[{loc}]")
        out[f"Events search '{loc}'"] = len(s["events"]) if s else None
    pages = m["api"].get("events.pages(limit=2)") or []
    out["Events pages (limit 2)"] = len(pages)
    pending = _api(m, "pending") or {}
    out["Staged proposals naming erased/unknown"] = sum(1 for p in pending.get("pending", []) for x in p.get("matches", []) if x.get("name") == "unknown")
    out["Integrity (P11)"] = m["integrity"]["status"] + (" " + ",".join(f.get("invariant_id") for f in m["integrity"]["findings"]) if m["integrity"]["findings"] else "")
    out["Operation journal rows"] = len(_rows(m, "operation_journal"))
    out["Graph revision"] = (_rows(m, "graph_state") or [{}])[0].get("revision")
    return out


def table(sid: str, variant: str) -> str:
    data = load(RUNS / sid / f"measure-{variant}.pkl")
    ma, mb, mbp = metrics(data["A"]), metrics(data["B"]), metrics(data["Bprime"])
    lines = [f"### {sid} — variant {variant}", "", "| Measure | Database A | Database B | Database B′ | Equivalent? |", "|---|---|---|---|---|"]
    for key in ma:
        eq = "yes" if ma[key] == mbp[key] else "**no**"
        fmt = lambda v: str(v).replace("|", "/")  # noqa: E731
        lines.append(f"| {key} | {fmt(ma[key])} | {fmt(mb[key])} | {fmt(mbp[key])} | {eq} |")
    full = compare.summary(compare.compare(data["A"], data["Bprime"]))
    lines += ["", f"Differential totals A vs B′: DB tables differing {sorted(full['db_tables_different'])}; "
                  f"API reads differing {len(full['api_different'])}/{full['api_total']} (+{len(full['api_order_only'])} ordering-only); "
                  f"files equal={full['files_equal']}; eligibility equal={full['eligibility_equal']}; recognition differing={full['recognition_different']}", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    runs = [a.split(":") for a in sys.argv[1:]] or [(s, "H2") for s in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")] + \
        [("S1", "H1"), ("S1", "H1b")] + [(s, "L") for s in ("S1", "S2", "S4", "S5", "S6")]
    for sid, variant in runs:
        print(table(sid, variant))
