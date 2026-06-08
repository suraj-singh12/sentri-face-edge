import { useState } from "react";

export function usePeopleController({ apiGet, apiPost, loadEvents, loadPeople, showToast }) {
  const [peopleGallery, setPeopleGallery] = useState(null);
  const [peopleGalleryImage, setPeopleGalleryImage] = useState(null);

  const peopleOpen = async (personId) => {
    if (!personId) return;
    setPeopleGallery(await apiGet(`/api/person?person_id=${encodeURIComponent(personId)}`));
    setPeopleGalleryImage(null);
  };

  const savePeopleProfile = async (values) => {
    const editorName = window.prompt("Editor's name");
    if (!editorName) return false;
    await apiPost("/api/person-update", {
      person_id: values.personId,
      name: values.name,
      rank: values.rank,
      country: values.country,
      importance: values.importance,
      editor_name: editorName,
    });
    setPeopleGallery(await apiGet(`/api/person?person_id=${encodeURIComponent(values.personId)}`));
    showToast("Person details updated");
    await Promise.all([loadPeople(), loadEvents()]);
    return true;
  };

  const peopleBack = () => {
    if (peopleGalleryImage) setPeopleGalleryImage(null);
    else setPeopleGallery(null);
  };

  return {
    state: { peopleGallery, peopleGalleryImage },
    actions: {
      peopleOpen,
      setPeopleGalleryImage,
      peopleBack,
      savePeopleProfile,
    },
  };
}
