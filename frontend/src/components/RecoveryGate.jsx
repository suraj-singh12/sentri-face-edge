import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  Center,
  Checkbox,
  Code,
  Group,
  Loader,
  Stack,
  Text,
  TextInput,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { IconAlertTriangle, IconCopy, IconLifebuoy } from "@tabler/icons-react";

import { useApiClient } from "../hooks/useApiClient.js";

export function RecoveryGate({ user, logout, children }) {
  const { apiGet, apiPost } = useApiClient();
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [destination, setDestination] = useState("");
  const [working, setWorking] = useState(false);
  const [riskAccepted, setRiskAccepted] = useState(false);
  const [recoveryCode, setRecoveryCode] = useState("");
  const [configuredReadiness, setConfiguredReadiness] = useState(null);
  const canConfigure = (user?.capabilities || []).includes("recovery");

  useEffect(() => {
    let active = true;
    apiGet("/api/recovery/readiness")
      .then((result) => {
        if (active) setStatus(result);
      })
      .catch((caught) => {
        if (active) setError(caught.message);
      });
    return () => {
      active = false;
    };
  }, []);

  if (!status && !error) {
    return <Center mih="100vh"><Loader /></Center>;
  }
  if (error) {
    return (
      <Center mih="100vh" p="md">
        <Alert color="red" title="Could not check disaster recovery">{error}</Alert>
      </Center>
    );
  }
  if ((status.ready || status.acknowledged) && !recoveryCode) return children;

  const configure = async () => {
    setError("");
    setWorking(true);
    try {
      const result = await apiPost("/api/recovery/configure", { destination });
      setRecoveryCode(result.recovery_code || "");
      setConfiguredReadiness(result.readiness || null);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setWorking(false);
    }
  };

  const continueWithoutRecovery = async () => {
    setError("");
    setWorking(true);
    try {
      const result = await apiPost("/api/recovery/acknowledge", {
        acknowledge_risk: true,
        acknowledgement_version: status.acknowledgement_version,
      });
      setStatus(result.readiness);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setWorking(false);
    }
  };

  const copyRecoveryCode = async () => {
    await navigator.clipboard.writeText(recoveryCode);
  };

  return (
    <Center mih="100vh" p="md">
      <Card withBorder radius="lg" p="xl" maw={720} w="100%">
        <Stack gap="lg">
          <Group gap="md" align="flex-start">
            <ThemeIcon size={48} radius="xl" color="teal" variant="light">
              <IconLifebuoy size={26} />
            </ThemeIcon>
            <Box>
              <Title order={2}>{recoveryCode ? "Save your recovery code" : "Protect this machine first"}</Title>
              <Text c="dimmed" mt={4}>
                {recoveryCode
                  ? "This code is shown once. Store it separately from this machine."
                  : "Disaster recovery keeps an encrypted copy outside SentriFace's live data directory."}
              </Text>
            </Box>
          </Group>

          {error ? <Alert color="red" title="Recovery setup failed">{error}</Alert> : null}

          {recoveryCode ? (
            <>
              <Alert color="orange" icon={<IconAlertTriangle size={18} />} title="Do not lose this code">
                The recovery kit and encrypted backups cannot restore the database without it.
              </Alert>
              <Group wrap="nowrap">
                <Code block fz="md" style={{ flex: 1, overflowWrap: "anywhere" }}>{recoveryCode}</Code>
                <Button variant="light" leftSection={<IconCopy size={16} />} onClick={copyRecoveryCode}>Copy</Button>
              </Group>
              {configuredReadiness && !configuredReadiness.ready ? (
                <Alert color="yellow" title="Recovery destination is not yet ready">
                  Check that the destination remains connected and contains the recovery kit.
                </Alert>
              ) : null}
              <Button onClick={() => {
                setRecoveryCode("");
                setStatus(configuredReadiness || { ...status, ready: true });
              }}>
                I saved the recovery code
              </Button>
            </>
          ) : canConfigure ? (
            <>
              <TextInput
                label="Recovery destination"
                description="Choose a folder on a separate local or removable drive. Network locations are rejected."
                placeholder="E:\SentriFace-Recovery"
                value={destination}
                onChange={(event) => setDestination(event.currentTarget.value)}
              />
              <Button onClick={configure} loading={working} disabled={!destination.trim()}>
                Configure disaster recovery
              </Button>

              <Alert color="red" icon={<IconAlertTriangle size={18} />} title="Continue without disaster recovery">
                Without an external recovery copy, disk failure, theft, ransomware, or loss of this machine may make
                all SentriFace data permanently unrecoverable.
              </Alert>
              <Checkbox
                checked={riskAccepted}
                onChange={(event) => setRiskAccepted(event.currentTarget.checked)}
                label="I understand that this machine has no usable disaster-recovery copy and accept the risk for all users of this installation."
              />
              <Button
                color="red"
                variant="light"
                loading={working}
                disabled={!riskAccepted}
                onClick={continueWithoutRecovery}
              >
                Continue without disaster recovery
              </Button>
            </>
          ) : (
            <>
              <Alert color="orange" title="Administrator action required">
                An administrator must configure disaster recovery or explicitly accept continuing without it.
              </Alert>
              <Button variant="default" onClick={logout}>Sign out</Button>
            </>
          )}
        </Stack>
      </Card>
    </Center>
  );
}
