import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert, Badge, Box, Button, Card, Center, Checkbox, Divider, Grid, Group,
  Loader, Paper, ScrollArea, SimpleGrid, Stack, Text, TextInput, ThemeIcon, Title,
} from "@mantine/core";
import {
  IconAlertTriangle, IconBriefcase, IconCheck, IconCpu, IconFileCertificate,
  IconFlask, IconFolder, IconLock, IconShieldCheck,
} from "@tabler/icons-react";

import { useApiClient } from "../hooks/useApiClient.js";

const EMPTY_FORM = {
  detectorPath: "",
  detectorSha256: "",
  recognizerPath: "",
  recognizerSha256: "",
  calibrationPath: "",
  calibrationSha256: "",
  organization: "",
  licensor: "",
  licenseReference: "",
  licenseName: "",
  accepted: false,
};

export function ModelGate({ user, logout, children }) {
  const { apiGet, apiPost, showToast } = useApiClient();
  const [status, setStatus] = useState(null);
  const [selectedId, setSelectedId] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const next = await apiGet("/api/models/status", { silent: true });
      setStatus(next);
      setError("");
    } catch (requestError) {
      setError(requestError?.message || "Model status is unavailable");
    } finally {
      setLoading(false);
    }
  }, [apiGet]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    const interval = window.setInterval(refresh, 15_000);
    return () => window.clearInterval(interval);
  }, [refresh]);
  useEffect(() => {
    const requireModels = () => { setLoading(true); refresh(); };
    window.addEventListener("sentriface-models-required", requireModels);
    return () => window.removeEventListener("sentriface-models-required", requireModels);
  }, [refresh]);

  const combinations = useMemo(
    () => [...(status?.combinations?.research || []), ...(status?.combinations?.commercial || [])],
    [status],
  );
  const selected = combinations.find((item) => item.id === selectedId) || null;
  const update = (field) => (event) => {
    const value = event?.currentTarget?.type === "checkbox" ? event.currentTarget.checked : event.currentTarget.value;
    setForm((current) => ({ ...current, [field]: value }));
  };

  const install = async () => {
    if (!selected) return;
    setInstalling(true);
    setError("");
    try {
      const next = await apiPost("/api/models/install", {
        combination_id: selected.id,
        detector_path: form.detectorPath,
        detector_sha256: form.detectorSha256,
        recognizer_path: form.recognizerPath,
        recognizer_sha256: form.recognizerSha256,
        calibration_path: form.calibrationPath || undefined,
        calibration_sha256: form.calibrationSha256 || undefined,
        organization: form.organization,
        licensor: form.licensor,
        license_reference: form.licenseReference,
        license_name: form.licenseName,
        accept_responsibility: form.accepted,
      }, { silent: true, timeoutMs: 10 * 60 * 1000 });
      setStatus(next);
      showToast("Recognition models verified and activated");
    } catch (requestError) {
      setError(requestError?.message || "The model bundle could not be activated");
    } finally {
      setInstalling(false);
    }
  };

  if (loading) {
    return <Center mih="100vh"><Stack align="center"><Loader /><Text c="dimmed">Checking local recognition models...</Text></Stack></Center>;
  }
  if (status?.ready) return children;

  const required = Boolean(selected)
    && form.detectorPath && /^[a-f0-9]{64}$/i.test(form.detectorSha256)
    && form.recognizerPath && /^[a-f0-9]{64}$/i.test(form.recognizerSha256)
    && ((!form.calibrationPath && !form.calibrationSha256)
      || (form.calibrationPath && /^[a-f0-9]{64}$/i.test(form.calibrationSha256)))
    && form.accepted
    && (selected.usage_basis !== "commercial-license" || (form.licensor && form.licenseReference))
    && (selected.usage_basis !== "permissive-license" || form.licenseName);

  return (
    <Box mih="100vh" bg="var(--mantine-color-body)" p={{ base: "md", md: "xl" }}>
      <Stack maw={1240} mx="auto" gap="lg">
        <Group justify="space-between" align="flex-start">
          <Box>
            <Group gap="xs"><ThemeIcon color="teal" variant="light" size="lg"><IconCpu size={21} /></ThemeIcon><Title order={1} size="h2">Choose recognition models</Title></Group>
            <Text c="dimmed" mt={6}>SentriFace is signed in, encrypted, and offline. Add a supported local detector and recognizer to continue.</Text>
          </Box>
          <Stack gap={2} align="flex-end"><Text size="sm" fw={700}>{user?.display_name}</Text><Button size="compact-sm" variant="subtle" color="gray" onClick={logout}>Sign out</Button></Stack>
        </Group>

        {status?.error ? <Alert color="orange" icon={<IconAlertTriangle size={18} />} title="Model setup required">{status.error}</Alert> : null}
        {!status?.can_configure ? (
          <Card withBorder radius="lg" p="xl"><Stack align="center" py="xl"><ThemeIcon size={56} radius="xl" color="orange" variant="light"><IconLock size={28} /></ThemeIcon><Title order={2} size="h3">Administrator action required</Title><Text c="dimmed" ta="center" maw={620}>Your account cannot install recognition models. Ask a SentriFace administrator to sign in and provide the locally licensed model files.</Text></Stack></Card>
        ) : (
          <>
            <Grid gutter="lg" align="stretch">
              <Grid.Col span={{ base: 12, md: 6 }}>
                <ModelSide
                  tone="orange"
                  icon={IconFlask}
                  eyebrow="NON-COMMERCIAL"
                  title="Research only"
                  description="Official InsightFace pretrained packages are supported here only for non-commercial research under their supplier terms."
                  warning="Do not select this side for a sold product, paid service, production deployment, or other commercial use."
                  items={status?.combinations?.research || []}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                />
              </Grid.Col>
              <Grid.Col span={{ base: 12, md: 6 }}>
                <ModelSide
                  tone="teal"
                  icon={IconBriefcase}
                  eyebrow="COMMERCIAL"
                  title="Commercial use"
                  description="Use supplier-licensed InsightFace weights or another compatible pair whose license permits your commercial deployment."
                  warning="SentriFace records your declaration but cannot authenticate or grant third-party model rights."
                  items={status?.combinations?.commercial || []}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                />
              </Grid.Col>
            </Grid>

            {selected ? (
              <Card withBorder radius="lg" p={{ base: "md", md: "xl" }} shadow="sm">
                <Stack gap="lg">
                  <Group justify="space-between" align="flex-start">
                    <Box><Badge color={selected.usage_basis === "noncommercial-research" ? "orange" : "teal"} variant="light">Selected combination</Badge><Title order={2} size="h3" mt="xs">{selected.name}</Title><Text size="sm" c="dimmed">{selected.detector} + {selected.recognizer}</Text></Box>
                    <ThemeIcon size={44} radius="xl" color="teal" variant="light"><IconCheck size={23} /></ThemeIcon>
                  </Group>
                  <Alert color="blue" icon={<IconFolder size={18} />} title="Local files only">Enter absolute paths on this machine. SentriFace never downloads or uploads model files. Verified copies will be installed under {status.models_dir}.</Alert>
                  <Text size="xs" c="dimmed">Checksum tools: Windows <code>Get-FileHash PATH -Algorithm SHA256</code>; macOS/Linux <code>shasum -a 256 PATH</code>.</Text>
                  <SetupExamples selected={selected} />
                  <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
                    <FileFields
                      title="Detector weights"
                      path={form.detectorPath}
                      digest={form.detectorSha256}
                      onPath={update("detectorPath")}
                      onDigest={update("detectorSha256")}
                      placeholder="C:\models\detector.onnx"
                      description={`An actual ONNX detector file from your model supplier${selected.detector_file ? `, normally named ${selected.detector_file} for this package` : ""}.`}
                    />
                    <FileFields
                      title="Recognizer weights"
                      path={form.recognizerPath}
                      digest={form.recognizerSha256}
                      onPath={update("recognizerPath")}
                      onDigest={update("recognizerSha256")}
                      placeholder="C:\models\recognizer.onnx"
                      description={`An actual 512-dimensional ArcFace-compatible ONNX recognizer${selected.recognizer_file ? `, normally named ${selected.recognizer_file} for this package` : ""}.`}
                    />
                  </SimpleGrid>
                  <FileFields
                    title="Calibration threshold file (optional)"
                    path={form.calibrationPath}
                    digest={form.calibrationSha256}
                    onPath={update("calibrationPath")}
                    onDigest={update("calibrationSha256")}
                    placeholder="C:\models\calibration.json"
                    description="Leave both fields empty to use SentriFace's built-in thresholds. For a custom validation-calibrated file, provide both its path and SHA-256."
                    required={false}
                  />
                  <Divider label="Usage declaration" labelPosition="left" />
                  <SimpleGrid cols={{ base: 1, md: 2 }}>
                    <TextInput label="Organization" value={form.organization} onChange={update("organization")} placeholder="Example: Acme Security Ltd (optional)" description="The person or organization operating this SentriFace installation." />
                    {selected.usage_basis === "commercial-license" ? <TextInput required label="Model licensor" value={form.licensor} onChange={update("licensor")} placeholder="Example: supplier named on your licence" description="Copy the legal supplier name from your model agreement." /> : null}
                    {selected.usage_basis === "commercial-license" ? <TextInput required label="License reference" value={form.licenseReference} onChange={update("licenseReference")} placeholder="Example: agreement, invoice, or entitlement ID" description="Use your real customer-specific reference; do not copy an example value." /> : null}
                    {selected.usage_basis === "permissive-license" ? <TextInput required label="Model license" value={form.licenseName} onChange={update("licenseName")} placeholder="Example: Apache-2.0" description="Enter the exact licence identifier supplied with these particular weight files." /> : null}
                  </SimpleGrid>
                  <Paper withBorder p="md" radius="md" bg="var(--mantine-color-default-hover)">
                    <Checkbox checked={form.accepted} onChange={update("accepted")} label="I supplied these files and accept responsibility for model licensing, biometric permissions, calibration, and the intended use. SentriFace supplies no model rights." />
                  </Paper>
                  {error ? <Alert color="red" title="Models were not activated">{error}</Alert> : null}
                  <Group justify="space-between"><Button variant="subtle" color="gray" onClick={() => { setSelectedId(""); setError(""); }}>Choose another combination</Button><Button size="md" leftSection={<IconShieldCheck size={18} />} loading={installing} disabled={!required} onClick={install}>Verify and start SentriFace</Button></Group>
                </Stack>
              </Card>
            ) : null}
          </>
        )}
        <Text size="xs" c="dimmed" ta="center">Supported means runtime compatibility only. It does not mean SentriFace owns, endorses, redistributes, or licenses the selected weights.</Text>
      </Stack>
    </Box>
  );
}

