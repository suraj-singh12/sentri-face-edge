import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Avatar, Badge, Box, Button, Checkbox, Group, Loader, Modal, NumberInput, Paper, Popover, SegmentedControl, SimpleGrid, Stack, Text } from "@mantine/core";
import { IconChevronDown } from "@tabler/icons-react";
import { useWorldExplore } from "../hooks/useWorldExplore.js";
import { EXPLORE_DEFAULT_FILTERS, validateExploreCriteria } from "../utils/world.js";
import { WorldExploreCanvas } from "./WorldExploreCanvas.jsx";
import { WorldRelationshipProof } from "./WorldRelationshipProof.jsx";
import { WorldView } from "./WorldView.jsx";

const DISCOVERIES = [{ value: "MOST_FREQUENTLY_SEEN", label: "Frequent" }, { value: "MULTIPLE_LOCATIONS", label: "Multiple locations" }, { value: "MOST_RECENTLY_SEEN", label: "Recently seen" }, { value: "CLUSTERS", label: "Clusters" }];
const TYPES = [["CO_OBSERVED", "Co-observed"], ["NOTE_REFERENCE", "Note references"], ["MANUAL_ASSOCIATION", "Manual associations"]];
export function WorldExploreView(props) {
  const model = useWorldExplore(props);
  const { scope, controller, graph, selected, discovery } = model;
  const proofBinding = useMemo(() => scope.data ? { revision: scope.data.graph_revision, asOf: scope.data.as_of, filters: scope.filters } : null, [scope.data?.graph_revision, scope.data?.as_of, scope.filters]);
  const [draft, setDraft] = useState(() => ({ ...EXPLORE_DEFAULT_FILTERS }));
  const [validation, setValidation] = useState(null);
  const [weaker, setWeaker] = useState(true);
  const [tab, setTab] = useState("discover");
  const [proof, setProof] = useState(false);
  const [relationshipProof, setRelationshipProof] = useState(false);
  const [failure, setFailure] = useState(null);
  const hasProofHierarchy = [scope.cluster, scope.person, scope.event, scope.evidence].some((level) => level?.active);
  useEffect(() => { if (proof && !relationshipProof && !hasProofHierarchy) setProof(false); }, [proof, relationshipProof, hasProofHierarchy]);
  useEffect(() => { if (proof) { setProof(false); controller.actions.closeWorldProof(); } }, [scope.data?.graph_revision, scope.data?.as_of]);
  const run = (fn) => (...args) => Promise.resolve(fn(...args)).catch(setFailure);
  const apply = (filters) => {
    const error = validateExploreCriteria(filters); setValidation(error);
    if (!error) { model.resetCanvas(); run(controller.actions.applyWorldScope)(filters, "SALIENCE"); }
  };
  const local = ["MOST_FREQUENTLY_SEEN", "MULTIPLE_LOCATIONS"].includes(model.collection);
  const clusters = model.collection === "CLUSTERS";
  const discoveryIsCurrent = discovery.collection === model.collection && discovery.data?.graph_revision === scope.data?.graph_revision
    && discovery.data?.as_of === scope.data?.as_of && (!local || discovery.period === model.period);
  const data = clusters ? scope.data : discoveryIsCurrent ? discovery.data : null;
  const page = data?.pagination?.[model.collection];
  const items = clusters ? data?.clusters || [] : data?.discoveries || [];
  const choose = (item) => { run(model.focus)(item, clusters ? "cluster" : "person"); setTab("canvas"); };
  const inspect = (item) => { model.setSelected(item); setTab("details"); };
  const showProof = async () => {
    if (!selected) return;
    setRelationshipProof(selected.type === "relationship");
    setProof(true);
    if (selected.type === "relationship") return;
    if (selected.type === "cluster") await controller.actions.openWorldCluster(selected.value);
    else await controller.actions.openWorldPerson(selected.type === "person" ? selected.value : { canonical_person_id: selected.value.source_person_id });
  };
  const openSource = async (eventId) => {
    setProof(true); setRelationshipProof(false);
    const personId = selected.type === "relationship" ? selected.value.source_person_id : selected.value.canonical_person_id;
    await controller.actions.openWorldPerson({ canonical_person_id: personId });
    await controller.actions.openWorldEvent({ event_id: eventId });
  };
  const proofProps = {};
  for (const [prop, action] of Object.entries({ onRefresh: "refreshWorld", onApplyScope: "applyWorldScope", onCollection: "selectWorldCollection", onNextPage: "nextWorldPage", onOpenCluster: "openWorldCluster", onCloseCluster: "closeWorldCluster", onRefreshCluster: "refreshWorldCluster", onClusterCollection: "selectWorldClusterCollection", onNextClusterPage: "nextWorldClusterPage", onOpenPerson: "openWorldPerson", onClosePerson: "closeWorldPerson", onRefreshPerson: "refreshWorldPerson", onPersonCollection: "selectWorldPersonCollection", onNextPersonPage: "nextWorldPersonPage", onOpenEvent: "openWorldEvent", onCloseEvent: "closeWorldEvent", onRefreshEvent: "refreshWorldEvent", onEventCollection: "selectWorldEventCollection", onNextEventPage: "nextWorldEventPage", onOpenEvidence: "openWorldEvidence", onCloseEvidence: "closeWorldEvidence", onRefreshEvidence: "refreshWorldEvidence", onEvidenceCollection: "selectWorldEvidenceCollection", onNextEvidencePage: "nextWorldEvidencePage", onValidateMediaOrigin: "validateWorldMediaOrigin" })) proofProps[prop] = run(controller.actions[action]);
  return <Box className="world-explore">
    <Paper withBorder p="xs" radius="md" className="explore-toolbar"><Group gap="sm" align="end">
      <NumberInput size="xs" label="Min. evidence strength" aria-label="Minimum evidence strength" min={1} allowDecimal={false} value={draft.min_relationship_strength} onChange={(value) => setDraft({ ...draft, min_relationship_strength: value })} w={180} />
      <ExploreEvidenceControl value={draft.evidence_type} onChange={(evidence_type) => setDraft({ ...draft, evidence_type })} />
      <Button size="xs" onClick={() => apply(draft)}>Apply</Button><Button size="xs" variant="default" onClick={() => { setDraft({ ...EXPLORE_DEFAULT_FILTERS }); setWeaker(true); apply({ ...EXPLORE_DEFAULT_FILTERS }); }}>Reset</Button>
      <ExploreWeakerControl value={weaker} onChange={setWeaker} />
      {(scope.loading || model.loading || discovery.loading) && <Loader size={16} aria-label="Processing World" />}
    </Group>{validation && <Text size="xs" c="red" role="alert">{validation}</Text>}</Paper>
    {(scope.error || model.error || failure || discovery.error) && <Alert color="red" title="World request failed" withCloseButton onClose={() => setFailure(null)}>{(scope.error || model.error || failure || discovery.error).message}<Button size="xs" variant="subtle" onClick={run(controller.actions.refreshWorld)}>Reload authoritative World</Button></Alert>}
    <SegmentedControl className="explore-compact-tabs" size="xs" value={tab} onChange={setTab} data={[{ value: "discover", label: "Discover" }, { value: "canvas", label: "Canvas" }, { value: "details", label: "Details" }]} aria-label="Explore panel" />
    <Box className="explore-panels" data-panel={tab}>
      <Paper withBorder radius="md" className="explore-discover"><Text fw={600} size="sm">Discover</Text>
        <ExploreDiscoveryControls collection={model.collection} onCollection={model.setCollection} period={model.period} onPeriod={model.setPeriod} />
        {!local && !clusters && <Text size="xs" c="dimmed" className="explore-discovery-context">Latest observed UTC day: {data?.discovery_context?.latest_observed_day || (discovery.loading ? "Loading…" : "No observations")}</Text>}
        <Box className="explore-records">{items.map((item) => <Button key={item.cluster_id || item.canonical_person_id} variant="subtle" size="xs" className="explore-record" onClick={() => choose(item)}><span>{item.display_name || `Cluster · ${item.member_count} Persons`}</span><Badge size="xs" variant="light">{item.count ?? item.member_count}</Badge></Button>)}{!items.length && !scope.loading && !discovery.loading && <Text size="xs" c="dimmed">No results in this authoritative collection.</Text>}</Box>
        <Group justify="space-between"><Text size="xs" c="dimmed">{page ? `${page.returned_count} of ${page.total_count}` : ""}</Text><Button size="compact-xs" variant="default" disabled={!page?.next_cursor || discovery.loading || scope.loading} onClick={run(clusters ? controller.actions.nextWorldPage : () => model.discover(page.next_cursor))}>Next</Button></Group>
      </Paper>
      <Paper withBorder radius="md" className="explore-graph-panel"><Group justify="space-between" p="xs"><Text size="sm" fw={600}>Canvas</Text><Button size="compact-xs" variant="subtle" onClick={model.resetCanvas}>Reset canvas</Button></Group><WorldExploreCanvas graph={graph} selected={selected} onSelect={inspect} weaker={weaker} /><Group p="xs" gap="xs">{graph.cluster && <Button variant="subtle" size="compact-xs" onClick={() => inspect({ type: "cluster", value: graph.cluster })}>{graph.cluster.member_count} cluster members</Button>}{["MEMBERS", "RELATIONSHIPS"].map((name) => graph.pages?.[name]?.has_more && <Button key={name} size="compact-xs" variant="default" disabled={model.loading} onClick={run(() => model.nextGraphPage(name))}>Next {name.toLowerCase()} page</Button>)}<Text size="xs" c="dimmed">{graph.pages && "Bounded pages; edges require both endpoints on the displayed member page."}</Text></Group></Paper>
      <WorldExploreInspector selected={selected} people={graph.people} onFocus={run(() => model.focus(selected.value))} onProof={run(showProof)} onSource={run(openSource)} />
    </Box>
    <Modal opened={proof} onClose={() => { if (document.querySelector(".world-media-modal")) return; setProof(false); controller.actions.closeWorldProof(); }} title="World supporting proof" size="90%" className="explore-proof" centered><Box h="100%">{relationshipProof && selected?.type === "relationship" && scope.data ? <WorldRelationshipProof relationship={selected.value} binding={proofBinding} apiGet={model.get} onStale={controller.actions.refreshWorld} validateMedia={() => controller.actions.validateWorldRevision(proofBinding.revision)} onOpenSource={openSource} /> : hasProofHierarchy ? <WorldView state={scope} {...proofProps} /> : null}</Box></Modal>
  </Box>;
}

