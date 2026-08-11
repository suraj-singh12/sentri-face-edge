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
  IconRefresh,
  IconRoute,
  IconUser,
} from "@tabler/icons-react";

import { SafeImage } from "../components/Shared.jsx";
import { mediaUrl } from "../utils.js";

const CLUSTER_COLLECTIONS = [
  { label: "Members", value: "MEMBERS" },
  { label: "Relationships", value: "RELATIONSHIPS" },
];

export function ClusterDrilldownView({
  cluster,
  onBack,
  onRefresh,
  onCollection,
  onNextPage,
}) {
  const collectionState = cluster.collections[cluster.collection];
  const data = collectionState?.data;
  const summary = cluster.summary || data?.clusters?.[0] || null;
  const page = data?.pagination?.[cluster.collection] || null;
  const [selected, setSelected] = useState(null);

  useEffect(() => setSelected(null), [cluster.collection, collectionState?.pageNumber, data?.graph_revision]);

  if (!summary && collectionState?.loading) {
    return (
      <Stack gap="sm" className="world-cluster-shell">
        <Button variant="subtle" size="xs" leftSection={<IconArrowLeft size={15} />} onClick={onBack} className="world-cluster-back">Back to World scope</Button>
        <Stack align="center" justify="center" className="world-cluster-loading">
          <Loader color="teal" />
          <Text size="sm" c="dimmed">Loading the authoritative cluster member page…</Text>
        </Stack>
      </Stack>
    );
  }

  if (!summary) {
    return (
      <Stack gap="sm" className="world-cluster-shell">
        <Button variant="subtle" size="xs" leftSection={<IconArrowLeft size={15} />} onClick={onBack} className="world-cluster-back">Back to World scope</Button>
        <Alert color="red" title="Cluster could not be loaded">{collectionState?.error?.message || "The required Cluster contract is unavailable."}</Alert>
        <Button variant="default" size="xs" leftSection={<IconRefresh size={15} />} onClick={onRefresh}>Try again</Button>
      </Stack>
    );
  }

  return (
    <Stack gap="sm" className="world-cluster-shell" data-world-level="CLUSTER">
      <ClusterHeader summary={summary} effectiveFilters={data?.effective_filters || cluster.binding?.filters} page={page} state={collectionState} onBack={onBack} onRefresh={onRefresh} />

      {collectionState?.error ? (
        <Alert color="yellow" title={`The ${cluster.collection.toLowerCase()} page could not be loaded`}>
          {collectionState.error.message}
        </Alert>
      ) : null}

      <Box className="world-cluster-workarea">
        <Box className="world-cluster-primary">
          <Group justify="space-between" align="center" wrap="nowrap" className="world-cluster-collection-bar">
            <SegmentedControl
              size="xs"
              value={cluster.collection}
              data={CLUSTER_COLLECTIONS}
              onChange={onCollection}
              disabled={collectionState?.loading}
              aria-label="Cluster collection"
            />
            <Box ta="right">
              <Text size="xs" c="dimmed">{page ? `Page ${collectionState.pageNumber} · ${page.returned_count} of ${page.total_count}` : "Bounded collection"}</Text>
              {page?.truncated ? <Text size="10px" c="yellow.7">{humanize(page.truncation_reason || "More results available")}</Text> : null}
            </Box>
          </Group>
          <Paper withBorder radius="md" className="world-cluster-collection">
            {collectionState?.loading && data ? <Box className="world-loading-stripe"><Loader size={16} /><Text size="xs">Replacing page…</Text></Box> : null}
            {collectionState?.loading && !data ? (
              <Stack align="center" justify="center" className="world-cluster-collection-loading"><Loader size={20} /><Text size="xs" c="dimmed">Loading authoritative {cluster.collection.toLowerCase()}…</Text></Stack>
            ) : cluster.collection === "MEMBERS" ? (
              <ClusterMembers people={data?.people || []} page={page} selected={selected} onSelect={(person) => setSelected({ type: "person", value: person })} />
            ) : (
              <ClusterRelationships relationships={data?.relationships || []} page={page} selected={selected} onSelect={(relationship) => setSelected({ type: "relationship", value: relationship })} />
            )}
          </Paper>
          {page?.has_more ? (
            <Group justify="center" mt="xs">
              <Button variant="default" size="xs" rightSection={<IconArrowRight size={14} />} onClick={onNextPage} disabled={collectionState?.loading || !page.next_cursor}>
                Next authoritative page
              </Button>
            </Group>
          ) : null}
        </Box>

        <Stack gap="sm" className="world-cluster-context">
          <Paper withBorder radius="md" className="world-cluster-explanation">
            <ClusterExplanation summary={summary} effectiveFilters={data?.effective_filters || cluster.binding?.filters} />
          </Paper>
          <Paper withBorder radius="md" className="world-cluster-inspector">
            <ClusterSelectionInspector item={selected} />
          </Paper>
        </Stack>
      </Box>
    </Stack>
  );
}