function ModelSide({ tone, icon: Icon, eyebrow, title, description, warning, items, selectedId, onSelect }) {
  return (
    <Card withBorder radius="lg" p={{ base: "md", md: "xl" }} h="100%" style={{ borderTop: `4px solid var(--mantine-color-${tone}-6)` }}>
      <Stack h="100%">
        <Group><ThemeIcon color={tone} variant="light" size="xl" radius="xl"><Icon size={24} /></ThemeIcon><Box><Text size="xs" fw={900} c={`${tone}.7`} lts={1}>{eyebrow}</Text><Title order={2} size="h3">{title}</Title></Box></Group>
        <Text size="sm" c="dimmed">{description}</Text>
        <Alert color={tone} variant="light" icon={<IconFileCertificate size={17} />}>{warning}</Alert>
        <ScrollArea.Autosize mah={390} offsetScrollbars>
          <Stack gap="sm">
            {items.map((item) => (
              <Paper key={item.id} component="button" type="button" withBorder radius="md" p="md" ta="left" onClick={() => onSelect(item.id)} style={{ cursor: "pointer", borderColor: selectedId === item.id ? `var(--mantine-color-${tone}-6)` : undefined, background: selectedId === item.id ? `var(--mantine-color-${tone}-light)` : undefined }}>
                <Group justify="space-between" wrap="nowrap"><Box><Text fw={800}>{item.name}</Text><Text size="xs" c="dimmed" mt={3}>{item.detector} + {item.recognizer}</Text>{item.detector_file ? <Text size="xs" c="dimmed" mt={3}>Package files: {item.detector_file} + {item.recognizer_file}</Text> : null}</Box>{selectedId === item.id ? <ThemeIcon color={tone} radius="xl" size="sm"><IconCheck size={13} /></ThemeIcon> : null}</Group>
                <Text size="xs" mt="sm">{item.note}</Text>
              </Paper>
            ))}
          </Stack>
        </ScrollArea.Autosize>
      </Stack>
    </Card>
  );
}

