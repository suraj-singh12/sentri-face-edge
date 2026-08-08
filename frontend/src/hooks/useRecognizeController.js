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
    setRecognition({ inputPath: path, faces: payload.faces || [], metrics: payload.metrics });
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
      setRecognitionAcceptedFaces((current) => current.includes(faceIndex) ? current : [...current, faceIndex]);
      openRecognitionFollowup({ name: best.name, personId: best.person_id, embeddingId: best.embedding_ids[0], decision: "duplicate", faceIndex, faceBox: face.box, forceBadQuality, conflictAcknowledged: Boolean(best.conflict_acknowledged) });
      showToast(`Duplicate image of ${best.name}`);
      return;
    }
    setRecognitionAcceptedFaces((current) => current.includes(faceIndex) ? current : [...current, faceIndex]);
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
    setRecognitionAcceptedFaces((current) => current.includes(faceIndex) ? current : [...current, faceIndex]);
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
    if (!recognitionFollowup || !recognition?.inputPath) return;
    let personId = recognitionFollowup.personId;
    let embeddingId = recognitionFollowup.embeddingId;
    let detailName = recognitionFollowup.name;
    let addedEmbedding = false;
    let createdPerson = false;
    const targetedPlaceholder = recognitionTargetPerson?.person_id === recognitionFollowup.personId;
    if (targetedPlaceholder) {
      const payload = await apiPost("/api/placeholder-enroll", {
        path: recognition.inputPath,
        person_id: recognitionFollowup.personId,
        face_index: recognitionFollowup.faceIndex,
        face_box: recognitionFollowup.faceBox,
        force_bad_quality: recognitionFollowup.forceBadQuality,
        conflict_acknowledged: recognitionFollowup.conflictAcknowledged,
        image_id: recognitionFollowup.imageId,
        date: recognitionFollowup.date,
        time: recognitionFollowup.time,
        place_seen: recognitionFollowup.placeSeen,
        individual_count: Number(recognitionFollowup.individualCount),
        event_occasion: recognitionFollowup.eventOccasion,
        added_by: recognitionFollowup.addedBy,
        notes: recognitionFollowup.notes,
        mentioned_person_ids: recognitionFollowup.mentionedPersonIds || [],
        operation_id: recognitionFollowup.identityOperationId,
      });
      embeddingId = payload.embedding_id;
      detailName = payload.name || detailName;
      addedEmbedding = true;
    } else if (recognitionFollowup.action === "existing") {
      const payload = await apiPost("/api/recognition-accept-existing", {
        path: recognition.inputPath,
        person_id: recognitionFollowup.personId,
        face_index: recognitionFollowup.faceIndex,
        face_box: recognitionFollowup.faceBox,
        force_bad_quality: recognitionFollowup.forceBadQuality,
        operation_id: recognitionFollowup.identityOperationId,
      });
      embeddingId = payload.embedding_id;
      detailName = payload.name || detailName;
      addedEmbedding = !payload.duplicate;
    }
    if (recognitionFollowup.action === "new") {
      const payload = await apiPost("/api/recognition-new", {
        path: recognition.inputPath,
        name: recognitionFollowup.name,
        face_index: recognitionFollowup.faceIndex,
        face_box: recognitionFollowup.faceBox,
        force_bad_quality: recognitionFollowup.forceBadQuality,
        operation_id: recognitionFollowup.identityOperationId,
        notes: recognitionFollowup.notes,
        mentioned_person_ids: recognitionFollowup.mentionedPersonIds || [],
      });
      personId = payload.person_id;
      embeddingId = payload.embedding_id;
      addedEmbedding = true;
      createdPerson = true;
    }
    if (!targetedPlaceholder) await apiPost("/api/recognition-followup", {
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
      notes: recognitionFollowup.action === "new" ? "" : recognitionFollowup.notes,
      mentioned_person_ids: recognitionFollowup.action === "new" ? [] : recognitionFollowup.mentionedPersonIds || [],
      operation_id: recognitionFollowup.followupOperationId,
    });
    setRecognitionFollowupDone(true);
    setRecognitionFollowup(null);
    if (createdPerson) {
      upsertPerson({
        person_id: personId,
        name: detailName,
        enrollment_status: "enrolled",
        is_placeholder: false,
        embedding_count: 1,
        representative_image: recognition.inputPath,
        favorite: false,
        tags: [],
        notes: recognitionFollowup.notes?.trim() || "",
        created_at: new Date().toISOString(),
        metadata: {
          rank: recognitionFollowup.rank || "",
          country: recognitionFollowup.country || "",
          importance: recognitionFollowup.importance || "",
          added_by: recognitionFollowup.addedBy || "",
        },
      });
    } else if (addedEmbedding) {
      updatePerson(personId, (person) => ({
        ...person,
        enrollment_status: "enrolled",
        is_placeholder: false,
        embedding_count: Number(person.embedding_count || 0) + 1,
        representative_image: person.representative_image || recognition.inputPath,
      }));
    }
    if (recognitionTargetPerson?.person_id === personId) {
      setRecognitionTargetPerson(null);
      await onExistingPersonEnrolled?.(personId);
    }
    showToast("Recognition details confirmed");
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
      clearRecognitionFollowupForm,
    },
  };
}
