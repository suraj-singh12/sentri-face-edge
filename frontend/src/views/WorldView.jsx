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
  MultiSelect,
  NumberInput,
  Paper,
  Popover,
  ScrollArea,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  TagsInput,
  Text,
  TextInput,
  ThemeIcon,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconAdjustments,
  IconArrowRight,
  IconBinaryTree,
  IconCalendarStats,
  IconInfoCircle,
  IconRefresh,
  IconRoute,
  IconUsers,
  IconWorld,
} from "@tabler/icons-react";

import { EMPTY_WORLD_FILTERS, worldPageFor } from "../utils/world.js";

const COLLECTION_TABS = [
  { label: "Overview", value: "PEOPLE" },
  { label: "Clusters", value: "CLUSTERS" },
  { label: "Relationships", value: "RELATIONSHIPS" },
  { label: "Patterns", value: "PATTERNS" },
];

export function WorldView({
  state,
  onRefresh,
  onApplyScope,
  onCollection,
  onNextPage,
}) {
  const data = state.data;
  const [draft, setDraft] = useState(() => ({ ...EMPTY_WORLD_FILTERS }));
  const [ranking, setRanking] = useState("SALIENCE");
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    setDraft({ ...EMPTY_WORLD_FILTERS, ...(state.filters || {}) });
    setRanking(state.ranking || "SALIENCE");
  }, [state.filters, state.ranking]);

  useEffect(() => setSelected(null), [data?.graph_revision, state.collection, state.pageNumber]);

  if (!data && state.loading) {
    return (
      <Stack align="center" justify="center" className="world-initial-loading">
        <Loader color="teal" />
        <Text size="sm" c="dimmed">Loading the authoritative World scope…</Text>
      </Stack>
    );
  }

  if (!data) {
    return (
      <Stack className="world-shell">
        <Alert color="red" title="World could not be loaded">
          {state.error?.message || "The World scope contract is unavailable."}
        </Alert>
        <Button variant="default" leftSection={<IconRefresh size={16} />} onClick={onRefresh}>Try again</Button>
      </Stack>
    );
  }

  const page = worldPageFor(data, state.collection);
  return (
    <Stack gap="sm" className="world-shell" data-contract="sentriface.world-graph-v2">
      <WorldHeader data={data} state={state} page={page} onRefresh={onRefresh} />

      {state.error ? (
        <Alert color="yellow" title="The last World request failed">
          The existing snapshot remains visible. {state.error.message}
        </Alert>
      ) : null}

      <WorldScopeControls
        data={data}
        draft={draft}
        ranking={ranking}
        disabled={state.loading}
        onDraft={setDraft}
        onRanking={setRanking}
        onApply={() => onApplyScope(draft, ranking)}
        onReset={() => {
          const filters = { ...EMPTY_WORLD_FILTERS };
          setDraft(filters);
          setRanking("SALIENCE");
          onApplyScope(filters, "SALIENCE");
        }}
      />

      <WorldTotals data={data} />

      <Group justify="space-between" align="center" gap="sm" wrap="nowrap" className="world-collection-bar">
        <SegmentedControl
          size="xs"
          value={state.collection}
          data={COLLECTION_TABS}
          onChange={onCollection}
          disabled={state.loading}
          aria-label="World collection"
        />
        <Text size="xs" c="dimmed">
          {page ? `Page ${state.pageNumber} · ${page.returned_count} of ${page.total_count}` : "Bounded collection"}
        </Text>
      </Group>

      <Box className="world-workarea">
        <Box className="world-exploration">
          {state.loading ? <Box className="world-loading-stripe"><Loader size={16} /><Text size="xs">Replacing scope…</Text></Box> : null}
          <WorldCollection data={data} collection={state.collection} onInspect={setSelected} selected={selected} />
          {page?.has_more ? (
            <Group justify="center" mt="sm">
              <Button
                variant="default"
                size="xs"
                rightSection={<IconArrowRight size={14} />}
                onClick={onNextPage}
                disabled={state.loading || !page.next_cursor}
              >
                Next authoritative page
              </Button>
            </Group>
          ) : null}
        </Box>
        <Paper withBorder radius="md" className="world-inspector">
          <WorldInspector item={selected} />
        </Paper>
      </Box>
    </Stack>
  );
}

