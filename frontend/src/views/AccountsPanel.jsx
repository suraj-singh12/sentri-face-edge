import { useEffect, useState } from "react";
import { Alert, Badge, Box, Button, Card, Group, Modal, MultiSelect, PasswordInput, Stack, Switch, Text, TextInput, Title } from "@mantine/core";

import { useApiClient } from "../hooks/useApiClient.js";

export function AccountsPanel({ currentUser }) {
  const { apiGet, apiPost, guarded, showToast } = useApiClient();
  const [users, setUsers] = useState([]);
  const [roleCatalog, setRoleCatalog] = useState([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [roles, setRoles] = useState(["viewer"]);
  const [disabled, setDisabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    const payload = await apiGet("/api/users");
    setUsers(payload.users || []);
    setRoleCatalog(payload.roles || []);
  };
  useEffect(() => { guarded(load)(); }, []);
  const roleOptions = roleCatalog.map((role) => ({ value: role.role, label: role.role[0].toUpperCase() + role.role.slice(1), description: role.description }));
  const clearForm = () => { setUsername(""); setDisplayName(""); setPassword(""); setRoles(["viewer"]); setDisabled(false); };
  const createUser = async () => {
    setBusy(true);
    try {
      await apiPost("/api/users", { username, display_name: displayName, password, roles });
      showToast("Machine account created");
      setCreateOpen(false);
      clearForm();
      await load();
    } finally { setBusy(false); }
  };
  const openEdit = (user) => {
    setEditing(user);
    setDisplayName(user.display_name || "");
    setRoles(user.roles || []);
    setDisabled(Boolean(user.disabled));
    setPassword("");
  };
  const saveUser = async () => {
    setBusy(true);
    try {
      await apiPost("/api/users/update", { user_id: editing.user_id, display_name: displayName, roles, disabled });
      showToast("Account roles updated");
      setEditing(null);
      clearForm();
      await load();
    } finally { setBusy(false); }
  };
  const resetPassword = async () => {
    if (password.length < 12) return;
    setBusy(true);
    try {
      await apiPost("/api/users/reset-password", { user_id: editing.user_id, password });
      showToast("Password reset; existing sessions were signed out");
      setPassword("");
    } finally { setBusy(false); }
  };
  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start"><Box><Title order={3} size="h4">Machine Accounts</Title><Text size="sm" c="dimmed">Credentials and roles apply only to this SentriFace data store on this machine.</Text></Box><Button onClick={() => { clearForm(); setCreateOpen(true); }}>Add account</Button></Group>
      <Alert color="blue" title="Backend-enforced roles">Hidden controls are only a convenience. Every protected operation is independently authorized by the local API.</Alert>
      {users.map((user) => (
        <Card key={user.user_id} withBorder radius="md">
          <Group justify="space-between" align="flex-start">
            <Box><Text fw={800}>{user.display_name}</Text><Text size="sm" c="dimmed">{user.username}{user.user_id === currentUser?.user_id ? " · current account" : ""}</Text><Group gap="xs" mt="xs">{user.roles.map((role) => <Badge key={role} variant="light">{role}</Badge>)}{user.disabled ? <Badge color="red">Disabled</Badge> : <Badge color="teal">Enabled</Badge>}</Group></Box>
            <Button variant="default" onClick={() => openEdit(user)}>Manage</Button>
          </Group>
        </Card>
      ))}
      <Modal opened={createOpen} onClose={() => setCreateOpen(false)} title="Add machine account" centered>
        <Stack><TextInput label="Username" value={username} onChange={(event) => setUsername(event.currentTarget.value)} /><TextInput label="Display name" value={displayName} onChange={(event) => setDisplayName(event.currentTarget.value)} /><PasswordInput label="Temporary password" description="At least 12 characters" value={password} onChange={(event) => setPassword(event.currentTarget.value)} /><MultiSelect label="Roles" data={roleOptions} value={roles} onChange={setRoles} searchable /><Group justify="flex-end"><Button variant="default" onClick={() => setCreateOpen(false)}>Cancel</Button><Button loading={busy} disabled={!username || password.length < 12 || !roles.length} onClick={guarded(createUser)}>Create</Button></Group></Stack>
      </Modal>
      <Modal opened={Boolean(editing)} onClose={() => setEditing(null)} title={`Manage ${editing?.username || "account"}`} centered>
        <Stack><TextInput label="Display name" value={displayName} onChange={(event) => setDisplayName(event.currentTarget.value)} /><MultiSelect label="Roles" data={roleOptions} value={roles} onChange={setRoles} searchable /><Switch label="Disable this account" checked={disabled} onChange={(event) => setDisabled(event.currentTarget.checked)} /><Group justify="flex-end"><Button variant="default" onClick={() => setEditing(null)}>Cancel</Button><Button loading={busy} disabled={!roles.length} onClick={guarded(saveUser)}>Save roles</Button></Group><Card withBorder><Text fw={700}>Administrator password reset</Text><Text size="xs" c="dimmed" mb="sm">Resets failed-login lockout and signs out all sessions for this account.</Text><PasswordInput label="New password" value={password} onChange={(event) => setPassword(event.currentTarget.value)} /><Button mt="sm" variant="light" color="orange" loading={busy} disabled={password.length < 12} onClick={guarded(resetPassword)}>Reset password</Button></Card></Stack>
      </Modal>
    </Stack>
  );
}