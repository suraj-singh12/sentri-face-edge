import { useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Group,
  Modal,
  Paper,
  ScrollArea,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconRefresh,
  IconShieldCheck,
} from "@tabler/icons-react";

export function RecoveryPanel({ state, actions }) {
  return (
    <Stack gap="md" data-testid="recovery-panel">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Box>
          <Title order={3} size="h4">Integrity & recovery</Title>
          <Text size="sm" c="dimmed">Run a factual integrity check, then prepare one explicitly supported recovery action.</Text>
        </Box>
        <Button
          leftSection={<IconRefresh size={16} />}
          loading={state.checking}
          disabled={state.preparing || state.executing}
          onClick={actions.checkIntegrity}
        >
          Run integrity check
        </Button>
      </Group>

      <Alert color="blue" icon={<IconShieldCheck size={18} />} title="Recovery is deliberate">
        Nothing runs automatically. Every available action is prepared and revalidated by the server before it can execute.
      </Alert>

      {state.report ? <IntegritySummary report={state.report} /> : (
        <Paper withBorder radius="md" p="xl">
          <Text ta="center" c="dimmed">No integrity report has been requested in this session.</Text>
        </Paper>
      )}

      {state.report ? (
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          <IntegrityFindingList
            findings={state.report.findings || []}
            selectedFindingId={state.selectedFindingId}
            onSelect={actions.selectFinding}
          />
          <IntegrityFindingDetail
            finding={state.selectedFinding}
            preparing={state.preparing}
            onPrepare={actions.prepareFindingAction}
          />
        </SimpleGrid>
      ) : null}

      <Card withBorder radius="md" p="md">
        <Group justify="space-between" align="flex-start">
          <Box>
            <Text fw={800}>Guarded merge revert</Text>
            <Text size="sm" c="dimmed">Recent normalized merges are not assumed reversible. Select one and ask P11-D to prove eligibility.</Text>
          </Box>
          <Button
            variant="default"
            loading={state.loadingOperations}
            disabled={state.preparing || state.executing}
            onClick={actions.loadRevertOperations}
          >
            Load merge history
          </Button>
        </Group>
        {state.revertOperations.length ? (
          <Stack gap="xs" mt="md">
            {state.revertOperations.map((operation) => (
              <Paper key={operation.operation_id} withBorder radius="sm" p="sm">
                <Group justify="space-between" wrap="nowrap">
                  <Box miw={0}>
                    <Group gap="xs"><Badge variant="light">{operation.status}</Badge><Text size="xs" c="dimmed">Preparation required</Text></Group>
                    <Text mt={4} size="sm" fw={700} ff="monospace" truncate>{operation.operation_id}</Text>
                    <Text size="xs" c="dimmed">{formatDate(operation.created_at)}</Text>
                  </Box>
                  <Button
                    size="xs"
                    variant="light"
                    loading={state.preparing}
                    disabled={state.executing}
                    onClick={() => actions.prepareRevert(operation.operation_id)}
                  >
                    Check eligibility
                  </Button>
                </Group>
              </Paper>
            ))}
          </Stack>
        ) : null}
      </Card>

      {state.result ? <RecoveryResultPanel result={state.result} onClose={actions.clearResult} /> : null}
      <RecoveryActionPlanModal
        plan={state.plan}
        executing={state.executing}
        onClose={actions.closePlan}
        onExecute={actions.executePrepared}
      />
    </Stack>
  );
}

export function IntegritySummary({ report }) {
  const counts = report.counts_by_severity || {};
  const color = report.status === "PASS" ? "teal" : report.status === "CRITICAL" ? "red" : "orange";
  return (
    <Card withBorder radius="md" p="md" data-testid="integrity-summary">
      <Group justify="space-between" align="flex-start">
        <Box>
          <Group gap="xs"><Text fw={800}>Integrity status</Text><Badge color={color}>{report.status}</Badge></Group>
          <Text size="xs" c="dimmed" mt={4}>Completed {formatDate(report.completed_at)} · schema {report.schema_version} · graph {report.graph_revision || "unavailable"}</Text>
        </Box>
        <Group gap="xs">
          {Object.entries(counts).map(([severity, count]) => (
            <Badge key={severity} variant="light" color={severityColor(severity)}>{severity} {count}</Badge>
          ))}
        </Group>
      </Group>
      {report.findings_truncated ? <Alert color="orange" mt="md" title="Report is bounded">Some findings were omitted. Recovery preparation is unavailable for a truncated authoritative report.</Alert> : null}
    </Card>
  );
}

export function IntegrityFindingList({ findings, selectedFindingId, onSelect }) {
  return (
    <Card withBorder radius="md" p="md">
      <Text fw={800} mb="sm">Findings</Text>
      {findings.length ? (
        <ScrollArea.Autosize mah={440}>
          <Stack gap="xs">
            {findings.map((finding) => (
              <Button
                key={finding.finding_id}
                variant={selectedFindingId === finding.finding_id ? "light" : "subtle"}
                color={severityColor(finding.severity)}
                justify="flex-start"
                h="auto"
                py="sm"
                onClick={() => onSelect(finding.finding_id)}
              >
                <Box ta="left" miw={0}>
                  <Group gap="xs"><Badge size="xs" color={severityColor(finding.severity)}>{finding.severity}</Badge><Text size="xs" fw={800}>{finding.invariant_id}</Text></Group>
                  <Text size="xs" c="dimmed" mt={4} lineClamp={2}>{finding.message}</Text>
                </Box>
              </Button>
            ))}
          </Stack>
        </ScrollArea.Autosize>
      ) : <Text size="sm" c="dimmed">No findings. The report passed.</Text>}
    </Card>
  );
}

