import { useCallback, useEffect, useRef, useState } from "react";

import {
  buildWorldClusterQuery,
  buildWorldEventQuery,
  buildWorldPersonQuery,
  buildWorldScopeQuery,
  EMPTY_WORLD_FILTERS,
  filtersFromEffective,
  invalidateWorldSnapshot,
  isInvalidWorldClusterError,
  isInvalidWorldEventError,
  isInvalidWorldPersonError,
  isStaleWorldError,
  requireWorldClusterContract,
  requireWorldEventContract,
  requireWorldPersonContract,
  requireWorldScopeContract,
  worldEntryMode,
} from "../utils/world.js";
import { useWorldEvidenceController } from "./useWorldEvidenceController.js";

const INITIAL_WORLD_STATE = {
  data: null,
  collection: "PEOPLE",
  filters: { ...EMPTY_WORLD_FILTERS },
  ranking: "SALIENCE",
  invalidated: false,
  pendingRevision: null,
  loading: false,
  error: null,
  pageNumber: 1,
};

function emptyClusterCollection() {
  return { data: null, loading: false, error: null, pageNumber: 1 };
}

function emptyWorldCluster(values = {}) {
  return {
    active: false,
    clusterId: null,
    collection: "MEMBERS",
    summary: null,
    binding: null,
    notice: null,
    collections: {
      MEMBERS: emptyClusterCollection(),
      RELATIONSHIPS: emptyClusterCollection(),
    },
    ...values,
  };
}

function emptyPersonCollection() {
  return { data: null, loading: false, error: null, pageNumber: 1 };
}

function emptyWorldPerson(values = {}) {
  return {
    active: false,
    personId: null,
    collection: "RELATIONSHIPS",
    root: null,
    binding: null,
    origin: null,
    notice: null,
    collections: {
      RELATIONSHIPS: emptyPersonCollection(),
      EVENTS: emptyPersonCollection(),
    },
    ...values,
  };
}

function emptyEventCollection() {
  return { data: null, loading: false, error: null, pageNumber: 1 };
}

function emptyWorldEvent(values = {}) {
  return {
    active: false,
    eventId: null,
    collection: "PARTICIPANTS",
    summary: null,
    binding: null,
    origin: null,
    notice: null,
    collections: {
      PARTICIPANTS: emptyEventCollection(),
      PROVENANCE: emptyEventCollection(),
      EVIDENCE: emptyEventCollection(),
      MEDIA: emptyEventCollection(),
    },
    ...values,
  };
}

function invalidateCollectionRequests(requestsRef) {
  const next = {};
  for (const [collection, request] of Object.entries(requestsRef.current)) {
    request.abort?.abort();
    next[collection] = { generation: request.generation + 1, abort: null };
  }
  requestsRef.current = next;
}

