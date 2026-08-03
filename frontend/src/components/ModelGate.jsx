import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert, Box, Button, Card, Center, Checkbox, FileButton, Group,
  Loader, Paper, SimpleGrid, Stack, Text, TextInput, ThemeIcon, Title,
} from "@mantine/core";
import {
  IconAlertTriangle, IconBriefcase, IconCheck,
  IconFileCheck, IconFlask, IconLock, IconShieldCheck, IconUpload,
} from "@tabler/icons-react";

import { useApiClient } from "../hooks/useApiClient.js";

const EMPTY_FORM = {
  detectorPath: "",
  detectorSha256: "",
  detectorName: "",
  detectorSize: 0,
  recognizerPath: "",
  recognizerSha256: "",
  recognizerName: "",
  recognizerSize: 0,
  organization: "",
  licensor: "",
  licenseReference: "",
  licenseName: "",
  accepted: false,
};

export function ModelGate({ user, logout, children }) {
  const { apiGet, apiPost, apiUpload, showToast } = useApiClient();
  const [status, setStatus] = useState(null);
  const [usageMode, setUsageMode] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [installing, setInstalling] = useState(false);
  const [uploading, setUploading] = useState("");
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
  const researchCombinations = status?.combinations?.research || [];
  const selected = combinations.find((item) => item.id === selectedId) || null;
  const researchMatch = useMemo(() => {
    if (!form.detectorName || !form.recognizerName) return null;
    const detectorName = form.detectorName.toLowerCase();
    const recognizerName = form.recognizerName.toLowerCase();
    return researchCombinations.find((item) => (
      item.detector_file?.toLowerCase() === detectorName
      && item.recognizer_file?.toLowerCase() === recognizerName
    )) || null;
  }, [form.detectorName, form.recognizerName, researchCombinations]);
  const bothFilesChosen = Boolean(form.detectorPath && form.recognizerPath);

  useEffect(() => {
    if (usageMode !== "research") return;
    setSelectedId(researchMatch?.id || "");
  }, [researchMatch, usageMode]);

  const update = (field) => (event) => {
    const value = event?.currentTarget?.type === "checkbox" ? event.currentTarget.checked : event.currentTarget.value;
    setForm((current) => ({ ...current, [field]: value }));
  };

  const selectModel = (kind) => async (file) => {
    if (!file) return;
    setUploading(kind);
    setError("");
    try {
      const uploaded = await apiUpload(
        `/api/models/upload?kind=${kind}&filename=${encodeURIComponent(file.name)}`,
        file,
        { silent: true, timeoutMs: 30 * 60 * 1000 },
      );
      setForm((current) => ({
        ...current,
        [`${kind}Path`]: uploaded.path,
        [`${kind}Sha256`]: uploaded.sha256,
        [`${kind}Name`]: uploaded.filename,
        [`${kind}Size`]: uploaded.size,
      }));
      showToast(`${uploaded.filename} is ready`);
    } catch (requestError) {
      setError(requestError?.message || `The ${kind} model could not be read`);
    } finally {
      setUploading("");
    }
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
        organization: form.organization,
        licensor: form.licensor,
        license_reference: form.licenseReference,
        license_name: form.licenseName,
        accept_responsibility: form.accepted,
      }, { silent: true, timeoutMs: 10 * 60 * 1000 });
      setStatus(next);
      showToast("Face recognition is ready");
    } catch (requestError) {
      setError(requestError?.message || "The model bundle could not be activated");
    } finally {
      setInstalling(false);
    }
  };

  if (loading) {
    return <Center mih="100vh"><Stack align="center"><Loader /><Text c="dimmed">Preparing face recognition...</Text></Stack></Center>;
  }
  if (status?.ready) return children;

  const required = Boolean(selected)
    && form.detectorPath && /^[a-f0-9]{64}$/i.test(form.detectorSha256)
    && form.recognizerPath && /^[a-f0-9]{64}$/i.test(form.recognizerSha256)
    && form.accepted
    && (selected.usage_basis !== "commercial-license" || (form.licensor && form.licenseReference))
    && (selected.usage_basis !== "permissive-license" || form.licenseName);

  return (
    <Box mih="100vh" bg="var(--mantine-color-body)" p={{ base: "md", md: "xl" }}>
      <Stack maw={920} mx="auto" gap="lg">
        <Group justify="space-between" align="flex-start">
          <Box>
            <Title order={1} size="h2">Set up face recognition</Title>
            <Text c="dimmed" mt={6}>Choose the two model files on this computer. SentriFace checks, copies, and configures them for you.</Text>
          </Box>
          <Stack gap={2} align="flex-end"><Text size="sm" fw={700}>{user?.display_name}</Text><Button size="compact-sm" variant="subtle" color="gray" onClick={logout}>Sign out</Button></Stack>
        </Group>

        {status?.error ? (
          <Alert color="orange" icon={<IconAlertTriangle size={18} />} title="Model files are needed">
            Choose both model files below to finish setup.
          </Alert>
        ) : null}
        {!status?.can_configure ? (
          <Card withBorder radius="lg" p="xl"><Stack align="center" py="xl"><ThemeIcon size={56} radius="xl" color="orange" variant="light"><IconLock size={28} /></ThemeIcon><Title order={2} size="h3">The owner account is needed</Title><Text c="dimmed" ta="center" maw={620}>Ask the person who set up SentriFace to sign in and choose the two model files.</Text></Stack></Card>
        ) : (
          <Card withBorder radius="lg" p={{ base: "md", md: "xl" }} shadow="sm">
            <Stack gap="xl">
              <Box>
                <Text fw={800} mb="sm">1. How will you use SentriFace?</Text>
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                  <UseChoice
                    selected={usageMode === "research"}
                    icon={IconFlask}
                    title="Personal or research"
                    description="Not for a paid service, a product you sell, or other business use."
                    onClick={() => { setUsageMode("research"); setSelectedId(""); setError(""); }}
                  />
                  <UseChoice
                    selected={usageMode === "commercial"}
                    icon={IconBriefcase}
                    title="Business or paid use"
                    description="You have model files whose licence allows this use."
                    onClick={() => { setUsageMode("commercial"); setSelectedId(""); setError(""); }}
                  />
                </SimpleGrid>
              </Box>

              {usageMode === "commercial" ? (
                <Box>
                  <Text fw={800} mb="sm">2. Where did your licensed model files come from?</Text>
                  <Stack gap="sm">
                    {(status?.combinations?.commercial || []).map((item) => (
                      <LicenseChoice key={item.id} item={item} selected={selectedId === item.id} onClick={() => setSelectedId(item.id)} />
                    ))}
                  </Stack>
                </Box>
              ) : null}

              {usageMode ? (
                <>
                  <Box>
                    <Text fw={800} mb="xs">{usageMode === "commercial" ? "3" : "2"}. Choose your two model files</Text>
                    <Text size="sm" c="dimmed" mb="md">Click each button and choose the matching file. You do not need to type a path or create a checksum.</Text>
                    <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
                      <ModelFilePicker
                        title="Face finder file"
                        filename={form.detectorName}
                        size={form.detectorSize}
                        loading={uploading === "detector"}
                        disabled={Boolean(uploading)}
                        onSelect={selectModel("detector")}
                        description="Usually starts with det_ and ends in .onnx."
                      />
                      <ModelFilePicker
                        title="Face matching file"
                        filename={form.recognizerName}
                        size={form.recognizerSize}
                        loading={uploading === "recognizer"}
                        disabled={Boolean(uploading)}
                        onSelect={selectModel("recognizer")}
                        description="Usually starts with w600k_ and ends in .onnx."
                      />
                    </SimpleGrid>
                  </Box>

                  {usageMode === "research" && researchMatch ? (
                    <Alert color="teal" icon={<IconCheck size={18} />} title="Files recognized">
                      {researchMatch.name}. SentriFace will create the matching settings automatically.
                    </Alert>
                  ) : null}
                  {usageMode === "research" && bothFilesChosen && !researchMatch ? (
                    <Alert color="red" icon={<IconAlertTriangle size={18} />} title="These files are not a supported pair">
                      Choose both files from the same InsightFace model package. For your files, choose <strong>det_500m.onnx</strong> and <strong>w600k_r50.onnx</strong>.
                    </Alert>
                  ) : null}

                  {selected ? (
                    <>
                      <SimpleGrid cols={{ base: 1, md: 2 }}>
                        <TextInput label="Organization or owner (optional)" value={form.organization} onChange={update("organization")} placeholder="Your name or organization" />
                        {selected.usage_basis === "commercial-license" ? <TextInput required label="Model supplier" value={form.licensor} onChange={update("licensor")} placeholder="Name on your model licence" /> : null}
                        {selected.usage_basis === "commercial-license" ? <TextInput required label="Licence or invoice number" value={form.licenseReference} onChange={update("licenseReference")} placeholder="Your agreement, invoice, or entitlement ID" /> : null}
                        {selected.usage_basis === "permissive-license" ? <TextInput required label="Model licence" value={form.licenseName} onChange={update("licenseName")} placeholder="For example, Apache-2.0" /> : null}
                      </SimpleGrid>
                      <Paper withBorder p="md" radius="md" bg="var(--mantine-color-default-hover)">
                        <Checkbox checked={form.accepted} onChange={update("accepted")} label="I confirm that I am allowed to use these model files and process face data for the purpose selected above." />
                      </Paper>
                      {error ? <Alert color="red" title="Setup could not be finished">{friendlySetupError(error)}</Alert> : null}
                      <Group justify="flex-end">
                        <Button size="md" leftSection={<IconShieldCheck size={18} />} loading={installing} disabled={!required} onClick={install}>Finish setup</Button>
                      </Group>
                    </>
                  ) : null}
                </>
              ) : null}
            </Stack>
          </Card>
        )}
        <Text size="xs" c="dimmed" ta="center">Your model supplier's licence still applies. SentriFace does not provide rights to third-party model files.</Text>
      </Stack>
    </Box>
  );
}

