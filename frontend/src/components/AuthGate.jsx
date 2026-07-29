import { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Card, Center, Group, Loader, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";

import { useApiClient } from "../hooks/useApiClient.js";

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

  const refresh = useCallback(async () => {
    try {
      setStatus(await apiGet("/api/auth/status", { silent: true }));
    } catch (requestError) {
      setError(requestError?.message || "SentriFace authentication is unavailable");
    } finally {
      setLoading(false);
    }
  }, [apiGet]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    const requireLogin = () => refresh();
    window.addEventListener("sentriface-auth-required", requireLogin);
    return () => window.removeEventListener("sentriface-auth-required", requireLogin);
  }, [refresh]);

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (status?.setup_required && password !== confirmation) {
      setError("Passwords do not match");
      return;
    }
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
      showToast(status?.setup_required ? "Administrator account created" : "Signed in");
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

  if (loading) return <Center mih="100vh"><Stack align="center"><Loader /><Text c="dimmed">Opening the local vault...</Text></Stack></Center>;
  if (!status?.authenticated) {
    const setup = Boolean(status?.setup_required);
    return (
      <Center mih="100vh" p="md">
        <Card withBorder shadow="md" radius="lg" p="xl" w="100%" maw={460}>
          <form onSubmit={submit}>
            <Stack>
              <Box><Title order={2}>SentriFace Edge</Title><Text c="dimmed">{setup ? "Create this machine's first administrator" : "Sign in to this machine"}</Text></Box>
              {setup ? <Alert color="blue" title="Machine-local account">Credentials are stored only inside this machine's encrypted SentriFace database.</Alert> : null}
              {error ? <Alert color="red">{error}</Alert> : null}
              <TextInput label="Username" value={username} onChange={(event) => setUsername(event.currentTarget.value)} autoComplete="username" required />
              {setup ? <TextInput label="Display name" value={displayName} onChange={(event) => setDisplayName(event.currentTarget.value)} autoComplete="name" /> : null}
              <PasswordInput label="Password" description={setup ? "At least 12 characters" : undefined} value={password} onChange={(event) => setPassword(event.currentTarget.value)} autoComplete={setup ? "new-password" : "current-password"} required />
              {setup ? <PasswordInput label="Confirm password" value={confirmation} onChange={(event) => setConfirmation(event.currentTarget.value)} autoComplete="new-password" required /> : null}
              <Button type="submit" loading={submitting}>{setup ? "Create administrator" : "Sign in"}</Button>
            </Stack>
          </form>
        </Card>
      </Center>
    );
  }
  return children({ user: status.user, roles: status.roles || [], logout, changePassword, refreshAuth: refresh });
}