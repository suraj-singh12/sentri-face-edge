import { useCallback, useEffect, useRef, useState } from "react";
import { useWorldController } from "./useWorldController.js";
import { buildWorldScopeQuery, buildWorldPersonQuery, buildWorldClusterQuery, requireWorldScopeContract, requireWorldPersonContract, requireWorldClusterContract, requireWorldDiscoveryContract, EXPLORE_DEFAULT_FILTERS, exploreRequest, requireExploreResponse, isStaleWorldError } from "../utils/world.js";

export function useWorldExplore({ apiGet, active, mutationRevision }) {
  const get = useCallback(async (path, options) => requireExploreResponse(await apiGet(exploreRequest(path), options), path), [apiGet]);
  const controller = useWorldController({ apiGet: get, activeView: active ? "world" : null, initialFilters: EXPLORE_DEFAULT_FILTERS, initialCollection: "CLUSTERS" });
  const scope = controller.state.world;
  const [period, setPeriod] = useState(30);
  const [collection, setCollection] = useState("MOST_FREQUENTLY_SEEN");
  const [discovery, setDiscovery] = useState({});
  const [graph, setGraph] = useState({ people: [], relationships: [], cluster: null });
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const requests = useRef({ discovery: null, graph: null });
  const generation = useRef(0);
  const scopeRef = useRef(scope);
  scopeRef.current = scope;
  const snapshot = scope.data;

  const cancel = useCallback(() => {
    generation.current += 1;
    Object.values(requests.current).forEach((request) => request?.abort());
  }, []);
  useEffect(() => () => cancel(), [cancel]);
  useEffect(() => {
    cancel(); setGraph({ people: [], relationships: [], cluster: null }); setSelected(null); setDiscovery({}); setLoading(false);
  }, [snapshot?.graph_revision, snapshot?.as_of, cancel]);
  useEffect(() => { if (mutationRevision) controller.actions.invalidateWorld({ graph_revision: mutationRevision }); }, [mutationRevision]);

  const recover = useCallback(async (failure) => {
    setError(failure);
    if (isStaleWorldError(failure)) {
      cancel(); setGraph({ people: [], relationships: [], cluster: null }); setSelected(null); setDiscovery({});
      await controller.actions.refreshWorld();
    }
  }, [cancel, controller.actions.refreshWorld]);

  const discoveryPeriod = ["MOST_FREQUENTLY_SEEN", "MULTIPLE_LOCATIONS"].includes(collection) ? period : null;
  const discover = useCallback(async (cursor = null) => {
    const current = scopeRef.current;
    if (!current.data || collection === "CLUSTERS") return;
    requests.current.discovery?.abort();
    const abort = new AbortController(); requests.current.discovery = abort;
    const binding = { revision: current.data.graph_revision, asOf: current.data.as_of, filters: current.filters };
    setDiscovery({ loading: true, error: null });
    try {
      const payload = requireWorldDiscoveryContract(await get(buildWorldScopeQuery({ ...binding, collection, cursor, discoveryPeriodDays: discoveryPeriod }), { signal: abort.signal, silent: true, dedupe: false, timeoutMs: 120_000 }), { collection, revision: binding.revision, period: discoveryPeriod });
      if (!abort.signal.aborted) setDiscovery({ data: payload, loading: false, collection, period: discoveryPeriod });
    } catch (failure) {
      if (abort.signal.aborted) return;
      setDiscovery({ loading: false, error: failure }); await recover(failure);
    }
  }, [get, collection, discoveryPeriod, recover]);
  // Period only schedules reads for the two local discoveries; graph and clusters retain their snapshot.
  useEffect(() => {
    if (!active || !snapshot || scope.loading) return;
    if (collection === "CLUSTERS") return;
    if (collection === "MOST_RECENTLY_SEEN" && discovery.collection === collection && discovery.data) return;
    discover();
    return () => requests.current.discovery?.abort();
  }, [active, snapshot?.graph_revision, snapshot?.as_of, scope.loading, collection, discoveryPeriod, discover]);

  const focus = useCallback(async (item, kind = "person") => {
    const current = scopeRef.current;
    if (!current.data || current.loading) return;
    requests.current.graph?.abort();
    const abort = new AbortController(); requests.current.graph = abort;
    const epoch = generation.current;
    const binding = { revision: current.data.graph_revision, asOf: current.data.as_of, filters: current.filters };
    const options = { signal: abort.signal, dedupe: false, silent: true, timeoutMs: 120_000 };
    setLoading(true); setError(null);
    try {
      let person = null;
      let clusterId = item.cluster_id;
      if (kind === "person") {
        const payload = requireWorldPersonContract(await get(buildWorldPersonQuery({ ...binding, personId: item.canonical_person_id }), options), { personId: item.canonical_person_id, revision: binding.revision, collection: "RELATIONSHIPS" });
        person = payload.people[0]; clusterId = person.cluster_memberships[0]?.cluster_id;
      }
      let next = { people: person ? [person] : [], relationships: [], cluster: null };
      if (clusterId) {
        const results = await Promise.all(["MEMBERS", "RELATIONSHIPS"].map(async (page) => requireWorldClusterContract(await get(buildWorldClusterQuery({ ...binding, clusterId, collection: page }), options), { clusterId, revision: binding.revision, collection: page })));
        const [members, relationships] = results;
        const people = [...members.people];
        if (person && !people.some((p) => p.canonical_person_id === person.canonical_person_id)) people.push(person);
        next = { people, relationships: relationships.relationships, cluster: members.clusters[0], pages: { MEMBERS: members.pagination.MEMBERS, RELATIONSHIPS: relationships.pagination.RELATIONSHIPS }, binding };
      }
      if (!abort.signal.aborted && epoch === generation.current) { setGraph(next); setSelected({ type: person ? "person" : "cluster", value: person || next.cluster, discovery: kind === "person" ? item : null }); setLoading(false); }
    } catch (failure) {
      if (abort.signal.aborted || epoch !== generation.current) return;
      setLoading(false); await recover(failure);
    }
  }, [get, recover]);

  const nextGraphPage = useCallback(async (collection) => {
    const page = graph.pages?.[collection];
    if (!page?.next_cursor || !graph.cluster) return;
    requests.current.graph?.abort(); const abort = new AbortController(); requests.current.graph = abort;
    setLoading(true);
    try {
      const payload = requireWorldClusterContract(await get(buildWorldClusterQuery({ ...graph.binding, clusterId: graph.cluster.cluster_id, collection, cursor: page.next_cursor }), { signal: abort.signal, silent: true, dedupe: false, timeoutMs: 120_000 }), { clusterId: graph.cluster.cluster_id, revision: graph.binding.revision, collection });
      if (!abort.signal.aborted) {
        setGraph((value) => ({ ...value, [collection === "MEMBERS" ? "people" : "relationships"]: collection === "MEMBERS" ? payload.people : payload.relationships, pages: { ...value.pages, [collection]: payload.pagination[collection] } }));
        setSelected(null); setLoading(false);
      }
    } catch (failure) { if (!abort.signal.aborted) { setLoading(false); await recover(failure); } }
  }, [get, graph, recover]);
  return { controller, get, scope, period, setPeriod, collection, setCollection, discovery, discover, graph, selected, setSelected, focus, loading, error, nextGraphPage, resetCanvas: () => { requests.current.graph?.abort(); setGraph({ people: [], relationships: [], cluster: null }); setSelected(null); setLoading(false); } };
}