function UseChoice({ selected, icon: Icon, title, description, onClick }) {
  return (
    <Paper component="button" type="button" withBorder radius="md" p="md" ta="left" onClick={onClick} style={{ cursor: "pointer", borderColor: selected ? "var(--mantine-color-teal-6)" : undefined, background: selected ? "var(--mantine-color-teal-light)" : undefined }}>
      <Group wrap="nowrap" align="flex-start">
        <ThemeIcon color={selected ? "teal" : "gray"} variant="light" size="lg" radius="xl"><Icon size={19} /></ThemeIcon>
        <Box style={{ flex: 1 }}><Text fw={800}>{title}</Text><Text size="sm" c="dimmed" mt={3}>{description}</Text></Box>
        {selected ? <ThemeIcon color="teal" radius="xl" size="sm"><IconCheck size={13} /></ThemeIcon> : null}
      </Group>
    </Paper>
  );
}

function LicenseChoice({ item, selected, onClick }) {
  const plainNames = {
    "insightface-commercial": "Licensed directly for InsightFace models",
    "other-commercial": "Licensed by another model supplier",
    "permissive-compatible": "Open-licence compatible models",
  };
  return (
    <Paper component="button" type="button" withBorder radius="md" p="md" ta="left" onClick={onClick} style={{ cursor: "pointer", borderColor: selected ? "var(--mantine-color-teal-6)" : undefined, background: selected ? "var(--mantine-color-teal-light)" : undefined }}>
      <Group justify="space-between" wrap="nowrap">
        <Box><Text fw={700}>{plainNames[item.id] || item.name}</Text><Text size="sm" c="dimmed">{item.note}</Text></Box>
        {selected ? <ThemeIcon color="teal" radius="xl" size="sm"><IconCheck size={13} /></ThemeIcon> : null}
      </Group>
    </Paper>
  );
}

