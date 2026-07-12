import { useCallback, useRef, useState } from "react";

import { DUPLICATE_MATCH_SCORE, NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import { clearFile, currentDateTimeParts, imageIdFromPath, isNewPersonSuggestion } from "../utils.js";

export function useRecognizeController({ apiGet, apiPost, loadEvents, loadPeople, showToast, uploadFile }) {
  const [recognition, setRecognition] = useState(null);
  const [recognitionGallery, setRecognitionGallery] = useState(null);
  const [recognitionGalleryImage, setRecognitionGalleryImage] = useState(null);
  const [recognitionAccepted, setRecognitionAccepted] = useState(false);
  const [recognitionFollowup, setRecognitionFollowup] = useState(null);
  const [recognitionFollowupDone, setRecognitionFollowupDone] = useState(false);
  const recognizeFileRef = useRef(null);

  const runRecognition = useCallback(async (path) => {
    const payload = await apiPost("/api/recognize", { path });
    setRecognition({ inputPath: path, face: payload.faces[0] || null, metrics: payload.metrics });
    setRecognitionGallery(null);
    setRecognitionGalleryImage(null);
    setRecognitionAccepted(false);
    setRecognitionFollowup(null);
    setRecognitionFollowupDone(false);
    showToast(`Recognized ${payload.faces.length} face(s)`);
    await loadEvents();
  }, [apiPost, loadEvents, showToast]);

  const recognizeLoadedImage = useCallback(async () => {
    const file = recognizeFileRef.current?.files?.[0];
    if (!file) return;
    await runRecognition(await uploadFile(file));
  }, [runRecognition, uploadFile]);

  const recognitionAccept = async () => {
    const best = recognition?.face?.matches?.[0];
    if (!recognition?.inputPath || !best || isNewPersonSuggestion(best)) return;
    if (best.score >= DUPLICATE_MATCH_SCORE) {
      setRecognitionAccepted(true);
      openRecognitionFollowup({ name: best.name, personId: best.person_id, embeddingId: best.embedding_ids[0], decision: "duplicate" });
      showToast(`Duplicate image of ${best.name}`);
      return;
    }
    setRecognitionAccepted(true);
    openRecognitionFollowup({ name: best.name, personId: best.person_id, decision: "existing", action: "existing" });
    showToast(`Fill details for ${best.name}`);
  };

  const recognitionNew = async () => {
    if (!recognition?.inputPath) return;
    setRecognitionAccepted(true);
    openRecognitionFollowup({ name: "", personId: "", decision: "new", action: "new" });
    showToast("Fill new person details");
  };

  const recognitionClear = () => {
    clearFile(recognizeFileRef);
    setRecognition(null);
    setRecognitionGallery(null);
    setRecognitionGalleryImage(null);
    setRecognitionAccepted(false);
    setRecognitionFollowup(null);
    setRecognitionFollowupDone(false);
  };

  const updateRecognitionFollowup = (field, value) => {
    setRecognitionFollowup((current) => current ? { ...current, [field]: value } : current);
  };

  const clearRecognitionFollowupForm = () => {
    const { date, time } = currentDateTimeParts();
    setRecognitionFollowup((current) => current ? {
      ...current,
      date,
      time,
      rank: "",
      placeSeen: "",
      individualCount: "",
      eventOccasion: "",
      country: "",
      importance: current.action === "new" ? NEW_PERSON_IMPORTANCE_OPTIONS[1] : "",
      addedBy: "",
      name: current.action === "new" ? "" : current.name,
    } : current);
    setRecognitionFollowupDone(false);
  };

  const confirmRecognitionFollowup = async (event) => {
    event.preventDefault();
    if (!recognitionFollowup || !recognition?.inputPath) return;
    let personId = recognitionFollowup.personId;
    let embeddingId = recognitionFollowup.embeddingId;
    let detailName = recognitionFollowup.name;
    if (recognitionFollowup.action === "existing") {
      const payload = await apiPost("/api/recognition-accept-existing", {
        path: recognition.inputPath,
        person_id: recognitionFollowup.personId,
      });
      embeddingId = payload.embedding_id;
      detailName = payload.name || detailName;
    }
    if (recognitionFollowup.action === "new") {
      const payload = await apiPost("/api/recognition-new", {
        path: recognition.inputPath,
        name: recognitionFollowup.name,
      });
      personId = payload.person_id;
      embeddingId = payload.embedding_id;
    }
    await apiPost("/api/recognition-followup", {
      path: recognition.inputPath,
      name: detailName,
      person_id: personId,
      embedding_id: embeddingId,
      image_id: recognitionFollowup.imageId,
      image_path: recognition.inputPath,
      decision: recognitionFollowup.decision,
      date: recognitionFollowup.date,
      time: recognitionFollowup.time,
      rank: recognitionFollowup.rank,
      country: recognitionFollowup.country,
      importance: recognitionFollowup.importance,
      place_seen: recognitionFollowup.placeSeen,
      individual_count: Number(recognitionFollowup.individualCount),
      event_occasion: recognitionFollowup.eventOccasion,
      added_by: recognitionFollowup.addedBy,
    });
    setRecognitionFollowupDone(true);
    setRecognitionFollowup(null);
    showToast("Recognition details confirmed");
    await Promise.all([loadPeople(), loadEvents()]);
  };

  const openRecognitionGallery = async (personId) => {
    if (!personId) return;
    setRecognitionGallery(await apiGet(`/api/person?person_id=${encodeURIComponent(personId)}`));
  };

  const recognitionGalleryBack = () => {
    setRecognitionGallery(null);
  };

  const selectRecognitionGalleryImage = (path) => {
    const embedding = recognitionGallery?.embeddings?.find((record) => (
      record.source_image === path || record.crop_path === path
    ));
    setRecognitionGalleryImage(embedding?.source_image || path);
  };

  function openRecognitionFollowup({ name, personId, embeddingId, decision, action }) {
    const { date, time } = currentDateTimeParts();
    setRecognitionFollowup({
      date,
      time,
      rank: "",
      placeSeen: "",
      individualCount: "",
      eventOccasion: "",
      country: "",
      importance: action === "new" ? NEW_PERSON_IMPORTANCE_OPTIONS[1] : "",
      addedBy: "",
      name,
      personId,
      embeddingId,
      imageId: imageIdFromPath(recognition?.inputPath || ""),
      decision,
      action,
    });
    setRecognitionFollowupDone(false);
  }

  return {
    state: {
      recognition,
      recognitionGallery,
      recognitionGalleryImage,
      recognitionAccepted,
      recognitionFollowup,
      recognitionFollowupDone,
    },
    refs: { recognizeFileRef },
    actions: {
      recognizeLoadedImage,
      recognitionAccept,
      recognitionNew,
      recognitionClear,
      openRecognitionGallery,
      setRecognitionGalleryImage: selectRecognitionGalleryImage,
      recognitionGalleryBack,
      updateRecognitionFollowup,
      confirmRecognitionFollowup,
      clearRecognitionFollowupForm,
    },
  };
}
