import { useCallback } from "react";
import { notifications } from "@mantine/notifications";

const DEFAULT_TIMEOUT_MS = 60_000;
const SESSION_TOKEN = document.querySelector('meta[name="sentriface-session-token"]')?.content || "";

function authorizedHeaders(headers = {}) {
  return { ...headers, "X-SentriFace-Session": SESSION_TOKEN };
}

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
      const error = new Error(payload.error || "Request failed");
      error.status = response.status;
      error.code = payload.code;
      error.reason = payload.reason;
      if (!options.silent) {
        showToast(error.message, "red", {
          title: error.code === "engine_busy" ? "Face engine is busy" : "Request failed",
        });
        error.notified = true;
      }
      throw error;
    }
    return payload;
  }, [showToast]);

  const request = useCallback(async (path, init = {}, options = {}) => {
    const controller = new AbortController();
    let timedOut = false;
    const forwardAbort = () => controller.abort();
    options.signal?.addEventListener("abort", forwardAbort, { once: true });
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
    try {
      return await readResponse(await fetch(path, {
        ...init,
        headers: authorizedHeaders(init.headers),
        signal: controller.signal,
      }), options);
    } catch (error) {
      if (timedOut) {
        const timeoutError = new Error("The server took too long to respond. It is safe to retry.");
        timeoutError.code = "request_timeout";
        throw timeoutError;
      }
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
      options.signal?.removeEventListener("abort", forwardAbort);
    }
  }, [readResponse]);

  const apiGet = useCallback((path, options = {}) => request(path, {}, options), [request]);

  const apiPost = useCallback((path, body, options = {}) => request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }, options), [request]);

  const apiUpload = useCallback((path, file, options = {}) => request(path, {
    method: "POST",
    headers: { "Content-Type": file.type || "application/octet-stream", ...(options.headers || {}) },
    body: file,
  }, { ...options, timeoutMs: options.timeoutMs ?? 120_000 }).catch((error) => {
    if (error.code === "request_timeout") {
      error.message = `Upload timed out for ${file.name}. It is safe to retry.`;
    }
    throw error;
  }), [request]);

  const apiDownload = useCallback(async (path, body, options = {}) => {
    const controller = new AbortController();
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, options.timeoutMs ?? 30 * 60 * 1000);
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: authorizedHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok) {
        await readResponse(response, options);
      }
      return {
        blob: await response.blob(),
        contentDisposition: response.headers.get("Content-Disposition") || "",
      };
    } catch (error) {
      if (timedOut) {
        const timeoutError = new Error("The encrypted export took too long. It is safe to retry.");
        timeoutError.code = "request_timeout";
        throw timeoutError;
      }
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
    }
  }, [readResponse]);
  const apiDelete = useCallback((path, options = {}) => request(
    path,
    { method: "DELETE" },
    options,
  ), [request]);

  const guarded = useCallback((fn) => async (...args) => {
    try {
      await fn(...args);
    } catch (error) {
      console.error(error);
      if (error?.name !== "AbortError" && !error?.notified) {
        showToast(error?.message || "The operation failed", "red", {
          title: error?.code === "request_timeout" ? "Server timeout" : "Connection or operation error",
          autoClose: 6000,
        });
      }
    }
  }, [showToast]);

  return { apiGet, apiPost, apiUpload, apiDownload, apiDelete, guarded, showToast };
}