function ClusterHeader({ summary, effectiveFilters, page, state, onBack, onRefresh }) {
  return (
    <Stack gap="xs">
      <Group justify="space-between" align="flex-start" wrap="nowrap" className="world-cluster-header">
        <Group gap="sm" wrap="nowrap" miw={0}>
          <ActionIcon variant="subtle" size={36} onClick={onBack} aria-label="Back to World scope"><IconArrowLeft size={18} /></ActionIcon>
          <ThemeIcon size={38} radius="md" variant="light" color="teal"><IconBinaryTree size={20} /></ThemeIcon>
          <Box miw={0}>
            <Group gap="xs" wrap="nowrap">
              <Title order={2} size="h3">Evidence-connected cluster</Title>
              <Badge size="xs" variant="outline" color="gray">Rank {summary.ranking.rank_position}</Badge>
            </Group>
            <Text size="xs" c="dimmed" lineClamp={1}>{effectiveScopeLabel(effectiveFilters)} · Revision-bound result</Text>
          </Box>
        </Group>
        <Group gap="xs" wrap="nowrap">
          {state?.loading ? <Loader size={17} /> : null}
          <Tooltip label="Refresh cluster">
            <ActionIcon variant="default" size={36} onClick={onRefresh} disabled={state?.loading} aria-label="Refresh Cluster"><IconRefresh size={17} /></ActionIcon>
          </Tooltip>
        </Group>
      </Group>
      <Group gap="xs" className="world-cluster-header-facts">
        <HeaderFact label="Members" value={summary.member_count} />
        <HeaderFact label="Relationships" value={summary.evidence_basis.relationship_count} />
        <HeaderFact label="Evidence" value={summary.evidence_basis.evidence_count} />
        <HeaderFact label="Event contributions" value={summary.activity_summary.member_event_contributions} />
        <HeaderFact label="Active members" value={summary.activity_summary.active_member_count} />
        {page?.truncated ? <Badge size="xs" color="yellow" variant="light">Current collection is bounded</Badge> : null}
      </Group>
    </Stack>
  );
}

function HeaderFact({ label, value }) {
  return <Paper withBorder radius="sm" px="xs" py={5} className="world-cluster-header-fact"><Text span size="sm" fw={800}>{value}</Text><Text span size="10px" c="dimmed"> {label}</Text></Paper>;
}