export function ExploreEvidenceControl({ value, onChange }) {
  const [opened, setOpened] = useState(false);
  return <Popover opened={opened} onChange={setOpened} trapFocus returnFocus position="bottom-start" width={250} shadow="md" closeOnEscape>
    <Popover.Target><Button size="xs" variant="default" rightSection={<IconChevronDown size={14} />} aria-label={`Evidence · ${value.length}/3`} aria-expanded={opened} aria-haspopup="dialog" onClick={() => setOpened((current) => !current)}>Evidence · {value.length}/3</Button></Popover.Target>
    <Popover.Dropdown role="dialog" aria-label="Relationship evidence selection">
      <Stack gap="sm"><Text size="xs" fw={600}>Count evidence from</Text>{TYPES.map(([type, label]) => <Checkbox key={type} size="sm" label={label} checked={value.includes(type)} onChange={(event) => onChange(event.currentTarget.checked ? [...value, type] : value.filter((item) => item !== type))} />)}<Text size="xs" c="dimmed">Selected types take effect with Apply.</Text></Stack>
    </Popover.Dropdown>
  </Popover>;
}

export function ExploreWeakerControl({ value, onChange }) {
  return <Button size="xs" className="explore-weaker-control" variant={value ? "light" : "default"} aria-label="Weaker links" aria-pressed={value} onClick={() => onChange(!value)} rightSection={<Badge size="sm" variant={value ? "filled" : "light"} color={value ? "teal" : "gray"}>{value ? "ON" : "OFF"}</Badge>}>Weaker links</Button>;
}

