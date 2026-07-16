import { useCallback } from "react";
import { notifications } from "@mantine/notifications";

export function useApiClient() {
  const showToast = useCallback((message, color = "teal", options = {}) => {
    notifications.show({
      message,
      color,
      title: options.title,
      autoClose: options.autoClose ?? 2400,
    });
  }, []);

  const readResponse = useCallback(async (response) => {
    const contentType = response.headers.get("Content-Type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : { error: await response.text() || response.statusText };
    console.debug("[sentriface-ui] response", response.status, payload);
    if (!response.ok) {
      showToast(payload.error || "Request failed", "red");
      throw new Error(payload.error || "Request failed");
    }
    return payload;
  }, [showToast]);

  const apiGet = useCallback(async (path) => {
    console.debug("[sentriface-ui] GET", path);
    return readResponse(await fetch(path));
  }, [readResponse]);

  const apiPost = useCallback(async (path, body) => {
    console.debug("[sentriface-ui] POST", path, body);
    return readResponse(await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }));
  }, [readResponse]);

  const apiDelete = useCallback(async (path) => {
    console.debug("[sentriface-ui] DELETE", path);
    return readResponse(await fetch(path, { method: "DELETE" }));
  }, [readResponse]);

  const guarded = useCallback((fn) => async (...args) => {
    try {
      await fn(...args);
    } catch (error) {
      console.error(error);
    }
  }, []);

  return { apiGet, apiPost, apiDelete, guarded, showToast };
}