function FileFields({ title, path, digest, onPath, onDigest, placeholder, description, required = true }) {
  return (
    <Stack gap="xs">
      <Text fw={800}>{title}</Text>
      <TextInput required={required} label="Local file path" value={path} onChange={onPath} placeholder={placeholder} description={description} />
      <TextInput required={required} label="SHA-256" value={digest} onChange={onDigest} placeholder="64 hexadecimal characters" styles={{ input: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" } }} />
    </Stack>
  );
}
function SetupExamples({ selected }) {
  const detectorName = selected.detector_file || "detector.onnx";
  const recognizerName = selected.recognizer_file || "recognizer.onnx";
  const usageExample = selected.usage_basis === "commercial-license"
    ? "Licensor: <supplier on your agreement> · Reference: <your agreement/invoice/entitlement ID>"
    : selected.usage_basis === "permissive-license"
      ? "Model licence: <exact identifier supplied with these weights, for example Apache-2.0>"
      : "Research declaration: non-commercial research only; organization is optional";
  const setupFile = {
    combination: selected.name,
    detector_path: `<absolute-path>/${detectorName}`,
    detector_sha256: "<64-character-sha256-of-detector>",
    recognizer_path: `<absolute-path>/${recognizerName}`,
    recognizer_sha256: "<64-character-sha256-of-recognizer>",
    calibration_path: "",
    calibration_sha256: "",
    organization: "<optional-organization-name>",
    usage_basis: selected.usage_basis,
    ...(selected.usage_basis === "commercial-license" ? {
      model_licensor: "<supplier-named-on-your-licence>",
      license_reference: "<agreement-invoice-or-entitlement-id>",
    } : {}),
    ...(selected.usage_basis === "permissive-license" ? {
      model_license: "<exact-licence-identifier-from-the-model-provider>",
    } : {}),
  };
  const calibrationFile = {
    schema_version: 1,
    recognizer_sha256: "<64-character-sha256-of-exact-recognizer>",
    representative_dataset: "<validation-dataset-description>",
    target_false_match_rate: 0.0001,
    thresholds: { possible: 0.40, likely: 0.50, strong: 0.60 },
  };

  return (
    <Paper withBorder radius="md" p="md" bg="var(--mantine-color-default-hover)">
      <Stack gap="xs">
        <Group justify="space-between" align="center">
          <Text fw={800}>Example values for this selection</Text>
          <Group gap="xs">
            <Button size="compact-xs" variant="default" onClick={() => downloadJsonExample(`${selected.id}.example.json`, setupFile)}>Download setup example</Button>
            <Button size="compact-xs" variant="default" onClick={() => downloadJsonExample("calibration-thresholds.example.json", calibrationFile)}>Download calibration example</Button>
          </Group>
        </Group>
        <Text size="sm"><Text span fw={700}>Detector path:</Text> <code>C:\licensed-models\{detectorName}</code></Text>
        <Text size="sm"><Text span fw={700}>Recognizer path:</Text> <code>C:\licensed-models\{recognizerName}</code></Text>
        <Text size="sm"><Text span fw={700}>Each SHA-256:</Text> <code>&lt;64 hexadecimal characters produced from that exact file&gt;</code></Text>
        <Text size="sm"><Text span fw={700}>Usage fields:</Text> {usageExample}</Text>
        <Text size="sm"><Text span fw={700}>Calibration:</Text> leave both optional fields empty for built-in thresholds, or provide a JSON file shaped like this:</Text>
        <Box
          component="pre"
          m={0}
          p="sm"
          style={{ overflowX: "auto", borderRadius: 6, fontSize: 12, background: "var(--mantine-color-body)" }}
        >{`{
  "schema_version": 1,
  "recognizer_sha256": "<SHA-256 of the exact recognizer>",
  "representative_dataset": "<description of your validation dataset>",
  "target_false_match_rate": 0.0001,
  "thresholds": { "possible": 0.40, "likely": 0.50, "strong": 0.60 }
}`}</Box>
        <Text size="xs" c="dimmed">Angle-bracket values are placeholders, never evidence. Equivalent templates are included under docs/examples/model-onboarding.</Text>
      </Stack>
    </Paper>
  );
}
function downloadJsonExample(filename, payload) {
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
