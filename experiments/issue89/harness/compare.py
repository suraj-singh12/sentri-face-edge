"""Differential comparison of two measurements (Database A vs B / B')."""
from __future__ import annotations

import json
import re

# Keys whose values are generated tokens bound to the graph revision counter or
# wall-clock report time. Their differences are *counted and reported*, never
# silently dropped (see ``normalized_token_differences``).
TOKEN_KEYS = {"graph_revision", "revision", "next_cursor", "cursor", "report_token", "started_at", "completed_at",
              "current_revision", "changed", "encounter_revision", "expected_revision", "retrieval"}

# Tables whose rows are security/session audit history written with the real
# clock (sign-in at every application start). Justified difference class S.
SECURITY_TABLES = {"app_users", "auth_audit"}


def alias_map(db: dict) -> dict[str, str]:
    """Generated identifiers -> stable domain labels (Person name, Event occasion)."""
    aliases = {}
    for row in db.get("persons", []):
        r = json.loads(row)
        aliases[r["person_id"]] = f"<P:{r['name']}>"
    for row in db.get("observations", []):
        r = json.loads(row)
        occasion = json.loads(r.get("context") or "{}").get("occasion")
        if occasion:
            aliases[r["observation_id"]] = f"<E:{occasion}>"
    return aliases


def _apply(text: str, aliases: dict[str, str]) -> str:
    if not aliases:
        return text
    pattern = re.compile("|".join(re.escape(k) for k in sorted(aliases, key=len, reverse=True)))
    return pattern.sub(lambda m: aliases[m.group(0)], text)


def diff_db(a: dict, b: dict, *, alias=True, extra_a=None, extra_b=None) -> dict:
    aa, ab = (alias_map(a), alias_map(b)) if alias else ({}, {})
    aa, ab = {**aa, **(extra_a or {})}, {**ab, **(extra_b or {})}
    out = {}
    for table in sorted(set(a) | set(b)):
        ra = {_apply(r, aa) for r in a.get(table, [])}
        rb = {_apply(r, ab) for r in b.get(table, [])}
        only_a, only_b = sorted(ra - rb), sorted(rb - ra)
        out[table] = {"A": len(a.get(table, [])), "B": len(b.get(table, [])), "only_A": only_a, "only_B": only_b,
                      "equal": not only_a and not only_b}
    return out


