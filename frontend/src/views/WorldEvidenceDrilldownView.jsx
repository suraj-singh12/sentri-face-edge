import { useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Divider,
  Group,
  Loader,
  Paper,
  ScrollArea,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconArrowRight,
  IconFileDescription,
  IconPhoto,
  IconRefresh,
  IconRoute,
} from "@tabler/icons-react";

import { SafeImage } from "../components/Shared.jsx";
import { WorldMediaPreview } from "../components/WorldMediaPreview.jsx";
import { mediaUrl } from "../utils.js";
import { worldEvidenceMediaRequestState } from "../utils/world.js";

const EVIDENCE_COLLECTIONS = [
  { label: "Evidence detail", value: "EVIDENCE" },
  { label: "Supporting media", value: "MEDIA" },
];

export function WorldEvidenceDrilldownView({ evidence, onBack, onRefresh, onCollection, onNextPage, onValidateMediaOrigin }) {
  const collectionState = evidence.collections[evidence.collection];
  const data = collectionState?.data;
  const detail = evidence.detail || data?.evidence?.[0] || null;
  const page = data?.pagination?.[evidence.collection] || null;
  const [previewMedia, setPreviewMedia] = useState(null);
  const closeMediaPreview = async () => {
    if (await onValidateMediaOrigin()) setPreviewMedia(null);
  };

  if (!detail && collectionState?.loading) {
    return <Stack gap="sm" className="world-evidence-shell"><Button variant="subtle" size="xs" leftSection={<IconArrowLeft size={15} />} onClick={onBack} className="world-evidence-back">{evidence.origin?.level === "RELATIONSHIP" ? "Back to relationship proof" : "Back to finalized event"}</Button><Stack align="center" justify="center" className="world-evidence-loading"><Loader color="teal" /><Text size="sm" c="dimmed">Loading authoritative evidence and provenance…</Text></Stack></Stack>;
  }
  if (!detail) {
    return <Stack gap="sm" className="world-evidence-shell"><Button variant="subtle" size="xs" leftSection={<IconArrowLeft size={15} />} onClick={onBack} className="world-evidence-back">{evidence.origin?.level === "RELATIONSHIP" ? "Back to relationship proof" : "Back to finalized event"}</Button><Alert color="red" title="World evidence could not be loaded">{collectionState?.error?.message || "The required World Evidence contract is unavailable."}</Alert><Button variant="default" size="xs" leftSection={<IconRefresh size={15} />} onClick={onRefresh}>Try again</Button></Stack>;
  }

  return (
    <Stack gap="sm" className="world-evidence-shell" data-world-level="EVIDENCE">
      <EvidenceHeader evidence={detail} binding={evidence.binding} state={collectionState} page={page} onBack={onBack} onRefresh={onRefresh} />
      {collectionState?.error ? <Alert color="yellow" title={`The ${evidence.collection.toLowerCase()} request failed`}>{collectionState.error.message}</Alert> : null}
      <Group justify="space-between" align="center" wrap="nowrap" className="world-evidence-collection-bar">
        <SegmentedControl size="xs" value={evidence.collection} data={EVIDENCE_COLLECTIONS} onChange={onCollection} disabled={collectionState?.loading} aria-label="World evidence collection" />
        <Box ta="right"><Text size="xs" c="dimmed">{page ? `Page ${collectionState.pageNumber} · ${page.returned_count} of ${page.total_count}` : "Bounded collection"}</Text>{page?.truncated ? <Text size="10px" c="yellow.7">{humanize(page.truncation_reason || "More results available")}</Text> : null}</Box>
      </Group>
      {evidence.collection === "EVIDENCE" ? (
        <EvidenceDetail evidence={detail} binding={evidence.binding} onMedia={() => onCollection("MEDIA")} />
      ) : (
        <SupportingMedia evidence={detail} state={collectionState} data={data} page={page} onPreview={setPreviewMedia} onRetry={onRefresh} />
      )}
      {page?.has_more ? <Group justify="center"><Button variant="default" size="xs" rightSection={<IconArrowRight size={14} />} onClick={onNextPage} disabled={collectionState?.loading || !page.next_cursor}>Next authoritative page</Button></Group> : null}
      <WorldMediaPreview item={previewMedia} opened={Boolean(previewMedia)} onClose={closeMediaPreview} origin={{ type: "EVIDENCE", evidenceId: detail.evidence_id, eventId: previewMedia?.supporting_event_id }} />
    </Stack>
  );
}

