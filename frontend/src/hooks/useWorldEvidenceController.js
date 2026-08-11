import { useCallback, useEffect, useRef, useState } from "react";

import {
  buildWorldEvidenceQuery,
  isInvalidWorldEvidenceError,
  requireWorldEvidenceContract,
} from "../utils/world.js";

function emptyEvidenceCollection() {
  return { data: null, loading: false, error: null, pageNumber: 1 };
}

export function emptyWorldEvidence(values = {}) {
  return {
    active: false,
    evidenceId: null,
    collection: "EVIDENCE",
    detail: null,
    binding: null,
    origin: null,
    notice: null,
    collections: {
      EVIDENCE: emptyEvidenceCollection(),
      MEDIA: emptyEvidenceCollection(),
    },
    ...values,
  };
}

export function useWorldEvidenceController({ apiGet, getEvent, onStale }) {
  const [evidence, setEvidence] = useState(() => emptyWorldEvidence());
  const evidenceRef = useRef(evidence);
  const requestsRef = useRef({
    EVIDENCE: { generation: 0, abort: null },
    MEDIA: { generation: 0, abort: null },
  });
  evidenceRef.current = evidence;

  const resetWorldEvidence = useCallback(({ notice = null } = {}) => {
    for (const request of Object.values(requestsRef.current)) request.abort?.abort();
    requestsRef.current = {
      EVIDENCE: { generation: requestsRef.current.EVIDENCE.generation + 1, abort: null },
      MEDIA: { generation: requestsRef.current.MEDIA.generation + 1, abort: null },
    };
    const next = emptyWorldEvidence({ notice });
    evidenceRef.current = next;
    setEvidence(next);
  }, []);

  const loadWorldEvidenceCollection = useCallback(async ({
    collection,
    cursor = null,
    pageNumber = 1,
    preserve = false,
  } = {}) => {
    const current = evidenceRef.current;
    const nextCollection = collection || current.collection || "EVIDENCE";
    if (!current.active || !current.evidenceId || !current.binding || !current.collections[nextCollection]) return null;
    const previousRequest = requestsRef.current[nextCollection];
    previousRequest.abort?.abort();
    const abort = new AbortController();
    const generation = previousRequest.generation + 1;
    requestsRef.current[nextCollection] = { generation, abort };
    setEvidence((value) => ({
      ...value,
      collection: nextCollection,
      collections: {
        ...value.collections,
        [nextCollection]: {
          ...value.collections[nextCollection],
          data: preserve ? value.collections[nextCollection].data : null,
          loading: true,
          error: null,
          pageNumber,
        },
      },
    }));
    try {
      const payload = requireWorldEvidenceContract(await apiGet(buildWorldEvidenceQuery({
        evidenceId: current.evidenceId,
        collection: nextCollection,
        filters: current.binding.filters,
        cursor,
        revision: current.binding.revision,
        asOf: current.binding.asOf,
      }), { dedupe: false, signal: abort.signal, silent: true, timeoutMs: 120_000 }), {
        evidenceId: current.evidenceId,
        collection: nextCollection,
        revision: current.binding.revision,
      });
      if (requestsRef.current[nextCollection].generation === generation) {
        setEvidence((value) => ({
          ...value,
          detail: payload.evidence[0],
          collection: nextCollection,
          collections: {
            ...value.collections,
            [nextCollection]: { data: payload, loading: false, error: null, pageNumber },
          },
        }));
      }
      return payload;
    } catch (error) {
      if (error?.name === "AbortError") return null;
      if (requestsRef.current[nextCollection].generation !== generation) return null;
      if (isInvalidWorldEvidenceError(error)) {
        resetWorldEvidence({ notice: "World changed, so the previous evidence view was closed and the authoritative scope was reloaded." });
        return onStale?.();
      }
      setEvidence((value) => ({
        ...value,
        collections: {
          ...value.collections,
          [nextCollection]: { ...value.collections[nextCollection], loading: false, error },
        },
      }));
      throw error;
    }
  }, [apiGet, onStale, resetWorldEvidence]);

  const openWorldEvidence = useCallback((evidenceSummary) => {
    const event = getEvent();
    if (!event?.active || !evidenceSummary?.evidence_id || !event.binding) return null;
    for (const request of Object.values(requestsRef.current)) request.abort?.abort();
    const next = emptyWorldEvidence({
      active: true,
      evidenceId: evidenceSummary.evidence_id,
      binding: event.binding,
      origin: {
        level: "EVENT",
        eventId: event.eventId,
        collection: event.collection,
        pageNumber: event.collections[event.collection]?.pageNumber || 1,
      },
    });
    evidenceRef.current = next;
    setEvidence(next);
    return loadWorldEvidenceCollection({ collection: "EVIDENCE" });
  }, [getEvent, loadWorldEvidenceCollection]);

  const closeWorldEvidence = useCallback(() => {
    for (const request of Object.values(requestsRef.current)) request.abort?.abort();
    setEvidence((value) => ({ ...value, active: false, notice: null }));
  }, []);

  const selectWorldEvidenceCollection = useCallback((collection) => {
    const current = evidenceRef.current;
    if (!current.active || !current.collections[collection]) return null;
    setEvidence((value) => ({ ...value, collection }));
    if (current.collections[collection].data) return current.collections[collection].data;
    return loadWorldEvidenceCollection({ collection, pageNumber: 1, preserve: false });
  }, [loadWorldEvidenceCollection]);

  const nextWorldEvidencePage = useCallback(() => {
    const current = evidenceRef.current;
    const collectionState = current.collections[current.collection];
    const page = collectionState?.data?.pagination?.[current.collection];
    if (!page?.has_more || !page.next_cursor) return null;
    return loadWorldEvidenceCollection({
      collection: current.collection,
      cursor: page.next_cursor,
      pageNumber: collectionState.pageNumber + 1,
      preserve: false,
    });
  }, [loadWorldEvidenceCollection]);

  const refreshWorldEvidence = useCallback(() => loadWorldEvidenceCollection({
    collection: evidenceRef.current.collection,
    pageNumber: 1,
    preserve: true,
  }), [loadWorldEvidenceCollection]);

  useEffect(() => () => {
    for (const request of Object.values(requestsRef.current)) request.abort?.abort();
  }, []);

  return {
    state: evidence,
    actions: {
      openWorldEvidence,
      closeWorldEvidence,
      selectWorldEvidenceCollection,
      nextWorldEvidencePage,
      refreshWorldEvidence,
      resetWorldEvidence,
    },
  };
}
