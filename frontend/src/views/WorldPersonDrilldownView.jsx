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
  Stack,
  Text,
  ThemeIcon,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconArrowRight,
  IconBinaryTree,
  IconCalendarEvent,
  IconMapPin,
  IconRefresh,
  IconRoute,
  IconUser,
} from "@tabler/icons-react";

import { SafeImage } from "../components/Shared.jsx";
import { mediaUrl } from "../utils.js";

const PERSON_COLLECTIONS = [
  { label: "Relationships", value: "RELATIONSHIPS" },
  { label: "Events", value: "EVENTS" },
];

export function WorldPersonDrilldownView({
  person,
  onBack,
  onRefresh,
  onCollection,
  onNextPage,
  onOpenEvent,
}) {
  const collectionState = person.collections[person.collection];
  const data = collectionState?.data;
  const root = person.root || data?.people?.[0] || null;
  const page = data?.pagination?.[person.collection] || null;
  const [selected, setSelected] = useState(null);

  useEffect(() => setSelected(null), [person.collection, collectionState?.pageNumber, data?.graph_revision]);

  if (!root && collectionState?.loading) {
    return (
      <Stack gap="sm" className="world-person-shell">
        <Button variant="subtle" size="xs" leftSection={<IconArrowLeft size={15} />} onClick={onBack} className="world-person-back">{backLabel(person.origin)}</Button>
        <Stack align="center" justify="center" className="world-person-loading">
          <Loader color="teal" />
          <Text size="sm" c="dimmed">Loading the authoritative scoped person…</Text>
        </Stack>
      </Stack>
    );
  }

  if (!root) {
    return (
      <Stack gap="sm" className="world-person-shell">
        <Button variant="subtle" size="xs" leftSection={<IconArrowLeft size={15} />} onClick={onBack} className="world-person-back">{backLabel(person.origin)}</Button>
        <Alert color="red" title="World person could not be loaded">{collectionState?.error?.message || "The required World Person contract is unavailable."}</Alert>
        <Button variant="default" size="xs" leftSection={<IconRefresh size={15} />} onClick={onRefresh}>Try again</Button>
      </Stack>
    );
  }

  return (
    <Stack gap="sm" className="world-person-shell" data-world-level="PERSON">
      <PersonHeader person={root} binding={person.binding} origin={person.origin} state={collectionState} page={page} onBack={onBack} onRefresh={onRefresh} />

      {collectionState?.error ? (
        <Alert color="yellow" title={`The ${person.collection.toLowerCase()} page could not be loaded`}>{collectionState.error.message}</Alert>
      ) : null}

      <Box className="world-person-workarea">
        <Box className="world-person-primary">
          <Group justify="space-between" align="center" wrap="nowrap" className="world-person-collection-bar">
            <SegmentedControl size="xs" value={person.collection} data={PERSON_COLLECTIONS} onChange={onCollection} disabled={collectionState?.loading} aria-label="World person collection" />
            <Box ta="right">
              <Text size="xs" c="dimmed">{page ? `Page ${collectionState.pageNumber} · ${page.returned_count} of ${page.total_count}` : "Bounded collection"}</Text>
              {page?.truncated ? <Text size="10px" c="yellow.7">{humanize(page.truncation_reason || "More results available")}</Text> : null}
            </Box>
          </Group>
          <Paper withBorder radius="md" className="world-person-collection">
            {collectionState?.loading && data ? <Box className="world-loading-stripe"><Loader size={16} /><Text size="xs">Replacing page…</Text></Box> : null}
            {collectionState?.loading && !data ? (
              <Stack align="center" justify="center" className="world-person-collection-loading"><Loader size={20} /><Text size="xs" c="dimmed">Loading authoritative {person.collection.toLowerCase()}…</Text></Stack>
            ) : person.collection === "RELATIONSHIPS" ? (
              <PersonRelationships root={root} people={data?.people || []} relationships={data?.relationships || []} page={page} selected={selected} onSelect={(relationship) => setSelected({ type: "relationship", value: relationship })} />
            ) : (
              <PersonEvents events={data?.events || []} page={page} selected={selected} onSelect={(event) => setSelected({ type: "event", value: event })} />
            )}
          </Paper>
          {page?.has_more ? (
            <Group justify="center" mt="xs">
              <Button variant="default" size="xs" rightSection={<IconArrowRight size={14} />} onClick={onNextPage} disabled={collectionState?.loading || !page.next_cursor}>Next authoritative page</Button>
            </Group>
          ) : null}
        </Box>

        <Stack gap="sm" className="world-person-context">
          <Paper withBorder radius="md" className="world-person-clusters"><ClusterMemberships memberships={root.cluster_memberships} /></Paper>
          <Paper withBorder radius="md" className="world-person-inspector"><PersonSelectionInspector item={selected} binding={person.binding} onOpenEvent={onOpenEvent} /></Paper>
        </Stack>
      </Box>
    </Stack>
  );
}

