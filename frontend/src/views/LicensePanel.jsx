import { useState } from "react";
import { Alert, Badge, Button, Card, Code, Group, Stack, Text, Textarea, Title } from "@mantine/core";
import { IconKey, IconRefresh, IconShieldCheck } from "@tabler/icons-react";

export function LicensePanel({ license, canActivate = false }) {
  const [token, setToken] = useState("");
  const status = license?.status;
  const licensed = Boolean(status?.licensed);
  const enforced = Boolean(status?.enforced);

  const activate = async () => {
    if (!token.trim()) return;
    await license.activate(token.trim());
    setToken("");
  };

  return (
    <Stack gap="md" className="license-panel">
      <Card withBorder radius="md" p="lg">
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={3}>License & activation</Title>
            <Text size="sm" c="dimmed" mt={4}>Verification happens locally. SentriFace does not contact an activation service.</Text>
          </div>
          <Badge color={licensed ? "teal" : enforced ? "orange" : "gray"} variant="light">
            {licensed ? "Activated" : enforced ? "Activation required" : "Not enforced in this runtime"}
          </Badge>
        </Group>
        {license?.error ? <Alert color="red" mt="md">{license.error}</Alert> : null}
        {status?.message ? <Alert color={licensed ? "teal" : "blue"} icon={licensed ? <IconShieldCheck size={18} /> : <IconKey size={18} />} mt="md">{status.message}</Alert> : null}
        {status?.machine_id ? (
          <Stack gap={4} mt="md">
            <Text size="sm" fw={700}>Machine ID</Text>
            <Code block>{status.machine_id}</Code>
            <Text size="xs" c="dimmed">This identifier contains no raw Windows MachineGuid.</Text>
          </Stack>
        ) : null}
        {status?.license ? (
          <Stack gap={3} mt="md">
            <Text size="sm"><b>License ID:</b> {status.license.license_id}</Text>
            <Text size="sm"><b>Edition:</b> {status.license.edition}</Text>
            <Text size="sm"><b>Type:</b> {status.license.license_type}</Text>
          </Stack>
        ) : null}
        {enforced && !licensed && canActivate ? (
          <Stack mt="md">
            <Textarea
              label="Signed offline license"
              description="Paste the complete SFE2 license issued for this machine."
              value={token}
              onChange={(event) => setToken(event.currentTarget.value)}
              minRows={4}
              maxLength={16384}
              autosize
            />
            <Group justify="flex-end">
              <Button variant="default" leftSection={<IconRefresh size={16} />} onClick={license.refresh}>Refresh</Button>
              <Button leftSection={<IconKey size={16} />} loading={license.activating} disabled={!token.trim()} onClick={activate}>Activate</Button>
            </Group>
          </Stack>
        ) : enforced && !licensed ? (
          <Alert color="yellow" mt="md">An administrator must activate this installation. Backup, restore, integrity recovery, and support remain available.</Alert>
        ) : null}
      </Card>
    </Stack>
  );
}
