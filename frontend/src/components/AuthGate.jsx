import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Box, Button, Card, Center, Group, Loader, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";

import { releaseWindow, useApiClient } from "../hooks/useApiClient.js";
import { requiredFieldErrors } from "../utils.js";

export function AuthGate({ children }) {
  const { apiGet, apiPost, showToast } = useApiClient();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [reloadRequired, setReloadRequired] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirmation, setNewPasswordConfirmation] = useState("");
  const windowActive = useRef(false);
  const clearError = (field) => setFieldErrors((current) => ({ ...current, [field]: undefined }));

  const refresh = useCallback(async () => {
    try {
      const next = await apiGet("/api/auth/status", { silent: true, dedupe: false });
      // Keep the same object when nothing changed so focus re-checks do not re-render the app.
      setStatus((current) => (JSON.stringify(current) === JSON.stringify(next) ? current : next));
    } catch (requestError) {
      setError(requestError?.message || "SentriFace authentication is unavailable");
    } finally {
      setLoading(false);
    }
  }, [apiGet]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    const requireLogin = () => refresh();
    const requireReload = () => setReloadRequired(true);
    // Re-check access when the operator returns, so an administrator's change shows promptly.
    const recheck = () => { if (document.visibilityState === "visible") refresh(); };
    window.addEventListener("sentriface-auth-required", requireLogin);
    window.addEventListener("sentriface-reload-required", requireReload);
    window.addEventListener("focus", recheck);
    document.addEventListener("visibilitychange", recheck);
    return () => {
      window.removeEventListener("sentriface-auth-required", requireLogin);
      window.removeEventListener("sentriface-reload-required", requireReload);
      window.removeEventListener("focus", recheck);
      document.removeEventListener("visibilitychange", recheck);
    };
  }, [refresh]);

  const authenticated = Boolean(status?.authenticated);
  const windowState = status?.window;
  windowActive.current = authenticated && windowState === "active";
  useEffect(() => {
    if (!authenticated) return undefined;
    // Check in so the server knows this window is still open, and notice another window taking over.
    const heartbeat = window.setInterval(async () => {
      try {
        const next = await apiPost("/api/auth/window", { action: "heartbeat" }, { silent: true });
        if (next?.window !== windowState) refresh();
      } catch (_) { /* Session and window errors refresh the gate through events. */ }
    }, (status?.window_heartbeat_seconds || 15) * 1000);
    return () => window.clearInterval(heartbeat);
  }, [apiPost, authenticated, refresh, status?.window_heartbeat_seconds, windowState]);
  useEffect(() => {
    const release = () => { if (windowActive.current) releaseWindow(); };
    window.addEventListener("pagehide", release);
    return () => window.removeEventListener("pagehide", release);
  }, []);

  const useThisWindow = async () => {
    setSubmitting(true);
    try {
      await apiPost("/api/auth/window", { action: "claim" }, { silent: true });
    } catch (_) { /* refresh shows the current state */ }
    await refresh();
    setSubmitting(false);
  };

  const saveRequiredPassword = async (event) => {
    event.preventDefault();
    setError("");
    const errors = requiredFieldErrors({ newPassword, newPasswordConfirmation }, [
      ["newPassword", "New password"], ["newPasswordConfirmation", "Password confirmation"],
    ]);
    if (!errors.newPassword && newPassword.length < 12) errors.newPassword = "Use at least 12 characters";
    if (!errors.newPasswordConfirmation && newPassword !== newPasswordConfirmation) errors.newPasswordConfirmation = "Passwords do not match";
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    setSubmitting(true);
    try {
      const next = await apiPost("/api/auth/set-password", { new_password: newPassword }, { silent: true });
      setNewPassword("");
      setNewPasswordConfirmation("");
      setStatus(next);
      showToast("Password saved");
    } catch (requestError) {
      setError(requestError?.message || "The password could not be saved");
    } finally {
      setSubmitting(false);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    const setup = Boolean(status?.setup_required);
    const errors = requiredFieldErrors({ username, password, confirmation }, [
      ["username", "Account name"], ["password", "Password"], ...(setup ? [["confirmation", "Password confirmation"]] : []),
    ]);
    if (setup && !errors.confirmation && password !== confirmation) errors.confirmation = "Passwords do not match";
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    setSubmitting(true);
    try {
      const next = await apiPost(status?.setup_required ? "/api/auth/signup" : "/api/auth/login", {
        username,
        display_name: displayName,
        password,
      }, { silent: true });
      setPassword("");
      setConfirmation("");
      setStatus(next);
      showToast(status?.setup_required ? "Account created" : "Signed in");
    } catch (requestError) {
      setError(requestError?.message || "Authentication failed");
    } finally {
      setSubmitting(false);
    }
  };

  const logout = async () => {
    try { await apiPost("/api/auth/logout", {}, { silent: true }); } catch (_) { /* Clear the local view regardless. */ }
    setStatus((current) => ({ ...current, authenticated: false, user: null, setup_required: false }));
    showToast("Signed out", "gray");
  };

  const changePassword = async (currentPassword, newPassword) => {
    await apiPost("/api/auth/change-password", { current_password: currentPassword, new_password: newPassword });
    setStatus((current) => ({ ...current, authenticated: false, user: null, setup_required: false }));
    showToast("Password changed. Sign in again.");
  };

  if (reloadRequired) {
    return (
      <Center mih="100vh" p="md">
        <Card withBorder shadow="md" radius="lg" p="xl" w="100%" maw={460}>
          <Stack>
            <Title order={2}>SentriFace was restarted</Title>
            <Text>This window is from before the restart. Reload it to sign in again. Changes that were not saved before the restart are not kept.</Text>
            <Button onClick={() => window.location.reload()}>Reload</Button>
          </Stack>
        </Card>
      </Center>
    );
  }
  if (loading) return <Center mih="100vh"><Stack align="center"><Loader /><Text c="dimmed">Opening the local vault...</Text></Stack></Center>;
  if (!status?.authenticated) {
    const setup = Boolean(status?.setup_required);
    return (
      <Center mih="100vh" p="md">
        <Card withBorder shadow="md" radius="lg" p="xl" w="100%" maw={460}>
          <form onSubmit={submit} noValidate>
            <Stack>
              <Group gap="sm" wrap="nowrap">
                <img src="/sentriface-icon-64.png" alt="" className="auth-brand-icon" aria-hidden="true" />
                <Box>
                  <Title order={2}>SentriFace Edge</Title>
                  <Text c="dimmed">{setup ? "Create the owner account for this computer" : "Sign in to continue"}</Text>
                </Box>
              </Group>
              {setup ? (
                <Alert color="blue" title="Private by default">
                  Your account and face data stay on this computer. Nothing is sent to an online service.
                </Alert>
              ) : null}
              {!setup && status?.session_ended ? (
                <Alert color="orange" title="Your session ended" role="alert">{status.session_ended.message}</Alert>
              ) : null}
              {error ? <Alert color="red">{error}</Alert> : null}
              <TextInput label="Account name" description={setup ? "You will use this name to sign in." : undefined} value={username} onChange={(event) => { setUsername(event.currentTarget.value); clearError("username"); }} error={fieldErrors.username} autoComplete="username" required />
              {setup ? <TextInput label="Your name (optional)" value={displayName} onChange={(event) => setDisplayName(event.currentTarget.value)} autoComplete="name" /> : null}
              <PasswordInput label="Password" description={setup ? "Use at least 12 characters." : undefined} value={password} onChange={(event) => { setPassword(event.currentTarget.value); clearError("password"); }} error={fieldErrors.password} autoComplete={setup ? "new-password" : "current-password"} required />
              {setup ? <PasswordInput label="Confirm password" value={confirmation} onChange={(event) => { setConfirmation(event.currentTarget.value); clearError("confirmation"); }} error={fieldErrors.confirmation} autoComplete="new-password" required /> : null}
              <Button type="submit" loading={submitting}>{setup ? "Create account" : "Sign in"}</Button>
            </Stack>
          </form>
        </Card>
      </Center>
    );
  }
  if (windowState === "in_use" || windowState === "replaced") {
    const replaced = windowState === "replaced";
    return (
      <Center mih="100vh" p="md">
        <Card withBorder shadow="md" radius="lg" p="xl" w="100%" maw={460}>
          <Stack>
            <Title order={2}>{replaced ? "SentriFace is now being used in another window" : "SentriFace is open in another window"}</Title>
            {replaced ? (
              <Text>This window has stopped so that only one window makes changes. Close it, or use it here instead.</Text>
            ) : (
              <>
                <Text>Only one window can be used at a time. Use this one instead, and the other window will stop.</Text>
                <Text size="sm" c="dimmed">Changes that were not saved in the other window are not kept.</Text>
              </>
            )}
            <Button loading={submitting} onClick={useThisWindow}>Use this window</Button>
          </Stack>
        </Card>
      </Center>
    );
  }
  if (status.user?.must_change_password) {
    const who = status.user.display_name && status.user.display_name !== status.user.username
      ? `${status.user.display_name} (${status.user.username})`
      : status.user.username;
    return (
      <Center mih="100vh" p="md">
        <Card withBorder shadow="md" radius="lg" p="xl" w="100%" maw={460}>
          <form onSubmit={saveRequiredPassword} noValidate>
            <Stack>
              <Group gap="sm" wrap="nowrap">
                <img src="/sentriface-icon-64.png" alt="" className="auth-brand-icon" aria-hidden="true" />
                <Box>
                  <Title order={2}>SentriFace Edge</Title>
                  <Text c="dimmed">Signed in as {who}</Text>
                </Box>
              </Group>
              <Title order={3} size="h4">Choose a new password</Title>
              <Alert color="blue">An administrator set this password. Choose your own before you continue.</Alert>
              {error ? <Alert color="red" role="alert">{error}</Alert> : null}
              <PasswordInput label="New password" description="Use at least 12 characters." value={newPassword} onChange={(event) => { setNewPassword(event.currentTarget.value); clearError("newPassword"); }} error={fieldErrors.newPassword} autoComplete="new-password" required data-autofocus />
              <PasswordInput label="Confirm new password" value={newPasswordConfirmation} onChange={(event) => { setNewPasswordConfirmation(event.currentTarget.value); clearError("newPasswordConfirmation"); }} error={fieldErrors.newPasswordConfirmation} autoComplete="new-password" required />
              <Button type="submit" loading={submitting}>Save and continue</Button>
              <Button variant="subtle" color="gray" onClick={logout} disabled={submitting}>Sign out</Button>
            </Stack>
          </form>
        </Card>
      </Center>
    );
  }
  return children({ user: status.user, roles: status.roles || [], logout, changePassword, refreshAuth: refresh });
}
