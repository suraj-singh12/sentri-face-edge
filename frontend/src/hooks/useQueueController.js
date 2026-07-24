import { useCallback, useRef, useState } from "react";

import { NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import { currentDateTimeParts, droppedImageFiles, isNewPersonSuggestion } from "../utils.js";

export function useQueueController({ apiGet, apiPost, loadEvents, loadPeople, showToast, uploadFile, uploadFolder }) {
  const [queueGroups, setQueueGroups] = useState([]);
  const [queueSessionId, setQueueSessionId] = useState("");
  const [queueProgress, setQueueProgress] = useState(null);
  const [queueSelectedGroup, setQueueSelectedGroup] = useState(null);
  const [queueSelectedFaces, setQueueSelectedFaces] = useState([]);
  const [queueAccepted, setQueueAccepted] = useState(false);
  const [queueFollowup, setQueueFollowup] = useState(null);
  const [queueFollowupDone, setQueueFollowupDone] = useState(false);
  const [queueGallery, setQueueGallery] = useState(null);
  const [queueGalleryImage, setQueueGalleryImage] = useState(null);
  const canceledQueueJobs = useRef(new Set());

  const loadQueueGroups = useCallback(async (sessionId = queueSessionId, options = {}) => {
    if (!sessionId) return;
    const payload = await apiGet(`/api/queue-groups?session_id=${encodeURIComponent(sessionId)}`);
    setQueueGroups(payload.groups);
    setQueueSelectedGroup((current) => {
      if (!current) return current;
      const refreshedGroup = payload.groups.find((group) => group.group_id === current.group_id);
      if (refreshedGroup) return refreshedGroup;
      if (!options.preserveSelectedGroup) return null;
      const removedFaceIds = new Set(options.removeFaceIds || []);
      return removedFaceIds.size
        ? { ...current, faces: current.faces.filter((face) => !removedFaceIds.has(face.init_face_id)) }
        : current;
    });
    return payload;
  }, [apiGet, queueSessionId]);

  const scanQueuePath = useCallback(async (path, options = {}) => {
    const jobId = options.jobId || crypto.randomUUID();
    const startedAt = Date.now();
    let pollId = null;
    setQueueProgress((current) => ({
      ...current,
      jobId,
      status: "running",
      phase: "scanning",
      startedAt,
      totalFiles: options.totalFiles || current?.totalFiles || 0,
      uploadedFiles: options.uploadedFiles || current?.uploadedFiles || 0,
    }));
    pollId = window.setInterval(async () => {
      try {
        const payload = await apiGet(`/api/queue-progress?job_id=${encodeURIComponent(jobId)}`);
        if (canceledQueueJobs.current.has(jobId)) return;
        setQueueProgress((current) => normalizeQueueProgress({ ...current, ...payload, jobId, startedAt }));
      } catch (error) {
        console.debug("[sentriface-ui] queue progress unavailable", error);
      }
    }, 450);
    try {
      const payload = await apiPost("/api/queue-scan", {
        path,
        job_id: jobId,
        total_files: options.totalFiles || 0,
        uploaded_files: options.uploadedFiles || options.totalFiles || 0,
        force_bad_quality: options.includeLowQuality !== false,
      });
      if (canceledQueueJobs.current.has(jobId)) return;
      setQueueSessionId(payload.session_id);
      setQueueGroups(payload.groups);
      resetQueueReview();
      const faceCount = payload.groups.reduce((total, group) => total + (group.faces?.length || 0), 0);
      showToast(`Queued ${faceCount} face(s) in ${payload.groups.length} group(s)`);
      setQueueProgress((current) => normalizeQueueProgress({
        ...current,
        jobId,
        status: "done",
        phase: "done",
        session_id: payload.session_id,
        groups: payload.groups.length,
        finishedAt: Date.now(),
      }));
      await loadEvents();
    } catch (error) {
      setQueueProgress((current) => normalizeQueueProgress({
        ...current,
        jobId,
        status: "failed",
        phase: "failed",
        finishedAt: Date.now(),
      }));
      throw error;
    } finally {
      if (pollId) window.clearInterval(pollId);
      window.setTimeout(() => {
        setQueueProgress((current) => current?.jobId === jobId && current.status === "done" ? null : current);
      }, 900);
    }
  }, [apiGet, apiPost, loadEvents, showToast]);

  const scanQueueFiles = async (files, options = {}) => {
    if (!files.length) {
      showToast("Choose or drop images", "yellow");
      throw new Error("Missing queue source");
    }
    const jobId = options.jobId || crypto.randomUUID();
    const startedAt = options.startedAt || Date.now();
    setQueueProgress({
      jobId,
      status: "running",
      phase: "uploading",
      totalFiles: files.length,
      uploadedFiles: 0,
      totalImages: 0,
      imagesScanned: 0,
      facesDetected: 0,
      embeddingsGenerated: 0,
      groups: 0,
      startedAt,
    });
    const onProgress = (progress) => {
      setQueueProgress((current) => normalizeQueueProgress({ ...current, ...progress, jobId, startedAt }));
    };
    const path = files.length === 1
      ? await uploadFile(files[0], { onProgress })
      : await uploadFolder(files, { onProgress });
    await scanQueuePath(path, { jobId, totalFiles: files.length, uploadedFiles: files.length });
  };

  const queueDrop = async (event) => {
    event.preventDefault();
    const jobId = crypto.randomUUID();
    const startedAt = Date.now();
    setQueueProgress({
      jobId,
      status: "running",
      phase: "uploading",
      totalFiles: 0,
      uploadedFiles: 0,
      totalImages: 0,
      imagesScanned: 0,
      facesDetected: 0,
      embeddingsGenerated: 0,
      groups: 0,
      startedAt,
    });
    const files = await droppedImageFiles(event.dataTransfer);
    if (!files.length) {
      setQueueProgress(null);
      showToast("Drop image files or a folder", "yellow");
      return;
    }
    await scanQueueFiles(files, { jobId, startedAt });
  };

  const cancelQueueProcessing = () => {
    setQueueProgress((current) => {
      if (current?.jobId) canceledQueueJobs.current.add(current.jobId);
      return null;
    });
    showToast("Stopped tracking queue processing", "yellow");
  };

  const openQueueGroup = (group) => {
    setQueueSelectedGroup(group);
    resetQueueDecision();
  };

  const toggleQueueFace = (faceId) => {
    if (queueAccepted) return;
    setQueueSelectedFaces((current) => (
      current.includes(faceId) ? current.filter((item) => item !== faceId) : [...current, faceId]
    ));
  };

  const queueAcceptExisting = async () => {
    const best = queueSelectedGroup?.matches?.[0];
    if (!queueSelectedGroup || !best || isNewPersonSuggestion(best)) return;
    const faceIds = selectedOrGroupFaceIds();
    setQueueAccepted(true);
    openQueueFollowup({ name: best.name, personId: best.person_id, decision: "existing", action: "existing", faceIds });
    showToast(`Fill details for ${best.name}`);
  };

  const queueNewPerson = async () => {
    if (!queueSelectedGroup) return;
    const faceIds = selectedOrGroupFaceIds();
    setQueueAccepted(true);
    openQueueFollowup({ name: "", personId: "", decision: "new", action: "new", faceIds });
    showToast("Fill new person details");
  };

  const queueDiscard = async () => {
    if (!queueSelectedGroup) return;
    const faceIds = selectedQueueFaceIds();
    await apiPost("/api/queue-discard", {
      session_id: queueSelectedGroup.session_id,
      group_id: queueSelectedGroup.group_id,
      face_ids: faceIds,
    });
    showToast(`Discarded ${faceIds.length} face(s)`);
    resetQueueDecision();
    await Promise.all([loadQueueGroups(queueSelectedGroup.session_id), loadEvents()]);
  };

  const updateQueueFollowup = (field, value) => {
    setQueueFollowup((current) => current ? { ...current, [field]: value } : current);
  };

  const clearQueueFollowupForm = () => {
    const { date, time } = currentDateTimeParts();
    setQueueFollowup((current) => current ? {
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
    setQueueFollowupDone(false);
  };

  const confirmQueueFollowup = async (event) => {
    event.preventDefault();
    if (!queueFollowup?.faceIds?.length || !queueSelectedGroup) return;
    const confirmedGroupId = queueSelectedGroup.group_id;
    const confirmedSessionId = queueSelectedGroup.session_id;
    const confirmedFaceIds = queueFollowup.faceIds;
    const payload = queueFollowup.action === "new"
      ? await apiPost("/api/queue-confirm-new", {
        session_id: queueSelectedGroup.session_id,
        group_id: queueSelectedGroup.group_id,
        face_ids: queueFollowup.faceIds,
        name: queueFollowup.name,
      })
      : await apiPost("/api/queue-confirm-existing", {
        session_id: queueSelectedGroup.session_id,
        group_id: queueSelectedGroup.group_id,
        face_ids: queueFollowup.faceIds,
        person_id: queueFollowup.personId,
      });
    const personId = payload.person_id || queueFollowup.personId;
    const entries = payload.accepted || [];
    await Promise.all(entries.map((entry) => apiPost("/api/recognition-followup", {
      path: entry.image_path,
      name: queueFollowup.name,
      person_id: personId,
      embedding_id: entry.embedding_id,
      image_id: entry.image_id,
      image_path: entry.image_path,
      decision: queueFollowup.decision,
      date: queueFollowup.date,
      time: queueFollowup.time,
      rank: queueFollowup.rank,
      country: queueFollowup.country,
      importance: queueFollowup.importance,
      place_seen: queueFollowup.placeSeen,
      individual_count: Number(queueFollowup.individualCount),
      event_occasion: queueFollowup.eventOccasion,
      added_by: queueFollowup.addedBy,
    })));
    setQueueFollowupDone(true);
    setQueueSelectedFaces([]);
    setQueueAccepted(false);
    setQueueGallery(null);
    setQueueGalleryImage(null);
    showToast(`Queue details confirmed for ${entries.length} face(s)`);
    const [queuePayload] = await Promise.all([
      loadQueueGroups(confirmedSessionId, { preserveSelectedGroup: true, removeFaceIds: confirmedFaceIds }),
      loadPeople(),
      loadEvents(),
    ]);
    window.setTimeout(() => {
      setQueueFollowup(null);
      setQueueFollowupDone(false);
      setQueueSelectedGroup((current) => {
        if (!current || current.group_id !== confirmedGroupId) return current;
        return queuePayload?.groups?.find((group) => group.group_id === confirmedGroupId) || null;
      });
    }, 1000);
  };

  const openQueueGallery = async (personId) => {
    if (!personId) return;
    setQueueGallery(await apiGet(`/api/person?person_id=${encodeURIComponent(personId)}`));
  };

  const queueGalleryBack = () => {
    setQueueGallery(null);
  };

  const selectQueueGalleryImage = (path) => {
    const embedding = queueGallery?.embeddings?.find((record) => (
      record.source_image === path || record.crop_path === path
    ));
    setQueueGalleryImage(embedding?.source_image || path);
  };

  function selectedQueueFaceIds() {
    if (!queueSelectedFaces.length) {
      showToast("Select faces first", "yellow");
      throw new Error("No queue faces selected");
    }
    return queueSelectedFaces;
  }

  function selectedOrGroupFaceIds() {
    if (queueSelectedFaces.length) return queueSelectedFaces;
    const faceIds = (queueSelectedGroup?.faces || []).map((face) => face.init_face_id);
    if (!faceIds.length) {
      throw new Error("No queue faces available");
    }
    return faceIds;
  }

  function openQueueFollowup({ name, personId, decision, action, faceIds }) {
    const { date, time } = currentDateTimeParts();
    setQueueFollowup({
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
      decision,
      action,
      faceIds,
    });
    setQueueFollowupDone(false);
  }

  function resetQueueDecision() {
    setQueueSelectedFaces([]);
    setQueueAccepted(false);
    setQueueFollowup(null);
    setQueueFollowupDone(false);
    setQueueGallery(null);
    setQueueGalleryImage(null);
  }

  function resetQueueReview() {
    setQueueSelectedGroup(null);
    resetQueueDecision();
  }

  function closeQueueReview() {
    setQueueSelectedGroup(null);
    resetQueueDecision();
  }

  return {
    state: {
      queueGroups,
      queueSessionId,
      queueProgress,
      queueSelectedGroup,
      queueSelectedFaces,
      queueAccepted,
      queueFollowup,
      queueFollowupDone,
      queueGallery,
      queueGalleryImage,
    },
    actions: {
      scanQueueFiles,
      queueDrop,
      cancelQueueProcessing,
      loadQueueGroups,
      openQueueGroup,
      toggleQueueFace,
      queueAcceptExisting,
      queueNewPerson,
      queueDiscard,
      updateQueueFollowup,
      confirmQueueFollowup,
      clearQueueFollowupForm,
      openQueueGallery,
      setQueueGalleryImage: selectQueueGalleryImage,
      queueGalleryBack,
      closeQueueReview,
    },
  };
}

function normalizeQueueProgress(progress) {
  return {
    jobId: progress.jobId || progress.job_id,
    status: progress.status || "running",
    phase: progress.phase || "uploading",
    totalFiles: Number(progress.totalFiles ?? progress.total_files ?? 0),
    uploadedFiles: Number(progress.uploadedFiles ?? progress.uploaded_files ?? 0),
    totalImages: Number(progress.totalImages ?? progress.total_images ?? 0),
    imagesScanned: Number(progress.imagesScanned ?? progress.images_scanned ?? 0),
    facesDetected: Number(progress.facesDetected ?? progress.faces_detected ?? 0),
    embeddingsGenerated: Number(progress.embeddingsGenerated ?? progress.embeddings_generated ?? 0),
    groups: Number(progress.groups ?? 0),
    startedAt: progress.startedAt || progress.started_at || Date.now(),
    finishedAt: progress.finishedAt || progress.finished_at || null,
    elapsedSeconds: Number(progress.elapsedSeconds ?? progress.elapsed_seconds ?? 0),
  };
}
