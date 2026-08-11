import { useEffect, useState } from "react";
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
  IconCalendarEvent,
  IconFileDescription,
  IconFingerprint,
  IconPhoto,
  IconRefresh,
  IconRoute,
  IconUser,
} from "@tabler/icons-react";

import { SafeImage } from "../components/Shared.jsx";
import { WorldMediaPreview } from "../components/WorldMediaPreview.jsx";
import { mediaUrl } from "../utils.js";

const EVENT_COLLECTIONS = [
  { label: "Participants", value: "PARTICIPANTS" },
  { label: "Provenance", value: "PROVENANCE" },
  { label: "Evidence", value: "EVIDENCE" },
  { label: "Media", value: "MEDIA" },
];

export function WorldEventDrilldownView({ event, onBack, onRefresh, onCollection, onNextPage, onOpenEvidence }) {
  const collectionState = event.collections[event.collection];
  const data = collectionState?.data;
  const summary = event.summary || data?.events?.[0] || null;
  const page = data?.pagination?.[event.collection] || null;
  const [selected, setSelected] = useState(null);
  const [previewMedia, setPreviewMedia] = useState(null);

  useEffect(() => setSelected(null), [event.collection, collectionState?.pageNumber, data?.graph_revision]);

  if (!summary && collectionState?.loading) {
    return (
      <Stack gap="sm" className="world-event-shell">
        <Button variant="subtle" size="xs" leftSection={<IconArrowLeft size={15} />} onClick={onBack} className="world-event-back">Back to scoped person</Button>
        <Stack align="center" justify="center" className="world-event-loading"><Loader color="teal" /><Text size="sm" c="dimmed">Loading the authoritative finalized event…</Text></Stack>
      </Stack>
    );
  }

  if (!summary) {
    return (
      <Stack gap="sm" className="world-event-shell">
        <Button variant="subtle" size="xs" leftSection={<IconArrowLeft size={15} />} onClick={onBack} className="world-event-back">Back to scoped person</Button>
        <Alert color="red" title="World event could not be loaded">{collectionState?.error?.message || "The required World Event contract is unavailable."}</Alert>
        <Button variant="default" size="xs" leftSection={<IconRefresh size={15} />} onClick={onRefresh}>Try again</Button>
      </Stack>
    );
  }

  return (
    <Stack gap="sm" className="world-event-shell" data-world-level="EVENT">
      <EventHeader summary={summary} binding={event.binding} state={collectionState} page={page} onBack={onBack} onRefresh={onRefresh} />
      {collectionState?.error ? <Alert color="yellow" title={`The ${event.collection.toLowerCase()} page could not be loaded`}>{collectionState.error.message}</Alert> : null}

      <Box className="world-event-workarea">
        <Box className="world-event-primary">
          <Group justify="space-between" align="center" wrap="nowrap" className="world-event-collection-bar">
            <SegmentedControl size="xs" value={event.collection} data={EVENT_COLLECTIONS} onChange={onCollection} disabled={collectionState?.loading} aria-label="World event collection" />
            <Box ta="right">
              <Text size="xs" c="dimmed">{page ? `Page ${collectionState.pageNumber} · ${page.returned_count} of ${page.total_count}` : "Bounded collection"}</Text>
              {page?.truncated ? <Text size="10px" c="yellow.7">{humanize(page.truncation_reason || "More results available")}</Text> : null}
            </Box>
          </Group>
          <Paper withBorder radius="md" className="world-event-collection">
            {collectionState?.loading && data ? <Box className="world-loading-stripe"><Loader size={16} /><Text size="xs">Replacing page…</Text></Box> : null}
            {collectionState?.loading && !data ? (
              <Stack align="center" justify="center" className="world-event-collection-loading"><Loader size={20} /><Text size="xs" c="dimmed">Loading authoritative {event.collection.toLowerCase()}…</Text></Stack>
            ) : <EventCollection collection={event.collection} event={data?.events?.[0]} evidence={data?.evidence || []} media={data?.media || []} page={page} selected={selected} onSelect={setSelected} />}
          </Paper>
          {page?.has_more ? <Group justify="center" mt="xs"><Button variant="default" size="xs" rightSection={<IconArrowRight size={14} />} onClick={onNextPage} disabled={collectionState?.loading || !page.next_cursor}>Next authoritative page</Button></Group> : null}
        </Box>

        <Stack gap="sm" className="world-event-context">
          <Paper withBorder radius="md" className="world-event-explanation"><EventExplanation summary={summary} binding={event.binding} /></Paper>
          <Paper withBorder radius="md" className="world-event-inspector"><EventSelectionInspector item={selected} eventId={summary.event_id} binding={event.binding} onOpenEvidence={onOpenEvidence} onPreviewMedia={setPreviewMedia} /></Paper>
        </Stack>
      </Box>
      <WorldMediaPreview item={previewMedia} opened={Boolean(previewMedia)} onClose={() => setPreviewMedia(null)} origin={{ type: "EVENT", eventId: summary.event_id }} />
    </Stack>
  );
}