function ModelFilePicker({ title, filename, size, loading, disabled, onSelect, description }) {
  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="sm">
        <Text fw={800}>{title}</Text>
        <Text size="sm" c="dimmed">{description}</Text>
        <FileButton onChange={onSelect} accept=".onnx,application/octet-stream">
          {(props) => (
            <Button {...props} variant={filename ? "light" : "filled"} leftSection={<IconUpload size={17} />} loading={loading} disabled={disabled}>
              {filename ? "Choose a different file" : "Browse files"}
            </Button>
          )}
        </FileButton>
        {filename ? (
          <Alert color="teal" icon={<IconFileCheck size={17} />} title={filename}>
            <Text size="sm">Ready · {formatBytes(size)}</Text>
          </Alert>
        ) : null}
      </Stack>
    </Paper>
  );
}

function friendlySetupError(message) {
  const text = String(message || "");
  if (/hash|sha-?256|checksum/i.test(text)) return "One of the files changed while it was being checked. Choose both files again.";
  if (/not found|path|staged/i.test(text)) return "One of the selected files is no longer available. Choose both files again.";
  if (/calibrat/i.test(text)) return "SentriFace could not create the matching settings for these files. Check that both files belong to the same supported model package.";
  return text || "Check the selected files and try again.";
}
function formatBytes(value) {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / (1024 ** exponent)).toFixed(exponent ? 1 : 0)} ${units[exponent]}`;
}
