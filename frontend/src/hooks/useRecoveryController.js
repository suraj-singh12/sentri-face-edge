import { useCallback, useMemo, useState } from "react";

const PREPARE_ROUTES = Object.freeze({
  GRAPH_REBUILD: "/api/integrity/graph-rebuild/prepare",
  R01: "/api/integrity/repairs/r01/prepare",
  R02: "/api/integrity/repairs/r02/prepare",
});

const EXECUTE_ROUTES = Object.freeze({
  GRAPH_REBUILD: "/api/integrity/graph-rebuild/execute",
  R01: "/api/integrity/repairs/r01/execute",
  R02: "/api/integrity/repairs/r02/execute",
  REVERT: "/api/integrity/reverts/execute",
});

export function useRecoveryController({ enabled = false, apiGet, apiPost, showToast }) {
  const [report, setReport] = useState(null);
  const [selectedFindingId, setSelectedFindingId] = useState("");
  const [plan, setPlan] = useState(null);
  const [result, setResult] = useState(null);
  const [revertOperations, setRevertOperations] = useState([]);
  const [checking, setChecking] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [loadingOperations, setLoadingOperations] = useState(false);

  const selectedFinding = useMemo(
    () => report?.findings?.find((finding) => finding.finding_id === selectedFindingId) || null,
    [report, selectedFindingId],
  );

  const checkIntegrity = useCallback(async () => {
    if (!enabled || checking) return null;
    setChecking(true);
    try {
      const next = await apiPost("/api/integrity/check", {}, { silent: true, timeoutMs: 120_000 });
      setReport(next);
      setSelectedFindingId("");
      setPlan(null);
      return next;
    } catch (error) {
      showToast(error.message || "The integrity check could not complete", "red", {
        title: "Integrity check failed",
        autoClose: 7000,
      });
      return null;
    } finally {
      setChecking(false);
    }
  }, [apiPost, checking, enabled, showToast]);

  const loadRevertOperations = useCallback(async () => {
    if (!enabled || loadingOperations) return null;
    setLoadingOperations(true);
    try {
      const payload = await apiGet("/api/integrity/revert-operations", { silent: true });
      setRevertOperations(payload.operations || []);
      return payload;
    } catch (error) {
      showToast(error.message || "Merge operation history could not be loaded", "red", {
        title: "Operation history unavailable",
      });
      return null;
    } finally {
      setLoadingOperations(false);
    }
  }, [apiGet, enabled, loadingOperations, showToast]);

  const prepareFindingAction = useCallback(async (action) => {
    if (!enabled || preparing || !report?.report_token || !action?.action_id) return null;
    const route = PREPARE_ROUTES[action.action_type];
    if (!route) return null;
    setPreparing(true);
    setResult(null);
    try {
      const prepared = await apiPost(route, {
        report_token: report.report_token,
        action_id: action.action_id,
      }, { silent: true, timeoutMs: 120_000 });
      setPlan({ ...prepared, operationId: crypto.randomUUID() });
      return prepared;
    } catch (error) {
      if (error.code === "stale_precondition" || error.code === "operation_refused") {
        setPlan(null);
        setResult({ committed: false, code: error.code, message: error.message });
        await checkIntegrity();
      } else {
        showToast(error.message || "The recovery plan could not be prepared", "red", {
          title: "Preparation refused",
          autoClose: 7000,
        });
      }
      return null;
    } finally {
      setPreparing(false);
    }
  }, [apiPost, checkIntegrity, enabled, preparing, report, showToast]);

  const prepareRevert = useCallback(async (operationId) => {
    if (!enabled || preparing || !operationId) return null;
    setPreparing(true);
    setResult(null);
    try {
      const prepared = await apiPost("/api/integrity/reverts/prepare", {
        operation_id: operationId,
      }, { silent: true, timeoutMs: 120_000 });
      setPlan({ ...prepared, operationId: crypto.randomUUID() });
      return prepared;
    } catch (error) {
      setPlan(null);
      setResult({ committed: false, code: error.code || "operation_refused", message: error.message });
      showToast(error.message || "This merge is not safely revertible", "red", {
        title: "Revert preparation refused",
        autoClose: 7000,
      });
      return null;
    } finally {
      setPreparing(false);
    }
  }, [apiPost, enabled, preparing, showToast]);

  const executePrepared = useCallback(async (reason) => {
    if (!enabled || executing || !plan?.token || !plan?.operationId) return null;
    const route = EXECUTE_ROUTES[plan.action_type];
    if (!route) return null;
    setExecuting(true);
    try {
      const executed = await apiPost(route, {
        token: plan.token,
        operation_id: plan.operationId,
        reason,
      }, { silent: true, timeoutMs: 120_000 });
      setResult(executed);
      setReport(executed.integrity_report || null);
      setSelectedFindingId("");
      setPlan(null);
      showToast("Recovery operation committed and the integrity check completed", "teal", {
        title: "Recovery complete",
        autoClose: 6500,
      });
      return executed;
    } catch (error) {
      if (error.committed && error.code === "postcheck_failed_after_commit") {
        setResult(error.payload);
        setReport(error.integrityReport || null);
        setPlan(null);
        showToast(
          "The operation committed, but post-operation integrity verification failed. Review the current report before doing anything else.",
          "red",
          { title: "Committed; verification failed", autoClose: 10_000 },
        );
        return error.payload;
      }
      if (error.code === "stale_precondition" || error.code === "operation_refused") {
        setPlan(null);
        setResult({ committed: false, code: error.code, message: error.message });
        await checkIntegrity();
      } else {
        showToast(error.message || "The recovery operation failed", "red", {
          title: "Recovery did not complete",
          autoClose: 8000,
        });
      }
      throw error;
    } finally {
      setExecuting(false);
    }
  }, [apiPost, checkIntegrity, enabled, executing, plan, showToast]);

  return {
    state: {
      report,
      selectedFinding,
      selectedFindingId,
      plan,
      result,
      revertOperations,
      checking,
      preparing,
      executing,
      loadingOperations,
    },
    actions: {
      checkIntegrity,
      loadRevertOperations,
      selectFinding: setSelectedFindingId,
      prepareFindingAction,
      prepareRevert,
      executePrepared,
      closePlan: () => { if (!executing) setPlan(null); },
      clearResult: () => setResult(null),
    },
  };
}