function EventHeader({ summary, binding, state, page, onBack, onRefresh }) {
  return (
    <Stack gap="xs">
      <Group justify="space-between" align="flex-start" wrap="nowrap" className="world-event-header">
        <Group gap="sm" wrap="nowrap" miw={0}>
          <ActionIcon variant="subtle" size={36} onClick={onBack} aria-label="Back to scoped person"><IconArrowLeft size={18} /></ActionIcon>
          <ThemeIcon size={40} radius="md" variant="light" color="teal"><IconCalendarEvent size={21} /></ThemeIcon>
          <Box miw={0}>
            <Group gap="xs" wrap="wrap"><Title order={2} size="h3">Finalized observation</Title><Badge size="xs" variant="outline" color="gray">{shortId(summary.event_id)}</Badge></Group>
            <Text size="xs" c="dimmed" lineClamp={1}>{formatDateTime(summary.occurred_at)} · {summary.location || "Location not recorded"} · {effectiveScopeLabel(binding?.filters)}</Text>
            <Text size="10px" c="dimmed" lineClamp={1}>{eventContext(summary.context_summary, summary.source)}</Text>
          </Box>
        </Group>
        <Group gap="xs" wrap="nowrap">{state?.loading ? <Loader size={17} /> : null}<Tooltip label="Refresh finalized event"><ActionIcon variant="default" size={36} onClick={onRefresh} disabled={state?.loading} aria-label="Refresh World Event"><IconRefresh size={17} /></ActionIcon></Tooltip></Group>
      </Group>
      <Group gap="xs" className="world-event-header-facts">
        <HeaderFact label="Effective participants" value={summary.participant_summary.total_count} />
        <HeaderFact label="Raw provenance" value={summary.participant_summary.provenance_total_count} />
        <HeaderFact label="Evidence" value={summary.evidence_summary.total_count} />
        <HeaderFact label="Media" value={summary.media_summary.total_count} />
        <Paper withBorder radius="sm" px="xs" py={5} className="world-event-header-fact"><Text span size="10px" c="dimmed">Finalized </Text><Text span size="xs" fw={700}>{formatDateTime(summary.finalized_at)}</Text></Paper>
        {page?.truncated ? <Badge size="xs" color="yellow" variant="light">Current collection is bounded</Badge> : null}
      </Group>
    </Stack>
  );
}

function HeaderFact({ label, value }) {
  return <Paper withBorder radius="sm" px="xs" py={5} className="world-event-header-fact"><Text span size="sm" fw={800}>{value}</Text><Text span size="10px" c="dimmed"> {label}</Text></Paper>;
}

function EventCollection({ collection, event, evidence, media, page, selected, onSelect }) {
  if (collection === "PARTICIPANTS") return <Participants items={event?.participants || []} page={page} selected={selected} onSelect={onSelect} />;
  if (collection === "PROVENANCE") return <Provenance items={event?.participant_provenance || []} page={page} selected={selected} onSelect={onSelect} />;
  if (collection === "EVIDENCE") return <Evidence items={evidence} page={page} selected={selected} onSelect={onSelect} />;
  return <Media items={media} page={page} selected={selected} onSelect={onSelect} />;
}

function Participants({ items, page, selected, onSelect }) {
  if (!items.length) return <EventEmpty page={page} noun="participants" />;
  return <ScrollArea.Autosize mah={535}><Stack gap={0}>{items.map((participant) => (
    <button key={participant.person_id} type="button" className="world-row world-event-participant-row" data-selected={selected?.type === "participant" && selected.value.person_id === participant.person_id} onClick={() => onSelect({ type: "participant", value: participant })}>
      <ThemeIcon size={34} radius="xl" variant="light" color="teal"><IconUser size={17} /></ThemeIcon>
      <span className="world-row-main"><Text component="span" size="sm" fw={800}>{shortId(participant.person_id)}</Text><Text component="span" size="10px" c="dimmed">Backend-returned effective canonical participant</Text></span>
      <Badge size="xs" variant="light" color="gray">Effective identity</Badge>
    </button>
  ))}</Stack></ScrollArea.Autosize>;
}

