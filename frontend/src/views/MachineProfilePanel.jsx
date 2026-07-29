import { useState } from "react";
import { Alert, Badge, Box, Button, Card, Group, Modal, SimpleGrid, Stack, Text, TextInput, Title } from "@mantine/core";

export function MachineProfilePanel({ profile, onConfigureRecovery }) {
  const [recoveryOpen, setRecoveryOpen] = useState(false);
  const [destination, setDestination] = useState(profile?.recovery?.destination || "");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [savingRecovery, setSavingRecovery] = useState(false);
  if (!profile) {
    return <Alert color="yellow" title="Machine profile unavailable">Reload app data after the local engine starts.</Alert>;
  }
  const hardware = profile.hardware || {};
  const modelUsage = profile.model_usage || {};
  const index = profile.index || {};
  const usageLabel = modelUsage.research_only
    ? "Non-commercial research"
    : modelUsage.license_name || modelUsage.usage_basis || "Not declared";
  const configureRecovery = async () => {
    if (!destination.trim() || savingRecovery) return;
    setSavingRecovery(true);
    try {
      const result = await onConfigureRecovery(destination.trim());
      if (!result) return;
      setRecoveryCode(result.recovery_code || "");
      setRecoveryOpen(false);
    } finally {
      setSavingRecovery(false);
    }
  };
  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start" className="debug-main-header">
        <Box>
          <Title order={3} size="h4">Machine Profile</Title>
          <Text size="sm" c="dimmed">Detected hardware and active local inference configuration</Text>
        </Box>
        <Badge size="lg" color="teal" variant="light">{String(profile.hardware_tier || "unknown").toUpperCase()}</Badge>
      </Group>

      <Alert color="blue" title={`Why SentriFace selected the ${profile.hardware_tier || "current"} profile`}>
        {hardware.reason || "SentriFace selected conservative settings for this machine."}
      </Alert>

      <ProfileCard title="Machine" items={[
        ["Operating system", hardware.operating_system || "Unknown"],
        ["Architecture", hardware.architecture || "Unknown"],
        ["Logical CPU threads", hardware.cpu_count ?? "Unknown"],
        ["Physical memory", hardware.memory_gb == null ? "Unavailable" : `${hardware.memory_gb} GB`],
      ]} />

      <ProfileCard title="Runtime limits" items={[
        ["Runtime", String(profile.runtime || "unknown").toUpperCase()],
        ["Inference workers", profile.max_workers ?? "-"],
        ["ONNX threads", profile.onnx_intra_threads ?? "-"],
        ["Batch size", profile.batch_size ?? "-"],
        ["Maximum image edge", profile.max_image_edge ? `${profile.max_image_edge}px` : "-"],
        ["Detector input", profile.detector_input_size ? `${profile.detector_input_size}px` : "-"],
        ["Index backend", index.actual || index.requested || "-"],
        ["Small-model preference", profile.prefer_small_models ? "Enabled" : "Disabled"],
      ]}>
        {index.degraded_reason ? <Alert color="yellow" title="Index fallback active" mt="md">{index.degraded_reason}</Alert> : null}
      </ProfileCard>

      <ProfileCard title="Matching policy" items={[
        ["Strong threshold", threshold(profile.high_confidence)],
        ["Moderate threshold", threshold(profile.medium_confidence)],
        ["Possible threshold", threshold(profile.possible_confidence)],
        ["Minimum quality", threshold(profile.min_quality_score)],
      ]}>
        <Text size="xs" c="dimmed" mt="md">These are similarity and quality thresholds, not identity probabilities.</Text>
      </ProfileCard>

      <Card withBorder radius="md">
        <Text fw={800} mb="md">Recognition models</Text>
        <Stack gap="xs">
          <ProfileLine label="Detector" value={profile.models?.detector} />
          <ProfileLine label="Recognizer" value={profile.models?.recognizer} />
          <Group justify="space-between"><Text size="sm" c="dimmed">Declared usage</Text><Badge color={modelUsage.research_only ? "orange" : "teal"} variant="light">{usageLabel}</Badge></Group>
          {modelUsage.licensor ? <ProfileLine label="Licensor" value={modelUsage.licensor} /> : null}
          {modelUsage.accepted_at ? <ProfileLine label="Terms accepted" value={new Date(modelUsage.accepted_at).toLocaleString()} /> : null}
        </Stack>
      </Card>

      <Card withBorder radius="md">
        <Group justify="space-between" align="flex-start">
          <Box>
            <Text fw={800}>Disaster recovery</Text>
            <Text size="sm" c="dimmed">Automatic encrypted backups to a separate local or removable drive</Text>
          </Box>
          <Badge color={profile.recovery?.configured ? "teal" : "yellow"} variant="light">{profile.recovery?.configured ? "Configured" : "Action required"}</Badge>
        </Group>
        <Stack gap="xs" mt="md">
          <ProfileLine label="Destination" value={profile.recovery?.destination || "Not configured"} />
          <ProfileLine label="Destination available" value={profile.recovery?.destination_available ? "Yes" : "No"} />
          <ProfileLine label="Recovery kit" value={profile.recovery?.recovery_kit_present ? "Present" : "Missing"} />
          <ProfileLine label="Last external backup" value={profile.recovery?.last_external_backup ? new Date(profile.recovery.last_external_backup).toLocaleString() : "None"} />
          <ProfileLine label="Retained external backups" value={`${profile.recovery?.external_backup_count || 0} / ${profile.recovery?.external_retention_limit || 10}`} />
        </Stack>
        <Button mt="md" variant="light" onClick={() => setRecoveryOpen(true)}>Configure recovery destination</Button>
      </Card>

      <Modal opened={recoveryOpen} onClose={() => setRecoveryOpen(false)} title="Configure disaster recovery" centered>
        <Stack>
          <Alert color="blue">Choose a folder outside the SentriFace data directory, preferably on another physical drive. SentriFace will write encrypted automatic backups and a recovery kit there.</Alert>
          <TextInput label="Recovery folder path" value={destination} onChange={(event) => setDestination(event.currentTarget.value)} placeholder="E:\\SentriFace Recovery" />
          <Group justify="flex-end"><Button variant="default" onClick={() => setRecoveryOpen(false)}>Cancel</Button><Button loading={savingRecovery} disabled={!destination.trim()} onClick={configureRecovery}>Create recovery kit</Button></Group>
        </Stack>
      </Modal>

      <Modal opened={Boolean(recoveryCode)} onClose={() => setRecoveryCode("")} title="Save this recovery code now" centered closeOnClickOutside={false} closeOnEscape={false}>
        <Stack>
          <Alert color="red" title="This code is required after machine loss">Store it in a password manager or print it. SentriFace will not display it again.</Alert>
          <Text style={{ overflowWrap: "anywhere" }} fw={800}>{recoveryCode}</Text>
          <Button onClick={() => navigator.clipboard?.writeText(recoveryCode)}>Copy recovery code</Button>
          <Button variant="default" onClick={() => setRecoveryCode("")}>I saved the code</Button>
        </Stack>
      </Modal>      <ProfileCard title="Security enforcement" items={[
        ["Database", profile.storage_security?.database_encrypted ? "SQLCipher encrypted" : "Not encrypted"],
        ["Managed images", profile.storage_security?.managed_files_encrypted ? "AES-256-GCM" : "Not encrypted"],
        ["Managed backups", profile.storage_security?.managed_backups_encrypted ? "Encrypted" : "Not encrypted"],
        ["Persistent logs", profile.storage_security?.persistent_logs_encrypted ? "Encrypted records" : "Not encrypted"],
        ["Master key", profile.storage_security?.key_protection || "Unknown"],
        ["Server listener", profile.offline_enforcement?.loopback_only ? "IPv4 loopback only" : "Unknown"],
        ["Outbound sockets", profile.offline_enforcement?.outbound_socket_guard ? "Blocked except loopback" : "Guard unavailable"],
      ]} />
      <Card withBorder radius="md">
        <Text fw={800} mb="md">Local storage</Text>
        <Stack gap="xs"><ProfileLine label="Data directory" value={profile.data_dir} /><ProfileLine label="Database" value={profile.db_path} /></Stack>
      </Card>
    </Stack>
  );
}

function ProfileCard({ title, items, children }) {
  return <Card withBorder radius="md"><Text fw={800} mb="md">{title}</Text><SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>{items.map(([label, value]) => <Box key={label}><Text size="xs" c="dimmed" fw={700}>{label}</Text><Text fw={800}>{value}</Text></Box>)}</SimpleGrid>{children}</Card>;
}

function ProfileLine({ label, value }) {
  return <Group justify="space-between" align="flex-start" wrap="nowrap"><Text size="sm" c="dimmed">{label}</Text><Text size="sm" fw={700} ta="right" style={{ overflowWrap: "anywhere" }}>{value || "-"}</Text></Group>;
}

function threshold(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(3) : "-";
}
