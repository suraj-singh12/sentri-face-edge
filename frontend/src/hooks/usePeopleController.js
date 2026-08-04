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
      `${result.deleted_embeddings || 0} photo record${result.deleted_embeddings === 1 ? "" : "s"} and ${result.deleted_sightings || 0} sighting${result.deleted_sightings === 1 ? "" : "s"} removed. Safety backup ${result.backup?.backup_id || "created"} retains a recovery copy.`,
      "red",
      { title: "Profile permanently deleted", autoClose: 9000 },
    );
    return result;
  };

  const mergePeople = async (sourcePersonId, targetPersonId) => {
    const result = await apiPost("/api/person-merge", {
      source_person_id: sourcePersonId,
      target_person_id: targetPersonId,
      operation_id: operationId(),
    });
    const target = await loadPerson(targetPersonId);
    setPeopleGallery(target);
    setPeopleGalleryImage(null);
    archivePersonLocally(sourcePersonId, new Date().toISOString(), { merged_into: targetPersonId });
    upsertPerson(personSummaryFromPayload(target));
    showToast(
      `Merged ${result.moved_embeddings} active photo${result.moved_embeddings === 1 ? "" : "s"} and ${result.moved_deleted_faces || 0} deleted face${result.moved_deleted_faces === 1 ? "" : "s"}. A database backup was created first.`,
    );
    return result;
  };

  const movePersonPhoto = async (personId, embeddingId, targetPersonId) => {
    const result = await apiPost("/api/person-photo-move", {
      embedding_id: embeddingId,
      target_person_id: targetPersonId,
      operation_id: operationId(),
    });
    const moved = peopleGallery?.embeddings?.find((item) => item.embedding_id === embeddingId);
    const updatedSourceGallery = peopleGallery?.person?.person_id === personId
      ? removeEmbeddingFromGallery(peopleGallery, embeddingId)
      : null;
    updatePerson(personId, (person) => ({
      ...person,
      embedding_count: Math.max(0, Number(person.embedding_count || 0) - 1),
      representative_image: updatedSourceGallery?.person?.representative_image ?? person.representative_image,
      metadata: updatedSourceGallery?.person?.metadata ?? person.metadata,
    }));
    updatePerson(targetPersonId, (person) => ({
      ...person,
      embedding_count: Number(person.embedding_count || 0) + 1,
      representative_image: person.representative_image || moved?.crop_path || moved?.source_image,
    }));
    setPeopleGallery((current) => current?.person?.person_id === personId
      ? removeEmbeddingFromGallery(current, embeddingId)
      : current);
    setPeopleGalleryImage(null);
    showToast(`Photo moved with ${result.moved_sightings} linked sighting${result.moved_sightings === 1 ? "" : "s"}`);
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
      person_archived: false,
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
      setPeopleGalleryImage,
      peopleBack,
      savePeopleProfile,
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

function personSummaryFromPayload(payload) {
  return {
    ...payload.person,
    embedding_count: (payload.embeddings || []).length,
    favorite: Boolean(payload.person.favorite),
    tags: payload.person.tags || payload.person.metadata?.tags || [],
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