function WorldHeader({ data, state, page, onRefresh }) {
  const scope = effectiveScopeLabel(data.effective_filters);
  return (
    <Group justify="space-between" align="flex-start" wrap="nowrap" className="world-header">
      <Group gap="sm" wrap="nowrap" miw={0}>
        <ThemeIcon size={38} radius="md" variant="light" color="teal"><IconWorld size={21} /></ThemeIcon>
        <Box miw={0}>
          <Group gap="xs" wrap="nowrap">
            <Title order={2} size="h3">World</Title>
            <Badge size="xs" variant="outline" color="gray">WORLD SCOPE</Badge>
          </Group>
          <Text size="xs" c="dimmed" lineClamp={1}>{scope}</Text>
        </Box>
      </Group>
      <Group gap="xs" wrap="nowrap">
        <Box ta="right" visibleFrom="sm">
          <Text size="xs" fw={700}>{formatDateTime(data.as_of)}</Text>
          <Text size="10px" c="dimmed">
            {page?.truncated ? `Bounded result · ${page.truncation_reason || "more available"}` : "Complete current page state"}
          </Text>
        </Box>
        {state.loading ? <Loader size={17} /> : null}
        <Tooltip label="Refresh World">
          <ActionIcon variant="default" size={36} onClick={onRefresh} disabled={state.loading} aria-label="Refresh World">
            <IconRefresh size={17} />
          </ActionIcon>
        </Tooltip>
      </Group>
    </Group>
  );
}

function WorldScopeControls({ data, draft, ranking, disabled, onDraft, onRanking, onApply, onReset }) {
  const set = (field, value) => onDraft((current) => ({ ...current, [field]: value }));
  const facets = data.available_facets || {};
  const locationPage = data.pagination?.LOCATION_FACETS;
  const recent = draft.recent_activity || null;
  return (
    <Paper withBorder radius="md" p="xs" className="world-scope-controls">
      <Group gap="xs" align="flex-end" wrap="wrap">
        <Select
          label="Time"
          size="xs"
          value={recent}
          clearable
          placeholder="All time"
          data={[
            { value: "LAST_7_DAYS", label: "Last 7 days" },
            { value: "LAST_30_DAYS", label: "Last 30 days" },
            { value: "LAST_90_DAYS", label: "Last 90 days" },
          ]}
          onChange={(value) => onDraft((current) => ({
            ...current,
            recent_activity: value || "",
            date_from: value ? "" : current.date_from,
            date_to: value ? "" : current.date_to,
          }))}
          className="world-filter-time"
        />
        <TextInput label="From" type="date" size="xs" value={draft.date_from || ""} disabled={Boolean(recent)} onChange={(event) => set("date_from", event.currentTarget.value)} className="world-filter-date" />
        <TextInput label="To" type="date" size="xs" value={draft.date_to || ""} disabled={Boolean(recent)} onChange={(event) => set("date_to", event.currentTarget.value)} className="world-filter-date" />
        <MultiSelect
          label={locationPage?.truncated ? `Location (${locationPage.returned_count} of ${locationPage.total_count})` : "Location"}
          size="xs"
          searchable
          clearable
          value={draft.locations || []}
          data={facetOptions(facets.locations)}
          onChange={(value) => set("locations", value)}
          placeholder="All locations"
          maxDropdownHeight={240}
          className="world-filter-location"
        />
        <Select
          label="Missing location"
          size="xs"
          value={draft.missing_location || "INCLUDE"}
          data={[
            { value: "INCLUDE", label: "Include" },
            { value: "EXCLUDE", label: "Exclude" },
            { value: "ONLY", label: "Only missing" },
          ]}
          onChange={(value) => set("missing_location", value || "INCLUDE")}
          className="world-filter-missing"
        />
        <Select
          label="Order"
          size="xs"
          value={ranking}
          data={[
            { value: "SALIENCE", label: "Scope salience" },
            { value: "RECENT_ACTIVITY", label: "Recent activity" },
            { value: "EVIDENCE_COUNT", label: "Evidence count" },
            { value: "DISPLAY_NAME", label: "Display name" },
          ]}
          onChange={(value) => onRanking(value || "SALIENCE")}
          className="world-filter-ranking"
        />
        <WorldAdvancedFilters draft={draft} facets={facets} set={set} />
        <Button size="xs" onClick={onApply} disabled={disabled}>Apply scope</Button>
        <Button size="xs" variant="subtle" color="gray" onClick={onReset} disabled={disabled}>Reset</Button>
      </Group>
    </Paper>
  );
}

