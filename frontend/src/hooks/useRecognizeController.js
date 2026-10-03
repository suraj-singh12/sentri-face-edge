import { useCallback, useEffect, useRef, useState } from "react";

import { NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import { clearFile, currentDateTimeParts, imageIdFromPath, isNewPersonSuggestion, requirePersonContract } from "../utils.js";
import { acceptedDecision, recognitionReviewReady, recognitionReviewState } from "../reviewState.js";
import { usePersistentState } from "./usePersistentState.js";

export function useRecognizeController({
  canReview = true,
  apiGet,
  apiPost,
  loadPeople,
  notifySkippedInputs,
  prepareImageFiles,
  showToast,
  uploadFile,
  onExistingPersonEnrolled,
  onGraphMutation,
}) {
  const [recognition, setRecognition] = usePersistentState("sentriface.recognize.result", null);
  const [selectedRecognitionFace, setSelectedRecognitionFace] = usePersistentState("sentriface.recognize.selectedFace", 1);
  const [recognitionGallery, setRecognitionGallery] = usePersistentState("sentriface.recognize.gallery", null);
  const [recognitionGalleryImage, setRecognitionGalleryImage] = usePersistentState("sentriface.recognize.galleryImage", null);
  const decisions = recognition?.faceDecisions || {};
  const recognitionAcceptedFaces = (recognition?.faces || []).filter((face) => acceptedDecision(decisions[face.index])).map((face) => face.index);
  const [recognitionFollowup, setRecognitionFollowup] = usePersistentState("sentriface.recognize.followup", null);
  const [recognitionFollowupDone, setRecognitionFollowupDone] = usePersistentState("sentriface.recognize.followupDone", false);
  const [recognitionTargetPerson, setRecognitionTargetPerson] = usePersistentState("sentriface.recognize.targetPerson", null);
  const [qualityOnly, setQualityOnly] = usePersistentState("sentriface.recognize.qualityOnly", true);
  const [eventDraft, setEventDraft] = usePersistentState("sentriface.recognize.eventDraft", null);
  const [proofOnlyDuplicateCandidates, setProofOnlyDuplicateCandidates] = useState([]);
  const recognizeFileRef = useRef(null);
  const recognitionRequestRef = useRef(null);
  const reviewReadGeneration = useRef(0);

  useEffect(() => {
    if (!recognition?.faces?.length || recognition.encounterMetadata || eventDraft || recognitionTargetPerson) return;
    const { date } = currentDateTimeParts();
    setEventDraft({ date, time: "", endTime: "", timePrecision: "unknown", placeSeen: "", eventOccasion: "", eventContext: "unknown", eventNotes: "", eventMentionedPersonIds: [] });
  }, [recognition, eventDraft, recognitionTargetPerson, setEventDraft]);

  const applyReview = useCallback((review) => {
    ++reviewReadGeneration.current;
    const staged = recognitionReviewState(review);
    setRecognition((current) => current?.reviewId === review.review_id ? { ...current, ...staged } : current);
  }, [setRecognition]);
  useEffect(() => {
    if (!canReview || !recognition?.reviewId) return;
    let active = true;
    const generation = reviewReadGeneration.current;
    apiGet(`/api/photo-review?review_id=${encodeURIComponent(recognition.reviewId)}`, { dedupe: false })
      .then((review) => { if (active && generation === reviewReadGeneration.current) applyReview(review); }).catch(() => {});
    return () => { active = false; };
  }, [canReview, recognition?.reviewId, apiGet, applyReview]);

  const runRecognition = useCallback(async (path, signal) => {
    const payload = await apiPost("/api/recognize", { path, quality_only: qualityOnly }, { signal, timeoutMs: 10 * 60 * 1000 });
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
    setRecognitionFollowup(null);
    setProofOnlyDuplicateCandidates([]);
    setRecognitionFollowupDone(false);
    const { date } = currentDateTimeParts();
    setEventDraft({ date, time: "", endTime: "", timePrecision: "unknown", placeSeen: "", eventOccasion: "", eventContext: "unknown", eventNotes: "", eventMentionedPersonIds: [] });
    showToast(`Recognized ${payload.faces.length} face(s)`);
  }, [apiPost, qualityOnly, showToast]);

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

  const enrollTargetFace = (faceIndex, forceBadQuality = false, conflictAcknowledged = false) => {
    // Explicit operator target is a Person contract, not a scored proposal.
    const target = recognitionTargetPerson;
    const face = recognition?.faces?.find((item) => item.index === faceIndex);
    if (!target?.person_id || !face) return;
    openRecognitionFollowup({ name: target.name, personId: target.person_id,
      decision: "existing", action: "existing", faceIndex, faceBox: face.box, forceBadQuality, conflictAcknowledged });
  };

  const recognitionNew = async (requestedFaceIndex, forceBadQuality = false) => {
    const faceIndex = requestedFaceIndex || selectedRecognitionFace;
    const face = recognition?.faces?.find((item) => item.index === faceIndex);
    if (!recognition?.inputPath || !face) return;
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
      quality_only: qualityOnly,
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
    setRecognitionFollowup(null);
    setProofOnlyDuplicateCandidates([]);
    setRecognitionFollowupDone(false);
    setEventDraft(null);
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

  const updateRecognitionEvent = (field, value) => {
    setEventDraft((current) => current ? { ...current, [field]: value } : current);
  };

  const confirmRecognitionEvent = (event) => {
    event.preventDefault();
    if (!eventDraft || !recognition) return;
    const confirmed = {
      ...eventDraft,
      time: eventDraft.timePrecision === "unknown" ? "" : eventDraft.time,
      endTime: eventDraft.timePrecision === "exact" ? eventDraft.endTime : "",
    };
    setRecognition((current) => current ? { ...current, encounterMetadata: confirmed } : current);
    setEventDraft(null);
  };

  const clearRecognitionFollowupForm = () => {
    const { date, time } = currentDateTimeParts();
    setRecognitionFollowup((current) => current ? {
      ...current,
      date: current.encounterLocked ? current.date : date,
      time: current.encounterLocked ? current.time : time,
      timePrecision: current.encounterLocked ? current.timePrecision : "exact",
      endTime: current.encounterLocked ? current.endTime : "",
      rank: "",
      placeSeen: current.encounterLocked ? current.placeSeen : "",
      individualCount: "",
      eventOccasion: current.encounterLocked ? current.eventOccasion : "",
      eventContext: current.encounterLocked ? current.eventContext : "unknown",
      eventNotes: current.encounterLocked ? current.eventNotes : "",
      country: "",
      importance: current.action === "new" ? NEW_PERSON_IMPORTANCE_OPTIONS[1] : "",
      addedBy: "",
      notes: "",
      mentionedPersonIds: [],
      name: current.action === "new" ? "" : current.name,
    } : current);
    setRecognitionFollowupDone(false);
  };

  const confirmRecognitionFollowup = async (event, createAnyway = false) => {
    event.preventDefault();
    if (!recognitionFollowup || !recognition?.reviewId) return;
    const addFaceOnly = Boolean(recognitionTargetPerson);
    if (recognitionFollowup.action === "new" && !addFaceOnly && !createAnyway) {
      const duplicateCheck = await apiPost("/api/proof-only-duplicate-check", {
        review_id: recognition.reviewId,
        face_id: `face-${recognitionFollowup.faceIndex}`,
      });
      if (duplicateCheck.candidates?.length) {
        setProofOnlyDuplicateCandidates(duplicateCheck.candidates);
        return;
      }
    }
    const review = await apiPost("/api/photo-review-decision", {
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
      notes: addFaceOnly ? "" : recognitionFollowup.notes,
      mentioned_person_ids: addFaceOnly ? [] : recognitionFollowup.mentionedPersonIds || [],
      recognition_detail: addFaceOnly ? {
        embedding_state: recognition?.faces?.find((face) => face.index === recognitionFollowup.faceIndex)?.quality?.status === "bad"
          ? (recognitionFollowup.forceBadQuality ? "POOR_ACCEPTED" : "PROOF_ONLY")
          : "GOOD",
      } : {
        image_id: recognitionFollowup.imageId,
        image_path: recognition.inputPath,
        name: recognitionFollowup.name,
        decision: recognitionFollowup.decision,
        date: recognitionFollowup.date,
        time: recognitionFollowup.time,
        time_precision: recognitionFollowup.timePrecision,
        end_time: recognitionFollowup.endTime,
        event_context: recognitionFollowup.eventContext,
        event_notes: recognitionFollowup.eventNotes,
        event_mentioned_person_ids: recognitionFollowup.eventMentionedPersonIds || [],
        rank: recognitionFollowup.rank,
        country: recognitionFollowup.country,
        importance: recognitionFollowup.importance,
        place_seen: recognitionFollowup.placeSeen,
        individual_count: Number(recognitionFollowup.individualCount),
        event_occasion: recognitionFollowup.eventOccasion,
        added_by: recognitionFollowup.addedBy,
        embedding_state: recognition?.faces?.find((face) => face.index === recognitionFollowup.faceIndex)?.quality?.status === "bad"
          ? (recognitionFollowup.forceBadQuality ? "POOR_ACCEPTED" : "PROOF_ONLY")
          : "GOOD",
        proof_only_duplicate_override: createAnyway,
      },
    });
    if (!addFaceOnly && !recognition?.encounterMetadata) setRecognition((current) => current ? ({
      ...current,
      encounterMetadata: {
        date: recognitionFollowup.date,
        time: recognitionFollowup.time,
        timePrecision: recognitionFollowup.timePrecision,
        endTime: recognitionFollowup.endTime,
        placeSeen: recognitionFollowup.placeSeen,
        eventOccasion: recognitionFollowup.eventOccasion,
        eventContext: recognitionFollowup.eventContext,
        eventNotes: recognitionFollowup.eventNotes,
        eventMentionedPersonIds: recognitionFollowup.eventMentionedPersonIds || [],
      },
    }) : current);
    setRecognitionFollowupDone(true);
    setRecognitionFollowup(null);
    setProofOnlyDuplicateCandidates([]);
    applyReview(review);
    if (addFaceOnly) {
      // Standalone enrollment explicitly selects this face; other detections
      // are not sightings or enrollment targets. Finalize through the existing
      // enrollment command, with durable negative decisions for those faces.
      for (const other of review.faces || []) {
        if (other.face_id !== `face-${recognitionFollowup.faceIndex}`) {
          applyReview(await apiPost("/api/photo-review-decision", { review_id: review.review_id, face_id: other.face_id, decision: "EXCLUDE" }));
        }
      }
      await finalizeRecognitionReview();
      return;
    }
    showToast("Face decision saved");
  };

  const useProofOnlyDuplicatePerson = (candidate) => {
    setProofOnlyDuplicateCandidates([]);
    setRecognitionFollowup((current) => current ? {
      ...current, action: "existing", decision: "existing",
      personId: candidate.person_id, name: candidate.name,
    } : current);
  };

  const createAfterProofOnlyDuplicateCheck = () => {
    setProofOnlyDuplicateCandidates([]);
    return confirmRecognitionFollowup({ preventDefault() {} }, true);
  };

  const setRecognitionFaceDecision = async (decision, faceIndex = selectedRecognitionFace) => {
    if (!recognition?.reviewId) return;
    const review = await apiPost("/api/photo-review-decision", {
      review_id: recognition.reviewId,
      face_id: `face-${faceIndex}`,
      decision,
    });
    applyReview(review);
  };

  const finalizeRecognitionReview = async () => {
    const result = await apiPost("/api/photo-review-complete", {
      review_id: recognition.reviewId,
      operation_id: recognition.completionOperationId,
      source: recognitionTargetPerson ? "add-face-review" : "check-photo",
      target_person_id: recognitionTargetPerson?.person_id,
    });
    await onGraphMutation?.(result);
    await loadPeople({ dedupe: false });
    if (recognitionTargetPerson?.person_id) {
      await onExistingPersonEnrolled?.(recognitionTargetPerson.person_id);
    }
    showToast("Review completed");
    setRecognitionTargetPerson(null);
    setEventDraft(null);
    setRecognition(null);
    setRecognitionFollowup(null);
  };

  const completeRecognitionReview = async () => {
    if (!recognition?.reviewId || !recognitionReviewReady(recognition.faces, decisions)) return;
    await finalizeRecognitionReview();
  };

  const openRecognitionGallery = async (personId) => {
    if (!personId) return;
    const payload = await apiGet(`/api/person?person_id=${encodeURIComponent(personId)}&view=effective`, { dedupe: false });
    requirePersonContract(payload.person);
    setRecognitionGallery(payload);
  };

  const recognitionSelectExisting = () => {
    setRecognitionFollowup(null);
    setRecognitionFollowupDone(false);
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
      date: recognition?.encounterMetadata?.date || date,
      time: recognition?.encounterMetadata?.time ?? time,
      timePrecision: recognition?.encounterMetadata?.timePrecision || "exact",
      endTime: recognition?.encounterMetadata?.endTime || "",
      rank: "",
      placeSeen: recognition?.encounterMetadata?.placeSeen || "",
      individualCount: "",
      eventOccasion: recognition?.encounterMetadata?.eventOccasion || "",
      eventContext: recognition?.encounterMetadata?.eventContext || "unknown",
      eventNotes: recognition?.encounterMetadata?.eventNotes || "",
      eventMentionedPersonIds: recognition?.encounterMetadata?.eventMentionedPersonIds || [],
      encounterLocked: Boolean(recognition?.encounterMetadata),
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
      recognitionFaceDecisions: decisions,
      recognitionReviewReady: recognitionReviewReady(recognition?.faces || [], decisions),
      recognitionFollowup,
      recognitionFollowupDone,
      recognitionProofOnlyDuplicateCandidates: proofOnlyDuplicateCandidates,
      recognitionTargetPerson,
      recognitionQualityOnly: qualityOnly,
      recognitionEventDraft: eventDraft,
    },
    refs: { recognizeFileRef },
    actions: {
      recognizeLoadedImage,
      setRecognitionQualityOnly: setQualityOnly,
      updateRecognitionEvent,
      confirmRecognitionEvent,
      recognitionAccept,
      enrollTargetFace,
      recognitionNew,
      recognitionSelectExisting,
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
      useProofOnlyDuplicatePerson,
      createAfterProofOnlyDuplicateCheck,
      skipRecognitionFace: (faceIndex) => setRecognitionFaceDecision("SKIP", faceIndex),
      discardRecognitionFace: (faceIndex) => setRecognitionFaceDecision("EXCLUDE", faceIndex),
      completeRecognitionReview,
      clearRecognitionFollowupForm,
    },
  };
}
