import { useCallback, useEffect, useRef, useState } from "react";

import { requirePersonContract } from "../utils.js";
import {
  graphNodeNavigation,
  graphRevisionChanged,
  invalidatePersonGraphSnapshot,
  personGraphEntryMode,
  requirePersonGraphContract,
} from "../utils/personGraph.js";

function operationId() {
  return globalThis.crypto?.randomUUID?.()
    || "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
      const value = Math.floor(Math.random() * 16);
      return (character === "x" ? value : (value & 0x3) | 0x8).toString(16);
    });
}

export function usePeopleController({
  activeView,
  apiGet,
  apiPost,
  loadPeople,
  loadDeletedFaces,
  showToast,
  onWorldMutation,
}) {
  const [peopleGallery, setPeopleGallery] = useState(null);
  const [peopleGalleryImage, setPeopleGalleryImage] = useState(null);
  const [personGraph, setPersonGraph] = useState({
    personId: null,
    data: null,
    active: false,
    invalidated: false,
    pendingRevision: null,
    loading: false,
    error: null,
  });
  const graphRequestRef = useRef(0);
  const personGraphRef = useRef(personGraph);
  const previousActiveViewRef = useRef(activeView);
  personGraphRef.current = personGraph;

  const loadPerson = async (personId, archived = false) => {
    const payload = await apiGet(
      `/api/person?person_id=${encodeURIComponent(personId)}&view=${archived ? "raw" : "effective"}${archived ? "&include_archived=1" : ""}`,
      { dedupe: false },
    );
    requirePersonContract(payload.person);
    return payload;
  };

  const peopleOpen = async (personId, options = {}) => {
    if (!personId) return;
    setPeopleGallery(await loadPerson(personId, Boolean(options.archived)));
    setPeopleGalleryImage(null);
  };

  const refreshPeopleProfile = async (personId) => {
    const payload = await loadPerson(personId);
    setPeopleGallery((current) => current?.person?.person_id === personId ? payload : current);
    setPeopleGalleryImage(null);
    return payload;
  };

  const loadPersonGraph = useCallback(async (personId, { preserve = false } = {}) => {
    if (!personId) return null;
    const requestId = graphRequestRef.current + 1;
    graphRequestRef.current = requestId;
    setPersonGraph((current) => ({
      personId,
      data: preserve && current.personId === personId ? current.data : null,
      active: true,
      invalidated: false,
      pendingRevision: null,
      loading: true,
      error: null,
    }));
    try {
      const payload = requirePersonGraphContract(await apiGet(
        `/api/person-graph?person_id=${encodeURIComponent(personId)}`,
        { dedupe: false },
      ));
      if (graphRequestRef.current === requestId) {
        setPersonGraph({
          personId,
          data: payload,
          active: true,
          invalidated: false,
          pendingRevision: null,
          loading: false,
          error: null,
        });
      }
      return payload;
    } catch (error) {
      if (graphRequestRef.current === requestId) {
        setPersonGraph((current) => ({ ...current, loading: false, error }));
      }
      throw error;
    }
  }, [apiGet]);

  const closePersonGraph = useCallback(() => {
    graphRequestRef.current += 1;
    setPersonGraph((current) => ({ ...current, active: false, loading: false, error: null }));
  }, []);

  const invalidatePersonGraph = useCallback((mutation = null) => {
    graphRequestRef.current += 1;
    setPersonGraph((current) => invalidatePersonGraphSnapshot(current, mutation));
    onWorldMutation?.(mutation);
  }, [onWorldMutation]);

  const openPersonGraph = useCallback(async (personId) => {
    if (!personId) return null;
    const cached = personGraphRef.current;
    if (personGraphEntryMode(cached, personId) === "LOAD") {
      return loadPersonGraph(personId);
    }

    const requestId = graphRequestRef.current + 1;
    graphRequestRef.current = requestId;
    setPersonGraph((current) => ({ ...current, active: true, loading: true, error: null }));
    try {
      const revision = await apiGet(
        `/api/graph-revision?current_revision=${encodeURIComponent(cached.data.graph_revision)}`,
        { dedupe: false, silent: true },
      );
      if (graphRequestRef.current !== requestId) return null;
      if (
        revision.stale
        || graphRevisionChanged(cached.data.graph_revision, revision.graph_revision)
      ) {
        return loadPersonGraph(personId);
      }
      setPersonGraph((current) => ({
        ...current,
        active: true,
        invalidated: false,
        pendingRevision: null,
        loading: false,
        error: null,
      }));
      return cached.data;
    } catch (error) {
      if (graphRequestRef.current === requestId) {
        setPersonGraph((current) => ({ ...current, loading: false, error }));
      }
      throw error;
    }
  }, [apiGet, loadPersonGraph]);

  const refreshPersonGraph = useCallback(async () => {
    if (!personGraph.personId) return null;
    return loadPersonGraph(personGraph.personId, { preserve: true });
  }, [loadPersonGraph, personGraph.personId]);

  const openPersonGraphNode = useCallback(async (node) => {
    const navigation = graphNodeNavigation(node);
    if (!navigation.allowed) {
      showToast(navigation.restriction, "yellow", { title: "Graph access restricted" });
      return false;
    }
    await openPersonGraph(navigation.personId);
    return true;
  }, [openPersonGraph, showToast]);

  useEffect(() => {
    const previousView = previousActiveViewRef.current;
    previousActiveViewRef.current = activeView;
    if (activeView !== "people" || previousView === "people") return;
    const cached = personGraphRef.current;
    if (cached.active && cached.personId && cached.data) {
      openPersonGraph(cached.personId).catch((error) => console.error(error));
    }
  }, [activeView, openPersonGraph]);

  const createIdentifiedPerson = async (values) => {
    const payload = await apiPost("/api/person-create", {
      name: values.name,
      rank: values.rank,
      country: values.country,
      importance: values.importance,
      tags: values.tags || [],
      seen_date: values.date,
      seen_time: values.time,
      place_seen: values.placeSeen,
      individual_count: Number(values.individualCount),
      event_occasion: values.eventOccasion,
      added_by: values.addedBy,
      operation_id: operationId(),
    });
    let graphMutation = payload;
    if ((values.notes || "").trim() || (values.mentionedPersonIds || []).length) {
      graphMutation = await apiPost("/api/person-notes", {
        person_id: payload.person.person_id,
        notes: values.notes || "",
        expected_previous_notes: "",
        mentioned_person_ids: values.mentionedPersonIds || [],
        operation_id: operationId(),
      });
    }
    invalidatePersonGraph(graphMutation);
    await loadPeople({ dedupe: false });
    showToast("Person created");
    return (await loadPerson(payload.person.person_id)).person;
  };

  const savePeopleProfile = async (values) => {
    const result = await apiPost("/api/person-update", {
      person_id: values.personId,
      name: values.name,
      rank: values.rank,
      country: values.country,
      importance: values.importance,
      tags: values.tags || [],
      editor_name: values.editorName,
      operation_id: operationId(),
    });
    invalidatePersonGraph(result);
    await loadPeople({ dedupe: false });
    await refreshPeopleProfile(values.personId);
    showToast("Person details updated");
    return true;
  };

  const savePersonNotes = async (personId, notes, expectedPreviousNotes, mentionedPersonIds = []) => {
    const payload = await apiPost("/api/person-notes", {
      person_id: personId,
      notes,
      expected_previous_notes: expectedPreviousNotes,
      mentioned_person_ids: mentionedPersonIds,
      operation_id: operationId(),
    });
    if (!payload.updated) return { updated: false, notes: payload.notes };
    invalidatePersonGraph(payload);
    await loadPeople({ dedupe: false });
    const refreshed = await refreshPeopleProfile(personId);
    showToast("Notes saved");
    return {
      updated: true,
      notes: refreshed.profile_note?.content || "",
      mentioned_person_ids: refreshed.profile_note?.mentioned_person_ids || [],
    };
  };

  const setFavorite = async (personId, favorite) => {
    const requestId = operationId();
    await apiPost("/api/person-preferences", {
      person_id: personId,
      favorite,
      operation_id: requestId,
    });
    await loadPeople({ dedupe: false });
    if (peopleGallery?.person?.effective_person_id === personId) await refreshPeopleProfile(personId);
    showToast(favorite ? "Added to favorites" : "Removed from favorites");
  };

  const setRepresentativePhoto = async (personId, embeddingId) => {
    const requestId = operationId();
    const result = await apiPost("/api/person-preferences", {
      person_id: personId,
      representative_embedding_id: embeddingId,
      operation_id: requestId,
    });
    invalidatePersonGraph(result);
    await loadPeople({ dedupe: false });
    await refreshPeopleProfile(personId);
    showToast("Profile photo updated");
  };

  const archivePerson = async (personId) => {
    const result = await apiPost("/api/person-archive", {
      person_id: personId,
      operation_id: operationId(),
    });
    invalidatePersonGraph(result);
    setPeopleGallery(null);
    setPeopleGalleryImage(null);
    await loadPeople({ dedupe: false });
    showToast("Person moved to Archived. A database backup was created first.");
  };

  const restorePerson = async (personId) => {
    const result = await apiPost("/api/person-restore", {
      person_id: personId,
      operation_id: operationId(),
    });
    invalidatePersonGraph(result);
    await loadPeople({ dedupe: false });
    setPeopleGallery(await loadPerson(result.person_id || personId));
    showToast("Person restored");
  };

  const permanentlyDeletePerson = async (personId) => {
    const result = await apiPost("/api/person-purge", {
      person_id: personId,
      operation_id: operationId(),
    });
    invalidatePersonGraph(result);
    setPeopleGallery(null);
    setPeopleGalleryImage(null);
    await loadPeople({ dedupe: false });
    await loadDeletedFaces({ dedupe: false });
    showToast(
      `The identity is deleted from active use. Historical identity and provenance remain represented. Safety backup ${result.backup?.backup_id || "created"} retains a recovery copy.`,
      "red",
      { title: "Profile deleted", autoClose: 9000 },
    );
    return result;
  };

  const mergePeople = async (sourcePersonId, targetPersonId) => {
    const preview = await apiPost("/api/person-merge-preview", {
      source_person_id: sourcePersonId,
      target_person_id: targetPersonId,
    });
    const result = await apiPost("/api/person-merge", {
      source_person_id: sourcePersonId,
      target_person_id: targetPersonId,
      operation_id: operationId(),
      conflict_resolutions: preview.proposed_conflict_resolutions,
    });
    invalidatePersonGraph(result);
    setPeopleGallery(null);
    setPeopleGalleryImage(null);
    await loadPeople({ dedupe: false });
    showToast("People merged; history and provenance were preserved");
    return result;
  };

  const movePersonPhoto = async (personId, embeddingId, targetPersonId) => {
    const result = await apiPost("/api/person-photo-move", {
      embedding_id: embeddingId,
      target_person_id: targetPersonId,
      operation_id: operationId(),
    });
    invalidatePersonGraph(result);
    await refreshPeopleProfile(personId);
    await loadPeople({ dedupe: false });
    showToast("Face ownership corrected");
    return result;
  };

  const deletePersonPhoto = async (personId, embeddingId) => {
    const result = await apiPost("/api/person-photo-delete", {
      embedding_id: embeddingId,
      operation_id: operationId(),
    });
    invalidatePersonGraph(result);
    await loadPeople({ dedupe: false });
    await loadDeletedFaces({ dedupe: false });
    await refreshPeopleProfile(personId);
    setPeopleGalleryImage(null);
    showToast(
      `Face moved to Deleted Faces for 30 days. ${result.retained_sightings || 0} linked sighting${result.retained_sightings === 1 ? "" : "s"} retained.`,
      "yellow",
      { title: "Face safely deleted" },
    );
    return result;
  };

  const restoreDeletedFace = async (embeddingId, personId) => {
    const result = await apiPost("/api/person-photo-restore", {
      embedding_id: embeddingId,
      operation_id: operationId(),
    });
    invalidatePersonGraph(result);
    await loadPeople({ dedupe: false });
    await loadDeletedFaces({ dedupe: false });
    if (peopleGallery?.person?.effective_person_id === personId) await refreshPeopleProfile(personId);
    showToast("Face restored to the person’s photo library");
    return result;
  };

  const permanentlyDeleteFace = async (embeddingId) => {
    const result = await apiPost("/api/person-photo-purge", {
      embedding_id: embeddingId,
      operation_id: operationId(),
    });
    invalidatePersonGraph(result);
    await loadPeople({ dedupe: false });
    await loadDeletedFaces({ dedupe: false });
    showToast(
      `${result.deleted_sightings || 0} linked sighting${result.deleted_sightings === 1 ? "" : "s"} removed from the live library. Safety backup ${result.backup?.backup_id || "created"} retains a recovery copy.`,
      "red",
      { title: "Live-library erasure complete", autoClose: 8000 },
    );
    return result;
  };

  const peopleBack = () => {
    setPeopleGalleryImage(null);
    setPeopleGallery(null);
  };

  return {
    state: { peopleGallery, peopleGalleryImage, personGraph },
    actions: {
      peopleOpen,
      refreshPeopleProfile,
      openPersonGraph,
      openPersonGraphNode,
      refreshPersonGraph,
      closePersonGraph,
      invalidatePersonGraph,
      createIdentifiedPerson,
      setPeopleGalleryImage,
      peopleBack,
      savePeopleProfile,
      savePersonNotes,
      setPeopleFavorite: setFavorite,
      setRepresentativePhoto,
      archivePerson,
      restorePerson,
      permanentlyDeletePerson,
      mergePeople,
      movePersonPhoto,
      deletePersonPhoto,
      restoreDeletedFace,
      permanentlyDeleteFace,
    },
  };
}
