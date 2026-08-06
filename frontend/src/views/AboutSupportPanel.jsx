import { useMemo, useState } from "react";
import { Alert, Box, Button, Card, Group, SimpleGrid, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import {
  IconCheck,
  IconClipboard,
  IconCpu,
  IconDatabase,
  IconDownload,
  IconMail,
  IconFileDescription,
  IconLock,
  IconPhotoOff,
} from "@tabler/icons-react";

export function AboutSupportPanel({ profile, events = [], onExportSupportPackage }) {
  const [copied, setCopied] = useState(false);
  const [emailCopied, setEmailCopied] = useState(false);
  const [exporting, setExporting] = useState(false);
  const report = useMemo(() => buildDiagnosticReport(profile, events), [events, profile]);

  if (!profile) {
    return <Alert color="yellow" title="About details are unavailable">Reload app data after SentriFace starts.</Alert>;
  }

  const application = profile.application || {};
  const hardware = profile.hardware || {};
  const modelNames = [fileName(profile.models?.detector), fileName(profile.models?.recognizer)].filter(Boolean);
  const storage = profile.storage_security || {};
  const protectedCount = [
    storage.database_encrypted,
    storage.managed_files_encrypted,
    storage.managed_backups_encrypted,
    storage.persistent_logs_encrypted,
  ].filter(Boolean).length;

  const copyReport = async () => {
    await copyText(JSON.stringify(report, null, 2));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  const exportPackage = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      await onExportSupportPackage?.();
    } finally {
      setExporting(false);
    }
  };

  const copySupportEmail = async () => {
    await copyText(SUPPORT_EMAIL);
    setEmailCopied(true);
    window.setTimeout(() => setEmailCopied(false), 2000);
  };

  return (
    <Stack gap="md" className="about-support-panel">
      <Box className="about-support-grid">
        <Card withBorder radius="md" className="about-card about-card--identity">
          <Group align="flex-start" wrap="nowrap" className="about-brand">
            <img src="/sentriface-icon-64.png" alt="SentriFace Edge" className="about-logo" />
            <Box>
              <Title order={3} size="h4">About SentriFace <Text span inherit c="teal">Edge</Text></Title>
              <Text size="sm" c="dimmed" mt={4}>
                Offline face recognition built to keep recognition and identity data on this computer.
              </Text>
            </Box>
          </Group>

          <Stack gap={0} mt="md" className="about-detail-list">
            <DetailRow icon={IconFileDescription} label="Version" value={application.version || "Unavailable"} />
            <DetailRow icon={IconCpu} label="Runtime" value={`${String(profile.runtime || "unknown").toUpperCase()} · ${hardware.operating_system || "Unknown OS"} ${hardware.architecture || ""}`.trim()} />
            <DetailRow icon={IconDatabase} label="Database schema" value={application.database_schema_version ?? "Unavailable"} />
            <DetailRow icon={IconCpu} label="Models in use" value={modelNames.length ? modelNames.join(" · ") : "Not configured"} />
            <DetailRow
              icon={IconLock}
              label="Local data protection"
              value={protectedCount === 4 ? "All managed storage protected" : `${protectedCount} of 4 protections active`}
            />
          </Stack>

          <Card withBorder radius="md" mt="md" className="developer-contact-card">
            <Group align="flex-start" wrap="nowrap">
              <ThemeIcon color="teal" variant="light" size={44} radius="md"><IconMail size={23} /></ThemeIcon>
              <Box className="developer-contact-copy">
                <Text fw={700}>Developer support</Text>
                <Text size="sm" c="dimmed">Suraj Singh</Text>
                <Text size="sm" c="dimmed" mt={4}>
                  Send questions, issue reports, or feature requests by email.
                </Text>
              </Box>
            </Group>
            <Group gap="xs" mt="md" wrap="wrap">
              <Button
                component="a"
                href={`mailto:${SUPPORT_EMAIL}`}
                variant="filled"
                leftSection={<IconMail size={17} />}
              >
                Email support
              </Button>
              <Button
                variant="default"
                leftSection={emailCopied ? <IconCheck size={17} /> : <IconClipboard size={17} />}
                onClick={copySupportEmail}
              >
                {emailCopied ? "Email copied" : "Copy email"}
              </Button>
            </Group>
            <Text component="a" href={`mailto:${SUPPORT_EMAIL}`} size="sm" mt="sm" className="support-email-link">
              {SUPPORT_EMAIL}
            </Text>
          </Card>
        </Card>

        <Card withBorder radius="md" className="about-card about-card--support">
          <Title order={3} size="h4">Support & troubleshooting</Title>
          <Text size="sm" c="dimmed" mt={4}>
            This computer may be offline. Copy the report or export a package, then share it from an internet-connected device.
          </Text>

          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" mt="md">
            <Button
              variant="default"
              className="support-action"
              leftSection={copied ? <IconCheck size={20} /> : <IconClipboard size={20} />}
              onClick={copyReport}
            >
              {copied ? "Diagnostic report copied" : "Copy diagnostic report"}
            </Button>
            <Button
              variant="default"
              className="support-action"
              leftSection={<IconDownload size={20} />}
              loading={exporting}
              onClick={exportPackage}
            >
              Export support package
            </Button>
          </SimpleGrid>

          <Text size="sm" fw={700} mt="lg" mb="xs">Included</Text>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing={6} className="support-contents-grid">
            <IncludedItem label="Application and schema versions" />
            <IncludedItem label="System and runtime summary" />
            <IncludedItem label="Processing configuration" />
            <IncludedItem label="Model filenames and declared usage" />
            <IncludedItem label="Protection and recovery readiness" />
            <IncludedItem label="Event types and timestamps" />
          </SimpleGrid>

          <Alert color="blue" icon={<IconPhotoOff size={18} />} mt="md">
            Face images, source images, embeddings, names, database contents, secrets, local paths, and event details are excluded.
          </Alert>
        </Card>
      </Box>
    </Stack>
  );
}

