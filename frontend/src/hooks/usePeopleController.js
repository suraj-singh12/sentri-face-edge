import { useState } from "react";

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
  updatePerson,
  upsertPerson,
  archivePersonLocally,
  restorePersonLocally,
  removePersonLocally,
  addDeletedFace,
  removeDeletedFace,
  showToast,
}) {
  const [peopleGallery, setPeopleGallery] = useState(null);
  const [peopleGalleryImage, setPeopleGalleryImage] = useState(null);

  const loadPerson = async (personId, archived = false) => apiGet(
    `/api/person?person_id=${encodeURIComponent(personId)}${archived ? "&include_archived=1" : ""}`,
  );

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

  const loadRelationshipGraphPerson = async (personId, archived = false, limit = 30) => apiGet(
    `/api/person-association-neighbors?person_id=${encodeURIComponent(personId)}&include_archived=${archived ? "1" : "0"}&limit=${encodeURIComponent(limit)}`,
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
      const notePayload = await apiPost("/api/person-notes", {
        person_id: payload.person.person_id,
        notes: values.notes || "",
        expected_previous_notes: "",
        mentioned_person_ids: values.mentionedPersonIds || [],
        operation_id: operationId(),
      });
      payload.person = { ...payload.person, notes: notePayload.notes };
    }
    upsertPerson(payload.person);
    showToast("Person created");
    return payload.person;
  };

  const createPersonAssociation = async (sourcePersonId, targetPersonId) => {
    throw new Error("Manual associations are temporarily unavailable until normalized graph evidence is enabled");
  };

  const createPlaceholderAssociation = async (sourcePersonId, name) => {
    throw new Error("Association profile creation is temporarily unavailable until normalized graph evidence is enabled");
  };

  const removePersonAssociation = async (sourcePersonId, associationId) => {
    throw new Error("Legacy association editing is unavailable; historical associations remain read-only");
  };

  const savePeopleProfile = async (values) => {
    const payload = await apiPost("/api/person-update", {
      person_id: values.personId,
      name: values.name,
      rank: values.rank,
      country: values.country,
      importance: values.importance,
      tags: values.tags || [],
      editor_name: values.editorName,
      operation_id: operationId(),
    });
    const metadataPatch = {
      rank: values.rank || "",
      country: values.country || "",
      importance: values.importance || "",
      tags: values.tags || [],
    };
    updatePerson(values.personId, (person) => ({
      ...person,
      name: values.name,
      tags: values.tags || [],
      metadata: { ...(person.metadata || {}), ...metadataPatch },
    }));
    setPeopleGallery((current) => current?.person?.person_id === values.personId ? {
      ...current,
      person: {
        ...current.person,
        name: values.name,
        tags: values.tags || [],
        metadata: { ...(current.person.metadata || {}), ...metadataPatch },
      },
      changes: payload.change
        ? [payload.change, ...(current.changes || []).filter((item) => item.change_id !== payload.change.change_id)]
        : current.changes,
    } : current);
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
    updatePerson(personId, (person) => ({ ...person, notes: payload.notes }));
    setPeopleGallery((current) => current?.person?.person_id === personId ? {
      ...current,
      person: { ...current.person, notes: payload.notes },
      associations: payload.associations || current.associations,
      changes: payload.change
        ? [payload.change, ...(current.changes || []).filter((item) => item.change_id !== payload.change.change_id)]
        : current.changes,
    } : current);
    showToast("Notes saved");
    return { updated: true, notes: payload.notes };
  };

  const setFavorite = async (personId, favorite) => {
    const requestId = operationId();
    const result = await apiPost("/api/person-preferences", {
      person_id: personId,
      favorite,
      operation_id: requestId,
    });
    updatePerson(personId, (person) => ({
      ...person,
      favorite: result.favorite,
      metadata: { ...(person.metadata || {}), favorite: result.favorite },
    }));
    setPeopleGallery((current) => current?.person?.person_id === personId ? {
      ...current,
      person: {
        ...current.person,
        favorite: result.favorite,
        metadata: { ...(current.person.metadata || {}), favorite: result.favorite },
      },
      management_events: [localManagementEvent(requestId, "person-preferences", result), ...(current.management_events || [])],
    } : current);
    showToast(favorite ? "Added to favorites" : "Removed from favorites");
  };

  const setRepresentativePhoto = async (personId, embeddingId) => {
    const requestId = operationId();
    const result = await apiPost("/api/person-preferences", {
      person_id: personId,
      representative_embedding_id: embeddingId,
      operation_id: requestId,
    });
    const record = peopleGallery?.embeddings?.find((item) => item.embedding_id === embeddingId);
    const representativeImage = record?.crop_path || record?.source_image || "";
    updatePerson(personId, (person) => ({
      ...person,
      representative_image: representativeImage || person.representative_image,
      metadata: { ...(person.metadata || {}), representative_embedding_id: embeddingId },
    }));
    setPeopleGallery((current) => current?.person?.person_id === personId ? {
      ...current,
      person: {
        ...current.person,
        representative_image: representativeImage || current.person.representative_image,
        metadata: { ...(current.person.metadata || {}), representative_embedding_id: embeddingId },
      },
      management_events: [localManagementEvent(requestId, "person-preferences", result), ...(current.management_events || [])],
    } : current);
    showToast("Profile photo updated");
  };

  const archivePerson = async (personId) => {
    const result = await apiPost("/api/person-archive", {
      person_id: personId,
      operation_id: operationId(),
    });
    setPeopleGallery(null);
    setPeopleGalleryImage(null);
    archivePersonLocally(personId, result.archived_at);
    showToast("Person moved to Archived. A database backup was created first.");
  };

  const restorePerson = async (personId) => {
    await apiPost("/api/person-restore", {
      person_id: personId,
      operation_id: operationId(),
    });
    restorePersonLocally(personId);
    setPeopleGallery((current) => current?.person?.person_id === personId ? {
      ...current,
      person: { ...current.person, deleted_at: null },
    } : current);
    showToast("Person restored");
  };

  const permanentlyDeletePerson = async (personId) => {
    const result = await apiPost("/api/person-purge", {
      person_id: personId,
      operation_id: operationId(),
    });
    setPeopleGallery(null);
    setPeopleGalleryImage(null);
    removePersonLocally(personId);
    showToast(
      `${result.deleted_embeddings || 0} photo record${result.deleted_embeddings === 1 ? "" : "s"}, ${result.deleted_sightings || 0} sighting${result.deleted_sightings === 1 ? "" : "s"}, and ${result.deleted_associations || 0} association${result.deleted_associations === 1 ? "" : "s"} removed. Safety backup ${result.backup?.backup_id || "created"} retains a recovery copy.`,
      "red",
      { title: "Profile permanently deleted", autoClose: 9000 },
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
    archivePersonLocally(sourcePersonId, undefined, {
      merged_into: result.target_person_id,
    });
    updatePerson(sourcePersonId, (person) => ({
      ...person,
      lifecycle_status: "MERGED",
      merged: true,
      canonical_person_id: result.target_person_id,
    }));
    const survivor = await loadPerson(result.target_person_id);
    upsertPerson(survivor.person);
    showToast("People merged; history and provenance were preserved");
    return result;
  };

  const undoPeopleMerge = async (mergeOperationId) => {
    throw new Error("Undo Merge is not available in P8-B");
  };

  const movePersonPhoto = async (personId, embeddingId, targetPersonId) => {
    const result = await apiPost("/api/person-photo-move", {
      embedding_id: embeddingId,
      target_person_id: targetPersonId,
      operation_id: operationId(),
    });
    await refreshPeopleProfile(personId);
    showToast("Face ownership corrected");
    return result;
  };

  const deletePersonPhoto = async (personId, embeddingId) => {
    const result = await apiPost("/api/person-photo-delete", {
      embedding_id: embeddingId,
      operation_id: operationId(),
    });
    const removed = peopleGallery?.embeddings?.find((item) => item.embedding_id === embeddingId);
    const updatedGallery = peopleGallery?.person?.person_id === personId
      ? removeEmbeddingFromGallery(peopleGallery, embeddingId, { keepDetails: true })
      : null;
    updatePerson(personId, (person) => ({
      ...person,
      embedding_count: Math.max(0, Number(person.embedding_count || 0) - 1),
      representative_image: updatedGallery?.person?.representative_image ?? person.representative_image,
      metadata: updatedGallery?.person?.metadata ?? person.metadata,
    }));
    setPeopleGallery((current) => current?.person?.person_id === personId
      ? removeEmbeddingFromGallery(current, embeddingId, { keepDetails: true })
      : current);
    addDeletedFace({
      ...result,
      person_name: peopleGallery?.person?.name || personId,
      person_lifecycle_status: "ACTIVE",
      canonical_person_id: null,
      person_archived: false,
      person_deleted: false,
      person_merged: false,
      quality_score: removed?.quality_score,
      created_at: removed?.created_at,
      sighting_count: result.retained_sightings || 0,
      days_remaining: 30,
    });
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
    removeDeletedFace(embeddingId);
    updatePerson(personId, (person) => ({ ...person, embedding_count: Number(person.embedding_count || 0) + 1 }));
    showToast("Face restored to the person’s photo library");
    return result;
  };

  const permanentlyDeleteFace = async (embeddingId) => {
    const result = await apiPost("/api/person-photo-purge", {
      embedding_id: embeddingId,
      operation_id: operationId(),
    });
    removeDeletedFace(embeddingId);
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
      createPersonAssociation,
      createPlaceholderAssociation,
      removePersonAssociation,
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
      undoPeopleMerge,
      movePersonPhoto,
      deletePersonPhoto,
      restoreDeletedFace,
      permanentlyDeleteFace,
    },
  };
}

function removeEmbeddingFromGallery(gallery, embeddingId, options = {}) {
  const embeddings = (gallery.embeddings || []).filter((item) => item.embedding_id !== embeddingId);
  const representativeId = gallery.person.metadata?.representative_embedding_id;
  const removedRepresentative = representativeId === embeddingId;
  const nextRepresentative = removedRepresentative ? embeddings[0] : null;
  return {
    ...gallery,
    embeddings,
    details: options.keepDetails
      ? gallery.details
      : (gallery.details || []).filter((item) => item.embedding_id !== embeddingId),
    person: {
      ...gallery.person,
      representative_image: removedRepresentative
        ? nextRepresentative?.crop_path || nextRepresentative?.source_image || ""
        : gallery.person.representative_image,
      metadata: removedRepresentative
        ? { ...(gallery.person.metadata || {}), representative_embedding_id: nextRepresentative?.embedding_id || "" }
        : gallery.person.metadata,
    },
  };
}

function localManagementEvent(id, type, result) {
  return {
    operation_id: id,
    operation_type: type,
    result,
    created_at: new Date().toISOString(),
  };
}
