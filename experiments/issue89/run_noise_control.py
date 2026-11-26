"""Harness noise control: build the same Database twice and compare.

    python -m experiments.issue89.run_noise_control

A differential method is only meaningful if two independent builds of the same
operations are identical except for the documented security-audit rows. This
builds S1 Database A twice (separate authorities, separate keys) and reports
every difference.
"""
from __future__ import annotations

import json

from .build import authority, build
from .harness import compare, measure
from .harness.app import App
from .run_scenario import EVIDENCE
from .scenarios import PROBES


def run() -> dict:
    results = {}
    measurements = []
    for sid in ("S1", "S1noise"):
        if sid == "S1noise":
            from .scenarios import SCENARIOS
            SCENARIOS["S1noise"] = SCENARIOS["S1"]
        build(sid, "A")
        app = App(authority(sid, "A")).start()
        measurements.append(measure.measure_all(app, PROBES))
        app.stop()
    full = compare.compare(*measurements)
    results["summary"] = compare.summary(full)
    results["db_detail"] = {t: {"only_first": v["only_A"][:3], "only_second": v["only_B"][:3]} for t, v in full["db"].items() if not v["equal"]}
    path = EVIDENCE / "noise-control"
    path.mkdir(parents=True, exist_ok=True)
    (path / "report.json").write_text(json.dumps(results, indent=1, default=str))
    return results


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=str)[:6000])
