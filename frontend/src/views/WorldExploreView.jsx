import { useEffect, useMemo, useState } from "react";
import { Alert, Badge, Box, Button, Checkbox, Group, Loader, Modal, NumberInput, Paper, SegmentedControl, Stack, Text } from "@mantine/core";
import { useWorldExplore } from "../hooks/useWorldExplore.js";
import { EXPLORE_DEFAULT_FILTERS, validateExploreCriteria } from "../utils/world.js";
import { WorldExploreCanvas } from "./WorldExploreCanvas.jsx";
import { WorldRelationshipProof } from "./WorldRelationshipProof.jsx";
import { WorldView } from "./WorldView.jsx";

const DISCOVERIES = [{ value: "MOST_FREQUENTLY_SEEN", label: "Most frequently seen" }, { value: "MULTIPLE_LOCATIONS", label: "Multiple locations" }, { value: "MOST_RECENTLY_SEEN", label: "Most recently seen" }, { value: "CLUSTERS", label: "Clusters" }];
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
  useEffect(() => setProof(false), [scope.data?.graph_revision, scope.data?.as_of]);
  const run = (fn) => (...args) => Promise.resolve(fn(...args)).catch(setFailure);
  const apply = (filters) => {
    const error = validateExploreCriteria(filters); setValidation(error);
    if (!error) { model.resetCanvas(); run(controller.actions.applyWorldScope)(filters, "SALIENCE"); }
  };
  const local = ["MOST_FREQUENTLY_SEEN", "MULTIPLE_LOCATIONS"].includes(model.collection);
  const clusters = model.collection === "CLUSTERS";
  const data = clusters ? scope.data : discovery.data;
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
      <Group gap="sm">{TYPES.map(([type, label]) => <Checkbox size="xs" key={type} label={label} checked={draft.evidence_type.includes(type)} onChange={(event) => setDraft({ ...draft, evidence_type: event.currentTarget.checked ? [...draft.evidence_type, type] : draft.evidence_type.filter((item) => item !== type) })} />)}</Group>
      <Button size="xs" onClick={() => apply(draft)}>Apply</Button><Button size="xs" variant="default" onClick={() => { setDraft({ ...EXPLORE_DEFAULT_FILTERS }); setWeaker(true); apply({ ...EXPLORE_DEFAULT_FILTERS }); }}>Reset</Button>
      <Checkbox size="xs" label="Show weaker connections" checked={weaker} onChange={(event) => setWeaker(event.currentTarget.checked)} />
      {(scope.loading || model.loading || discovery.loading) && <Loader size={16} aria-label="Processing World" />}
    </Group>{validation && <Text size="xs" c="red" role="alert">{validation}</Text>}</Paper>
    {(scope.error || model.error || failure || discovery.error) && <Alert color="red" title="World request failed" withCloseButton onClose={() => setFailure(null)}>{(scope.error || model.error || failure || discovery.error).message}<Button size="xs" variant="subtle" onClick={run(controller.actions.refreshWorld)}>Reload authoritative World</Button></Alert>}
    <SegmentedControl className="explore-compact-tabs" size="xs" value={tab} onChange={setTab} data={[{ value: "discover", label: "Discover" }, { value: "canvas", label: "Canvas" }, { value: "details", label: "Details" }]} aria-label="Explore panel" />
    <Box className="explore-panels" data-panel={tab}>
      <Paper withBorder radius="md" className="explore-discover"><Text fw={600} size="sm">Discover</Text>
        <Text size="xs" c="dimmed" mt="sm">Period-based discoveries</Text><SegmentedControl size="xs" value={String(model.period)} onChange={(value) => model.setPeriod(Number(value))} data={["7", "30", "90"].map((value) => ({ value, label: `${value} days` }))} aria-label="Discovery Period" />
        {DISCOVERIES.slice(0, 2).map((item) => <Button key={item.value} size="xs" variant={model.collection === item.value ? "light" : "subtle"} onClick={() => model.setCollection(item.value)}>{item.label}</Button>)}
        <Text size="xs" c="dimmed" mt="sm">Independent of Period</Text>{DISCOVERIES.slice(2).map((item) => <Button key={item.value} size="xs" variant={model.collection === item.value ? "light" : "subtle"} onClick={() => model.setCollection(item.value)}>{item.label}</Button>)}
        <Text size="xs" c="dimmed" mt="xs">{local ? `Within ${model.period} days` : clusters ? "Qualifying evidence components" : `Latest observed UTC day: ${data?.discovery_context?.latest_observed_day || "No observations"}`}</Text>
        <Box className="explore-records">{items.map((item) => <Button key={item.cluster_id || item.canonical_person_id} variant="subtle" size="xs" className="explore-record" onClick={() => choose(item)}><span>{item.display_name || `Cluster · ${item.member_count} Persons`}</span><Badge size="xs" variant="light">{item.count ?? item.member_count}</Badge></Button>)}{!items.length && !scope.loading && !discovery.loading && <Text size="xs" c="dimmed">No results in this authoritative collection.</Text>}</Box>
        <Group justify="space-between"><Text size="xs" c="dimmed">{page ? `${page.returned_count} of ${page.total_count}` : ""}</Text><Button size="compact-xs" variant="default" disabled={!page?.next_cursor || discovery.loading || scope.loading} onClick={run(clusters ? controller.actions.nextWorldPage : () => model.discover(page.next_cursor))}>Next</Button></Group>
      </Paper>
      <Paper withBorder radius="md" className="explore-graph-panel"><Group justify="space-between" p="xs"><Text size="sm" fw={600}>Canvas</Text><Button size="compact-xs" variant="subtle" onClick={model.resetCanvas}>Reset canvas</Button></Group><WorldExploreCanvas graph={graph} selected={selected} onSelect={inspect} weaker={weaker} /><Group p="xs" gap="xs">{graph.cluster && <Button variant="subtle" size="compact-xs" onClick={() => inspect({ type: "cluster", value: graph.cluster })}>{graph.cluster.member_count} cluster members</Button>}{["MEMBERS", "RELATIONSHIPS"].map((name) => graph.pages?.[name]?.has_more && <Button key={name} size="compact-xs" variant="default" disabled={model.loading} onClick={run(() => model.nextGraphPage(name))}>Next {name.toLowerCase()} page</Button>)}<Text size="xs" c="dimmed">{graph.pages && "Bounded pages; edges require both endpoints on the displayed member page."}</Text></Group></Paper>
      <Paper withBorder radius="md" className="explore-inspector"><Text size="sm" fw={600}>Inspector</Text><Box className="explore-inspector-body">{!selected ? <Text size="sm" c="dimmed">Select a Person, cluster or direct relationship.</Text> : <Stack gap="xs"><Badge variant="light" size="xs">{selected.type}</Badge><Text fw={600} size="sm">{selected.value.display_name || (selected.type === "cluster" ? `${selected.value.member_count} Persons` : "Direct relationship")}</Text><Text size="xs">{selected.value.explanation?.summary || "Authoritative World selection"}</Text>{selected.type === "relationship" && <><Text size="sm">Strength {selected.value.selected_evidence_strength}</Text><Text size="xs" c="dimmed">{selected.value.qualifies_for_cluster ? "Qualifies for cluster membership" : "Below threshold · does not affect membership"}</Text>{Object.entries(selected.value.evidence_type_counts).map(([type, count]) => <Text size="xs" key={type}>{TYPES.find(([id]) => id === type)?.[1] || type}: {count}</Text>)}<Text size="xs">{selected.value.encounter_recurrence?.count ?? 0} distinct supporting Encounters</Text></>}{selected.type === "person" && <><Text size="xs">{selected.value.lifecycle_state} · {selected.value.identity_state}</Text><Button variant="light" size="xs" disabled={!selected.value.allowed_actions?.includes("OPEN")} onClick={run(() => model.focus(selected.value))}>Focus Person</Button></>}{selected.discovery?.locations?.length > 0 && <Group gap={4}>{selected.discovery.locations.map((place) => <Badge key={place} size="xs" variant="outline">{place}</Badge>)}</Group>}{selected.discovery?.supporting_encounters?.map((event) => <Button key={event.event_id} variant="subtle" size="compact-xs" onClick={run(() => openSource(event.event_id))}>{event.occurred_at.slice(0, 10)} · {event.location || "Unknown location"}</Button>)}<Button size="xs" onClick={run(showProof)}>Show more · supporting proof</Button></Stack>}</Box></Paper>
    </Box>
    <Modal opened={proof} onClose={() => setProof(false)} title="World supporting proof" size="90%" className="explore-proof" centered><Box h="100%">{relationshipProof && selected?.type === "relationship" && scope.data ? <WorldRelationshipProof relationship={selected.value} binding={proofBinding} apiGet={model.get} onStale={controller.actions.refreshWorld} validateMedia={controller.actions.validateWorldMediaOrigin} onOpenSource={openSource} /> : hasProofHierarchy ? <WorldView state={scope} {...proofProps} /> : null}</Box></Modal>
  </Box>;
}