function PersonHeader({ person, binding, origin, state, page, onBack, onRefresh }) {
  const mediaReference = person.display?.representative_media_reference || person.display?.representative_media || null;
  const loaded = person.analytics_state === "LOADED";
  return (
    <Stack gap="xs">
      <Group justify="space-between" align="flex-start" wrap="nowrap" className="world-person-header">
        <Group gap="sm" wrap="nowrap" miw={0}>
          <ActionIcon variant="subtle" size={36} onClick={onBack} aria-label={backLabel(origin)}><IconArrowLeft size={18} /></ActionIcon>
          <SafeImage src={mediaReference ? mediaUrl(mediaReference) : ""} alt="" className="world-person-header-photo" fallback={<ThemeIcon size={44} radius="xl" variant="light" color="gray"><IconUser size={22} /></ThemeIcon>} />
          <Box miw={0}>
            <Group gap="xs" wrap="wrap">
              <Title order={2} size="h3" lineClamp={1}>{person.display_name}</Title>
              <Badge size="xs" variant="light" color={lifecycleColor(person.lifecycle_state)}>{person.lifecycle_state}</Badge>
              <Badge size="xs" variant="outline" color="gray">{humanize(person.identity_state)}</Badge>
              <Badge size="xs" variant="outline" color="gray">{humanize(person.biometric_state)}</Badge>
            </Group>
            <Text size="xs" c="dimmed" lineClamp={1}>{[person.display.rank, person.display.country].filter(Boolean).join(" · ") || "No profile facets returned"} · {effectiveScopeLabel(binding?.filters)}</Text>
            <Text size="10px" c="dimmed" lineClamp={1}>{person.ranking.ranking_reason}</Text>
          </Box>
        </Group>
        <Group gap="xs" wrap="nowrap">
          {state?.loading ? <Loader size={17} /> : null}
          <Tooltip label="Refresh scoped person"><ActionIcon variant="default" size={36} onClick={onRefresh} disabled={state?.loading} aria-label="Refresh World Person"><IconRefresh size={17} /></ActionIcon></Tooltip>
        </Group>
      </Group>
      <Group gap="xs" className="world-person-header-facts">
        {loaded ? (
          <>
            <HeaderFact label="Finalized events" value={person.activity_summary.finalized_event_count} />
            <HeaderFact label="Relationships" value={person.intelligence_summary.relationship_count} />
            <HeaderFact label="Evidence" value={person.intelligence_summary.relationship_evidence_count} />
            <HeaderFact label="Activity" value={humanize(person.activity_summary.activity_bucket)} />
          </>
        ) : <Badge size="xs" color="gray" variant="light">Scoped analytics not loaded</Badge>}
        <Paper withBorder radius="sm" px="xs" py={5} className="world-person-actions"><Text span size="10px" c="dimmed">Allowed actions </Text><Text span size="xs" fw={700}>{person.allowed_actions.map(humanize).join(", ") || "None"}</Text></Paper>
        {page?.truncated ? <Badge size="xs" color="yellow" variant="light">Current collection is bounded</Badge> : null}
      </Group>
    </Stack>
  );
}

function HeaderFact({ label, value }) {
  return <Paper withBorder radius="sm" px="xs" py={5} className="world-person-header-fact"><Text span size="sm" fw={800}>{value}</Text><Text span size="10px" c="dimmed"> {label}</Text></Paper>;
}

