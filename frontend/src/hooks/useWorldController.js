import { useCallback, useEffect, useRef, useState } from "react";

import {
  buildWorldScopeQuery,
  EMPTY_WORLD_FILTERS,
  filtersFromEffective,
  invalidateWorldSnapshot,
  isStaleWorldError,
  requireWorldScopeContract,
  worldEntryMode,
} from "../utils/world.js";

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

export function useWorldController({ activeView, apiGet }) {
  const [world, setWorld] = useState(INITIAL_WORLD_STATE);
  const requestRef = useRef({ generation: 0, abort: null });
  const worldRef = useRef(world);
  const previousActiveViewRef = useRef(activeView);
  worldRef.current = world;

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
      }), { dedupe: false, signal: abort.signal, silent: true, timeoutMs: 120_000 }));
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

  const applyWorldScope = useCallback((filters, ranking) => loadWorld({
    collection: worldRef.current.collection,
    filters,
    ranking,
    pageNumber: 1,
    preserve: true,
  }), [loadWorld]);

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

  const invalidateWorld = useCallback((mutation = null) => {
    requestRef.current.abort?.abort();
    requestRef.current = { generation: requestRef.current.generation + 1, abort: null };
    setWorld((current) => invalidateWorldSnapshot(current, mutation));
  }, []);

  useEffect(() => () => requestRef.current.abort?.abort(), []);

  useEffect(() => {
    const previousView = previousActiveViewRef.current;
    previousActiveViewRef.current = activeView;
    if (activeView !== "world") return;
    const cached = worldRef.current;
    if (previousView === "world" && cached.data) return;
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
        loadWorld({ preserve: false }).catch((error) => console.error(error));
      } else {
        setWorld((current) => ({ ...current, loading: false, error: null }));
      }
    }).catch((error) => {
      if (requestRef.current.generation === generation) {
        setWorld((current) => ({ ...current, loading: false, error }));
      }
    });
  }, [activeView, apiGet, loadWorld]);

  return {
    state: { world },
    actions: {
      loadWorld,
      refreshWorld,
      applyWorldScope,
      selectWorldCollection,
      nextWorldPage,
      invalidateWorld,
    },
  };
}