export function ExploreDiscoveryControls({ collection, onCollection, period, onPeriod }) {
  const options = (items) => <Group gap={4} grow wrap="nowrap" className="explore-discovery-options" role="group" aria-label={items[0].value === "MOST_FREQUENTLY_SEEN" ? "Period-based discoveries" : "Independent discoveries"}>{items.map((item) => <Button key={item.value} size="compact-xs" variant={collection === item.value ? "light" : "default"} aria-pressed={collection === item.value} onClick={() => onCollection(item.value)}>{item.label}</Button>)}</Group>;
  return <Stack gap={8} className="explore-discovery-controls">
    <Stack gap={5}><Group justify="space-between" gap={4} wrap="nowrap"><Text size="10px" c="dimmed" fw={600}>Period-based</Text><SegmentedControl size="xs" className="explore-period" value={String(period)} onChange={(value) => onPeriod(Number(value))} data={["7", "30", "90"].map((value) => ({ value, label: `${value}d` }))} aria-label="Discovery Period in days" /></Group>{options(DISCOVERIES.slice(0, 2))}</Stack>
    <Stack gap={5} className="explore-independent-controls"><Text size="10px" c="dimmed" fw={600}>Independent of Period</Text>{options(DISCOVERIES.slice(2))}</Stack>
  </Stack>;
}

