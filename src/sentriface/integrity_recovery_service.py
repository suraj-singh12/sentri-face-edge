from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import asdict
from enum import Enum
from typing import Any

from sentriface.engine import FaceEngine
from sentriface.errors import SentriFaceError
from sentriface.integrity import IntegrityFinding, IntegrityReport, ReadOnlyIntegrityChecker
from sentriface.models import (
    ArchivedCanonicalSurvivorRepairPrecondition,
    NoteReferenceReconciliationPrecondition,
    NoteReferenceRepairPlan,
    OperationRevertPrecondition,
)


REPORT_CONTRACT = "sentriface.integrity-recovery"
REPORT_CONTRACT_VERSION = 1
MAX_UI_FINDINGS = 500
MAX_UI_ENTITIES = 16
MAX_UI_EVIDENCE = 12
MAX_TOKEN_BYTES = 128_000


class RecoveryTokenError(SentriFaceError):
    """A P11-E preparation or report token is invalid or no longer usable."""


class RecoveryPreparationRefused(SentriFaceError):
    """The selected report item is not an admitted P11-E action."""


class IntegrityRecoveryApplication:
    """Bounded P11-E adapter over the frozen P11-A/B/C/D services."""

    def __init__(self, engine: FaceEngine, *, token_secret: str) -> None:
        self.engine = engine
        self._token_secret = token_secret.encode("utf-8")

    def check(self) -> dict[str, Any]:
        report = self._run_check()
        return self._report_with_token(report)

    def prepare_graph_rebuild(self, report_token: str, action_id: str) -> dict[str, Any]:
        action = self._selected_action(report_token, action_id, "GRAPH_REBUILD")
        token = self._encode_token({
            "kind": "graph-rebuild",
            "report_fingerprint": action["report_fingerprint"],
            "graph_revision": action.get("graph_revision"),
        })
        return self._plan_payload(
            token,
            action_type="GRAPH_REBUILD",
            title="Rebuild the graph projection",
            summary="Replace only the derived graph projection from authoritative relationship evidence.",
            affected_entities=(),
            expected_changes=("Recompute graph connections from authoritative evidence.",),
            preserved_history=("Persons, evidence, corrections, notes, merges, and existing journal history are not rewritten.",),
            graph_revision=action.get("graph_revision"),
            invariant_ids=("P11-GRAPH-001",),
        )

    def execute_graph_rebuild(
        self,
        token: str,
        operation_id: str,
        *,
        actor: dict,
        reason: str,
        source: str,
    ) -> dict[str, Any]:
        self._decode_token(token, "graph-rebuild")
        result = self.engine.graph.rebuild_projection(
            operation_id,
            actor=actor,
            reason=reason,
            source=source,
            context={"recovery_ui_contract": REPORT_CONTRACT_VERSION},
        )
        return self._success_payload("GRAPH_REBUILD", result)

    def prepare_r01(self, report_token: str, action_id: str) -> dict[str, Any]:
        action = self._selected_action(report_token, action_id, "R01")
        precondition = self.engine.prepare_restore_archived_canonical_survivor(
            str(action["survivor_person_id"]),
        )
        token = self._encode_token({
            "kind": "r01",
            "precondition": _json_value(asdict(precondition)),
        })
        return self._plan_payload(
            token,
            action_type="R01",
            title="Restore the archived canonical survivor",
            summary="Restore only the proven terminal survivor to active lifecycle state.",
            affected_entities=(("person_id", precondition.survivor_person_id),),
            expected_changes=("Change the terminal survivor lifecycle from archived to active.",),
            preserved_history=("Canonical mappings, merge manifests, evidence, notes, and prior journal transitions remain unchanged.",),
            graph_revision=precondition.graph_revision,
            invariant_ids=precondition.invariant_ids,
        )

    def execute_r01(
        self,
        token: str,
        operation_id: str,
        *,
        actor: dict,
        reason: str,
        source: str,
    ) -> dict[str, Any]:
        payload = self._decode_token(token, "r01")
        precondition = _r01_precondition(payload.get("precondition"))
        result = self.engine.repair_archived_canonical_survivor(
            precondition,
            operation_id,
            actor=actor,
            reason=reason,
            source=source,
        )
        return self._success_payload("R01", result)

    def prepare_r02(self, report_token: str, action_id: str) -> dict[str, Any]:
        action = self._selected_action(report_token, action_id, "R02")
        precondition = self.engine.prepare_note_reference_reconciliation(
            str(action["note_id"]), str(action["referenced_person_id"]),
        )
        token = self._encode_token({
            "kind": "r02",
            "precondition": _json_value(asdict(precondition)),
        })
        return self._plan_payload(
            token,
            action_type="R02",
            title="Reconcile note reference state",
            summary=_r02_plan_summary(precondition.plan),
            affected_entities=(
                ("note_id", precondition.note_id),
                ("person_id", precondition.referenced_person_id),
            ),
            expected_changes=(_r02_plan_summary(precondition.plan),),
            preserved_history=("Note revisions and retired occurrence/evidence history remain immutable.",),
            graph_revision=precondition.graph_revision,
            invariant_ids=precondition.invariant_ids,
            plan_code=precondition.plan.value,
        )

    def execute_r02(
        self,
        token: str,
        operation_id: str,
        *,
        actor: dict,
        reason: str,
        source: str,
    ) -> dict[str, Any]:
        payload = self._decode_token(token, "r02")
        precondition = _r02_precondition(payload.get("precondition"))
        result = self.engine.repair_note_reference_state(
            precondition,
            operation_id,
            actor=actor,
            reason=reason,
            source=source,
        )
        return self._success_payload("R02", result)

    def list_revert_operations(self) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        for operation in self.engine.list_recent_operations(500):
            if operation.get("operation_type") != "identity.merge":
                continue
            entities = _bounded_entities(operation.get("affected_entities") or ())
            candidates.append({
                "operation_id": str(operation.get("operation_id") or ""),
                "operation_type": "identity.merge",
                "status": str(operation.get("status") or "UNKNOWN"),
                "created_at": str(operation.get("created_at") or ""),
                "completed_at": str(operation.get("completed_at") or "") or None,
                "affected_entities": entities,
                "eligibility": "PREPARATION_REQUIRED",
            })
            if len(candidates) >= 51:
                break
        return {
            "contract": REPORT_CONTRACT,
            "contract_version": REPORT_CONTRACT_VERSION,
            "operations": candidates[:50],
            "truncated": len(candidates) > 50,
        }

    def prepare_revert(self, original_operation_id: str) -> dict[str, Any]:
        precondition = self.engine.operation_reverts.prepare_revert(original_operation_id)
        token = self._encode_token({
            "kind": "revert",
            "precondition": _json_value(asdict(precondition)),
        })
        return self._plan_payload(
            token,
            action_type="REVERT",
            title="Revert the guarded merge operation",
            summary="Restore only the source identity state proven safe by the P11-D whitelist.",
            affected_entities=precondition.affected_entities,
            expected_changes=("Restore the merge source as a new active lifecycle transition and rebuild the derived graph.",),
            preserved_history=("The original merge, manifest, conflicts, affected items, and journal history remain present.",),
            graph_revision=precondition.graph_revision,
            invariant_ids=(),
            original_operation_id=precondition.operation_id,
        )

    def execute_revert(
        self,
        token: str,
        operation_id: str,
        *,
        actor: dict,
        reason: str,
        source: str,
    ) -> dict[str, Any]:
        payload = self._decode_token(token, "revert")
        precondition = _revert_precondition(payload.get("precondition"))
        result = self.engine.operation_reverts.execute_revert(
            precondition,
            operation_id,
            actor=actor,
            reason=reason,
            source=source,
        )
        return self._success_payload("REVERT", result)

    def postcheck_failure_payload(self, action_type: str, result: dict, report: IntegrityReport) -> dict[str, Any]:
        return {
            "contract": REPORT_CONTRACT,
            "contract_version": REPORT_CONTRACT_VERSION,
            "committed": True,
            "code": "postcheck_failed_after_commit",
            "action_type": action_type,
            "message": "The operation committed, but the post-operation integrity check did not pass.",
            "operation_result": _bounded_result(result),
            "integrity_report": self._report_with_token(report),
        }

    def _success_payload(self, action_type: str, result: dict) -> dict[str, Any]:
        report = self._run_check()
        return {
            "contract": REPORT_CONTRACT,
            "contract_version": REPORT_CONTRACT_VERSION,
            "committed": True,
            "code": "committed",
            "action_type": action_type,
            "operation_result": _bounded_result(result),
            "integrity_report": self._report_with_token(report),
        }

    def _report_with_token(self, report: IntegrityReport) -> dict[str, Any]:
        actions = self._action_candidates(report)
        payload = self._report_payload(report, actions)
        payload["report_token"] = self._encode_token({
            "kind": "integrity-report",
            "schema_version": report.schema_version,
            "graph_revision": report.graph_revision,
            "report_fingerprint": _report_fingerprint(report),
            "actions": actions,
        })
        return payload

    def _run_check(self) -> IntegrityReport:
        return ReadOnlyIntegrityChecker(
            self.engine.store.db_path,
            database_key=getattr(self.engine.store, "database_key", None),
            max_findings=10_000,
        ).run()

    def _report_payload(self, report: IntegrityReport, actions: list[dict[str, Any]]) -> dict[str, Any]:
        action_by_finding: dict[str, dict[str, str]] = {}
        public_actions: list[dict[str, str]] = []
        for action in actions:
            public = {
                "action_id": action["action_id"],
                "action_type": action["action_type"],
                "label": action["label"],
                "state": "PREPARATION_REQUIRED",
            }
            public_actions.append(public)
            for finding_id in action.get("finding_ids", ()):
                action_by_finding[finding_id] = public
        findings = []
        for finding in report.findings[:MAX_UI_FINDINGS]:
            finding_id = _finding_id(finding)
            action = action_by_finding.get(finding_id)
            findings.append({
                "finding_id": finding_id,
                "invariant_id": finding.invariant_id,
                "domain": finding.domain,
                "severity": finding.severity.value,
                "message": str(finding.message)[:320],
                "affected_entities": _bounded_entities(finding.entity_ids),
                "evidence": _bounded_evidence(finding.evidence),
                "classification": _finding_classification(finding, action),
                "action_hint": action,
            })
        ui_truncated = len(report.findings) > MAX_UI_FINDINGS
        return {
            "contract": REPORT_CONTRACT,
            "contract_version": REPORT_CONTRACT_VERSION,
            "status": report.status,
            "started_at": report.started_at,
            "completed_at": report.completed_at,
            "schema_version": report.schema_version,
            "graph_revision": report.graph_revision,
            "counts_by_severity": dict(report.counts_by_severity),
            "checks_run_count": len(report.checks_run),
            "findings": findings,
            "findings_truncated": bool(report.findings_truncated or ui_truncated),
            "actions": public_actions,
        }

    def _action_candidates(self, report: IntegrityReport) -> list[dict[str, Any]]:
        if report.findings_truncated:
            return []
        actions: dict[str, dict[str, Any]] = {}
        graph_findings = [item for item in report.findings if item.invariant_id == "P11-GRAPH-001"]
        blocking_non_graph = [
            item for item in report.findings
            if item.severity.value in {"CRITICAL", "ERROR"}
            and item.invariant_id != "P11-GRAPH-001"
        ]
        if graph_findings and not blocking_non_graph:
            action_id = _action_id("GRAPH_REBUILD", report.graph_revision or "")
            actions[action_id] = {
                "action_id": action_id,
                "action_type": "GRAPH_REBUILD",
                "label": "Prepare graph rebuild",
                "finding_ids": [_finding_id(item) for item in graph_findings],
                "graph_revision": report.graph_revision,
                "report_fingerprint": _report_fingerprint(report),
            }
        for finding in report.findings:
            entities = dict(finding.entity_ids)
            if finding.invariant_id == "P11-IDENTITY-003" and entities.get("terminal_person_id"):
                survivor_id = str(entities["terminal_person_id"])
                action_id = _action_id("R01", survivor_id)
                action = actions.setdefault(action_id, {
                    "action_id": action_id,
                    "action_type": "R01",
                    "label": "Prepare survivor restoration",
                    "finding_ids": [],
                    "survivor_person_id": survivor_id,
                })
                action["finding_ids"].append(_finding_id(finding))
            if finding.invariant_id in {"P11-NOTE-002", "P11-NOTE-003"}:
                note_id = entities.get("note_id")
                person_id = entities.get("person_id") or entities.get("referenced_person_id")
                if note_id and person_id:
                    action_id = _action_id("R02", str(note_id), str(person_id))
                    action = actions.setdefault(action_id, {
                        "action_id": action_id,
                        "action_type": "R02",
                        "label": "Prepare note reference reconciliation",
                        "finding_ids": [],
                        "note_id": str(note_id),
                        "referenced_person_id": str(person_id),
                    })
                    action["finding_ids"].append(_finding_id(finding))
        return list(actions.values())

    def _selected_action(self, token: str, action_id: str, expected_type: str) -> dict[str, Any]:
        payload = self._decode_token(token, "integrity-report")
        actions = payload.get("actions")
        if not isinstance(actions, list):
            raise RecoveryTokenError("The integrity report token is malformed")
        for action in actions:
            if not isinstance(action, dict) or action.get("action_id") != action_id:
                continue
            if action.get("action_type") != expected_type:
                raise RecoveryPreparationRefused("The selected action does not match this preparation route")
            return action
        raise RecoveryPreparationRefused("The selected integrity report does not offer this action")

    def _plan_payload(
        self,
        token: str,
        *,
        action_type: str,
        title: str,
        summary: str,
        affected_entities: Any,
        expected_changes: tuple[str, ...],
        preserved_history: tuple[str, ...],
        graph_revision: str | None,
        invariant_ids: Any,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "contract": REPORT_CONTRACT,
            "contract_version": REPORT_CONTRACT_VERSION,
            "token": token,
            "action_type": action_type,
            "title": title,
            "summary": summary,
            "affected_entities": _bounded_entities(affected_entities),
            "expected_changes": list(expected_changes),
            "preserved_history": list(preserved_history),
            "graph_revision": graph_revision,
            "invariant_ids": [str(value) for value in tuple(invariant_ids)[:16]],
            "confirmation_phrase": "CONFIRM",
            **{key: _bounded_result(value) for key, value in extra.items()},
        }

    def _encode_token(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(_json_value(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(raw) > MAX_TOKEN_BYTES:
            raise RecoveryTokenError("The prepared recovery state is too large")
        signature = hmac.new(self._token_secret, raw, hashlib.sha256).digest()
        return f"{_b64(raw)}.{_b64(signature)}"

    def _decode_token(self, token: str, expected_kind: str) -> dict[str, Any]:
        if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_BYTES * 2:
            raise RecoveryTokenError("A valid preparation token is required")
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
            raw = _unb64(encoded_payload)
            signature = _unb64(encoded_signature)
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RecoveryTokenError("The preparation token is malformed") from exc
        expected = hmac.new(self._token_secret, raw, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise RecoveryTokenError("The preparation token fingerprint changed")
        if not isinstance(payload, dict) or payload.get("kind") != expected_kind:
            raise RecoveryTokenError("The preparation token is for a different action")
        return payload


def _r01_precondition(value: Any) -> ArchivedCanonicalSurvivorRepairPrecondition:
    payload = _precondition_dict(value)
    for key in ("invariant_ids", "affected_entity_ids", "merge_source_person_ids", "merge_operation_ids"):
        payload[key] = tuple(payload.get(key) or ())
    payload["merge_paths"] = tuple(tuple(path) for path in payload.get("merge_paths") or ())
    return ArchivedCanonicalSurvivorRepairPrecondition(**payload)


def _r02_precondition(value: Any) -> NoteReferenceReconciliationPrecondition:
    payload = _precondition_dict(value)
    payload["plan"] = NoteReferenceRepairPlan(payload["plan"])
    for key in (
        "invariant_ids", "affected_entity_ids", "finding_entity_ids",
        "latest_revision_mentions", "occurrence_ids", "active_occurrence_ids",
        "evidence_ids", "active_evidence_ids",
    ):
        payload[key] = tuple(payload.get(key) or ())
    return NoteReferenceReconciliationPrecondition(**payload)


def _revert_precondition(value: Any) -> OperationRevertPrecondition:
    payload = _precondition_dict(value)
    for key in ("affected_entities", "relevant_revisions"):
        payload[key] = tuple(tuple(item) for item in payload.get(key) or ())
    payload["dependency_operation_ids"] = tuple(payload.get("dependency_operation_ids") or ())
    return OperationRevertPrecondition(**payload)


def _precondition_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RecoveryTokenError("The prepared recovery precondition is malformed")
    return dict(value)


def _finding_id(finding: IntegrityFinding) -> str:
    raw = json.dumps({
        "invariant_id": finding.invariant_id,
        "message": finding.message,
        "entity_ids": list(finding.entity_ids),
        "evidence": list(finding.evidence),
    }, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"finding-{hashlib.sha256(raw).hexdigest()[:24]}"


def _action_id(action_type: str, *parts: str) -> str:
    raw = json.dumps([action_type, *parts], separators=(",", ":")).encode("utf-8")
    return f"action-{hashlib.sha256(raw).hexdigest()[:24]}"


def _report_fingerprint(report: IntegrityReport) -> str:
    raw = json.dumps({
        "schema_version": report.schema_version,
        "graph_revision": report.graph_revision,
        "status": report.status,
        "findings": [_finding_id(item) for item in report.findings],
        "truncated": report.findings_truncated,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _bounded_entities(value: Any) -> list[dict[str, str]]:
    if isinstance(value, dict):
        items = value.items()
    else:
        items = value or ()
    result = []
    for item in items:
        if isinstance(item, dict):
            key = item.get("type") or item.get("entity_type") or "entity_id"
            raw_value = item.get("id") or item.get("entity_id") or ""
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            key, raw_value = item
        else:
            continue
        result.append({"type": str(key)[:64], "id": str(raw_value)[:160]})
        if len(result) >= MAX_UI_ENTITIES:
            break
    return result


def _bounded_evidence(value: Any) -> list[dict[str, str]]:
    result = []
    denied = (
        "path", "error", "diagnostic", "sql", "database", "media",
        "content", "embedding", "actor", "journal",
    )
    for item in value or ():
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        key, raw_value = str(item[0]), item[1]
        if any(fragment in key.casefold() for fragment in denied):
            continue
        result.append({"name": key[:64], "value": str(raw_value)[:200]})
        if len(result) >= MAX_UI_EVIDENCE:
            break
    return result


def _finding_classification(finding: IntegrityFinding, action: dict[str, str] | None) -> str:
    if action is not None:
        return "SAFE_ACTION_PREPARATION_AVAILABLE"
    if finding.future_handling.value == "UNRECOVERABLE_FROM_LOCAL_STATE":
        return "BACKUP_RESTORE_ONLY"
    return "MANUAL_REVIEW"


def _bounded_result(value: Any, depth: int = 0) -> Any:
    if depth > 3:
        return "[bounded]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, dict):
        denied = (
            "path", "sql", "stack", "traceback", "embedding", "journal",
            "actor", "content", "media", "database", "secret", "key",
        )
        result = {}
        for key, item in list(value.items())[:40]:
            if any(fragment in str(key).casefold() for fragment in denied):
                continue
            result[str(key)[:80]] = _bounded_result(item, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_bounded_result(item, depth + 1) for item in list(value)[:40]]
    return str(value)[:500]


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _r02_plan_summary(plan: NoteReferenceRepairPlan) -> str:
    return {
        NoteReferenceRepairPlan.APPEND_OCCURRENCE_AND_EVIDENCE: "Append one current mention occurrence and its supporting evidence.",
        NoteReferenceRepairPlan.RETIRE_OCCURRENCE_AND_EVIDENCE: "Retire the stale current mention occurrence and its active evidence.",
        NoteReferenceRepairPlan.APPEND_EVIDENCE: "Append the missing active note-reference evidence.",
        NoteReferenceRepairPlan.REPLACE_DUPLICATE_ACTIVE_EVIDENCE: "Retire duplicate active evidence and append one current replacement.",
        NoteReferenceRepairPlan.RETIRE_STALE_EVIDENCE: "Retire active note-reference evidence whose authoritative source is inactive.",
    }[plan]


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
