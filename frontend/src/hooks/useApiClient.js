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

  const readResponse = useCallback(async (response, options = {}) => {
    const contentType = response.headers.get("Content-Type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : { error: await response.text() || response.statusText };
    if (!response.ok) {
      if (!options.silent) showToast(payload.error || "Request failed", "red");
      const error = new Error(payload.error || "Request failed");
      error.status = response.status;
      error.code = payload.code;
      error.reason = payload.reason;
      throw error;
    }
    return payload;
  }, [showToast]);

  const apiGet = useCallback(async (path) => {
    return readResponse(await fetch(path));
  }, [readResponse]);

  const apiPost = useCallback(async (path, body, options = {}) => {
    return readResponse(await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: options.signal,
    }), options);
  }, [readResponse]);

  const apiUpload = useCallback(async (path, file, options = {}) => {
    const controller = new AbortController();
    let timedOut = false;
    const forwardAbort = () => controller.abort();
    options.signal?.addEventListener("abort", forwardAbort, { once: true });
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, options.timeoutMs ?? 120_000);
    try {
      return await readResponse(await fetch(path, {
        method: "POST",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
        signal: controller.signal,
      }), options);
    } catch (error) {
      if (timedOut) throw new Error(`Upload timed out for ${file.name}`);
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
      options.signal?.removeEventListener("abort", forwardAbort);
    }
  }, [readResponse]);

  const apiDelete = useCallback(async (path) => {
    return readResponse(await fetch(path, { method: "DELETE" }));
  }, [readResponse]);

  const guarded = useCallback((fn) => async (...args) => {
    try {
      await fn(...args);
    } catch (error) {
      console.error(error);
    }
  }, []);

  return { apiGet, apiPost, apiUpload, apiDelete, guarded, showToast };
}
