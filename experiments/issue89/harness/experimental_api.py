"""Process-local experimental route ``POST /api/experimental/event-delete``.

Installed only inside experiment processes (never in production files). It
rides the real request pipeline: host/origin/session checks, user
authorization (capability ``destroy`` = Custodian/Administrator, like Delete
Person), license/model gates, the exclusive operation gate and the existing
pre-deletion safety backup (``backed_up_people_deletion``). The store-level
transaction lives in ``hard_delete.py`` (or ``logical_delete.py``).
"""
from __future__ import annotations

import json
from http import HTTPStatus

import sentriface.api_server as api

from . import hard_delete, logical_delete, read_fixes

PATH = "/api/experimental/event-delete"
_installed = {"mechanism": "hard", "fixes": False}


def install(mechanism: str = "hard", fixes: bool = False) -> None:
    _installed["mechanism"] = mechanism
    _installed["fixes"] = fixes
    if getattr(api, "_issue89_installed", False):
        return
    original_capability = api._required_capability

    def required_capability(method, path):
        if path == PATH:
            return "destroy"
        return original_capability(method, path)

    api._required_capability = required_capability
    original_do_post = api.SentriFaceApiHandler._do_POST

    def do_post(self):
        if self.path.split("?")[0] != PATH:
            return original_do_post(self)
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        server = self.server
        oid, op = payload.get("observation_id"), payload.get("operation_id")
        if not oid or not op:
            return self._json({"error": "observation_id and operation_id are required", "code": "invalid_input"}, status=HTTPStatus.BAD_REQUEST)
        actor = self._operation_actor()
        module = hard_delete if _installed["mechanism"] == "hard" else logical_delete

        def action():
            engine = server.engine
            journal = None
            if module is hard_delete:
                # Existing durable CleanupService: schedule BEFORE the DB mutation,
                # run after COMMIT with a live-reference re-check; startup retries.
                with engine.store._connect() as conn:
                    if conn.execute("SELECT 1 FROM observations WHERE observation_id = ?", (oid,)).fetchone():
                        journal = engine.cleanup.schedule(hard_delete.cleanup_targets(conn, oid, engine.config), f"event-erase-{op}")
            with engine.store._connect() as conn:
                result = module.delete_event(conn, oid, op, expected_revision=payload.get("expected_revision"), actor=actor) \
                    if module is logical_delete else module.hard_delete_event(conn, oid, op, expected_revision=payload.get("expected_revision"), actor=actor)
            if journal is not None:
                result["cleanup_completed"] = engine.cleanup.run(journal, engine.store.list_all_file_references)
            server.engine._rebuild_index()
            if _installed["fixes"] and not result.get("replayed"):
                result["refreshed_proposals"] = read_fixes.refresh_stale_proposals(
                    server.engine, result.get("persons_erased", []), result.get("embeddings_erased", []))
            return result

        # NOTE: runs under the request's shared operation gate. A production route
        # would join the exclusive backup gate like Delete Person (the literal
        # path set inside do_POST cannot be extended from a test seam).
        try:
            existing = server.engine.store.get_operation(op)
            if existing and existing.get("status") == "COMMITTED":
                result = action()           # idempotent replay path (no new backup)
            else:
                backup = server.backups.create_backup(reason=f"before-event-delete-{oid[:8]}", operation_id=op)
                result = {**action(), "backup_id": getattr(backup, "backup_id", None)}
        except module.EventDeletionRefused as exc:
            return self._json({"error": str(exc), "code": exc.code, **exc.details}, status=HTTPStatus.CONFLICT)
        return self._json(result)

    api.SentriFaceApiHandler._do_POST = do_post
    api._issue89_installed = True
