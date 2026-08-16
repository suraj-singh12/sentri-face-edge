import { useCallback, useEffect, useState } from "react";

import { useApiClient } from "./useApiClient.js";

export function useLicenseController() {
  const { apiGet, apiPost, showToast } = useApiClient();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      setStatus(await apiGet("/api/license/status", { silent: true }));
      setError("");
    } catch (caught) {
      setError(caught?.message || "License status is unavailable");
    } finally {
      setLoading(false);
    }
  }, [apiGet]);

  useEffect(() => { refresh(); }, [refresh]);

  const activate = useCallback(async (token) => {
    setActivating(true);
    setError("");
    try {
      const next = await apiPost("/api/license/activate", { token }, { silent: true });
      setStatus(next);
      showToast("SentriFace Edge is activated", "teal");
      return next;
    } catch (caught) {
      setError(caught?.message || "The license was refused");
      throw caught;
    } finally {
      setActivating(false);
    }
  }, [apiPost, showToast]);

  return { status, loading, activating, error, refresh, activate };
}