function ClusterMembers({ people, page, selected, onSelect }) {
  if (!people.length) return <ClusterEmpty page={page} noun="members" />;
  return (
    <ScrollArea.Autosize mah={545}>
      <Stack gap={0}>
        {people.map((person) => {
          const mediaReference = person.display?.representative_media_reference || person.display?.representative_media || null;
          return (
            <button
              key={person.canonical_person_id}
              type="button"
              className="world-row world-cluster-member-row"
              data-lifecycle={person.lifecycle_state}
              data-selected={selected?.type === "person" && selected.value.canonical_person_id === person.canonical_person_id}
              onClick={() => onSelect(person)}
            >
              <SafeImage
                src={mediaReference ? mediaUrl(mediaReference) : ""}
                alt=""
                className="world-cluster-member-photo"
                fallback={<ThemeIcon size={36} radius="xl" variant="light" color="gray"><IconUser size={18} /></ThemeIcon>}
              />
              <span className="world-row-main">
                <Text component="span" size="sm" fw={800}>{person.display_name}</Text>
                <Text component="span" size="10px" c="dimmed">{[person.display.rank, person.display.country, humanize(person.biometric_state)].filter(Boolean).join(" · ") || "No profile facets returned"}</Text>
                <Text component="span" size="10px">{person.ranking.ranking_reason}</Text>
              </span>
              {person.analytics_state === "LOADED" ? (
                <span className="world-person-metrics">
                  <Metric value={person.activity_summary.finalized_event_count} label="events" />
                  <Metric value={person.intelligence_summary.relationship_count} label="relations" />
                  <Metric value={person.intelligence_summary.relationship_evidence_count} label="evidence" />
                </span>
              ) : <Text size="10px" c="dimmed" className="world-analytics-unavailable">Analytics not loaded</Text>}
              <Badge size="xs" variant="light" color={lifecycleColor(person.lifecycle_state)}>{person.lifecycle_state}</Badge>
            </button>
          );
        })}
      </Stack>
    </ScrollArea.Autosize>
  );
}

function ClusterRelationships({ relationships, page, selected, onSelect }) {
  if (!relationships.length) return <ClusterEmpty page={page} noun="relationships" />;
  return (
    <ScrollArea.Autosize mah={545}>
      <Stack gap={0}>
        {relationships.map((relationship) => (
          <button
            key={relationship.relationship_id}
            type="button"
            className="world-row world-cluster-relationship-row"
            data-directionality={relationship.directionality}
            data-selected={selected?.type === "relationship" && selected.value.relationship_id === relationship.relationship_id}
            onClick={() => onSelect(relationship)}
          >
            <ThemeIcon size={32} variant="light" color="blue"><IconRoute size={16} /></ThemeIcon>
            <span className="world-row-main">
              <Text component="span" size="xs" fw={800}>{shortId(relationship.source_person_id)} <Text span c="dimmed">{relationship.directionality === "UNDIRECTED" ? "↔" : "→"}</Text> {shortId(relationship.target_person_id)}</Text>
              <Text component="span" size="10px" c="dimmed">{relationship.relationship_types.map(humanize).join(", ")} · {humanize(relationship.directionality)}</Text>
              <Text component="span" size="10px">{Object.entries(relationship.evidence_type_counts).map(([type, count]) => `${humanize(type)} ${count}`).join(" · ")}</Text>
            </span>
            <Metric value={relationship.evidence_count} label="evidence" />
            <Box ta="right" className="world-cluster-occurrence"><Text size="10px" c="dimmed">Last {formatDate(relationship.last_occurrence_at)}</Text><Text size="10px" c="dimmed">{humanize(relationship.strength_basis)}</Text></Box>
          </button>
        ))}
      </Stack>
    </ScrollArea.Autosize>
  );
}

function ClusterEmpty({ page, noun }) {
  const complete = page && !page.has_more && page.total_count === 0;
  return <Stack gap={2} align="center" ta="center" p="lg"><Text size="sm" fw={700}>{complete ? `No ${noun} in this cluster response` : `No ${noun} returned on this page`}</Text><Text size="xs" c="dimmed">{page ? `${page.returned_count} returned of ${page.total_count} authoritative ${noun}.` : "Page state is unavailable."}</Text></Stack>;
}