def _strip_tokens(value, counter, path=""):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in TOKEN_KEYS:
                result[key] = "<token>"
                counter.append(f"{path}.{key}")
            else:
                result[key] = _strip_tokens(item, counter, f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [_strip_tokens(item, counter, f"{path}[]") for item in value]
    if isinstance(value, str) and re.fullmatch(r"g\d+", value):
        counter.append(f"{path}=<graph revision>")
        return "<token>"
    return value


def _first_differences(x, y, path="", limit=6, out=None):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if type(x) is not type(y):
        out.append(f"{path}: {json.dumps(x)[:160]} != {json.dumps(y)[:160]}")
    elif isinstance(x, dict):
        for key in sorted(set(x) | set(y)):
            if key not in x or key not in y:
                out.append(f"{path}.{key}: {'missing in A' if key not in x else 'missing in B'}")
            else:
                _first_differences(x[key], y[key], f"{path}.{key}", limit, out)
    elif isinstance(x, list):
        if len(x) != len(y):
            out.append(f"{path}: len {len(x)} != {len(y)}")
        for index, (i, j) in enumerate(zip(x, y)):
            _first_differences(i, j, f"{path}[{index}]", limit, out)
    elif x != y:
        out.append(f"{path}: {json.dumps(x)[:160]} != {json.dumps(y)[:160]}")
    return out


def _canonical(value):
    """Order-insensitive form (lists sorted, rank positions dropped) used only to
    *classify* a difference as ordering-only; it never makes payloads equal."""
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items() if k not in {"rank_position", "ranking"}}
    if isinstance(value, list):
        return sorted((_canonical(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    return value


def diff_json(a: dict, b: dict, aliases_a: dict, aliases_b: dict, root_a: str = "", root_b: str = "") -> dict:
    out = {}
    for key in sorted(set(a) | set(b)):
        if key not in a or key not in b:
            out[key] = {"equal": False, "detail": ["missing in A" if key not in a else "missing in B"]}
            continue
        tokens_a, tokens_b = [], []
        ja = json.loads(_apply(json.dumps(_strip_tokens(a[key], tokens_a), sort_keys=True, default=str), aliases_a))
        jb = json.loads(_apply(json.dumps(_strip_tokens(b[key], tokens_b), sort_keys=True, default=str), aliases_b))
        equal = ja == jb
        out[key] = {"equal": equal, "tokens_normalized": len(tokens_a)}
        if not equal:
            out[key]["detail"] = _first_differences(ja, jb)
            out[key]["order_only"] = _canonical(ja) == _canonical(jb)
    return out


def _restored_paths(files: dict) -> dict:
    """Restore relocates registry-owned media to restored-media/<dir>/<random>.
    Physical location is not portable identity (DOMAIN_MODEL Batch 3.6), so
    relocated paths are aliased to their plaintext content hash only."""
    return {f"<AUTH>/{path}": f"<RESTORED:{digest[:16]}>" for path, digest in files.items() if path.startswith("restored-media/")}


def compare(ma: dict, mb: dict) -> dict:
    aa = {**alias_map(ma["db"]), **ma.get("cluster_aliases", {}), **_restored_paths(ma["files"])}
    ab = {**alias_map(mb["db"]), **mb.get("cluster_aliases", {}), **_restored_paths(mb["files"])}
    db = diff_db(ma["db"], mb["db"], extra_a=aa, extra_b=ab)
    files_a, files_b = ma["files"], mb["files"]
    fa = {_apply("<AUTH>/" + k, aa): v for k, v in files_a.items()}
    fb = {_apply("<AUTH>/" + k, ab): v for k, v in files_b.items()}
    files = {"A": len(fa), "B": len(fb), "only_A": sorted(set(fa.items()) - set(fb.items())),
             "only_B": sorted(set(fb.items()) - set(fa.items()))}
    files["equal"] = not files["only_A"] and not files["only_B"]
    elig_a = sorted(_apply(x, aa) for x in ma["eligibility"])
    elig_b = sorted(_apply(x, ab) for x in mb["eligibility"])
    api = diff_json(ma["api"], mb["api"], aa, ab)
    rec = {k: {"equal": ma["recognition"][k] == mb["recognition"].get(k)} for k in ma["recognition"]}
    for k, v in rec.items():
        if not v["equal"]:
            v["detail"] = _first_differences(ma["recognition"][k], mb["recognition"].get(k))
    integ = {"A": ma["integrity"]["status"], "B": mb["integrity"]["status"],
             "A_findings": [f"{f.get('invariant_id')}:{f.get('severity')}" for f in ma["integrity"]["findings"]],
             "B_findings": [f"{f.get('invariant_id')}:{f.get('severity')}" for f in mb["integrity"]["findings"]]}
    return {"db": db, "files": files, "eligibility": {"equal": elig_a == elig_b, "A": len(elig_a), "B": len(elig_b),
                                                      "only_A": sorted(set(elig_a) - set(elig_b)), "only_B": sorted(set(elig_b) - set(elig_a))},
            "api": api, "recognition": rec, "integrity": integ}


def summary(result: dict) -> dict:
    db_bad = {t: (v["A"], v["B"], len(v["only_A"]), len(v["only_B"])) for t, v in result["db"].items() if not v["equal"]}
    api_bad = [k for k, v in result["api"].items() if not v["equal"] and not v.get("order_only")]
    api_order = [k for k, v in result["api"].items() if not v["equal"] and v.get("order_only")]
    return {"db_tables_different": db_bad, "files_equal": result["files"]["equal"],
            "files": (result["files"]["A"], result["files"]["B"], len(result["files"]["only_A"]), len(result["files"]["only_B"])),
            "eligibility_equal": result["eligibility"]["equal"], "api_total": len(result["api"]), "api_different": api_bad, "api_order_only": api_order,
            "recognition_different": [k for k, v in result["recognition"].items() if not v["equal"]],
            "integrity": result["integrity"]}
