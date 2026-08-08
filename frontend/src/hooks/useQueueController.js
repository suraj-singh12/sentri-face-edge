import { useCallback, useEffect, useRef, useState } from "react";

import { NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import { currentDateTimeParts, droppedImageFiles, isNewPersonSuggestion } from "../utils.js";
import { usePersistentState } from "./usePersistentState.js";

export function useQueueController({
  enabled = true,
  apiDelete,
  apiGet,
  apiPost,
  updatePerson,
  upsertPerson,
  notifySkippedInputs,
  prepareImageFiles,
  showToast,
  uploadFile,
  uploadFolder,
}) {
  const [queueSessions, setQueueSessions] = useState([]);
  const [queueGroups, setQueueGroups] = useState([]);
  const [queueSessionId, setQueueSessionId] = usePersistentState("sentriface.queue.sessionId", "");
  const [queueProgress, setQueueProgress] = useState(null);
  const [queueSelectedGroup, setQueueSelectedGroup] = useState(null);
  const [queueSelectedGroupId, setQueueSelectedGroupId] = usePersistentState("sentriface.queue.selectedGroupId", "");
  const [queueSelectedFaces, setQueueSelectedFaces] = usePersistentState("sentriface.queue.selectedFaces", []);
  const [queueAccepted, setQueueAccepted] = usePersistentState("sentriface.queue.accepted", false);
  const [queueFollowup, setQueueFollowup] = usePersistentState("sentriface.queue.followup", null);
  const [queueFollowupDone, setQueueFollowupDone] = usePersistentState("sentriface.queue.followupDone", false);
  const [queueGallery, setQueueGallery] = useState(null);
  const [queueGalleryImage, setQueueGalleryImage] = useState(null);
  const [queueReviewStats, setQueueReviewStats] = useState(emptyQueueReviewStats);
  const canceledQueueJobs = useRef(new Set());
  const queueAbortControllers = useRef(new Map());
  const restoredQueueRef = useRef(false);

  const loadQueueGroups = useCallback(async (sessionId = queueSessionId, options = {}) => {
    if (!sessionId) {
      setQueueGroups([]);
      return;
    }
    const payload = await apiGet(`/api/queue-groups?session_id=${encodeURIComponent(sessionId)}`);
    setQueueSessionId(sessionId);
    setQueueGroups(payload.groups);
    const selectedGroupStillExists = !queueSelectedGroupId
      || payload.groups.some((group) => group.group_id === queueSelectedGroupId);
    if (!selectedGroupStillExists && !options.preserveSelectedGroup) {
      setQueueSelectedGroupId("");
      resetQueueDecision();
    }
    setQueueReviewStats((current) => current.totalGroups ? current : {
      ...emptyQueueReviewStats,
      totalGroups: payload.groups.length,
      totalFaces: payload.groups.reduce((total, group) => total + (group.faces?.length || 0), 0),
      skippedGroups: payload.groups.filter((group) => group.status === "skipped").length,
    });
    setQueueSelectedGroup((current) => {
      const desiredGroupId = current?.group_id || queueSelectedGroupId;
      if (!desiredGroupId) return null;
      const refreshedGroup = payload.groups.find((group) => group.group_id === desiredGroupId);
      if (refreshedGroup) return refreshedGroup;
      if (!options.preserveSelectedGroup) return null;
      const removedFaceIds = new Set(options.removeFaceIds || []);
      return removedFaceIds.size
        ? { ...current, faces: current.faces.filter((face) => !removedFaceIds.has(face.init_face_id)) }
        : current;
    });
    return payload;
  }, [apiGet, queueSelectedGroupId, queueSessionId, setQueueSessionId]);

  const loadQueueSessions = useCallback(async (preferredSessionId = queueSessionId) => {
    const payload = await apiGet("/api/queue-sessions");
    const sessions = payload.sessions || [];
    setQueueSessions(sessions);
    const selected = sessions.find((session) => session.session_id === preferredSessionId) || sessions[0] || null;
    if (!selected) {
      setQueueSessionId("");
      setQueueGroups([]);
      setQueueSelectedGroup(null);
      setQueueSelectedGroupId("");
      resetQueueDecision();
      return payload;
    }
    if (selected.session_id !== queueSessionId) {
      setQueueSelectedGroup(null);
      setQueueSelectedGroupId("");
      resetQueueDecision();
    }
    await loadQueueGroups(selected.session_id);
    return payload;
  }, [apiGet, loadQueueGroups, queueSessionId, setQueueSelectedGroupId, setQueueSessionId]);

  useEffect(() => {
    if (!enabled || restoredQueueRef.current) return;
    restoredQueueRef.current = true;
    loadQueueSessions().catch((error) => console.error("[sentriface-ui] unable to restore queue", error));
  }, [enabled, loadQueueSessions]);

  const removeClosedQueueSession = (sessionId) => {
    setQueueSessions((current) => current.filter((session) => session.session_id !== sessionId));
    if (queueSessionId === sessionId) {
      setQueueSessionId("");
      setQueueGroups([]);
    }
  };

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
    let progressRequestInFlight = false;
    pollId = window.setInterval(async () => {
      if (progressRequestInFlight) return;
      progressRequestInFlight = true;
      try {
        const payload = await apiGet(`/api/queue-progress?job_id=${encodeURIComponent(jobId)}`);
        if (canceledQueueJobs.current.has(jobId)) return;
        setQueueProgress((current) => normalizeQueueProgress({ ...current, ...payload, jobId, startedAt }));
      } catch {
        // Progress polling is advisory; the scan request remains authoritative.
      } finally {
        progressRequestInFlight = false;
      }
    }, 1000);
    try {
      const payload = await apiPost("/api/queue-scan", {
        path,
        job_id: jobId,
        total_files: options.totalFiles || 0,
        uploaded_files: options.uploadedFiles || options.totalFiles || 0,
        force_bad_quality: options.includeLowQuality !== false,
      }, { signal: options.signal });
      if (canceledQueueJobs.current.has(jobId)) return;
      const scanRejectedFiles = Number(payload.rejected_files || 0);
      if (scanRejectedFiles > 0) {
        notifySkippedInputs(
          scanRejectedFiles,
          Math.max(0, Number(options.uploadedFiles || options.totalFiles || 0) - scanRejectedFiles),
        );
      }
      setQueueSessionId(payload.session_id);
      setQueueGroups(payload.groups);
      setQueueSessions((current) => [
        queueSessionSummary(payload.session_id, payload.groups, path),
        ...current.filter((session) => session.session_id !== payload.session_id),
      ]);
      setQueueReviewStats({
        ...emptyQueueReviewStats,
        totalGroups: payload.groups.length,
        totalFaces: payload.groups.reduce((total, group) => total + (group.faces?.length || 0), 0),
      });
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
    } catch (error) {
      if (options.signal?.aborted || canceledQueueJobs.current.has(jobId)) return;
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
      canceledQueueJobs.current.delete(jobId);
      window.setTimeout(() => {
        setQueueProgress((current) => current?.jobId === jobId && current.status === "done" ? null : current);
      }, 900);
    }
  }, [apiGet, apiPost, notifySkippedInputs, setQueueSessionId, showToast]);

  const scanQueueFiles = async (files, options = {}) => {
    const prepared = await prepareImageFiles(files, options.source || "queue");
    const imageFiles = prepared.validFiles;
    if (!imageFiles.length) {
      setQueueProgress(null);
      if (prepared.rejected.length) {
        notifySkippedInputs(prepared.rejected.length, 0);
      } else {
        showToast("Choose or drop images", "yellow");
      }
      return;
    }
    const jobId = options.jobId || crypto.randomUUID();
    const startedAt = options.startedAt || Date.now();
    const abortController = new AbortController();
    queueAbortControllers.current.set(jobId, abortController);
    setQueueProgress({
      jobId,
      status: "running",
      phase: "uploading",
      totalFiles: imageFiles.length,
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
    try {
      const upload = imageFiles.length === 1
        ? await uploadFile(imageFiles[0], { onProgress, signal: abortController.signal })
        : await uploadFolder(imageFiles, { onProgress, signal: abortController.signal });
      const rejectedCount = prepared.rejected.length + upload.rejectedFiles;
      notifySkippedInputs(rejectedCount, upload.uploadedFiles);
      if (!upload.path) {
        setQueueProgress(null);
        return;
      }
      if (abortController.signal.aborted) return;
      await scanQueuePath(upload.path, {
        jobId,
        totalFiles: upload.uploadedFiles,
        uploadedFiles: upload.uploadedFiles,
        signal: abortController.signal,
      });
    } catch (error) {
      if (abortController.signal.aborted || error?.name === "AbortError") return;
      setQueueProgress((current) => normalizeQueueProgress({
        ...current,
        jobId,
        status: "failed",
        phase: "failed",
        error: readableUploadError(error),
        finishedAt: Date.now(),
      }));
      throw error;
    } finally {
      queueAbortControllers.current.delete(jobId);
      canceledQueueJobs.current.delete(jobId);
    }
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
    await scanQueueFiles(files, { jobId, startedAt, source: "queue-drop" });
  };

  const cancelQueueProcessing = async () => {
    if (queueProgress?.status === "failed") {
      setQueueProgress(null);
      return;
    }
    const jobId = queueProgress?.jobId;
    if (!jobId) return;
    const previousPhase = queueProgress.phase;
    const abortController = queueAbortControllers.current.get(jobId);
    canceledQueueJobs.current.add(jobId);

    if (previousPhase === "uploading") {
      abortController?.abort();
      setQueueProgress(null);
      showToast("Queue upload canceled", "yellow");
      return;
    }

    setQueueProgress((current) => current?.jobId === jobId
      ? { ...current, status: "cancelling", phase: "cancelling" }
      : current);
    try {
      const cancellation = await apiPost("/api/queue-cancel", { job_id: jobId }, { silent: true });
      if (!cancellation.cancel_requested && cancellation.status === "done") {
        canceledQueueJobs.current.delete(jobId);
        abortController?.abort();
        setQueueProgress(null);
        await loadQueueSessions();
        showToast("Queue processing had already finished", "yellow");
        return;
      }
      // Abort the original HTTP request only after the independent cancellation
      // request reached the server. Then wait for backend rollback/cleanup.
      abortController?.abort();
      const deadline = Date.now() + 30_000;
      let terminal = null;
      while (Date.now() < deadline) {
        const snapshot = await apiGet(
          `/api/queue-progress?job_id=${encodeURIComponent(jobId)}`,
          { silent: true, timeoutMs: 5_000 },
        );
        setQueueProgress((current) => current?.jobId === jobId
          ? normalizeQueueProgress({ ...current, ...snapshot, jobId })
          : current);
        if (["cancelled", "done", "failed"].includes(snapshot.status)) {
          terminal = snapshot;
          break;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 750));
      }
      if (terminal?.status === "cancelled") {
        setQueueProgress(null);
        showToast("Queue processing canceled and temporary files cleaned up", "yellow");
      } else if (terminal?.status === "done") {
        canceledQueueJobs.current.delete(jobId);
        setQueueProgress(null);
        await loadQueueSessions();
        showToast("Queue processing had already finished", "yellow");
      } else if (terminal?.status === "failed") {
        throw new Error(terminal.error || "Queue cleanup failed after cancellation");
      } else {
        showToast(
          "Cancellation was accepted. Backend cleanup is still finishing; keep SentriFace open.",
          "yellow",
          { title: "Cleanup still in progress", autoClose: 8000 },
        );
      }    } catch (error) {
      canceledQueueJobs.current.delete(jobId);
      setQueueProgress((current) => current?.jobId === jobId
        ? { ...current, status: "running", phase: previousPhase }
        : current);
      showToast(
        error?.message || "The server could not cancel queue processing",
        "red",
        { title: "Cancellation failed" },
      );
    }
  };

  const openQueueGroup = (group) => {
    setQueueSelectedGroup(group);
    setQueueSelectedGroupId(group.group_id);
    resetQueueDecision();
    setQueueSelectedFaces(group.faces.map((face) => face.init_face_id));
  };

  const selectQueueSession = async (sessionId) => {
    if (!sessionId || sessionId === queueSessionId) return;
    setQueueSelectedGroup(null);
    setQueueSelectedGroupId("");
    resetQueueDecision();
    setQueueReviewStats(emptyQueueReviewStats);
    await loadQueueGroups(sessionId);
  };

  const discardQueueSession = async () => {
    if (!queueSessionId) return;
    const discardedSessionId = queueSessionId;
    await apiDelete(`/api/queue-session?session_id=${encodeURIComponent(discardedSessionId)}`);
    setQueueProgress(null);
    setQueueSessionId("");
    setQueueGroups([]);
    setQueueSelectedGroup(null);
    setQueueSelectedGroupId("");
    resetQueueDecision();
    setQueueReviewStats(emptyQueueReviewStats);
    const remaining = queueSessions.filter((session) => session.session_id !== discardedSessionId);
    setQueueSessions(remaining);
    if (remaining[0]) await loadQueueGroups(remaining[0].session_id);
    showToast("Queue session and its pending photos were discarded", "yellow");
  };

  const toggleQueueFace = (faceId) => {
    if (queueAccepted) return;
    setQueueSelectedFaces((current) => (
      current.includes(faceId) ? current.filter((item) => item !== faceId) : [...current, faceId]
    ));
  };

  const selectAllQueueFaces = () => {
    if (queueAccepted) return;
    setQueueSelectedFaces((queueSelectedGroup?.faces || []).map((face) => face.init_face_id));
  };

  const clearQueueFaces = () => {
    if (queueAccepted) return;
    setQueueSelectedFaces([]);
  };

  const queueAcceptExisting = async (selectedPerson = null) => {
    const best = selectedPerson || queueSelectedGroup?.matches?.[0];
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
    const payload = await apiPost("/api/queue-discard", {
      session_id: queueSelectedGroup.session_id,
      group_id: queueSelectedGroup.group_id,
      face_ids: faceIds,
    });
    showToast(`Discarded ${faceIds.length} face(s)`);
    resetQueueDecision();
    setQueueSelectedGroup(null);
    setQueueSelectedGroupId("");
    if (payload.session_closed) {
      setQueueProgress(null);
      removeClosedQueueSession(queueSelectedGroup.session_id);
    }
    setQueueGroups(payload.groups || []);
    if (!payload.session_closed) setQueueSessions((current) => current.map((session) => session.session_id === queueSelectedGroup.session_id
        ? queueSessionSummary(session.session_id, payload.groups, session.source_path, session.created_at)
        : session));
  };

  const discardQueueGroup = async (group) => {
    if (!group?.faces?.length) return;
    const payload = await apiPost("/api/queue-discard", {
      session_id: group.session_id,
      group_id: group.group_id,
      face_ids: group.faces.map((face) => face.init_face_id),
    });
    if (queueSelectedGroup?.group_id === group.group_id) {
      setQueueSelectedGroup(null);
      setQueueSelectedGroupId("");
      resetQueueDecision();
    }
    if (payload.session_closed) {
      setQueueProgress(null);
      removeClosedQueueSession(group.session_id);
    }
    setQueueGroups(payload.groups || []);
    if (!payload.session_closed) setQueueSessions((current) => current.map((session) => session.session_id === group.session_id
        ? queueSessionSummary(session.session_id, payload.groups, session.source_path, session.created_at)
        : session));
    showToast(`Discarded group with ${group.faces.length} face(s)`, "yellow");
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
      notes: "",
      mentionedPersonIds: [],
      name: current.action === "new" ? "" : current.name,
    } : current);
    setQueueFollowupDone(false);
  };

  const confirmQueueFollowup = async (event) => {
    event.preventDefault();
    if (!queueFollowup?.faceIds?.length || !queueSelectedGroup) return;
    const confirmedSessionId = queueSelectedGroup.session_id;
    const payload = queueFollowup.action === "new"
      ? await apiPost("/api/queue-confirm-new", {
        session_id: queueSelectedGroup.session_id,
        group_id: queueSelectedGroup.group_id,
        face_ids: queueFollowup.faceIds,
        name: queueFollowup.name,
        notes: queueFollowup.notes,
        mentioned_person_ids: queueFollowup.mentionedPersonIds || [],
        operation_id: queueFollowup.identityOperationId,
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
      })
      : await apiPost("/api/queue-confirm-existing", {
        session_id: queueSelectedGroup.session_id,
        group_id: queueSelectedGroup.group_id,
        face_ids: queueFollowup.faceIds,
        person_id: queueFollowup.personId,
        operation_id: queueFollowup.identityOperationId,
        notes: queueFollowup.notes,
        mentioned_person_ids: queueFollowup.mentionedPersonIds || [],
        name: queueFollowup.name,
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
      });
    const personId = payload.person_id || queueFollowup.personId;
    const entries = payload.accepted || [];
    if (payload.session_closed) removeClosedQueueSession(confirmedSessionId);
    else {
      setQueueGroups(payload.groups || []);
      setQueueSessions((current) => current.map((session) => session.session_id === confirmedSessionId
        ? queueSessionSummary(session.session_id, payload.groups, session.source_path, session.created_at)
        : session));
    }
    setQueueFollowupDone(true);
    setQueueSelectedFaces([]);
    setQueueAccepted(false);
    setQueueGallery(null);
    setQueueGalleryImage(null);
    setQueueReviewStats((current) => ({
      ...current,
      reviewedGroups: current.reviewedGroups + 1,
      processedFaces: current.processedFaces + entries.length,
      personsUpdated: current.personsUpdated + (entries.length ? 1 : 0),
      activities: [
        ...current.activities,
        {
          label: queueFollowup.name || "New person",
          detail: `${entries.length} photo${entries.length === 1 ? "" : "s"} confirmed`,
        },
      ],
    }));
    if (queueFollowup.action === "new") {
      upsertPerson({
        person_id: personId,
        name: queueFollowup.name,
        enrollment_status: "enrolled",
        is_placeholder: false,
        embedding_count: entries.length,
        representative_image: entries[0]?.image_path || "",
        favorite: false,
        tags: [],
        notes: queueFollowup.notes?.trim() || "",
        created_at: new Date().toISOString(),
        metadata: {
          rank: queueFollowup.rank || "",
          country: queueFollowup.country || "",
          importance: queueFollowup.importance || "",
          added_by: queueFollowup.addedBy || "",
        },
      });
    } else {
      updatePerson(personId, (person) => ({
        ...person,
        enrollment_status: "enrolled",
        is_placeholder: false,
        embedding_count: Number(person.embedding_count || 0) + entries.length,
        representative_image: person.representative_image || entries[0]?.image_path || "",
      }));
    }
    showToast(`Queue details confirmed for ${entries.length} face(s)`);
    window.setTimeout(() => {
      setQueueFollowup(null);
      setQueueFollowupDone(false);
      setQueueSelectedGroup(null);
      setQueueSelectedGroupId("");
    }, 1000);
  };

  const queueSkipGroup = async () => {
    if (!queueSelectedGroup) return;
    const payload = await apiPost("/api/queue-skip", {
      session_id: queueSelectedGroup.session_id,
      group_id: queueSelectedGroup.group_id,
    });
    setQueueGroups(payload.groups);
    setQueueSessions((current) => current.map((session) => session.session_id === queueSessionId
      ? queueSessionSummary(session.session_id, payload.groups, session.source_path, session.created_at)
      : session));
    setQueueReviewStats((current) => ({
      ...current,
      skippedGroups: current.skippedGroups + 1,
      activities: [...current.activities, {
        label: queueSelectedGroup.group_id,
        detail: `${queueSelectedGroup.faces.length} photo${queueSelectedGroup.faces.length === 1 ? "" : "s"} skipped`,
      }],
    }));
    showToast("Group skipped for now", "yellow");
    setQueueSelectedGroup(null);
    resetQueueDecision();
  };

  const queueResumeSkipped = async () => {
    if (!queueSessionId) return;
    const payload = await apiPost("/api/queue-resume-skipped", { session_id: queueSessionId });
    setQueueGroups(payload.groups);
    setQueueSessions((current) => current.map((session) => session.session_id === queueSessionId
      ? queueSessionSummary(session.session_id, payload.groups, session.source_path, session.created_at)
      : session));
    setQueueReviewStats((current) => ({ ...current, skippedGroups: 0 }));
    showToast(`Restored ${payload.resumed} skipped group(s)`);
  };

  const queueRejectSuggestedMatch = async () => {
    const best = queueSelectedGroup?.matches?.[0];
    if (!queueSelectedGroup || !best) return;
    const payload = await apiPost("/api/queue-reject-match", {
      session_id: queueSelectedGroup.session_id,
      group_id: queueSelectedGroup.group_id,
      person_id: best.person_id,
    });
    setQueueGroups(payload.groups);
    setQueueSessions((current) => current.map((session) => session.session_id === queueSessionId
      ? queueSessionSummary(session.session_id, payload.groups, session.source_path, session.created_at)
      : session));
    setQueueSelectedGroup(null);
    resetQueueDecision();
    showToast(`Removed ${best.name} as the suggestion`, "yellow");
  };

  const loadQueuePeopleCandidates = async (sessionId, groupId) => apiGet(
    `/api/queue-person-candidates?session_id=${encodeURIComponent(sessionId)}&group_id=${encodeURIComponent(groupId)}`,
  );

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
    return selectedQueueFaceIds();
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
      notes: "",
      mentionedPersonIds: [],
      name,
      personId,
      decision,
      action,
      faceIds,
      identityOperationId: crypto.randomUUID(),
      followupOperationIds: Object.fromEntries(faceIds.map((faceId) => [faceId, crypto.randomUUID()])),
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
    setQueueSelectedGroupId("");
    resetQueueDecision();
  }

  function closeQueueReview() {
    setQueueSelectedGroup(null);
    setQueueSelectedGroupId("");
    resetQueueDecision();
  }

  return {
    state: {
      queueSessions,
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
      queueReviewStats,
    },
    actions: {
      scanQueueFiles,
      queueDrop,
      cancelQueueProcessing,
      loadQueueGroups,
      loadQueueSessions,
      selectQueueSession,
      discardQueueSession,
      openQueueGroup,
      toggleQueueFace,
      selectAllQueueFaces,
      clearQueueFaces,
      queueAcceptExisting,
      queueNewPerson,
      queueDiscard,
      discardQueueGroup,
      queueSkipGroup,
      queueResumeSkipped,
      queueRejectSuggestedMatch,
      loadQueuePeopleCandidates,
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

const emptyQueueReviewStats = {
  totalGroups: 0,
  totalFaces: 0,
  reviewedGroups: 0,
  processedFaces: 0,
  personsUpdated: 0,
  skippedGroups: 0,
  activities: [],
};

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
    error: progress.error || "",
  };
}

function queueSessionSummary(sessionId, groups = [], sourcePath = "", createdAt = "") {
  return {
    session_id: sessionId,
    source_path: sourcePath,
    status: "pending",
    created_at: createdAt || new Date().toISOString(),
    group_count: groups.length,
    face_count: groups.reduce((total, group) => total + (group.faces?.length || 0), 0),
    pending_count: groups.filter((group) => group.status === "pending" && group.faces?.length).length,
    skipped_count: groups.filter((group) => group.status === "skipped" && group.faces?.length).length,
  };
}

function readableUploadError(error) {
  const message = String(error?.message || error || "Upload failed");
  if (message.includes("codec can't decode") || message.includes("Unknown endpoint")) {
    return "The app server was out of date. Reload the page and select the folder again.";
  }
  if (/failed to fetch|networkerror/i.test(message)) {
    return "The server connection was interrupted. Check that SentriFace is running, then try again.";
  }
  return message;
}