function WorldAdvancedFilters({ draft, facets, set }) {
  return (
    <Popover width={620} position="bottom-end" shadow="md" withinPortal>
      <Popover.Target>
        <Button size="xs" variant="default" leftSection={<IconAdjustments size={15} />}>
          More filters{advancedFilterCount(draft) ? ` · ${advancedFilterCount(draft)}` : ""}
        </Button>
      </Popover.Target>
      <Popover.Dropdown>
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
          <FacetSelect label="Lifecycle" value={draft.lifecycle} data={facets.lifecycle} onChange={(value) => set("lifecycle", value)} />
          <FacetSelect label="Identity state" value={draft.identity_state} data={facets.identity_state} onChange={(value) => set("identity_state", value)} />
          <FacetSelect label="Biometric state" value={draft.biometric_state} data={facets.biometric_state} onChange={(value) => set("biometric_state", value)} />
          <FacetSelect label="Country" value={draft.country} data={facets.country} onChange={(value) => set("country", value)} />
          <FacetSelect label="Rank" value={draft.rank} data={facets.rank} onChange={(value) => set("rank", value)} />
          <FacetSelect label="Priority" value={draft.priority} data={facets.priority} onChange={(value) => set("priority", value)} />
          <FacetSelect label="Evidence type" value={draft.evidence_type} data={facets.evidence_type} onChange={(value) => set("evidence_type", value)} />
          <FacetSelect label="Activity" value={draft.activity} data={facets.activity} onChange={(value) => set("activity", value)} />
          <FacetSelect label="Pattern type" value={draft.pattern_type} data={facets.pattern_type} onChange={(value) => set("pattern_type", value)} />
          <TagsInput label="Relationship type" size="xs" value={draft.relationship_type || []} onChange={(value) => set("relationship_type", value)} placeholder="Backend relationship type" />
          <NumberInput label="Minimum evidence strength" size="xs" min={1} allowDecimal={false} value={draft.min_relationship_strength ?? ""} onChange={(value) => set("min_relationship_strength", value === "" ? null : value)} />
        </SimpleGrid>
        <Text size="10px" c="dimmed" mt="xs">Selections express request intent. SentriFace applies and returns the effective scope.</Text>
      </Popover.Dropdown>
    </Popover>
  );
}

function FacetSelect({ label, value, data, onChange }) {
  return <MultiSelect label={label} size="xs" searchable clearable value={value || []} data={facetOptions(data)} onChange={onChange} />;
}

function WorldTotals({ data }) {
  const totals = data.scope_totals || {};
  const facets = data.available_facets || {};
  const locations = Array.isArray(facets.locations) ? facets.locations : [];
  const missing = locations.find((item) => item.value === "MISSING")?.count;
  const items = [
    { label: "Effective people", value: totals.people ?? 0, icon: IconUsers },
    { label: "Finalized events", value: totals.finalized_events ?? 0, icon: IconCalendarStats },
    { label: "Relationships", value: totals.relationships ?? 0, icon: IconRoute },
    { label: "Evidence clusters", value: totals.clusters ?? 0, icon: IconBinaryTree },
    { label: "Location facets", value: data.pagination?.LOCATION_FACETS?.total_count ?? "—", note: missing ? `${missing} events missing location` : "No missing-location count", icon: IconWorld },
  ];
  return (
    <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }} spacing="xs" className="world-summary-grid">
      {items.map((item) => {
        const SummaryIcon = item.icon;
        return (
        <Paper key={item.label} withBorder radius="md" p="xs" className="world-summary-item">
          <Group gap="xs" wrap="nowrap">
            <ThemeIcon size={28} variant="light" color="teal"><SummaryIcon size={15} /></ThemeIcon>
            <Box miw={0}>
              <Text size="lg" fw={800} lh={1}>{item.value}</Text>
              <Text size="10px" c="dimmed" truncate>{item.note || item.label}</Text>
            </Box>
          </Group>
        </Paper>
      )})}
    </SimpleGrid>
  );
}

function WorldCollection({ data, collection, onInspect, selected }) {
  if (collection === "PEOPLE") return <WorldOverview data={data} onInspect={onInspect} selected={selected} />;
  if (collection === "CLUSTERS") return <ClusterGrid clusters={data.clusters} onInspect={onInspect} selected={selected} />;
  if (collection === "RELATIONSHIPS") return <RelationshipList relationships={data.relationships} onInspect={onInspect} selected={selected} />;
  return <PatternList patterns={data.patterns} onInspect={onInspect} selected={selected} />;
}