const countAvailable = (value) => Number.isSafeInteger(value) && value >= 0;
const humanize = (value) => String(value || "").replaceAll("_", " ").toLowerCase();

export function WorldExploreInspector({ selected, people = [], onFocus, onProof, onSource }) {
  const bodyRef = useRef(null);
  useEffect(() => { if (bodyRef.current) bodyRef.current.scrollTop = 0; }, [selected?.type, selected?.value]);
  const value = selected?.value;
  const type = selected?.type;
  const person = type === "person", cluster = type === "cluster", relationship = type === "relationship";
  const loaded = person && value.analytics_state === "LOADED";
  const nameFor = (id) => people.find((item) => item.canonical_person_id === id)?.display_name || id;
  const title = person ? value.display_name : cluster ? "Evidence-connected cluster" : relationship ? `${nameFor(value.source_person_id)} · ${nameFor(value.target_person_id)}` : "";
  const primary = person ? (loaded ? value.activity_summary?.finalized_event_count : null) : cluster ? value.member_count : value?.selected_evidence_strength;
  const primaryLabel = person ? "Finalized Encounters" : cluster ? "Cluster members" : "Selected evidence strength";
  const caption = person ? (loaded ? "Distinct Encounter appearances in the applied World scope." : "Encounter activity is not loaded. Focus this Person to view it.") : cluster ? "People connected by qualifying evidence under the applied criteria." : "Active records from the selected evidence types under the applied criteria.";
  const secondary = person && loaded ? [["Relationships", value.intelligence_summary?.relationship_count], ["Evidence records", value.intelligence_summary?.relationship_evidence_count]] : cluster ? [["Qualifying relationships", value.evidence_basis?.relationship_count], ["Evidence records", value.evidence_basis?.evidence_count]] : relationship ? [["Supporting Encounters", value.encounter_recurrence?.count]] : [];
  const context = person ? "Encounter activity and relationships are measured separately. Inspect source records and provenance in supporting proof."
    : cluster ? "Membership follows qualifying evidence under the applied criteria. Shared membership does not imply a direct relationship between every pair."
      : value?.qualifies_for_cluster ? "This direct relationship contributes to cluster membership under the applied criteria."
        : "This direct relationship is below threshold and does not contribute to cluster membership.";
  const metrics = secondary.filter(([, count]) => countAvailable(count));
  return <Paper withBorder radius="md" className="explore-inspector" data-inspector-type={type || "empty"}>
    <Text size="sm" fw={600}>Inspector</Text>
    <Box ref={bodyRef} className="explore-inspector-body">{!selected ? <Text size="sm" c="dimmed">Select a Person, cluster or direct relationship.</Text> : <Stack gap="sm">
      <Box className="explore-inspector-subject"><Badge size="xs" variant="light">{person ? "Person" : cluster ? "Cluster" : "Direct relationship"}</Badge><Group wrap="nowrap" gap="sm" mt="xs" align="flex-start">{person && <Avatar color="teal" radius="md" size={38}>{value.display_name?.split(/\s+/u).slice(0, 2).map((part) => part[0]).join("")}</Avatar>}<Text component="h3" className="explore-inspector-title">{title}</Text></Group>{person && <Group gap={5} mt="xs"><Badge size="xs" variant="outline" color="gray">{humanize(value.lifecycle_state)}</Badge><Badge size="xs" variant="outline" color="gray">{humanize(value.identity_state)}</Badge></Group>}</Box>
      <Paper withBorder radius="md" className="explore-inspector-finding"><Text size="xs" fw={600}>{primaryLabel}</Text><Group justify="space-between" gap="xs" mt={4}><Text className="explore-inspector-number">{countAvailable(primary) ? primary : "—"}</Text>{relationship && <Badge size="xs" variant="light" color={value.qualifies_for_cluster ? "teal" : "gray"}>{value.qualifies_for_cluster ? "Qualifies" : "Below threshold"}</Badge>}</Group><Text size="xs" c="dimmed" mt={5}>{caption}</Text></Paper>
      {metrics.length > 0 && <SimpleGrid cols={metrics.length === 1 ? 1 : 2} spacing="xs" className="explore-inspector-metrics">{metrics.map(([label, count]) => <Paper withBorder radius="md" p="xs" key={label}><Text size="xl" fw={700}>{count}</Text><Text size="xs" c="dimmed">{label}</Text></Paper>)}</SimpleGrid>}
      {relationship && <InspectorSection title="Supporting evidence">{Object.entries(value.evidence_type_counts || {}).map(([kind, count]) => <Group key={kind} justify="space-between" gap="xs" wrap="nowrap" className="explore-inspector-row"><Text size="xs">{TYPES.find(([id]) => id === kind)?.[1] || humanize(kind)}</Text><Text size="xs" fw={600}>{count}</Text></Group>)}</InspectorSection>}
      <InspectorSection title="Context"><Text size="xs" c="dimmed">{context}</Text>{relationship && <>{value.first_occurrence_at && <InspectorFact label="First recorded" value={value.first_occurrence_at.slice(0, 10)} />}{value.last_occurrence_at && <InspectorFact label="Last recorded" value={value.last_occurrence_at.slice(0, 10)} />}</>}{person && [value.display?.rank, value.display?.country].filter(Boolean).length > 0 && <Text size="xs" mt={6}>{[value.display?.rank, value.display?.country].filter(Boolean).join(" · ")}</Text>}</InspectorSection>
      {cluster && value.member_preview?.length > 0 && <InspectorSection title="Member preview"><Text size="xs">{value.member_preview.map((member) => member.display_name).join(", ")}</Text>{value.member_preview_state?.has_more && <Text size="xs" c="dimmed">More members in supporting proof.</Text>}</InspectorSection>}
      {selected.discovery?.locations?.length > 0 && <InspectorSection title="Recorded locations"><Group gap={4}>{selected.discovery.locations.map((place) => <Badge key={place} size="xs" variant="outline">{place}</Badge>)}</Group></InspectorSection>}
      {selected.discovery?.supporting_encounters?.length > 0 && <InspectorSection title="Source Encounters"><Stack gap={4}>{selected.discovery.supporting_encounters.map((event) => <Button key={event.event_id} variant="subtle" size="compact-xs" className="explore-inspector-source" onClick={() => onSource(event.event_id)}>{event.occurred_at.slice(0, 10)} · {event.location || "Unknown location"}</Button>)}</Stack></InspectorSection>}
    </Stack>}</Box>
    {selected && <Stack gap={6} className="explore-inspector-actions" data-person={person}>{person && <Button variant="default" size="xs" disabled={!value.allowed_actions?.includes("OPEN")} onClick={onFocus}>Focus Person</Button>}<Button size="sm" onClick={onProof}>Inspect supporting proof</Button></Stack>}
  </Paper>;
}

function InspectorSection({ title, children }) {
  return <Box className="explore-inspector-section"><Text size="10px" c="dimmed" fw={600} mb={5}>{title}</Text>{children}</Box>;
}
function InspectorFact({ label, value }) {
  return <Group justify="space-between" gap="xs" className="explore-inspector-row"><Text size="xs" c="dimmed">{label}</Text><Text size="xs" fw={600}>{value}</Text></Group>;
}