function ClusterMemberships({ memberships }) {
  return (
    <Stack gap="xs" p="sm">
      <Box><Text fw={800}>Current World clusters</Text><Text size="10px" c="dimmed">Backend-derived, revision-bound memberships</Text></Box>
      <Divider />
      {!memberships.length ? <Text size="xs" c="dimmed">No cluster memberships exist in this effective World scope.</Text> : memberships.map((membership) => (
        <Box key={membership.cluster_id} className="world-person-membership">
          <Group justify="space-between" gap="xs" wrap="nowrap"><Group gap={6} wrap="nowrap" miw={0}><IconBinaryTree size={15} /><Text size="xs" fw={800} truncate>{shortId(membership.cluster_id)}</Text></Group><Badge size="xs" variant="light" color="gray">{membership.member_count} members</Badge></Group>
          <Text size="10px" c="dimmed">{humanize(membership.grouping_algorithm)} · {membership.algorithm_version}</Text>
        </Box>
      ))}
      <Text size="10px" c="dimmed">Clusters describe scoped evidence connectivity, not organizations or affiliations.</Text>
    </Stack>
  );
}

function PersonRelationships({ root, people, relationships, page, selected, onSelect }) {
  if (!relationships.length) return <PersonEmpty page={page} noun="relationships" />;
  const peopleById = new Map(people.map((person) => [person.canonical_person_id, person]));
  return (
    <ScrollArea.Autosize mah={545}><Stack gap={0}>{relationships.map((relationship) => {
      const neighborId = relationship.source_person_id === root.canonical_person_id ? relationship.target_person_id : relationship.source_person_id;
      const neighbor = peopleById.get(neighborId);
      return (
        <button key={relationship.relationship_id} type="button" className="world-row world-person-relationship-row" data-selected={selected?.type === "relationship" && selected.value.relationship_id === relationship.relationship_id} onClick={() => onSelect(relationship)}>
          <ThemeIcon size={32} variant="light" color="blue"><IconRoute size={16} /></ThemeIcon>
          <span className="world-row-main">
            <Text component="span" size="xs" fw={800}>{neighbor?.display_name || shortId(neighborId)}</Text>
            <Text component="span" size="10px" c="dimmed">{relationship.relationship_types.map(humanize).join(", ")} · {humanize(relationship.directionality)}</Text>
            <Text component="span" size="10px">{Object.entries(relationship.evidence_type_counts).map(([type, count]) => `${humanize(type)} ${count}`).join(" · ")}</Text>
          </span>
          <Metric value={relationship.evidence_count} label="evidence" />
          <Box ta="right" className="world-person-neighbor-state"><Text size="10px" c="dimmed">Last {formatDate(relationship.last_occurrence_at)}</Text><Text size="10px" c="dimmed">{humanize(relationship.strength_basis)}</Text><Text size="10px" c="dimmed">Neighbor analytics {humanize(neighbor?.analytics_state || "NOT_LOADED")}</Text></Box>
        </button>
      );
    })}</Stack></ScrollArea.Autosize>
  );
}

function PersonEvents({ events, page, selected, onSelect }) {
  if (!events.length) return <PersonEmpty page={page} noun="events" />;
  return (
    <ScrollArea.Autosize mah={545}><Stack gap={0}>{events.map((event) => (
      <button key={event.event_id} type="button" className="world-row world-person-event-row" data-selected={selected?.type === "event" && selected.value.event_id === event.event_id} onClick={() => onSelect(event)}>
        <ThemeIcon size={32} variant="light" color="teal"><IconCalendarEvent size={16} /></ThemeIcon>
        <span className="world-row-main">
          <Text component="span" size="xs" fw={800}>{formatDateTime(event.occurred_at)}</Text>
          <Text component="span" size="10px" c={event.location ? "dimmed" : "yellow.7"}><IconMapPin size={11} /> {event.location || "Location not recorded"}</Text>
          <Text component="span" size="10px">{eventContext(event.context_summary, event.source)}</Text>
        </span>
        <span className="world-event-metrics"><Metric value={event.participant_summary.total_count} label="participants" /><Metric value={event.evidence_summary.total_count} label="evidence" /><Metric value={event.media_summary.total_count} label="media" /></span>
        <Text size="10px" c="dimmed">{shortId(event.event_id)}</Text>
      </button>
    ))}</Stack></ScrollArea.Autosize>
  );
}

function PersonEmpty({ page, noun }) {
  const complete = page && !page.has_more && page.total_count === 0;
  return <Stack gap={2} align="center" ta="center" p="lg"><Text size="sm" fw={700}>{complete ? `No scoped ${noun}` : `No ${noun} returned on this page`}</Text><Text size="xs" c="dimmed">{page ? `${page.returned_count} returned of ${page.total_count} authoritative ${noun}.` : "Page state is unavailable."}</Text></Stack>;
}

