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
  Paper,
  SimpleGrid,
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
  const [destinations, setDestinations] = useState([]);
  const [manualOpen, setManualOpen] = useState(false);
  const canConfigure = (user?.capabilities || []).includes("recovery");

  useEffect(() => {
    let active = true;
    Promise.all([
      apiGet("/api/recovery/readiness"),
      canConfigure
        ? apiGet("/api/recovery/destinations", { silent: true }).catch(() => ({ destinations: [] }))
        : Promise.resolve({ destinations: [] }),
    ])
      .then(([readiness, destinationResult]) => {
        if (active) {
          setStatus(readiness);
          setDestinations(destinationResult.destinations || []);
        }
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
        <Alert color="red" title="Could not check your backup">{error}</Alert>
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
              <Title order={2}>{recoveryCode ? "Save your recovery code" : "Set up a safety copy"}</Title>
              <Text c="dimmed" mt={4}>
                {recoveryCode
                  ? "This code is shown once. Store it separately from this machine."
                  : "Save an encrypted copy on a different drive so your data can be restored if this computer is lost or damaged."}
              </Text>
            </Box>
          </Group>

          {error ? <Alert color="red" title="Backup setup failed">{error}</Alert> : null}

          {recoveryCode ? (
            <>
              <Alert color="orange" icon={<IconAlertTriangle size={18} />} title="Do not lose this code">
                  You cannot restore your backup without this code.
              </Alert>
              <Group wrap="nowrap">
                <Code block fz="md" style={{ flex: 1, overflowWrap: "anywhere" }}>{recoveryCode}</Code>
                <Button variant="light" leftSection={<IconCopy size={16} />} onClick={copyRecoveryCode}>Copy</Button>
              </Group>
              {configuredReadiness && !configuredReadiness.ready ? (
                <Alert color="yellow" title="The backup drive is not ready">
                  Check that the drive is connected and try again.
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
              {destinations.length ? (
                <Box>
                  <Text fw={700} mb="xs">Choose a connected drive</Text>
                  <SimpleGrid cols={{ base: 1, sm: 2 }}>
                    {destinations.map((item) => (
                      <Paper
                        key={item.path}
                        component="button"
                        type="button"
                        withBorder
                        radius="md"
                        p="md"
                        ta="left"
                        onClick={() => setDestination(item.path)}
                        style={{
                          cursor: "pointer",
                          borderColor: destination === item.path ? "var(--mantine-color-teal-6)" : undefined,
                          background: destination === item.path ? "var(--mantine-color-teal-light)" : undefined,
                        }}
                      >
                        <Text fw={700}>{item.label}</Text>
                        <Text size="sm" c="dimmed">SentriFace Backup</Text>
                      </Paper>
                    ))}
                  </SimpleGrid>
                </Box>
              ) : (
                <Alert color="blue" title="No separate drive was found">
                  Connect a USB or external drive, then refresh this page. You can also enter a folder location manually.
                </Alert>
              )}
              {manualOpen || !destinations.length ? (
                <TextInput
                  label="Folder location"
                  description="Use a folder on a separate or removable drive—not on this computer's main drive."
                  placeholder={navigator.userAgent.includes("Windows") ? "E:\\SentriFace Backup" : "/Volumes/Backup Drive/SentriFace Backup"}
                  value={destination}
                  onChange={(event) => setDestination(event.currentTarget.value)}
                />
              ) : (
                <Button variant="subtle" color="gray" onClick={() => setManualOpen(true)}>Enter a different folder</Button>
              )}
              <Button onClick={configure} loading={working} disabled={!destination.trim()}>
                Create safety copy
              </Button>

              <Alert color="red" icon={<IconAlertTriangle size={18} />} title="Skip the safety copy">
                If this computer is damaged, stolen, or infected, your SentriFace data may be lost permanently.
              </Alert>
              <Checkbox
                checked={riskAccepted}
                onChange={(event) => setRiskAccepted(event.currentTarget.checked)}
                label="I understand that my data may not be recoverable without a safety copy."
              />
              <Button
                color="red"
                variant="light"
                loading={working}
                disabled={!riskAccepted}
                onClick={continueWithoutRecovery}
              >
                Skip for now
              </Button>
            </>
          ) : (
            <>
              <Alert color="orange" title="The owner account is needed">
                Ask the person who set up SentriFace to create a safety copy or choose to skip it.
              </Alert>
              <Button variant="default" onClick={logout}>Sign out</Button>
            </>
          )}
        </Stack>
      </Card>
    </Center>
  );
}
