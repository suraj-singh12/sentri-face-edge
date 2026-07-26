import { useCallback, useRef } from "react";

import { DUPLICATE_MATCH_SCORE, NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import { clearFile, currentDateTimeParts, imageIdFromPath, isNewPersonSuggestion } from "../utils.js";
import { usePersistentState } from "./usePersistentState.js";

export function useRecognizeController({ apiGet, apiPost, loadEvents, loadPeople, showToast, uploadFile }) {
  const [recognition, setRecognition] = usePersistentState("sentriface.recognize.result", null);
  const [selectedRecognitionFace, setSelectedRecognitionFace] = usePersistentState("sentriface.recognize.selectedFace", 1);
  const [recognitionGallery, setRecognitionGallery] = usePersistentState("sentriface.recognize.gallery", null);
  const [recognitionGalleryImage, setRecognitionGalleryImage] = usePersistentState("sentriface.recognize.galleryImage", null);
  const [recognitionAcceptedFaces, setRecognitionAcceptedFaces] = usePersistentState("sentriface.recognize.acceptedFaces", []);
  const [recognitionFollowup, setRecognitionFollowup] = usePersistentState("sentriface.recognize.followup", null);
  const [recognitionFollowupDone, setRecognitionFollowupDone] = usePersistentState("sentriface.recognize.followupDone", false);
  const recognizeFileRef = useRef(null);

  const runRecognition = useCallback(async (path) => {
    const payload = await apiPost("/api/recognize", { path });
    setRecognition({ inputPath: path, faces: payload.faces || [], metrics: payload.metrics });
    setSelectedRecognitionFace(payload.faces?.[0]?.index || 1);
    setRecognitionGallery(null);
    setRecognitionGalleryImage(null);
    setRecognitionAcceptedFaces([]);
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

  const recognitionAccept = async (requestedFaceIndex, forceBadQuality = false) => {
    const faceIndex = requestedFaceIndex || selectedRecognitionFace;
    const face = recognition?.faces?.find((item) => item.index === faceIndex);
    const best = face?.matches?.[0];
    if (!recognition?.inputPath || !best || isNewPersonSuggestion(best)) return;
    setSelectedRecognitionFace(faceIndex);
    setRecognitionGallery(null);
    setRecognitionGalleryImage(null);
    if (best.score >= DUPLICATE_MATCH_SCORE) {
      setRecognitionAcceptedFaces((current) => current.includes(faceIndex) ? current : [...current, faceIndex]);
      openRecognitionFollowup({ name: best.name, personId: best.person_id, embeddingId: best.embedding_ids[0], decision: "duplicate", faceIndex, faceBox: face.box, forceBadQuality });
      showToast(`Duplicate image of ${best.name}`);
      return;
    }
    setRecognitionAcceptedFaces((current) => current.includes(faceIndex) ? current : [...current, faceIndex]);
    openRecognitionFollowup({ name: best.name, personId: best.person_id, decision: "existing", action: "existing", faceIndex, faceBox: face.box, forceBadQuality });
    showToast(`Fill details for ${best.name}`);
  };

  const recognitionNew = async (requestedFaceIndex, forceBadQuality = false) => {
    const faceIndex = requestedFaceIndex || selectedRecognitionFace;
    const face = recognition?.faces?.find((item) => item.index === faceIndex);
    if (!recognition?.inputPath || !face || (face.quality?.status === "bad" && !forceBadQuality)) return;
    setSelectedRecognitionFace(faceIndex);
    setRecognitionGallery(null);
    setRecognitionGalleryImage(null);
    setRecognitionAcceptedFaces((current) => current.includes(faceIndex) ? current : [...current, faceIndex]);
    openRecognitionFollowup({ name: "", personId: "", decision: "new", action: "new", faceIndex, faceBox: face.box, forceBadQuality });
    showToast("Fill new person details");
  };

  const selectRecognitionFace = (faceIndex) => {
    setSelectedRecognitionFace(faceIndex);
    setRecognitionGallery(null);
    setRecognitionGalleryImage(null);
  };

  const recognitionClear = () => {
    clearFile(recognizeFileRef);
    setRecognition(null);
    setSelectedRecognitionFace(1);
    setRecognitionGallery(null);
    setRecognitionGalleryImage(null);
    setRecognitionAcceptedFaces([]);
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
        face_index: recognitionFollowup.faceIndex,
        face_box: recognitionFollowup.faceBox,
        force_bad_quality: recognitionFollowup.forceBadQuality,
      });
      embeddingId = payload.embedding_id;
      detailName = payload.name || detailName;
    }
    if (recognitionFollowup.action === "new") {
      const payload = await apiPost("/api/recognition-new", {
        path: recognition.inputPath,
        name: recognitionFollowup.name,
        face_index: recognitionFollowup.faceIndex,
        face_box: recognitionFollowup.faceBox,
        force_bad_quality: recognitionFollowup.forceBadQuality,
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

  function openRecognitionFollowup({ name, personId, embeddingId, decision, action, faceIndex, faceBox, forceBadQuality = false }) {
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
      imageId: `${imageIdFromPath(recognition?.inputPath || "")}#face-${String(faceIndex).padStart(2, "0")}`,
      faceIndex,
      faceBox,
      forceBadQuality,
      decision,
      action,
    });
    setRecognitionFollowupDone(false);
  }

  return {
    state: {
      recognition,
      selectedRecognitionFace,
      recognitionGallery,
      recognitionGalleryImage,
      recognitionAcceptedFaces,
      recognitionFollowup,
      recognitionFollowupDone,
    },
    refs: { recognizeFileRef },
    actions: {
      recognizeLoadedImage,
      recognitionAccept,
      recognitionNew,
      recognitionClear,
      selectRecognitionFace,
      openRecognitionGallery,
      setRecognitionGalleryImage: selectRecognitionGalleryImage,
      recognitionGalleryBack,
      updateRecognitionFollowup,
      confirmRecognitionFollowup,
      clearRecognitionFollowupForm,
    },
  };
}