function EvidenceHeader({ evidence, binding, state, page, onBack, onRefresh }) {
  return (
    <Stack gap="xs">
      <Group justify="space-between" align="flex-start" wrap="nowrap" className="world-evidence-header">
        <Group gap="sm" wrap="nowrap" miw={0}>
          <ActionIcon variant="subtle" size={36} onClick={onBack} aria-label="Back to supporting evidence"><IconArrowLeft size={18} /></ActionIcon>
          <ThemeIcon size={40} radius="md" variant="light" color="blue"><IconFileDescription size={21} /></ThemeIcon>
          <Box miw={0}>
            <Group gap="xs" wrap="wrap"><Title order={2} size="h3">Evidence</Title><Badge size="xs" color="blue" variant="light">{evidence.evidence_type}</Badge><Badge size="xs" color={evidence.active ? "teal" : "gray"} variant="outline">{evidence.active ? "ACTIVE" : "INACTIVE"}</Badge></Group>
            <Text size="xs" c="dimmed">{formatDateTime(evidence.occurred_at)} · {humanize(evidence.directionality)} · {effectiveScopeLabel(binding?.filters)}</Text>
            <Text size="10px" c="dimmed" lineClamp={1}>{sourceLabel(evidence.supporting_references)}</Text>
          </Box>
        </Group>
        <Group gap="xs" wrap="nowrap">{state?.loading ? <Loader size={17} /> : null}<Tooltip label="Refresh evidence"><ActionIcon variant="default" size={36} onClick={onRefresh} disabled={state?.loading} aria-label="Refresh World Evidence"><IconRefresh size={17} /></ActionIcon></Tooltip></Group>
      </Group>
      <Group gap="xs" className="world-evidence-header-facts"><HeaderFact label="Evidence ID" value={shortId(evidence.evidence_id)} /><HeaderFact label="Direction" value={humanize(evidence.directionality)} /><HeaderFact label="Supporting media" value={mediaAvailabilityLabel(evidence.media_summary)} />{page?.truncated ? <Badge size="xs" color="yellow" variant="light">Current collection is bounded</Badge> : null}</Group>
    </Stack>
  );
}

function HeaderFact({ label, value }) {
  return <Paper withBorder radius="sm" px="xs" py={5} className="world-evidence-header-fact"><Text span size="10px" c="dimmed">{label} </Text><Text span size="xs" fw={800}>{value}</Text></Paper>;
}

function EvidenceDetail({ evidence, binding, onMedia }) {
  const changed = evidence.raw_endpoints.some((item, index) => item !== evidence.effective_endpoints[index]);
  return (
    <Box className="world-evidence-workarea">
      <Stack gap="sm" className="world-evidence-primary">
        <Paper withBorder radius="md" p="sm" className="world-evidence-endpoints">
          <Group justify="space-between" align="flex-start"><Box><Text fw={800}>Authoritative endpoints</Text><Text size="10px" c="dimmed">Historical raw identity remains distinct from current effective identity</Text></Box>{changed ? <Badge size="xs" variant="light" color="violet">Interpretation changed</Badge> : <Badge size="xs" variant="outline" color="gray">No endpoint divergence</Badge>}</Group>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs" mt="sm"><EndpointPanel label="Raw endpoints" endpoints={evidence.raw_endpoints} directionality={evidence.directionality} color="gray" /><EndpointPanel label="Current effective endpoints" endpoints={evidence.effective_endpoints} directionality={evidence.directionality} color="teal" /></SimpleGrid>
          <Text size="10px" c="dimmed" mt="xs">Endpoint resolution and directionality are returned by the backend; this view does not reconstruct correction or canonical chains.</Text>
        </Paper>
        <Paper withBorder radius="md" p="sm" className="world-evidence-provenance">
          <Text fw={800}>Provenance and source</Text><Text size="10px" c="dimmed" mb="xs">Authoritative origin records</Text>
          <FactRow label="Created operation" value={evidence.provenance.created_operation_id} /><FactRow label="Provenance source" value={evidence.provenance.source || "Not supplied"} />
          <Divider my="xs" />
          {evidence.supporting_references.map((reference) => <Box key={`${reference.source_entity_type}-${reference.source_entity_id}`} className="world-evidence-source-row"><Group gap="xs"><ThemeIcon size={28} variant="light" color="blue"><IconRoute size={14} /></ThemeIcon><Box miw={0}><Text size="xs" fw={800}>{reference.source_entity_type} · {reference.source_entity_id}</Text><Text size="10px" c="dimmed">Evidence revision {reference.evidence_revision_id}</Text></Box></Group></Box>)}
        </Paper>
      </Stack>
      <Stack gap="sm" className="world-evidence-context">
        <Paper withBorder radius="md" p="sm"><EvidenceExplanation evidence={evidence} binding={binding} /></Paper>
        <Paper withBorder radius="md" p="sm"><MediaStatus summary={evidence.media_summary} onMedia={onMedia} /></Paper>
      </Stack>
    </Box>
  );
}

