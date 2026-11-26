"""Build Database A / Database B authorities for a scenario through the real app."""
from __future__ import annotations

import json
import os
import pickle
from pathlib import Path

from .harness.app import App
from .harness.workflows import Operator
from .scenarios import SCENARIOS, base

RUNS = Path(os.environ.get("ISSUE89_RUNS", "/projects/sandbox/runs"))


def authority(sid: str, variant: str) -> Path:
    return RUNS / sid / variant / "data"


def build(sid: str, variant: str, *, keep_running=False):
    """variant: 'A' (control, X never existed) or 'B' (experimental, with X)."""
    scenario = SCENARIOS[sid]
    app = App(authority(sid, variant), fresh=True).start()
    op = Operator(app)
    base(op)
    if variant == "B":
        scenario.x(op)
    scenario.post(op, variant)
    log = authority(sid, variant).parent / "recognition-proposals.json"
    log.write_text(json.dumps(op.recognition_log, indent=1))
    (authority(sid, variant).parent / "probes.json").write_text(json.dumps(getattr(op, "probes", {}), indent=1, default=str))
    if keep_running:
        return app, op
    app.stop()
    return None


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        pickle.dump(data, stream)


def load(path: Path):
    with Path(path).open("rb") as stream:
        return pickle.load(stream)
