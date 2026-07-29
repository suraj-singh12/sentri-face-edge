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
  loadDeletedFaces,
  loadEvents,
  loadPeople,
  showToast,
}) {
  const [peopleGallery, setPeopleGallery] = useState(null);
  const [peopleGalleryImage, setPeopleGalleryImage] = useState(null);

  const loadPerson = async (personId, archived = false) => apiGet(
    `/api/person?person_id=${encodeURIComponent(personId)}${archived ? "&include_archived=1" : ""}`,
  );

  const refreshPersonAndLists = async (personId, archived = false) => {
    const [person] = await Promise.all([
      loadPerson(personId, archived),
      loadPeople(),
      loadDeletedFaces(),
      loadEvents(),
    ]);
    setPeopleGallery(person);
    return person;
  };

  const peopleOpen = async (personId, options = {}) => {
    if (!personId) return;
    setPeopleGallery(await loadPerson(personId, Boolean(options.archived)));
    setPeopleGalleryImage(null);
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
    await refreshPersonAndLists(values.personId);
    showToast("Person details updated");
    return true;
  };

  const setFavorite = async (personId, favorite) => {
    await apiPost("/api/person-preferences", {
      person_id: personId,
      favorite,
      operation_id: operationId(),
    });
    if (peopleGallery?.person.person_id === personId) {
      await refreshPersonAndLists(personId);
    } else {
      await Promise.all([loadPeople(), loadDeletedFaces(), loadEvents()]);
    }
    showToast(favorite ? "Added to favorites" : "Removed from favorites");
  };

  const setRepresentativePhoto = async (personId, embeddingId) => {
    await apiPost("/api/person-preferences", {
      person_id: personId,
      representative_embedding_id: embeddingId,
      operation_id: operationId(),
    });
    await refreshPersonAndLists(personId);
    showToast("Profile photo updated");
  };

  const archivePerson = async (personId) => {
    await apiPost("/api/person-archive", {
      person_id: personId,
      operation_id: operationId(),
    });
    setPeopleGallery(null);
    setPeopleGalleryImage(null);
    await Promise.all([loadPeople(), loadDeletedFaces(), loadEvents()]);
    showToast("Person moved to Archived. A database backup was created first.");
  };

  const restorePerson = async (personId) => {
    await apiPost("/api/person-restore", {
      person_id: personId,
      operation_id: operationId(),
    });
    await refreshPersonAndLists(personId);
    showToast("Person restored");
  };

  const mergePeople = async (sourcePersonId, targetPersonId) => {
    const result = await apiPost("/api/person-merge", {
      source_person_id: sourcePersonId,
      target_person_id: targetPersonId,
      operation_id: operationId(),
    });
    setPeopleGallery(await loadPerson(targetPersonId));
    setPeopleGalleryImage(null);
    await Promise.all([loadPeople(), loadDeletedFaces(), loadEvents()]);
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
    await refreshPersonAndLists(personId);
    setPeopleGalleryImage(null);
    showToast(`Photo moved with ${result.moved_sightings} linked sighting${result.moved_sightings === 1 ? "" : "s"}`);
    return result;
  };

  const deletePersonPhoto = async (personId, embeddingId) => {
    const result = await apiPost("/api/person-photo-delete", {
      embedding_id: embeddingId,
      operation_id: operationId(),
    });
    await refreshPersonAndLists(personId);
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
    await Promise.all([loadPeople(), loadDeletedFaces(), loadEvents()]);
    if (peopleGallery?.person.person_id === personId) {
      await refreshPersonAndLists(personId);
    }
    showToast("Face restored to the person’s photo library");
    return result;
  };

  const permanentlyDeleteFace = async (embeddingId) => {
    const result = await apiPost("/api/person-photo-purge", {
      embedding_id: embeddingId,
      operation_id: operationId(),
    });
    await Promise.all([loadPeople(), loadDeletedFaces(), loadEvents()]);
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
      mergePeople,
      movePersonPhoto,
      deletePersonPhoto,
      restoreDeletedFace,
      permanentlyDeleteFace,
    },
  };
}