const SUPPORT_EMAIL = "sentriface-support@gmail.com";

function DetailRow({ icon: Icon, label, value }) {
  return (
    <Group justify="space-between" wrap="nowrap" className="about-detail-row">
      <Group gap="sm" wrap="nowrap">
        <ThemeIcon variant="subtle" color="gray"><Icon size={17} /></ThemeIcon>
        <Text size="sm" c="dimmed">{label}</Text>
      </Group>
      <Text size="sm" fw={600} ta="right">{String(value)}</Text>
    </Group>
  );
}

function IncludedItem({ label }) {
  return (
    <Group gap="sm" wrap="nowrap" align="flex-start" className="support-included-item">
      <ThemeIcon size={18} radius="xl" color="teal" variant="filled"><IconCheck size={11} /></ThemeIcon>
      <Text size="sm" c="dimmed">{label}</Text>
    </Group>
  );
}

export function buildDiagnosticReport(profile, events = []) {
  const eventCounts = {};
  const eventHistory = events.map((item) => {
    const event = String(item?.event || "unknown");
    eventCounts[event] = (eventCounts[event] || 0) + 1;
    return { timestamp: String(item?.timestamp || ""), event };
  });
  const hardware = profile?.hardware || {};
  const storage = profile?.storage_security || {};
  const readiness = profile?.recovery_readiness || {};
  return {
    generated_at: new Date().toISOString(),
    application: profile?.application || {},
    runtime: profile?.runtime || "unknown",
    hardware: {
      tier: profile?.hardware_tier || "unknown",
      cpu_count: hardware.cpu_count ?? null,
      memory_gb: hardware.memory_gb ?? null,
      operating_system: hardware.operating_system || "unknown",
      architecture: hardware.architecture || "unknown",
    },
    processing: {
      max_workers: profile?.max_workers ?? null,
      onnx_intra_threads: profile?.onnx_intra_threads ?? null,
      max_image_edge: profile?.max_image_edge ?? null,
      detector_input_size: profile?.detector_input_size ?? null,
      batch_size: profile?.batch_size ?? null,
      prefer_small_models: Boolean(profile?.prefer_small_models),
    },
    models: {
      detector: fileName(profile?.models?.detector) || "not configured",
      recognizer: fileName(profile?.models?.recognizer) || "not configured",
      usage: profile?.model_usage || {},
    },
    offline_enforcement: profile?.offline_enforcement || {},
    storage_security: {
      database_encrypted: Boolean(storage.database_encrypted),
      managed_files_encrypted: Boolean(storage.managed_files_encrypted),
      managed_backups_encrypted: Boolean(storage.managed_backups_encrypted),
      persistent_logs_encrypted: Boolean(storage.persistent_logs_encrypted),
      key_protection: storage.key_protection || "unknown",
    },
    recovery_readiness: {
      ready: Boolean(readiness.ready),
      configured: Boolean(readiness.configured),
      destination_available: Boolean(readiness.destination_available),
      recovery_kit_present: Boolean(readiness.recovery_kit_present),
      external_backup_present: Boolean(readiness.external_backup_present),
      acknowledged: Boolean(readiness.acknowledged),
    },
    events: { total: eventHistory.length, counts: eventCounts, history: eventHistory },
  };
}

function fileName(value) {
  if (!value) return "";
  return String(value).split(/[\\/]/).pop();
}

async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const area = document.createElement("textarea");
  area.value = value;
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}