function WorldOverview({ data, onInspect, selected }) {
  return (
    <Box className="world-overview-grid">
      <WorldSection title="Ranked people" subtitle="Canonical people ordered by the backend" count={data.pagination.PEOPLE?.total_count}>
        <PeopleList people={data.people} onInspect={onInspect} selected={selected} />
      </WorldSection>
      <Stack gap="sm" className="world-overview-secondary">
        <WorldSection title="Evidence-connected clusters" subtitle="Revision-bound summaries, not affiliations" count={data.pagination.CLUSTERS?.total_count}>
          <ClusterGrid clusters={data.clusters} onInspect={onInspect} selected={selected} compact />
        </WorldSection>
        <WorldSection title="Measured patterns" subtitle="Deterministic facts returned for this scope" count={data.pagination.PATTERNS?.total_count}>
          <PatternList patterns={data.patterns} onInspect={onInspect} selected={selected} compact />
        </WorldSection>
      </Stack>
    </Box>
  );
}

function WorldSection({ title, subtitle, count, children }) {
  return (
    <Paper withBorder radius="md" className="world-section">
      <Group justify="space-between" p="xs" className="world-section-header" wrap="nowrap">
        <Box miw={0}><Text size="sm" fw={800}>{title}</Text><Text size="10px" c="dimmed" truncate>{subtitle}</Text></Box>
        {Number.isFinite(Number(count)) ? <Badge size="xs" variant="light" color="gray">{count}</Badge> : null}
      </Group>
      <Divider />
      <ScrollArea.Autosize mah={500}>{children}</ScrollArea.Autosize>
    </Paper>
  );
}

function PeopleList({ people, onInspect, selected }) {
  if (!people.length) return <WorldEmpty title="No people in this scope" detail="The backend returned a complete empty people page." />;
  return <Stack gap={0}>{people.map((person) => (
    <button key={person.canonical_person_id} type="button" className="world-row world-person-row" data-selected={selected?.type === "person" && selected.value.canonical_person_id === person.canonical_person_id} onClick={() => onInspect({ type: "person", value: person })}>
      <ThemeIcon size={32} radius="xl" color={person.lifecycle_state === "ACTIVE" ? "teal" : "gray"} variant="light"><IconUsers size={16} /></ThemeIcon>
      <span className="world-row-main">
        <Text component="span" size="sm" fw={800}>{person.display_name}</Text>
        <Text component="span" size="10px" c="dimmed">{[person.display?.rank, person.display?.country, humanize(person.biometric_state)].filter(Boolean).join(" · ") || "No profile facets"}</Text>
      </span>
      <span className="world-person-metrics">
        {person.analytics_state === "LOADED" ? (
          <>
            <Metric value={person.activity_summary?.finalized_event_count} label="events" />
            <Metric value={person.intelligence_summary?.relationship_count} label="relations" />
            <Metric value={person.intelligence_summary?.relationship_evidence_count} label="evidence" />
          </>
        ) : <Text size="10px" c="dimmed">Analytics not loaded</Text>}
      </span>
      <Badge size="xs" variant="light" color={lifecycleColor(person.lifecycle_state)}>{person.lifecycle_state}</Badge>
    </button>
  ))}</Stack>;
}

function ClusterGrid({ clusters, onInspect, selected, compact = false }) {
  if (!clusters.length) return <WorldEmpty title="No evidence-connected clusters" detail="No qualifying backend cluster summaries exist in this scope." />;
  return <SimpleGrid cols={compact ? 1 : { base: 1, md: 2 }} spacing={0}>{clusters.map((cluster) => (
    <button key={cluster.cluster_id} type="button" className="world-row world-cluster-row" data-selected={selected?.type === "cluster" && selected.value.cluster_id === cluster.cluster_id} onClick={() => onInspect({ type: "cluster", value: cluster })}>
      <span className="world-row-main">
        <Group gap="xs" wrap="nowrap"><Text component="span" size="sm" fw={800}>Cluster {cluster.ranking?.rank_position || "—"}</Text><Badge size="xs" variant="outline">{cluster.member_count} members</Badge></Group>
        <Text component="span" size="10px" c="dimmed">{cluster.member_preview.map((person) => person.display_name).join(", ") || "Member preview unavailable"}</Text>
        <Text component="span" size="10px">{cluster.evidence_basis?.evidence_count ?? "—"} evidence · {cluster.evidence_basis?.relationship_count ?? "—"} relationships · {cluster.activity_summary?.member_event_contributions ?? "—"} event contributions</Text>
      </span>
      {cluster.member_preview_state?.truncated ? <Badge size="xs" color="yellow" variant="light">Preview limited</Badge> : null}
    </button>
  ))}</SimpleGrid>;
}