export function IntegrityFindingDetail({ finding, preparing, onPrepare }) {
  if (!finding) {
    return <Card withBorder radius="md" p="md"><Text c="dimmed" size="sm">Select a finding to inspect its factual details.</Text></Card>;
  }
  return (
    <Card withBorder radius="md" p="md">
      <Group justify="space-between"><Text fw={800}>{finding.invariant_id}</Text><Badge color={severityColor(finding.severity)}>{finding.severity}</Badge></Group>
      <Text size="sm" mt="md">{finding.message}</Text>
      <Text size="xs" c="dimmed" mt={4}>{finding.domain} · {humanize(finding.classification)}</Text>
      <Divider my="md" />
      <Text size="xs" fw={800} tt="uppercase" c="dimmed">Affected entities</Text>
      <Stack gap={3} mt={6}>
        {(finding.affected_entities || []).map((entity) => <Text key={`${entity.type}:${entity.id}`} size="xs"><Text span fw={700}>{humanize(entity.type)}:</Text> <Text span ff="monospace">{entity.id}</Text></Text>)}
        {!finding.affected_entities?.length ? <Text size="xs" c="dimmed">No bounded entity identifiers supplied.</Text> : null}
      </Stack>
      {finding.evidence?.length ? <><Text size="xs" fw={800} tt="uppercase" c="dimmed" mt="md">Evidence</Text><Stack gap={3} mt={6}>{finding.evidence.map((item) => <Text key={item.name} size="xs"><Text span fw={700}>{humanize(item.name)}:</Text> {item.value}</Text>)}</Stack></> : null}
      {finding.action_hint ? (
        <Button mt="lg" loading={preparing} onClick={() => onPrepare(finding.action_hint)}>
          {finding.action_hint.label}
        </Button>
      ) : (
        <Alert color="gray" mt="lg" title="No safe action is exposed">This finding requires manual review or a later recovery boundary. The UI cannot mutate it.</Alert>
      )}
    </Card>
  );
}

export function RecoveryActionPlanModal({ plan, executing, onClose, onExecute }) {
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  useEffect(() => { setReason(""); setConfirmation(""); }, [plan?.token]);
  if (!plan) return null;
  const confirmed = confirmation === plan.confirmation_phrase && reason.trim().length > 0;
  return (
    <Modal opened onClose={onClose} title={plan.title} centered size="lg" closeOnClickOutside={!executing} closeOnEscape={!executing}>
      <Stack gap="md">
        <Text size="sm">{plan.summary}</Text>
        <PlanList title="Expected changes" values={plan.expected_changes} />
        <PlanList title="History preserved" values={plan.preserved_history} />
        {plan.affected_entities?.length ? <PlanList title="Affected entities" values={plan.affected_entities.map((item) => `${humanize(item.type)}: ${item.id}`)} monospace /> : null}
        <Textarea label="Reason" description="Stored as bounded operation context." value={reason} maxLength={500} minRows={2} onChange={(event) => setReason(event.currentTarget.value)} disabled={executing} required />
        <TextInput label={`Type ${plan.confirmation_phrase} to continue`} value={confirmation} onChange={(event) => setConfirmation(event.currentTarget.value)} disabled={executing} autoComplete="off" />
        <Alert color="orange" icon={<IconAlertTriangle size={18} />}>Execution revalidates the exact prepared token. A changed or ambiguous state will be refused without applying this plan.</Alert>
        <Group justify="flex-end"><Button variant="default" onClick={onClose} disabled={executing}>Cancel</Button><Button color="orange" loading={executing} disabled={!confirmed} onClick={() => onExecute(reason.trim())}>Execute prepared action</Button></Group>
      </Stack>
    </Modal>
  );
}

export function RecoveryResultPanel({ result, onClose }) {
  const committedFailure = result.committed && result.code === "postcheck_failed_after_commit";
  const success = result.committed && !committedFailure;
  return (
    <Alert
      color={success ? "teal" : "red"}
      icon={success ? <IconCircleCheck size={18} /> : <IconAlertTriangle size={18} />}
      title={committedFailure ? "Operation committed; verification failed" : success ? "Recovery operation committed" : "Recovery action refused"}
      withCloseButton
      onClose={onClose}
      data-testid="recovery-result"
    >
      {committedFailure
        ? "The database change committed, but the mandatory post-operation integrity check did not pass. Review the displayed report; no automatic follow-up ran."
        : result.message || (success ? "The post-operation integrity report is displayed above." : "No prepared mutation was applied.")}
    </Alert>
  );
}

function PlanList({ title, values = [], monospace = false }) {
  return <Box><Text size="xs" fw={800} tt="uppercase" c="dimmed">{title}</Text><Stack gap={4} mt={5}>{values.map((value) => <Text key={value} size="sm" ff={monospace ? "monospace" : undefined}>• {value}</Text>)}</Stack></Box>;
}

function severityColor(severity) {
  return { CRITICAL: "red", ERROR: "red", WARNING: "orange", INFO: "blue" }[severity] || "gray";
}

function humanize(value) {
  return String(value || "").toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value || "Unknown") : date.toLocaleString();
}