function Provenance({ items, page, selected, onSelect }) {
  if (!items.length) return <EventEmpty page={page} noun="provenance records" />;
  return <ScrollArea.Autosize mah={535}><Stack gap={0}>{items.map((item, index) => (
    <button key={`${item.raw_person_id}-${index}`} type="button" className="world-row world-event-provenance-row" data-selected={selected?.type === "provenance" && selected.index === index} onClick={() => onSelect({ type: "provenance", value: item, index })}>
      <ThemeIcon size={34} variant="light" color="violet"><IconFingerprint size={17} /></ThemeIcon>
      <span className="world-row-main"><Text component="span" size="xs" fw={800}>{shortId(item.raw_person_id)} <Text span c="dimmed">→</Text> {shortId(item.effective_person_id)}</Text><Text component="span" size="10px" c="dimmed">{humanize(item.relationship_to_effective_identity)}</Text><Text component="span" size="10px">{item.correction_operation_ids.length ? `${item.correction_operation_ids.length} backend correction operation${item.correction_operation_ids.length === 1 ? "" : "s"}` : "No correction operation supplied"}</Text></span>
      <Badge size="xs" variant="outline" color="gray">Raw → effective</Badge>
    </button>
  ))}</Stack></ScrollArea.Autosize>;
}

function Evidence({ items, page, selected, onSelect }) {
  if (!items.length) return <EventEmpty page={page} noun="evidence records" />;
  return <ScrollArea.Autosize mah={535}><Stack gap={0}>{items.map((item) => (
    <button key={item.evidence_id} type="button" className="world-row world-event-evidence-row" data-selected={selected?.type === "evidence" && selected.value.evidence_id === item.evidence_id} onClick={() => onSelect({ type: "evidence", value: item })}>
      <ThemeIcon size={34} variant="light" color="blue"><IconFileDescription size={17} /></ThemeIcon>
      <span className="world-row-main"><Text component="span" size="xs" fw={800}>{humanize(item.evidence_type)} · {humanize(item.directionality)}</Text><Text component="span" size="10px" c="dimmed">{endpointLabel(item.effective_endpoints)} · {formatDateTime(item.occurred_at)}</Text><Text component="span" size="10px">{item.explanation.summary}</Text></span>
      <Box ta="right"><Badge size="xs" variant="light" color={item.media_summary.availability === "AVAILABLE" ? "teal" : "gray"}>{item.media_summary.total_count} media</Badge><Text size="10px" c="dimmed">{shortId(item.evidence_id)}</Text></Box>
    </button>
  ))}</Stack></ScrollArea.Autosize>;
}

function Media({ items, page, selected, onSelect }) {
  if (!items.length) return <EventEmpty page={page} noun="media references" />;
  return <ScrollArea.Autosize mah={535}><SimpleGrid cols={{ base: 2, sm: 3, lg: 4 }} spacing="xs" p="xs">{items.map((item) => (
    <button key={item.media_id} type="button" className="world-event-media-card" data-selected={selected?.type === "media" && selected.value.media_id === item.media_id} onClick={() => onSelect({ type: "media", value: item })}>
      <SafeImage src={item.media_reference ? mediaUrl(item.media_reference) : ""} alt="" className="world-event-media-thumb" fallback={<ThemeIcon size={42} variant="light" color="gray"><IconPhoto size={21} /></ThemeIcon>} />
      <span className="world-row-main"><Text component="span" size="xs" fw={800}>{shortId(item.media_id)}</Text><Text component="span" size="10px" c="dimmed">{formatDateTime(item.occurred_at)}</Text><Text component="span" size="10px">{item.source || "Source not supplied"}</Text></span>
    </button>
  ))}</SimpleGrid></ScrollArea.Autosize>;
}

function EventEmpty({ page, noun }) {
  const complete = page && !page.has_more && page.total_count === 0;
  return <Stack gap={2} align="center" ta="center" p="lg"><Text size="sm" fw={700}>{complete ? `No ${noun} for this finalized event` : `No ${noun} returned on this page`}</Text><Text size="xs" c="dimmed">{page ? `${page.returned_count} returned of ${page.total_count} authoritative ${noun}.` : "Page state is unavailable."}</Text></Stack>;
}

function EventExplanation({ summary, binding }) {
  const explanation = summary.explanation;
  return (
    <Stack gap="sm" p="sm"><Box><Text fw={800}>Event fact</Text><Text size="10px" c="dimmed">Finalized observation and backend explanation</Text></Box><Text size="sm">{explanation.summary}</Text><Divider /><InspectorRow label="Event ID" value={summary.event_id} /><InspectorRow label="Observed" value={formatDateTime(summary.occurred_at)} /><InspectorRow label="Location" value={summary.location || "Not recorded"} /><InspectorRow label="Source" value={summary.source || "Not supplied"} /><InspectorRow label="Context" value={eventContext(summary.context_summary)} /><InspectorRow label="Effective scope" value={effectiveScopeLabel(binding?.filters)} /><FactorRows factors={explanation.factual_factors} /><Box className="world-limitations"><Text size="xs" fw={700}>Limitations</Text>{explanation.limitations.map((limitation) => <Text key={limitation} size="xs" c="dimmed">{limitation}</Text>)}</Box></Stack>
  );
}