function EndpointPanel({ label, endpoints, directionality, color }) {
  return <Paper withBorder radius="sm" p="xs" className="world-evidence-endpoint-panel"><Text size="10px" tt="uppercase" fw={800} c="dimmed">{label}</Text><Group gap="xs" wrap="nowrap" mt={5}><Badge size="sm" variant="light" color={color}>{shortId(endpoints[0])}</Badge><Text fw={800} c="dimmed">{directionGlyph(directionality)}</Text><Badge size="sm" variant="light" color={color}>{shortId(endpoints[1])}</Badge></Group></Paper>;
}

function EvidenceExplanation({ evidence, binding }) {
  const explanation = evidence.explanation;
  return <Stack gap="sm"><Box><Text fw={800}>What this evidence supports</Text><Text size="10px" c="dimmed">Backend factual explanation</Text></Box><Text size="sm">{explanation.summary}</Text><FactRow label="Basis" value={humanize(explanation.basis_type)} /><FactRow label="Method" value={humanize(explanation.method)} /><FactRow label="Occurrence" value={`${formatDateTime(evidence.occurrence_bounds.first)} — ${formatDateTime(evidence.occurrence_bounds.last)}`} /><FactRow label="Effective scope" value={effectiveScopeLabel(binding?.filters)} /><Divider />{explanation.factual_factors.length ? <Box><Text size="xs" fw={700} mb={3}>Factual factors</Text>{explanation.factual_factors.map((factor, index) => <FactRow key={`${factor.factor}-${index}`} label={humanize(factor.factor)} value={formatFactorValue(factor.value)} />)}</Box> : null}<Box className="world-limitations"><Text size="xs" fw={700}>Limitations</Text>{explanation.limitations.map((limitation) => <Text key={limitation} size="xs" c="dimmed">{limitation}</Text>)}</Box></Stack>;
}

function MediaStatus({ summary, onMedia }) {
  if (summary.availability === "UNAVAILABLE") return <Stack gap="xs"><Text fw={800}>No supporting media for this evidence type</Text><Text size="xs" c="dimmed">{humanize(summary.reason)}</Text><Badge size="xs" variant="outline" color="gray" w="fit-content">UNAVAILABLE</Badge></Stack>;
  return <Stack gap="xs"><Text fw={800}>Supporting media available</Text><Text size="xs" c="dimmed">{summary.total_count} authoritative media reference{summary.total_count === 1 ? "" : "s"}. The collection is not requested until opened.</Text><Button size="xs" variant="light" leftSection={<IconPhoto size={14} />} onClick={onMedia}>Request supporting media</Button></Stack>;
}

