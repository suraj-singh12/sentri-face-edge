import { useCallback, useRef } from "react";

import { NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import { clearFile, currentDateTimeParts, imageIdFromPath, isNewPersonSuggestion } from "../utils.js";
import { usePersistentState } from "./usePersistentState.js";

export function useRecognizeController({
  apiGet,
  apiPost,
  updatePerson,
  upsertPerson,
  notifySkippedInputs,
  prepareImageFiles,
  showToast,
  uploadFile,
  onExistingPersonEnrolled,
}) {
  const [recognition, setRecognition] = usePersistentState("sentriface.recognize.result", null);
  const [selectedRecognitionFace, setSelectedRecognitionFace] = usePersistentState("sentriface.recognize.selectedFace", 1);
  const [recognitionGallery, setRecognitionGallery] = usePersistentState("sentriface.recognize.gallery", null);
  const [recognitionGalleryImage, setRecognitionGalleryImage] = usePersistentState("sentriface.recognize.galleryImage", null);
  const [recognitionAcceptedFaces, setRecognitionAcceptedFaces] = usePersistentState("sentriface.recognize.acceptedFaces", []);
  const [recognitionFollowup, setRecognitionFollowup] = usePersistentState("sentriface.recognize.followup", null);
  const [recognitionFollowupDone, setRecognitionFollowupDone] = usePersistentState("sentriface.recognize.followupDone", false);
  const [recognitionTargetPerson, setRecognitionTargetPerson] = usePersistentState("sentriface.recognize.targetPerson", null);
  const recognizeFileRef = useRef(null);
  const recognitionRequestRef = useRef(null);

  const runRecognition = useCallback(async (path, signal) => {
    const payload = await apiPost("/api/recognize", { path }, { signal, timeoutMs: 10 * 60 * 1000 });
    setRecognition({
      inputPath: path,
      reviewId: payload.review_id,
      completionOperationId: crypto.randomUUID(),
      faces: payload.faces || [],
      metrics: payload.metrics,
    });
    setSelectedRecognitionFace(payload.faces?.[0]?.index || 1);
    setRecognitionGallery(null);
    setRecognitionGalleryImage(null);
    setRecognitionAcceptedFaces([]);
    setRecognitionFollowup(null);
    setRecognitionFollowupDone(false);
    showToast(`Recognized ${payload.faces.length} face(s)`);
  }, [apiPost, showToast]);

  const recognizeLoadedImage = useCallback(async () => {
    const file = recognizeFileRef.current?.files?.[0];
    if (!file) return;
    const prepared = await prepareImageFiles([file], "recognize");
    if (!prepared.validFiles.length) {
      clearFile(recognizeFileRef);
      notifySkippedInputs(prepared.rejected.length, 0);
      return;
    }
    recognitionRequestRef.current?.abort();
    const controller = new AbortController();
    recognitionRequestRef.current = controller;
    const upload = await uploadFile(prepared.validFiles[0], { signal: controller.signal });
    const rejectedCount = prepared.rejected.length + upload.rejectedFiles;
    notifySkippedInputs(rejectedCount, upload.uploadedFiles);
    clearFile(recognizeFileRef);
    if (!upload.path) return;
    await runRecognition(upload.path, controller.signal);
    recognitionRequestRef.current = null;
  }, [notifySkippedInputs, prepareImageFiles, runRecognition, uploadFile]);

  const recognitionAccept = async (requestedFaceIndex, forceBadQuality = false, selectedPerson = null) => {
    const faceIndex = requestedFaceIndex || selectedRecognitionFace;
    const face = recognition?.faces?.find((item) => item.index === faceIndex);
    const best = selectedPerson || face?.matches?.[0];
    if (!recognition?.inputPath || !best || isNewPersonSuggestion(best)) return;
    setSelectedRecognitionFace(faceIndex);
    setRecognitionGallery(null);
    setRecognitionGalleryImage(null);
    if (best.is_duplicate) {
      openRecognitionFollowup({ name: best.name, personId: best.person_id, embeddingId: best.embedding_ids[0], decision: "duplicate", faceIndex, faceBox: face.box, forceBadQuality, conflictAcknowledged: Boolean(best.conflict_acknowledged) });
      showToast(`Duplicate image of ${best.name}`);
      return;
    }
    openRecognitionFollowup({ name: best.name, personId: best.person_id, decision: "existing", action: "existing", faceIndex, faceBox: face.box, forceBadQuality, conflictAcknowledged: Boolean(best.conflict_acknowledged) });
    showToast(`Fill details for ${best.name}`);
  };

  const recognitionNew = async (requestedFaceIndex, forceBadQuality = false) => {
    const faceIndex = requestedFaceIndex || selectedRecognitionFace;
    const face = recognition?.faces?.find((item) => item.index === faceIndex);
    if (!recognition?.inputPath || !face || (face.quality?.status === "bad" && !forceBadQuality)) return;
    setSelectedRecognitionFace(faceIndex);
    setRecognitionGallery(null);
    setRecognitionGalleryImage(null);
    openRecognitionFollowup({ name: "", personId: "", decision: "new", action: "new", faceIndex, faceBox: face.box, forceBadQuality });
    showToast("Fill new person details");
  };

  const selectRecognitionFace = (faceIndex) => {
    setSelectedRecognitionFace(faceIndex);
    setRecognitionGallery(null);
    setRecognitionGalleryImage(null);
  };

  const loadRecognitionPeopleCandidates = async (faceIndex) => {
    const face = recognition?.faces?.find((item) => item.index === faceIndex);
    if (!recognition?.inputPath || !face) return { candidates: [] };
    return apiPost("/api/recognition-person-candidates", {
      path: recognition.inputPath,
      face_index: faceIndex,
      face_box: face.box,
    });
  };

  const recognitionClear = () => {
    recognitionRequestRef.current?.abort();
    recognitionRequestRef.current = null;
    if (recognition?.reviewId) {
      void apiPost("/api/photo-review-cancel", { review_id: recognition.reviewId }, { silent: true })
        .catch(() => {});
    }
    if (recognition?.inputPath) {
      void apiPost("/api/upload-file-discard", { path: recognition.inputPath }, { silent: true })
        .catch(() => {});
    }    clearFile(recognizeFileRef);
    setRecognition(null);
    setSelectedRecognitionFace(1);
    setRecognitionGallery(null);
    setRecognitionGalleryImage(null);
    setRecognitionAcceptedFaces([]);
    setRecognitionFollowup(null);
    setRecognitionFollowupDone(false);
  };

  const startExistingPersonEnrollment = (person) => {
    recognitionClear();
    setRecognitionTargetPerson({
      person_id: person.person_id,
      name: person.name,
      representative_image: person.representative_image || "",
    });
  };

  const cancelExistingPersonEnrollment = () => {
    recognitionClear();
    setRecognitionTargetPerson(null);
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
      notes: "",
      mentionedPersonIds: [],
      name: current.action === "new" ? "" : current.name,
    } : current);
    setRecognitionFollowupDone(false);
  };

  const confirmRecognitionFollowup = async (event) => {
    event.preventDefault();
    if (!recognitionFollowup || !recognition?.reviewId) return;
    await apiPost("/api/photo-review-decision", {
      review_id: recognition.reviewId,
      face_id: `face-${recognitionFollowup.faceIndex}`,
      decision: recognitionFollowup.action === "new"
        ? "ACCEPT_NEW_PERSON"
        : "ACCEPT_EXISTING_PERSON",
      person_id: recognitionFollowup.action === "new" ? undefined : recognitionFollowup.personId,
      new_person_name: recognitionFollowup.action === "new" ? recognitionFollowup.name : undefined,
      new_person_metadata: recognitionFollowup.action === "new" ? {
        rank: recognitionFollowup.rank || "",
        country: recognitionFollowup.country || "",
        importance: recognitionFollowup.importance || "",
        added_by: recognitionFollowup.addedBy || "",
      } : undefined,
      notes: recognitionFollowup.notes,
      mentioned_person_ids: recognitionFollowup.mentionedPersonIds || [],
      recognition_detail: {
        image_id: recognitionFollowup.imageId,
        image_path: recognition.inputPath,
        name: recognitionFollowup.name,
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
      },
    });
    setRecognitionFollowupDone(true);
    setRecognitionFollowup(null);
    setRecognitionAcceptedFaces((current) => current.includes(recognitionFollowup.faceIndex)
      ? current
      : [...current, recognitionFollowup.faceIndex]);
    showToast("Face decision saved");
  };

  const skipRecognitionFace = async (faceIndex = selectedRecognitionFace) => {
    if (!recognition?.reviewId) return;
    await apiPost("/api/photo-review-decision", {
      review_id: recognition.reviewId,
      face_id: `face-${faceIndex}`,
      decision: "SKIP",
    });
    setRecognitionAcceptedFaces((current) => current.includes(faceIndex) ? current : [...current, faceIndex]);
  };

  const completeRecognitionReview = async () => {
    if (!recognition?.reviewId || recognitionAcceptedFaces.length !== recognition.faces.length) return;
    const result = await apiPost("/api/photo-review-complete", {
      review_id: recognition.reviewId,
      operation_id: recognition.completionOperationId,
      source: "check-photo",
    });
    for (const person of result.created_people || []) upsertPerson(person);
    showToast("Review completed");
    setRecognition(null);
    setRecognitionAcceptedFaces([]);
    setRecognitionFollowup(null);
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

  function openRecognitionFollowup({ name, personId, embeddingId, decision, action, faceIndex, faceBox, forceBadQuality = false, conflictAcknowledged = false }) {
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
      notes: "",
      mentionedPersonIds: [],
      name,
      personId,
      embeddingId,
      imageId: `${imageIdFromPath(recognition?.inputPath || "")}#face-${String(faceIndex).padStart(2, "0")}`,
      faceIndex,
      faceBox,
      forceBadQuality,
      conflictAcknowledged,
      decision,
      action,
      identityOperationId: crypto.randomUUID(),
      followupOperationId: crypto.randomUUID(),
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
      recognitionTargetPerson,
    },
    refs: { recognizeFileRef },
    actions: {
      recognizeLoadedImage,
      recognitionAccept,
      recognitionNew,
      recognitionClear,
      startExistingPersonEnrollment,
      cancelExistingPersonEnrollment,
      selectRecognitionFace,
      loadRecognitionPeopleCandidates,
      openRecognitionGallery,
      setRecognitionGalleryImage: selectRecognitionGalleryImage,
      recognitionGalleryBack,
      updateRecognitionFollowup,
      confirmRecognitionFollowup,
      skipRecognitionFace,
      completeRecognitionReview,
      clearRecognitionFollowupForm,
    },
  };
}