function PersonSelectionInspector({ item, binding, onOpenEvent }) {
  if (!item) return <Stack gap="xs" p="sm"><Text fw={800}>Selection details</Text><Text size="sm" c="dimmed">Select a relationship or event for its authoritative scoped summary.</Text></Stack>;
  if (item.type === "event") {
    const event = item.value;
    return (
      <Stack gap="sm" p="sm">
        <Box><Text size="xs" c="dimmed" tt="uppercase" fw={700}>Event navigation intent</Text><Text fw={800}>{formatDateTime(event.occurred_at)}</Text></Box>
        <InspectorRow label="Event ID" value={event.event_id} />
        <InspectorRow label="Location" value={event.location || "Not recorded"} />
        <InspectorRow label="Source" value={event.source || "Not supplied"} />
        <InspectorRow label="Participants" value={event.participant_summary.total_count} />
        <InspectorRow label="Evidence" value={event.evidence_summary.total_count} />
        <InspectorRow label="Media" value={event.media_summary.total_count} />
        <InspectorRow label="Revision binding" value={shortId(binding?.revision)} />
        <Text size="xs">{event.explanation.summary}</Text>
        <Button size="xs" variant="light" rightSection={<IconArrowRight size={14} />} onClick={() => onOpenEvent(event)}>Open finalized event</Button>
        <Text size="10px" c="dimmed">This issues a fresh World EVENT request. The PERSON event summary is not reused as event detail.</Text>
      </Stack>
    );
  }
  const relationship = item.value;
  const explanation = relationship.explanation;
  return (
    <Stack gap="sm" p="sm">
      <Box><Text size="xs" c="dimmed" tt="uppercase" fw={700}>Relationship</Text><Text fw={800}>{shortId(relationship.source_person_id)} {relationship.directionality === "UNDIRECTED" ? "↔" : "→"} {shortId(relationship.target_person_id)}</Text></Box>
      <Text size="sm">{explanation.summary}</Text>
      <Divider />
      <InspectorRow label="Types" value={relationship.relationship_types.map(humanize).join(", ")} />
      <InspectorRow label="Directionality" value={humanize(relationship.directionality)} />
      <InspectorRow label="Evidence count" value={relationship.evidence_count} />
      <InspectorRow label="Evidence types" value={Object.entries(relationship.evidence_type_counts).map(([type, count]) => `${humanize(type)} ${count}`).join(", ")} />
      <InspectorRow label="Strength basis" value={humanize(relationship.strength_basis)} />
      <InspectorRow label="First occurrence" value={formatDate(relationship.first_occurrence_at)} />
      <InspectorRow label="Last occurrence" value={formatDate(relationship.last_occurrence_at)} />
      <FactorRows factors={explanation.factual_factors} />
      <Box className="world-limitations"><Text size="xs" fw={700}>Limitations</Text>{explanation.limitations.map((limitation) => <Text key={limitation} size="xs" c="dimmed">{limitation}</Text>)}</Box>
      <Text size="10px" c="dimmed">Evidence navigation remains reserved for P10-F5.</Text>
    </Stack>
  );
}

function FactorRows({ factors }) {
  if (!factors.length) return null;
  return <Box><Text size="xs" fw={700} mb={3}>Factual factors</Text>{factors.map((factor, index) => <InspectorRow key={`${factor.factor}-${index}`} label={humanize(factor.factor)} value={formatFactorValue(factor.value)} />)}</Box>;
}

function InspectorRow({ label, value }) {
  return <Group justify="space-between" align="flex-start" gap="sm" wrap="nowrap" className="world-inspector-row"><Text size="xs" c="dimmed">{label}</Text><Text size="xs" fw={700} ta="right">{value ?? "—"}</Text></Group>;
}

function Metric({ value, label }) {
  return <span className="world-metric"><Text component="span" size="xs" fw={800}>{value}</Text><Text component="span" size="9px" c="dimmed">{label}</Text></span>;
}

function backLabel(origin) {
  return origin?.level === "CLUSTER" ? "Back to cluster" : "Back to World scope";
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

function eventContext(context, source) {
  const values = [context?.occasion, context?.event_type, context?.description, source].filter(Boolean);
  return values.join(" · ") || "No event context supplied";
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

function lifecycleColor(value) {
  return { ACTIVE: "teal", ARCHIVED: "yellow", DELETED: "red", MERGED: "violet" }[value] || "gray";
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