function SupportingMedia({ evidence, state, data, page, onPreview, onRetry }) {
  const requestState = worldEvidenceMediaRequestState({
    availability: evidence.media_summary.availability,
    data,
    loading: state?.loading,
    error: state?.error,
  });
  if (requestState === "EVIDENCE_MEDIA_NOT_REQUESTED") return <Paper withBorder radius="md" p="sm"><Stack gap="xs" align="center" ta="center"><Text size="sm" fw={700}>Supporting media not requested</Text><Text size="xs" c="dimmed">Open this collection to request authoritative media references.</Text></Stack></Paper>;
  if (requestState === "EVIDENCE_MEDIA_LOADING") return <Paper withBorder radius="md" className="world-evidence-media-collection"><Stack align="center" justify="center" className="world-evidence-media-loading"><Loader size={20} /><Text size="xs" c="dimmed">Loading authoritative supporting media…</Text></Stack></Paper>;
  if (requestState === "EVIDENCE_MEDIA_REQUEST_FAILED") return <Paper withBorder radius="md" p="sm"><Stack gap="xs" align="center" ta="center"><Text size="sm" fw={700}>Supporting media request failed</Text><Text size="xs" c="dimmed">No successful media page was returned. This is not an empty result.</Text><Button size="xs" variant="light" leftSection={<IconRefresh size={14} />} onClick={onRetry}>Retry supporting media</Button></Stack></Paper>;
  if (requestState === "EVIDENCE_MEDIA_UNAVAILABLE") return <Paper withBorder radius="md" p="sm"><Stack gap="xs"><Text fw={800}>No supporting media for this evidence type</Text><Text size="xs" c="dimmed">The backend explicitly marks media unavailable: {humanize(evidence.media_summary.reason)}.</Text><Badge size="xs" variant="outline" color="gray" w="fit-content">REQUESTED · UNAVAILABLE</Badge></Stack></Paper>;
  if (requestState === "EVIDENCE_MEDIA_EMPTY") return <Paper withBorder radius="md" p="sm"><Stack gap={2} align="center" ta="center"><Text size="sm" fw={700}>No supporting media returned</Text><Text size="xs" c="dimmed">The media collection was requested and is empty: {page.returned_count} of {page.total_count}.</Text></Stack></Paper>;
  const media = data.media;
  return <Paper withBorder radius="md" className="world-evidence-media-collection">{state?.loading ? <Box className="world-loading-stripe"><Loader size={16} /><Text size="xs">Replacing media page…</Text></Box> : null}<ScrollArea.Autosize mah={570}><SimpleGrid cols={{ base: 2, sm: 3, lg: 4 }} spacing="xs" p="xs">{media.map((item) => <button key={item.media_id} type="button" className="world-evidence-media-card" onClick={() => onPreview(item)}><SafeImage src={item.media_reference ? mediaUrl(item.media_reference) : ""} alt="" className="world-evidence-media-thumb" fallback={<Stack align="center" gap={2}><ThemeIcon size={42} variant="light" color="gray"><IconPhoto size={21} /></ThemeIcon><Text size="10px" c="dimmed">Preview unavailable</Text></Stack>} /><span className="world-row-main"><Text component="span" size="xs" fw={800}>{shortId(item.media_id)}</Text><Text component="span" size="10px" c="dimmed">{formatDateTime(item.occurred_at)}</Text><Text component="span" size="10px">{item.source || "Source not supplied"}</Text><Text component="span" size="10px" c="dimmed">Event {shortId(item.supporting_event_id)}</Text></span></button>)}</SimpleGrid></ScrollArea.Autosize></Paper>;
}

function FactRow({ label, value }) {
  return <Group justify="space-between" align="flex-start" gap="sm" wrap="nowrap" className="world-inspector-row"><Text size="xs" c="dimmed">{label}</Text><Text size="xs" fw={700} ta="right">{value ?? "—"}</Text></Group>;
}

function directionGlyph(directionality) {
  return directionality === "UNDIRECTED" ? "↔" : "→";
}

function sourceLabel(references) {
  return references.map((item) => `${item.source_entity_type} ${shortId(item.source_entity_id)}`).join(" · ");
}

function mediaAvailabilityLabel(summary) {
  return summary.availability === "AVAILABLE" ? `${summary.total_count} available` : "Unavailable for type";
}

function effectiveScopeLabel(filters = {}) {
  const parts = [];
  if (filters.recent_activity) parts.push(humanize(filters.recent_activity));
  else if (filters.date_from || filters.date_to) parts.push(`${formatDate(filters.date_from) || "Start"} to ${formatDate(filters.date_to) || "Now"}`);
  else parts.push("All recorded time");
  if (filters.locations?.length) parts.push(filters.locations.join(", "));
  parts.push(`${humanize(filters.missing_location || "INCLUDE")} missing locations`);
  return parts.join(" · ");
}

function formatFactorValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.map(formatFactorValue).join(", ") || "—";
  if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${humanize(key)}: ${formatFactorValue(item)}`).join(" · ");
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return humanize(value);
}

function humanize(value) {
  return String(value ?? "").replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function shortId(value) {
  const text = String(value || "");
  return text.length > 18 ? `${text.slice(0, 9)}…${text.slice(-6)}` : text;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