function RelationshipList({ relationships, onInspect, selected }) {
  if (!relationships.length) return <WorldEmpty title="No typed relationships" detail="The backend returned no aggregate relationships for this scope." />;
  return <Stack gap={0}>{relationships.map((relationship) => (
    <button key={relationship.relationship_id} type="button" className="world-row world-relationship-row" data-selected={selected?.type === "relationship" && selected.value.relationship_id === relationship.relationship_id} onClick={() => onInspect({ type: "relationship", value: relationship })}>
      <ThemeIcon size={30} variant="light" color="blue"><IconRoute size={15} /></ThemeIcon>
      <span className="world-row-main">
        <Text component="span" size="xs" fw={800}>{shortId(relationship.source_person_id)} <Text span c="dimmed">{relationship.directionality === "UNDIRECTED" ? "↔" : "→"}</Text> {shortId(relationship.target_person_id)}</Text>
        <Text component="span" size="10px" c="dimmed">{relationship.relationship_types.map(humanize).join(", ") || "Typed relationship"} · {humanize(relationship.directionality)}</Text>
      </span>
      <Metric value={relationship.evidence_count} label="evidence" />
      <Text size="10px" c="dimmed">{formatDate(relationship.last_occurrence_at)}</Text>
    </button>
  ))}</Stack>;
}

function PatternList({ patterns, onInspect, selected, compact = false }) {
  if (!patterns.length) return <WorldEmpty title="No measured patterns" detail="SentriFace did not return a supported pattern for this scope." />;
  return <Stack gap={compact ? 0 : "xs"}>{patterns.map((pattern) => (
    <button key={pattern.pattern_id} type="button" className="world-row world-pattern-row" data-selected={selected?.type === "pattern" && selected.value.pattern_id === pattern.pattern_id} onClick={() => onInspect({ type: "pattern", value: pattern })}>
      <ThemeIcon size={30} variant="light" color="yellow"><IconInfoCircle size={16} /></ThemeIcon>
      <span className="world-row-main">
        <Group gap="xs"><Text component="span" size="sm" fw={800}>{humanize(pattern.pattern_type)}</Text><Badge size="xs" variant="light" color="gray">{pattern.status}</Badge></Group>
        <Text component="span" size="10px" c="dimmed">{pattern.explanation.summary}</Text>
      </span>
    </button>
  ))}</Stack>;
}

function WorldInspector({ item }) {
  if (!item) return (
    <Stack gap="xs" p="sm">
      <Text fw={800}>World inspector</Text>
      <Text size="sm" c="dimmed">Select a person, cluster, relationship, or pattern to see the backend explanation and factual factors.</Text>
      <Divider />
      <Text size="xs" c="dimmed">World shows measured scope intelligence. Cluster membership and ranking are revision-bound backend results.</Text>
    </Stack>
  );
  const value = item.value;
  const explanation = value.explanation || {};
  return (
    <Stack gap="sm" p="sm">
      <Box>
        <Text size="xs" c="dimmed" tt="uppercase" fw={700}>{item.type}</Text>
        <Text fw={800}>{itemTitle(item)}</Text>
      </Box>
      <Text size="sm">{explanation.summary || "No explanation summary returned."}</Text>
      <Divider />
      <InspectorRow label="Basis" value={humanize(explanation.basis_type)} />
      {item.type === "person" ? <InspectorRow label="Canonical identity" value={value.canonical_person_id} /> : null}
      {item.type === "person" ? <InspectorRow label="Lifecycle" value={humanize(value.lifecycle_state)} /> : null}
      {item.type === "person" ? <InspectorRow label="Biometric state" value={humanize(value.biometric_state)} /> : null}
      {item.type === "person" ? <InspectorRow label="Allowed actions" value={(value.allowed_actions || []).map(humanize).join(", ") || "None"} /> : null}
      {item.type === "relationship" ? <InspectorRow label="Strength basis" value={humanize(value.strength_basis)} /> : null}
      {item.type === "pattern" ? <InspectorRow label="Measurements" value={formatFactorValue(value.metrics)} /> : null}
      {value.ranking?.rank_position ? <InspectorRow label="Rank" value={value.ranking.rank_position} /> : null}
      {explanation.evidence_count !== null && explanation.evidence_count !== undefined ? <InspectorRow label="Evidence items" value={explanation.evidence_count} /> : null}
      {explanation.first_occurrence_at ? <InspectorRow label="First occurrence" value={formatDate(explanation.first_occurrence_at)} /> : null}
      {explanation.last_occurrence_at ? <InspectorRow label="Last occurrence" value={formatDate(explanation.last_occurrence_at)} /> : null}
      <ExplanationFactors title="Factual factors" factors={explanation.factual_factors} />
      <ExplanationFactors title="Derived calculation" factors={explanation.derived_factors} />
      {explanation.method ? <InspectorRow label="Method" value={humanize(explanation.method)} /> : null}
      {explanation.threshold ? <InspectorRow label="Threshold" value={formatFactorValue(explanation.threshold)} /> : null}
      {explanation.sample ? <InspectorRow label="Sample" value={formatFactorValue(explanation.sample)} /> : null}
      {(explanation.limitations || []).length ? (
        <Box className="world-limitations">
          <Text size="xs" fw={700}>Limitations</Text>
          {(explanation.limitations || []).map((limitation) => <Text key={limitation} size="xs" c="dimmed">{limitation}</Text>)}
        </Box>
      ) : null}
      {item.type === "cluster" ? <Text size="10px" c="dimmed">Cluster drilldown is reserved for P10-F2. Selection currently establishes inspection intent only.</Text> : null}
    </Stack>
  );
}