function ClusterExplanation({ summary, effectiveFilters }) {
  const explanation = summary.explanation;
  return (
    <Stack gap="sm" p="sm">
      <Box><Text fw={800}>Why this cluster exists</Text><Text size="10px" c="dimmed">Backend-provided factual explanation</Text></Box>
      <Text size="sm">{explanation.summary}</Text>
      <Divider />
      <InspectorRow label="Ranking context" value={summary.ranking.reason} />
      <InspectorRow label="Grouping method" value={humanize(summary.grouping_algorithm)} />
      <InspectorRow label="Occurrence" value={`${formatDate(explanation.first_occurrence_at)} – ${formatDate(explanation.last_occurrence_at)}`} />
      <InspectorRow label="Effective scope" value={effectiveScopeLabel(effectiveFilters)} />
      <FactorRows title="Factual factors" factors={explanation.factual_factors} />
      <FactorRows title="Strongest qualifying factors" factors={explanation.strongest_factors} />
      {summary.evidence_basis.strongest_relationships.length ? (
        <Box><Text size="xs" fw={700} mb={3}>Strongest qualifying relationships</Text>{summary.evidence_basis.strongest_relationships.map((relationship) => (
          <InspectorRow key={relationship.relationship_id} label={`${shortId(relationship.source_person_id)} ↔ ${shortId(relationship.target_person_id)}`} value={`${relationship.evidence_count} evidence`} />
        ))}</Box>
      ) : null}
      <InspectorRow label="Method" value={humanize(explanation.method)} />
      {explanation.threshold ? <InspectorRow label="Threshold" value={formatFactorValue(explanation.threshold)} /> : null}
      <Box className="world-limitations"><Text size="xs" fw={700}>Limitations</Text>{explanation.limitations.map((limitation) => <Text key={limitation} size="xs" c="dimmed">{limitation}</Text>)}</Box>
    </Stack>
  );
}

function ClusterSelectionInspector({ item }) {
  if (!item) return <Stack gap="xs" p="sm"><Text fw={800}>Selection details</Text><Text size="sm" c="dimmed">Select a member or relationship for its authoritative summary.</Text></Stack>;
  if (item.type === "person") {
    const person = item.value;
    return (
      <Stack gap="sm" p="sm">
        <Box><Text size="xs" c="dimmed" tt="uppercase" fw={700}>Member navigation intent</Text><Text fw={800}>{person.display_name}</Text></Box>
        <InspectorRow label="Canonical identity" value={person.canonical_person_id} />
        <InspectorRow label="Lifecycle" value={humanize(person.lifecycle_state)} />
        <InspectorRow label="Biometric state" value={humanize(person.biometric_state)} />
        <InspectorRow label="Analytics" value={humanize(person.analytics_state)} />
        <InspectorRow label="Allowed actions" value={person.allowed_actions.map(humanize).join(", ") || "None"} />
        <Text size="xs" c="dimmed">Person selection is prepared for the frozen World PERSON contract in P10-F3. No profile API or person drilldown is opened in this phase.</Text>
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
      <FactorRows title="Factual factors" factors={explanation.factual_factors} />
      <Box className="world-limitations"><Text size="xs" fw={700}>Limitations</Text>{explanation.limitations.map((limitation) => <Text key={limitation} size="xs" c="dimmed">{limitation}</Text>)}</Box>
      <Text size="10px" c="dimmed">Evidence navigation remains reserved for a later P10-F phase.</Text>
    </Stack>
  );
}

function FactorRows({ title, factors }) {
  if (!Array.isArray(factors) || !factors.length) return null;
  return <Box><Text size="xs" fw={700} mb={3}>{title}</Text>{factors.map((factor, index) => <InspectorRow key={`${factor.factor || factor.relationship_id}-${index}`} label={humanize(factor.factor || "Relationship")} value={formatFactorValue(factor.value ?? factor)} />)}</Box>;
}

function InspectorRow({ label, value }) {
  return <Group justify="space-between" align="flex-start" gap="sm" wrap="nowrap" className="world-inspector-row"><Text size="xs" c="dimmed">{label}</Text><Text size="xs" fw={700} ta="right">{value ?? "—"}</Text></Group>;
}

function Metric({ value, label }) {
  return <span className="world-metric"><Text component="span" size="xs" fw={800}>{value ?? "—"}</Text><Text component="span" size="9px" c="dimmed">{label}</Text></span>;
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