function EventSelectionInspector({ item, eventId, binding, onOpenEvidence, onPreviewMedia }) {
  if (!item) return <Stack gap="xs" p="sm"><Text fw={800}>Selection details</Text><Text size="sm" c="dimmed">Select an event child record for its authoritative facts or later-phase navigation intent.</Text></Stack>;
  if (item.type === "participant") return <Stack gap="sm" p="sm"><Box><Text size="xs" c="dimmed" tt="uppercase" fw={700}>Effective participant</Text><Text fw={800}>{item.value.person_id}</Text></Box><Text size="xs" c="dimmed">The frozen EVENT participant entry supplies a canonical ID but no allowed actions or person presentation state. PERSON navigation is therefore not enabled here.</Text></Stack>;
  if (item.type === "provenance") {
    const value = item.value;
    return <Stack gap="sm" p="sm"><Box><Text size="xs" c="dimmed" tt="uppercase" fw={700}>Raw participant provenance</Text><Text fw={800}>{shortId(value.raw_person_id)} → {shortId(value.effective_person_id)}</Text></Box><InspectorRow label="Interpretation" value={humanize(value.relationship_to_effective_identity)} /><InspectorRow label="Correction operations" value={value.correction_operation_ids.map(shortId).join(", ") || "None supplied"} /><Text size="10px" c="dimmed">This is the backend-provided raw-to-effective mapping. React does not reconstruct correction or merge chains.</Text></Stack>;
  }
  if (item.type === "media") {
    const value = item.value;
    return <Stack gap="sm" p="sm"><Box><Text size="xs" c="dimmed" tt="uppercase" fw={700}>Event media</Text><Text fw={800}>{shortId(value.media_id)}</Text></Box><InspectorRow label="Event" value={value.supporting_event_id} /><InspectorRow label="Supporting evidence" value={value.supporting_evidence_id || "None supplied"} /><InspectorRow label="Occurred" value={formatDateTime(value.occurred_at)} /><InspectorRow label="Revision binding" value={shortId(binding?.revision)} /><Button size="xs" variant="light" leftSection={<IconPhoto size={14} />} onClick={() => onPreviewMedia(value)}>Inspect event media</Button></Stack>;
  }
  const value = item.value;
  return <Stack gap="sm" p="sm"><Box><Text size="xs" c="dimmed" tt="uppercase" fw={700}>Evidence detail</Text><Text fw={800}>{shortId(value.evidence_id)}</Text></Box><InspectorRow label="Event" value={eventId} /><InspectorRow label="Type" value={humanize(value.evidence_type)} /><InspectorRow label="Directionality" value={humanize(value.directionality)} /><InspectorRow label="Effective endpoints" value={endpointLabel(value.effective_endpoints)} /><InspectorRow label="Raw endpoints" value={endpointLabel(value.raw_endpoints)} /><InspectorRow label="Occurrence" value={formatDateTime(value.occurred_at)} /><InspectorRow label="Media availability" value={`${humanize(value.media_summary.availability)} · ${value.media_summary.total_count}`} /><InspectorRow label="Revision binding" value={shortId(binding?.revision)} /><Text size="sm">{value.explanation.summary}</Text><Button size="xs" variant="light" leftSection={<IconFileDescription size={14} />} onClick={() => onOpenEvidence(value)}>Open authoritative evidence</Button></Stack>;
}

function FactorRows({ factors }) {
  if (!factors.length) return null;
  return <Box><Text size="xs" fw={700} mb={3}>Factual factors</Text>{factors.map((factor, index) => <InspectorRow key={`${factor.factor}-${index}`} label={humanize(factor.factor)} value={formatFactorValue(factor.value)} />)}</Box>;
}

function InspectorRow({ label, value }) {
  return <Group justify="space-between" align="flex-start" gap="sm" wrap="nowrap" className="world-inspector-row"><Text size="xs" c="dimmed">{label}</Text><Text size="xs" fw={700} ta="right">{value ?? "—"}</Text></Group>;
}

function endpointLabel(values) {
  return values?.length ? values.map(shortId).join(" ↔ ") : "No endpoints supplied";
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

function eventContext(context, source = null) {
  const values = [context?.occasion, context?.event_type, context?.description, source].filter(Boolean);
  return values.join(" · ") || "No context supplied";
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