function ExplanationFactors({ title, factors }) {
  if (!Array.isArray(factors) || !factors.length) return null;
  return <Box><Text size="xs" fw={700} mb={3}>{title}</Text>{factors.map((factor, index) => <InspectorRow key={`${factor.factor}-${index}`} label={humanize(factor.factor)} value={formatFactorValue(factor.value)} />)}</Box>;
}

function InspectorRow({ label, value }) {
  return <Group justify="space-between" align="flex-start" gap="sm" wrap="nowrap" className="world-inspector-row"><Text size="xs" c="dimmed">{label}</Text><Text size="xs" fw={700} ta="right">{value ?? "—"}</Text></Group>;
}

function Metric({ value, label }) {
  return <span className="world-metric"><Text component="span" size="xs" fw={800}>{value ?? "—"}</Text><Text component="span" size="9px" c="dimmed">{label}</Text></span>;
}

function WorldEmpty({ title, detail }) {
  return <Stack align="center" gap={2} p="xl" ta="center"><Text size="sm" fw={700}>{title}</Text><Text size="xs" c="dimmed">{detail}</Text></Stack>;
}

function facetOptions(values) {
  return (Array.isArray(values) ? values : []).map((item) => ({ value: String(item.value), label: `${humanize(item.value)} (${item.count})` }));
}

function advancedFilterCount(filters) {
  return ["lifecycle", "identity_state", "biometric_state", "country", "rank", "priority", "evidence_type", "relationship_type", "activity", "pattern_type"]
    .reduce((count, key) => count + (filters[key]?.length || 0), filters.min_relationship_strength ? 1 : 0);
}

function effectiveScopeLabel(filters = {}) {
  const parts = [];
  if (filters.recent_activity) parts.push(humanize(filters.recent_activity));
  else if (filters.date_from || filters.date_to) parts.push(`${formatDate(filters.date_from) || "Start"} to ${formatDate(filters.date_to) || "Now"}`);
  else parts.push("All recorded time");
  if (filters.locations?.length) parts.push(filters.locations.join(", "));
  parts.push(`${humanize(filters.missing_location || "INCLUDE")} missing locations`);
  const personFilters = [filters.lifecycle, filters.identity_state, filters.biometric_state, filters.country, filters.rank, filters.priority, filters.activity].flat().filter(Boolean);
  if (personFilters.length) parts.push(`${personFilters.length} effective person filter${personFilters.length === 1 ? "" : "s"}`);
  return parts.join(" · ");
}

function itemTitle(item) {
  if (item.type === "person") return item.value.display_name;
  if (item.type === "cluster") return `Cluster ${item.value.ranking?.rank_position || shortId(item.value.cluster_id)}`;
  if (item.type === "relationship") return `${shortId(item.value.source_person_id)} ${item.value.directionality === "UNDIRECTED" ? "↔" : "→"} ${shortId(item.value.target_person_id)}`;
  return humanize(item.value.pattern_type);
}

function formatFactorValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.map((item) => typeof item === "object" ? formatFactorValue(item) : humanize(item)).join(", ") || "—";
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
  return text.length > 16 ? `${text.slice(0, 8)}…${text.slice(-5)}` : text;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function formatDateTime(value) {
  if (!value) return "Snapshot time unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
