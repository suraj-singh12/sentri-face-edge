import { useState } from "react";

import { requirePersonContract } from "../utils.js";

function operationId() {
  return globalThis.crypto?.randomUUID?.()
    || "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
      const value = Math.floor(Math.random() * 16);
      return (character === "x" ? value : (value & 0x3) | 0x8).toString(16);
    });
}

export function usePeopleController({
  apiGet,
  apiPost,
  loadPeople,
  loadDeletedFaces,
  showToast,
}) {
  const [peopleGallery, setPeopleGallery] = useState(null);
  const [peopleGalleryImage, setPeopleGalleryImage] = useState(null);

  const loadPerson = async (personId, archived = false) => {
    const payload = await apiGet(
      `/api/person?person_id=${encodeURIComponent(personId)}${archived ? "&include_archived=1" : ""}`,
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

  const loadRelationshipGraphPerson = async (personId, _archived = false, limit = 30) => apiGet(
    `/api/person-relationship-graph?person_id=${encodeURIComponent(personId)}&limit=${encodeURIComponent(limit)}`,
    { dedupe: false },
  );

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
    if ((values.notes || "").trim() || (values.mentionedPersonIds || []).length) {
      await apiPost("/api/person-notes", {
        person_id: payload.person.person_id,
        notes: values.notes || "",
        expected_previous_notes: "",
        mentioned_person_ids: values.mentionedPersonIds || [],
        operation_id: operationId(),
      });
    }
    await loadPeople({ dedupe: false });
    showToast("Person created");
    return (await loadPerson(payload.person.person_id)).person;
  };

  const savePeopleProfile = async (values) => {
    await apiPost("/api/person-update", {
      person_id: values.personId,
      name: values.name,
      rank: values.rank,
      country: values.country,
      importance: values.importance,
      tags: values.tags || [],
      editor_name: values.editorName,
      operation_id: operationId(),
    });
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
    await apiPost("/api/person-preferences", {
      person_id: personId,
      representative_embedding_id: embeddingId,
      operation_id: requestId,
    });
    await loadPeople({ dedupe: false });
    await refreshPeopleProfile(personId);
    showToast("Profile photo updated");
  };

  const archivePerson = async (personId) => {
    await apiPost("/api/person-archive", {
      person_id: personId,
      operation_id: operationId(),
    });
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
    await loadPeople({ dedupe: false });
    setPeopleGallery(await loadPerson(result.person_id || personId));
    showToast("Person restored");
  };

  const permanentlyDeletePerson = async (personId) => {
    const result = await apiPost("/api/person-purge", {
      person_id: personId,
      operation_id: operationId(),
    });
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
    state: { peopleGallery, peopleGalleryImage },
    actions: {
      peopleOpen,
      refreshPeopleProfile,
      loadRelationshipGraphPerson,
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