export function useWorldController({ activeView, apiGet, initialFilters = EMPTY_WORLD_FILTERS, initialCollection = "PEOPLE" }) {
  const [world, setWorld] = useState(() => ({ ...INITIAL_WORLD_STATE, filters: { ...initialFilters }, collection: initialCollection }));
  const [worldCluster, setWorldCluster] = useState(() => emptyWorldCluster());
  const [worldPerson, setWorldPerson] = useState(() => emptyWorldPerson());
  const [worldEvent, setWorldEvent] = useState(() => emptyWorldEvent());
  const requestRef = useRef({ generation: 0, abort: null });
  const clusterRequestsRef = useRef({
    MEMBERS: { generation: 0, abort: null },
    RELATIONSHIPS: { generation: 0, abort: null },
  });
  const personRequestsRef = useRef({
    RELATIONSHIPS: { generation: 0, abort: null },
    EVENTS: { generation: 0, abort: null },
  });
  const eventRequestsRef = useRef({
    PARTICIPANTS: { generation: 0, abort: null },
    PROVENANCE: { generation: 0, abort: null },
    EVIDENCE: { generation: 0, abort: null },
    MEDIA: { generation: 0, abort: null },
  });
  const retainedRevisionRequestRef = useRef({ generation: 0, abort: null });
  const worldRef = useRef(world);
  const worldClusterRef = useRef(worldCluster);
  const worldPersonRef = useRef(worldPerson);
  const worldEventRef = useRef(worldEvent);
  const previousActiveViewRef = useRef(activeView);
  worldRef.current = world;
  worldClusterRef.current = worldCluster;
  worldPersonRef.current = worldPerson;
  worldEventRef.current = worldEvent;

  const loadWorld = useCallback(async ({
    collection,
    filters,
    ranking,
    cursor = null,
    revision = null,
    asOf = null,
    pageNumber = 1,
    preserve = false,
  } = {}) => {
    const current = worldRef.current;
    const nextCollection = collection || current.collection || "PEOPLE";
    const nextFilters = filters || current.filters;
    const nextRanking = ranking || current.ranking;
    retainedRevisionRequestRef.current.abort?.abort();
    retainedRevisionRequestRef.current = {
      generation: retainedRevisionRequestRef.current.generation + 1,
      abort: null,
    };
    requestRef.current.abort?.abort();
    const abort = new AbortController();
    const generation = requestRef.current.generation + 1;
    requestRef.current = { generation, abort };
    setWorld((value) => ({
      ...value,
      data: preserve ? value.data : null,
      collection: nextCollection,
      filters: nextFilters,
      ranking: nextRanking,
      invalidated: false,
      pendingRevision: null,
      loading: true,
      error: null,
      pageNumber,
    }));
    try {
      const payload = requireWorldScopeContract(await apiGet(buildWorldScopeQuery({
        collection: nextCollection,
        filters: nextFilters,
        ranking: nextRanking,
        cursor,
        revision,
        asOf,
      }), { dedupe: false, signal: abort.signal, silent: true, timeoutMs: 120_000 }), {
        collection: nextCollection,
      });
      if (requestRef.current.generation === generation) {
        setWorld({
          data: payload,
          collection: nextCollection,
          filters: filtersFromEffective(payload.effective_filters),
          ranking: payload.ranking,
          invalidated: false,
          pendingRevision: null,
          loading: false,
          error: null,
          pageNumber,
        });
      }
      return payload;
    } catch (error) {
      if (error?.name === "AbortError") return null;
      if (requestRef.current.generation !== generation) return null;
      if ((cursor || revision) && isStaleWorldError(error)) {
        return loadWorld({
          collection: nextCollection,
          filters: nextFilters,
          ranking: nextRanking,
          pageNumber: 1,
          preserve: false,
        });
      }
      setWorld((value) => ({ ...value, loading: false, error }));
      throw error;
    }
  }, [apiGet]);

  const refreshWorld = useCallback(() => loadWorld({ preserve: true }), [loadWorld]);

  const recoverStaleEvidence = useCallback(() => {
    for (const request of Object.values(eventRequestsRef.current)) request.abort?.abort();
    for (const request of Object.values(personRequestsRef.current)) request.abort?.abort();
    for (const request of Object.values(clusterRequestsRef.current)) request.abort?.abort();
    setWorldEvent(emptyWorldEvent());
    setWorldPerson(emptyWorldPerson());
    setWorldCluster(emptyWorldCluster());
    return loadWorld({
      collection: worldRef.current.collection,
      filters: worldRef.current.filters,
      ranking: worldRef.current.ranking,
      pageNumber: 1,
      preserve: false,
    });
  }, [loadWorld]);

  const getWorldEvent = useCallback(() => worldEventRef.current, []);
  const evidenceController = useWorldEvidenceController({ apiGet, getEvent: getWorldEvent, onStale: recoverStaleEvidence });
  const worldEvidence = evidenceController.state;
  const {
    openWorldEvidence: requestWorldEvidence,
    closeWorldEvidence: dismissWorldEvidence,
    selectWorldEvidenceCollection,
    nextWorldEvidencePage,
    refreshWorldEvidence,
    resetWorldEvidence,
  } = evidenceController.actions;

  const discardRetainedWorldHierarchy = useCallback(({ notice = null } = {}) => {
    retainedRevisionRequestRef.current.abort?.abort();
    retainedRevisionRequestRef.current = {
      generation: retainedRevisionRequestRef.current.generation + 1,
      abort: null,
    };
    invalidateCollectionRequests(clusterRequestsRef);
    invalidateCollectionRequests(personRequestsRef);
    invalidateCollectionRequests(eventRequestsRef);
    const nextCluster = emptyWorldCluster({ notice });
    const nextPerson = emptyWorldPerson();
    const nextEvent = emptyWorldEvent();
    worldClusterRef.current = nextCluster;
    worldPersonRef.current = nextPerson;
    worldEventRef.current = nextEvent;
    setWorldCluster(nextCluster);
    setWorldPerson(nextPerson);
    setWorldEvent(nextEvent);
    resetWorldEvidence();
  }, [resetWorldEvidence]);

  const reloadAuthoritativeWorld = useCallback((notice = null) => {
    const current = worldRef.current;
    discardRetainedWorldHierarchy({ notice });
    return loadWorld({
      collection: current.collection,
      filters: current.filters,
      ranking: current.ranking,
      pageNumber: 1,
      preserve: false,
    });
  }, [discardRetainedWorldHierarchy, loadWorld]);

  const validateRetainedWorldRevision = useCallback(async (retainedRevision, onCurrent) => {
    const scopeRevision = worldRef.current.data?.graph_revision;
    if (!retainedRevision || !scopeRevision || retainedRevision !== scopeRevision) {
      await reloadAuthoritativeWorld("World changed, so the retained navigation hierarchy was discarded.");
      return false;
    }
    retainedRevisionRequestRef.current.abort?.abort();
    const abort = new AbortController();
    const generation = retainedRevisionRequestRef.current.generation + 1;
    retainedRevisionRequestRef.current = { generation, abort };
    try {
      const revision = await apiGet(
        `/api/graph-revision?current_revision=${encodeURIComponent(retainedRevision)}`,
        { dedupe: false, signal: abort.signal, silent: true },
      );
      if (retainedRevisionRequestRef.current.generation !== generation) return false;
      if (revision.stale || revision.graph_revision !== retainedRevision) {
        await reloadAuthoritativeWorld("World changed, so the retained navigation hierarchy was discarded.");
        return false;
      }
      return onCurrent ? onCurrent() !== false : true;
    } catch (error) {
      if (error?.name === "AbortError" || retainedRevisionRequestRef.current.generation !== generation) return false;
      setWorld((current) => ({ ...current, error }));
      return false;
    }
  }, [apiGet, reloadAuthoritativeWorld]);

  const openWorldEvidence = useCallback((evidenceSummary) => {
    retainedRevisionRequestRef.current.abort?.abort();
    retainedRevisionRequestRef.current = {
      generation: retainedRevisionRequestRef.current.generation + 1,
      abort: null,
    };
    return requestWorldEvidence(evidenceSummary);
  }, [requestWorldEvidence]);

  const closeWorldEvidence = useCallback(() => {
    const evidenceId = worldEvidence.evidenceId;
    const retainedRevision = worldEvidence.binding?.revision;
    return validateRetainedWorldRevision(retainedRevision, () => dismissWorldEvidence({
      evidenceId,
      revision: retainedRevision,
    }));
  }, [dismissWorldEvidence, validateRetainedWorldRevision, worldEvidence.binding?.revision, worldEvidence.evidenceId]);

  const validateWorldMediaOrigin = useCallback(() => {
    const retainedRevision = worldEvidence.active
      ? worldEvidence.binding?.revision
      : worldEventRef.current.binding?.revision;
    return validateRetainedWorldRevision(retainedRevision);
  }, [validateRetainedWorldRevision, worldEvidence.active, worldEvidence.binding?.revision]);

  const applyWorldScope = useCallback((filters, ranking) => {
    for (const request of Object.values(clusterRequestsRef.current)) request.abort?.abort();
    for (const request of Object.values(personRequestsRef.current)) request.abort?.abort();
    for (const request of Object.values(eventRequestsRef.current)) request.abort?.abort();
    setWorldCluster(emptyWorldCluster());
    setWorldPerson(emptyWorldPerson());
    setWorldEvent(emptyWorldEvent());
    resetWorldEvidence();
    return loadWorld({
      collection: worldRef.current.collection,
      filters,
      ranking,
      pageNumber: 1,
      preserve: true,
    });
  }, [loadWorld, resetWorldEvidence]);

  const selectWorldCollection = useCallback((collection) => {
    if (collection === worldRef.current.collection && worldRef.current.data) return null;
    return loadWorld({ collection, pageNumber: 1, preserve: false });
  }, [loadWorld]);

  const nextWorldPage = useCallback(() => {
    const current = worldRef.current;
    const page = current.data?.pagination?.[current.collection];
    if (!page?.has_more || !page.next_cursor) return null;
    return loadWorld({
      cursor: page.next_cursor,
      revision: current.data.graph_revision,
      asOf: current.data.as_of,
      pageNumber: current.pageNumber + 1,
      preserve: false,
    });
  }, [loadWorld]);

  const recoverStaleCluster = useCallback(async (message = "The selected cluster is no longer valid in the current World snapshot.") => {
    for (const request of Object.values(clusterRequestsRef.current)) request.abort?.abort();
    clusterRequestsRef.current = {
      MEMBERS: { generation: clusterRequestsRef.current.MEMBERS.generation + 1, abort: null },
      RELATIONSHIPS: { generation: clusterRequestsRef.current.RELATIONSHIPS.generation + 1, abort: null },
    };
    setWorldCluster(emptyWorldCluster({ notice: message }));
    setWorldPerson(emptyWorldPerson());
    setWorldEvent(emptyWorldEvent());
    resetWorldEvidence();
    return loadWorld({
      collection: worldRef.current.collection,
      filters: worldRef.current.filters,
      ranking: worldRef.current.ranking,
      pageNumber: 1,
      preserve: false,
    });
  }, [loadWorld, resetWorldEvidence]);

  const loadWorldClusterCollection = useCallback(async ({
    collection,
    cursor = null,
    pageNumber = 1,
    preserve = false,
  } = {}) => {
    const cluster = worldClusterRef.current;
    const nextCollection = collection || cluster.collection || "MEMBERS";
    if (!cluster.active || !cluster.clusterId || !cluster.binding) return null;
    const previousRequest = clusterRequestsRef.current[nextCollection];
    previousRequest.abort?.abort();
    const abort = new AbortController();
    const generation = previousRequest.generation + 1;
    clusterRequestsRef.current[nextCollection] = { generation, abort };
    setWorldCluster((current) => ({
      ...current,
      collection: nextCollection,
      collections: {
        ...current.collections,
        [nextCollection]: {
          ...current.collections[nextCollection],
          data: preserve ? current.collections[nextCollection].data : null,
          loading: true,
          error: null,
          pageNumber,
        },
      },
    }));
    try {
      const payload = requireWorldClusterContract(await apiGet(buildWorldClusterQuery({
        clusterId: cluster.clusterId,
        collection: nextCollection,
        filters: cluster.binding.filters,
        ranking: cluster.binding.ranking,
        cursor,
        revision: cluster.binding.revision,
        asOf: cluster.binding.asOf,
      }), { dedupe: false, signal: abort.signal, silent: true, timeoutMs: 120_000 }), {
        clusterId: cluster.clusterId,
        collection: nextCollection,
        revision: cluster.binding.revision,
      });
      if (clusterRequestsRef.current[nextCollection].generation === generation) {
        setWorldCluster((current) => ({
          ...current,
          summary: current.summary || payload.clusters[0],
          collection: nextCollection,
          collections: {
            ...current.collections,
            [nextCollection]: { data: payload, loading: false, error: null, pageNumber },
          },
        }));
      }
      return payload;
    } catch (error) {
      if (error?.name === "AbortError") return null;
      if (clusterRequestsRef.current[nextCollection].generation !== generation) return null;
      if (isInvalidWorldClusterError(error)) {
        return recoverStaleCluster("World changed, so the previous revision-bound cluster was closed and the authoritative scope was reloaded.");
      }
      setWorldCluster((current) => ({
        ...current,
        collections: {
          ...current.collections,
          [nextCollection]: { ...current.collections[nextCollection], loading: false, error },
        },
      }));
      throw error;
    }
  }, [apiGet, recoverStaleCluster]);

  const openWorldCluster = useCallback((clusterSummary) => {
    const scope = worldRef.current.data;
    if (!clusterSummary?.cluster_id || !scope?.graph_revision || !scope?.as_of) return null;
    if (clusterSummary.graph_revision !== scope.graph_revision) {
      return recoverStaleCluster();
    }
    retainedRevisionRequestRef.current.abort?.abort();
    retainedRevisionRequestRef.current = {
      generation: retainedRevisionRequestRef.current.generation + 1,
      abort: null,
    };
    for (const request of Object.values(clusterRequestsRef.current)) request.abort?.abort();
    for (const request of Object.values(personRequestsRef.current)) request.abort?.abort();
    for (const request of Object.values(eventRequestsRef.current)) request.abort?.abort();
    setWorldPerson(emptyWorldPerson());
    setWorldEvent(emptyWorldEvent());
    resetWorldEvidence();
    const nextCluster = emptyWorldCluster({
      active: true,
      clusterId: clusterSummary.cluster_id,
      binding: {
        revision: scope.graph_revision,
        asOf: scope.as_of,
        filters: filtersFromEffective(scope.effective_filters),
        ranking: scope.ranking,
      },
    });
    worldClusterRef.current = nextCluster;
    setWorldCluster(nextCluster);
    return loadWorldClusterCollection({ collection: "MEMBERS" });
  }, [loadWorldClusterCollection, recoverStaleCluster, resetWorldEvidence]);

  const closeWorldCluster = useCallback(() => {
    const clusterId = worldClusterRef.current.clusterId;
    const retainedRevision = worldClusterRef.current.binding?.revision;
    return validateRetainedWorldRevision(retainedRevision, () => {
      const current = worldClusterRef.current;
      if (!current.active || current.clusterId !== clusterId || current.binding?.revision !== retainedRevision) return false;
      invalidateCollectionRequests(clusterRequestsRef);
      const next = { ...current, active: false, notice: null };
      worldClusterRef.current = next;
      setWorldCluster(next);
      return true;
    });
  }, [validateRetainedWorldRevision]);

  const selectWorldClusterCollection = useCallback((collection) => {
    const cluster = worldClusterRef.current;
    if (!cluster.active || !cluster.collections[collection]) return null;
    setWorldCluster((current) => ({ ...current, collection }));
    if (cluster.collections[collection].data) return cluster.collections[collection].data;
    return loadWorldClusterCollection({ collection, pageNumber: 1, preserve: false });
  }, [loadWorldClusterCollection]);

  const nextWorldClusterPage = useCallback(() => {
    const cluster = worldClusterRef.current;
    const state = cluster.collections[cluster.collection];
    const page = state?.data?.pagination?.[cluster.collection];
    if (!page?.has_more || !page.next_cursor) return null;
    return loadWorldClusterCollection({
      collection: cluster.collection,
      cursor: page.next_cursor,
      pageNumber: state.pageNumber + 1,
      preserve: false,
    });
  }, [loadWorldClusterCollection]);

  const refreshWorldCluster = useCallback(() => loadWorldClusterCollection({
    collection: worldClusterRef.current.collection,
    pageNumber: 1,
    preserve: true,
  }), [loadWorldClusterCollection]);

  const recoverStalePerson = useCallback(async (message = "World changed, so the previous person view was closed and the authoritative scope was reloaded.") => {
    for (const request of Object.values(personRequestsRef.current)) request.abort?.abort();
    personRequestsRef.current = {
      RELATIONSHIPS: { generation: personRequestsRef.current.RELATIONSHIPS.generation + 1, abort: null },
      EVENTS: { generation: personRequestsRef.current.EVENTS.generation + 1, abort: null },
    };
    for (const request of Object.values(clusterRequestsRef.current)) request.abort?.abort();
    setWorldPerson(emptyWorldPerson({ notice: message }));
    setWorldEvent(emptyWorldEvent());
    resetWorldEvidence();
    setWorldCluster(emptyWorldCluster());
    return loadWorld({
      collection: worldRef.current.collection,
      filters: worldRef.current.filters,
      ranking: worldRef.current.ranking,
      pageNumber: 1,
      preserve: false,
    });
  }, [loadWorld, resetWorldEvidence]);

  const loadWorldPersonCollection = useCallback(async ({
    collection,
    cursor = null,
    pageNumber = 1,
    preserve = false,
  } = {}) => {
    const person = worldPersonRef.current;
    const nextCollection = collection || person.collection || "RELATIONSHIPS";
    if (!person.active || !person.personId || !person.binding) return null;
    const previousRequest = personRequestsRef.current[nextCollection];
    previousRequest.abort?.abort();
    const abort = new AbortController();
    const generation = previousRequest.generation + 1;
    personRequestsRef.current[nextCollection] = { generation, abort };
    setWorldPerson((current) => ({
      ...current,
      collection: nextCollection,
      collections: {
        ...current.collections,
        [nextCollection]: {
          ...current.collections[nextCollection],
          data: preserve ? current.collections[nextCollection].data : null,
          loading: true,
          error: null,
          pageNumber,
        },
      },
    }));
    try {
      const payload = requireWorldPersonContract(await apiGet(buildWorldPersonQuery({
        personId: person.personId,
        collection: nextCollection,
        filters: person.binding.filters,
        ranking: person.binding.ranking,
        cursor,
        revision: person.binding.revision,
        asOf: person.binding.asOf,
      }), { dedupe: false, signal: abort.signal, silent: true, timeoutMs: 120_000 }), {
        personId: person.personId,
        collection: nextCollection,
        revision: person.binding.revision,
      });
      if (personRequestsRef.current[nextCollection].generation === generation) {
        setWorldPerson((current) => ({
          ...current,
          root: payload.people[0],
          collection: nextCollection,
          collections: {
            ...current.collections,
            [nextCollection]: { data: payload, loading: false, error: null, pageNumber },
          },
        }));
      }
      return payload;
    } catch (error) {
      if (error?.name === "AbortError") return null;
      if (personRequestsRef.current[nextCollection].generation !== generation) return null;
      if (isInvalidWorldPersonError(error)) return recoverStalePerson();
      setWorldPerson((current) => ({
        ...current,
        collections: {
          ...current.collections,
          [nextCollection]: { ...current.collections[nextCollection], loading: false, error },
        },
      }));
      throw error;
    }
  }, [apiGet, recoverStalePerson]);

  const openWorldPerson = useCallback((personSummary) => {
    const scope = worldRef.current.data;
    const cluster = worldClusterRef.current;
    const binding = cluster.active ? cluster.binding : (
      scope?.graph_revision && scope?.as_of ? {
        revision: scope.graph_revision,
        asOf: scope.as_of,
        filters: filtersFromEffective(scope.effective_filters),
        ranking: scope.ranking,
      } : null
    );
    if (!personSummary?.canonical_person_id || !binding) return null;
    retainedRevisionRequestRef.current.abort?.abort();
    retainedRevisionRequestRef.current = {
      generation: retainedRevisionRequestRef.current.generation + 1,
      abort: null,
    };
    for (const request of Object.values(personRequestsRef.current)) request.abort?.abort();
    for (const request of Object.values(eventRequestsRef.current)) request.abort?.abort();
    setWorldEvent(emptyWorldEvent());
    resetWorldEvidence();
    const nextPerson = emptyWorldPerson({
      active: true,
      personId: personSummary.canonical_person_id,
      binding,
      origin: cluster.active
        ? { level: "CLUSTER", clusterId: cluster.clusterId }
        : { level: "WORLD_SCOPE" },
    });
    worldPersonRef.current = nextPerson;
    setWorldPerson(nextPerson);
    return loadWorldPersonCollection({ collection: "RELATIONSHIPS" });
  }, [loadWorldPersonCollection, resetWorldEvidence]);

  const closeWorldPerson = useCallback(() => {
    const personId = worldPersonRef.current.personId;
    const retainedRevision = worldPersonRef.current.binding?.revision;
    return validateRetainedWorldRevision(retainedRevision, () => {
      const current = worldPersonRef.current;
      if (!current.active || current.personId !== personId || current.binding?.revision !== retainedRevision) return false;
      invalidateCollectionRequests(personRequestsRef);
      invalidateCollectionRequests(eventRequestsRef);
      const nextEvent = emptyWorldEvent();
      const nextPerson = { ...current, active: false, notice: null };
      worldEventRef.current = nextEvent;
      worldPersonRef.current = nextPerson;
      setWorldEvent(nextEvent);
      resetWorldEvidence();
      setWorldPerson(nextPerson);
      return true;
    });
  }, [resetWorldEvidence, validateRetainedWorldRevision]);

  const selectWorldPersonCollection = useCallback((collection) => {
    const person = worldPersonRef.current;
    if (!person.active || !person.collections[collection]) return null;
    setWorldPerson((current) => ({ ...current, collection }));
    if (person.collections[collection].data) return person.collections[collection].data;
    return loadWorldPersonCollection({ collection, pageNumber: 1, preserve: false });
  }, [loadWorldPersonCollection]);

  const nextWorldPersonPage = useCallback(() => {
    const person = worldPersonRef.current;
    const state = person.collections[person.collection];
    const page = state?.data?.pagination?.[person.collection];
    if (!page?.has_more || !page.next_cursor) return null;
    return loadWorldPersonCollection({
      collection: person.collection,
      cursor: page.next_cursor,
      pageNumber: state.pageNumber + 1,
      preserve: false,
    });
  }, [loadWorldPersonCollection]);

  const refreshWorldPerson = useCallback(() => loadWorldPersonCollection({
    collection: worldPersonRef.current.collection,
    pageNumber: 1,
    preserve: true,
  }), [loadWorldPersonCollection]);

  const recoverStaleEvent = useCallback(async (message = "World changed, so the previous event view was closed and the authoritative scope was reloaded.") => {
    for (const request of Object.values(eventRequestsRef.current)) request.abort?.abort();
    eventRequestsRef.current = {
      PARTICIPANTS: { generation: eventRequestsRef.current.PARTICIPANTS.generation + 1, abort: null },
      PROVENANCE: { generation: eventRequestsRef.current.PROVENANCE.generation + 1, abort: null },
      EVIDENCE: { generation: eventRequestsRef.current.EVIDENCE.generation + 1, abort: null },
      MEDIA: { generation: eventRequestsRef.current.MEDIA.generation + 1, abort: null },
    };
    for (const request of Object.values(personRequestsRef.current)) request.abort?.abort();
    for (const request of Object.values(clusterRequestsRef.current)) request.abort?.abort();
    setWorldEvent(emptyWorldEvent({ notice: message }));
    setWorldPerson(emptyWorldPerson());
    setWorldCluster(emptyWorldCluster());
    resetWorldEvidence();
    return loadWorld({
      collection: worldRef.current.collection,
      filters: worldRef.current.filters,
      ranking: worldRef.current.ranking,
      pageNumber: 1,
      preserve: false,
    });
  }, [loadWorld, resetWorldEvidence]);

  const loadWorldEventCollection = useCallback(async ({
    collection,
    cursor = null,
    pageNumber = 1,
    preserve = false,
  } = {}) => {
    const event = worldEventRef.current;
    const nextCollection = collection || event.collection || "PARTICIPANTS";
    if (!event.active || !event.eventId || !event.binding) return null;
    const previousRequest = eventRequestsRef.current[nextCollection];
    previousRequest.abort?.abort();
    const abort = new AbortController();
    const generation = previousRequest.generation + 1;
    eventRequestsRef.current[nextCollection] = { generation, abort };
    setWorldEvent((current) => ({
      ...current,
      collection: nextCollection,
      collections: {
        ...current.collections,
        [nextCollection]: {
          ...current.collections[nextCollection],
          data: preserve ? current.collections[nextCollection].data : null,
          loading: true,
          error: null,
          pageNumber,
        },
      },
    }));
    try {
      const payload = requireWorldEventContract(await apiGet(buildWorldEventQuery({
        eventId: event.eventId,
        collection: nextCollection,
        filters: event.binding.filters,
        cursor,
        revision: event.binding.revision,
        asOf: event.binding.asOf,
      }), { dedupe: false, signal: abort.signal, silent: true, timeoutMs: 120_000 }), {
        eventId: event.eventId,
        collection: nextCollection,
        revision: event.binding.revision,
      });
      if (eventRequestsRef.current[nextCollection].generation === generation) {
        setWorldEvent((current) => ({
          ...current,
          summary: payload.events[0],
          collection: nextCollection,
          collections: {
            ...current.collections,
            [nextCollection]: { data: payload, loading: false, error: null, pageNumber },
          },
        }));
      }
      return payload;
    } catch (error) {
      if (error?.name === "AbortError") return null;
      if (eventRequestsRef.current[nextCollection].generation !== generation) return null;
      if (isInvalidWorldEventError(error)) return recoverStaleEvent();
      setWorldEvent((current) => ({
        ...current,
        collections: {
          ...current.collections,
          [nextCollection]: { ...current.collections[nextCollection], loading: false, error },
        },
      }));
      throw error;
    }
  }, [apiGet, recoverStaleEvent]);

  const openWorldEvent = useCallback((eventSummary) => {
    const person = worldPersonRef.current;
    if (!person.active || !eventSummary?.event_id || !person.binding) return null;
    retainedRevisionRequestRef.current.abort?.abort();
    retainedRevisionRequestRef.current = {
      generation: retainedRevisionRequestRef.current.generation + 1,
      abort: null,
    };
    for (const request of Object.values(eventRequestsRef.current)) request.abort?.abort();
    resetWorldEvidence();
    const nextEvent = emptyWorldEvent({
      active: true,
      eventId: eventSummary.event_id,
      binding: person.binding,
      origin: {
        level: "PERSON",
        personId: person.personId,
        collection: person.collection,
        pageNumber: person.collections[person.collection]?.pageNumber || 1,
      },
    });
    worldEventRef.current = nextEvent;
    setWorldEvent(nextEvent);
    return loadWorldEventCollection({ collection: "PARTICIPANTS" });
  }, [loadWorldEventCollection, resetWorldEvidence]);

  const closeWorldEvent = useCallback(() => {
    const eventId = worldEventRef.current.eventId;
    const retainedRevision = worldEventRef.current.binding?.revision;
    return validateRetainedWorldRevision(retainedRevision, () => {
      const current = worldEventRef.current;
      if (!current.active || current.eventId !== eventId || current.binding?.revision !== retainedRevision) return false;
      invalidateCollectionRequests(eventRequestsRef);
      const next = { ...current, active: false, notice: null };
      worldEventRef.current = next;
      setWorldEvent(next);
      resetWorldEvidence();
      return true;
    });
  }, [resetWorldEvidence, validateRetainedWorldRevision]);

  const selectWorldEventCollection = useCallback((collection) => {
    const event = worldEventRef.current;
    if (!event.active || !event.collections[collection]) return null;
    setWorldEvent((current) => ({ ...current, collection }));
    if (event.collections[collection].data) return event.collections[collection].data;
    return loadWorldEventCollection({ collection, pageNumber: 1, preserve: false });
  }, [loadWorldEventCollection]);

  const nextWorldEventPage = useCallback(() => {
    const event = worldEventRef.current;
    const state = event.collections[event.collection];
    const page = state?.data?.pagination?.[event.collection];
    if (!page?.has_more || !page.next_cursor) return null;
    return loadWorldEventCollection({
      collection: event.collection,
      cursor: page.next_cursor,
      pageNumber: state.pageNumber + 1,
      preserve: false,
    });
  }, [loadWorldEventCollection]);

  const refreshWorldEvent = useCallback(() => loadWorldEventCollection({
    collection: worldEventRef.current.collection,
    pageNumber: 1,
    preserve: true,
  }), [loadWorldEventCollection]);

  const invalidateWorld = useCallback((mutation = null) => {
    requestRef.current.abort?.abort();
    requestRef.current = { generation: requestRef.current.generation + 1, abort: null };
    setWorld((current) => invalidateWorldSnapshot(current, mutation));
    discardRetainedWorldHierarchy({ notice: "World changed, so the previous revision-bound hierarchy was closed." });
  }, [discardRetainedWorldHierarchy]);

  useEffect(() => () => {
    requestRef.current.abort?.abort();
    retainedRevisionRequestRef.current.abort?.abort();
    for (const request of Object.values(clusterRequestsRef.current)) request.abort?.abort();
    for (const request of Object.values(personRequestsRef.current)) request.abort?.abort();
    for (const request of Object.values(eventRequestsRef.current)) request.abort?.abort();
  }, []);

  useEffect(() => {
    const previousView = previousActiveViewRef.current;
    previousActiveViewRef.current = activeView;
    if (activeView !== "world") return;
    const cached = worldRef.current;
    if (previousView === "world" && cached.data && !cached.invalidated) return;
    if (worldEntryMode(cached) === "LOAD") {
      loadWorld({ preserve: Boolean(cached.data) }).catch((error) => console.error(error));
      return;
    }
    const generation = requestRef.current.generation + 1;
    requestRef.current = { generation, abort: null };
    setWorld((current) => ({ ...current, loading: true, error: null }));
    apiGet(
      `/api/graph-revision?current_revision=${encodeURIComponent(cached.data.graph_revision)}`,
      { dedupe: false, silent: true },
    ).then((revision) => {
      if (requestRef.current.generation !== generation) return;
      if (revision.stale || revision.graph_revision !== cached.data.graph_revision) {
        discardRetainedWorldHierarchy();
        loadWorld({ preserve: false }).catch((error) => console.error(error));
      } else {
        setWorld((current) => ({ ...current, loading: false, error: null }));
      }
    }).catch((error) => {
      if (requestRef.current.generation === generation) {
        setWorld((current) => ({ ...current, loading: false, error }));
      }
    });
  }, [activeView, apiGet, discardRetainedWorldHierarchy, loadWorld]);

  return {
    state: { world: { ...world, cluster: worldCluster, person: worldPerson, event: worldEvent, evidence: worldEvidence } },
    actions: {
      loadWorld,
      refreshWorld,
      applyWorldScope,
      selectWorldCollection,
      nextWorldPage,
      openWorldCluster,
      closeWorldCluster,
      selectWorldClusterCollection,
      nextWorldClusterPage,
      refreshWorldCluster,
      openWorldPerson,
      closeWorldPerson,
      selectWorldPersonCollection,
      nextWorldPersonPage,
      refreshWorldPerson,
      openWorldEvent,
      closeWorldEvent,
      selectWorldEventCollection,
      nextWorldEventPage,
      refreshWorldEvent,
      openWorldEvidence,
      closeWorldEvidence,
      selectWorldEvidenceCollection,
      nextWorldEvidencePage,
      refreshWorldEvidence,
      validateWorldMediaOrigin,
      invalidateWorld,
    },
  };
}
