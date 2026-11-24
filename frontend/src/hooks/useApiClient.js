import { createElement, useCallback } from "react";
import { notifications } from "@mantine/notifications";
import { ToastContent } from "../components/ToastStack.jsx";

// Semantic toast colors: red failed, orange caution, teal done, gray neutral.
const TOAST_COLORS = { red: "red", orange: "orange", yellow: "orange", teal: "teal", gray: "gray" };
const DEFAULT_TIMEOUT_MS = 60_000;
const SESSION_TOKEN = typeof document === "undefined" ? "" : document.querySelector('meta[name="sentriface-session-token"]')?.content || "";
const GET_REQUESTS_IN_FLIGHT = new Map();
// One operator uses one window; the server accepts changes only from the active window.
export const WINDOW_ID = typeof crypto !== "undefined" && crypto.randomUUID
  ? crypto.randomUUID()
  : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
const RELOADED_FROM_KEY = "sentriface.window.reloadedFrom";
// Written only while this page unloads, so a duplicated tab never inherits it.
export const RELOADED_FROM_WINDOW_ID = readReloadedFrom();
export const WINDOW_CODES = ["window_in_use", "window_replaced"];
export const SESSION_ENDED_CODES = ["authentication_required", "setup_required", "page_session_expired", "password_change_required", ...WINDOW_CODES];

function authorizedHeaders(headers = {}) {
  return { ...headers, "X-SentriFace-Session": SESSION_TOKEN, "X-SentriFace-Window": WINDOW_ID };
}

function readReloadedFrom() {
  try {
    const value = window.sessionStorage.getItem(RELOADED_FROM_KEY);
    window.sessionStorage.removeItem(RELOADED_FROM_KEY);
    return value || "";
  } catch (_) {
    return "";
  }
}

export function rememberWindowForReload() {
  try { window.sessionStorage.setItem(RELOADED_FROM_KEY, WINDOW_ID); } catch (_) { /* Reload then waits for the release. */ }
}

export function releaseWindow() {
  // keepalive lets the request finish while the page unloads, so a reload is not blocked.
  fetch("/api/auth/window", {
    method: "POST",
    keepalive: true,
    headers: authorizedHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ action: "release" }),
  }).catch(() => {});
}

export function useApiClient() {
  const showToast = useCallback((message, color = "teal", options = {}) => {
    notifications.show({
      message: createElement(ToastContent, null, message),
      color: TOAST_COLORS[color] || "gray",
      title: options.title,
      autoClose: options.autoClose ?? 4500,
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
      error.committed = Boolean(payload.committed);
      error.operationResult = payload.operation_result;
      error.integrityReport = payload.integrity_report;
      error.payload = payload;
      if (error.code === "page_session_expired") {
        window.dispatchEvent(new CustomEvent("sentriface-reload-required"));
      } else if (["authentication_required", "setup_required", "password_change_required", ...WINDOW_CODES].includes(error.code)) {
        window.dispatchEvent(new CustomEvent("sentriface-auth-required", { detail: payload.session_ended || null }));
      }
      if (SESSION_ENDED_CODES.includes(error.code)) {
        // The sign-in or reload screen explains this; a generic error toast would not.
        error.notified = true;
        throw error;
      }
      if (error.code === "models_required") {
        window.dispatchEvent(new CustomEvent("sentriface-models-required"));
      }
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

  const apiGet = useCallback((path, options = {}) => {
    if (options.signal || options.dedupe === false) return request(path, { headers: options.headers }, options);
    const existing = GET_REQUESTS_IN_FLIGHT.get(path);
    if (existing) return existing;
    const pending = request(path, {}, options).finally(() => {
      if (GET_REQUESTS_IN_FLIGHT.get(path) === pending) GET_REQUESTS_IN_FLIGHT.delete(path);
    });
    GET_REQUESTS_IN_FLIGHT.set(path, pending);
    return pending;
  }, [request]);

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
      return await fn(...args);
    } catch (error) {
      console.error(error);
      if (error?.name !== "AbortError" && !error?.notified) {
        showToast(error?.message || "The operation failed", "red", {
          title: error?.code === "request_timeout" ? "Server timeout" : "Connection or operation error",
          autoClose: 4500,
        });
      }
    }
  }, [showToast]);

  return { apiGet, apiPost, apiUpload, apiDownload, apiDelete, guarded, showToast };
}
