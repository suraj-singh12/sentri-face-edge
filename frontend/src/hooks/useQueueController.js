import { useCallback, useState } from "react";

import { NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import { currentDateTimeParts, droppedImageFiles, isNewPersonSuggestion } from "../utils.js";

export function useQueueController({ apiGet, apiPost, loadEvents, loadPeople, showToast, uploadFile, uploadFolder }) {
  const [queueGroups, setQueueGroups] = useState([]);
  const [queueSessionId, setQueueSessionId] = useState("");
  const [queueSelectedGroup, setQueueSelectedGroup] = useState(null);
  const [queueSelectedFaces, setQueueSelectedFaces] = useState([]);
  const [queueAccepted, setQueueAccepted] = useState(false);
  const [queueFollowup, setQueueFollowup] = useState(null);
  const [queueFollowupDone, setQueueFollowupDone] = useState(false);
  const [queueGallery, setQueueGallery] = useState(null);
  const [queueGalleryImage, setQueueGalleryImage] = useState(null);

  const loadQueueGroups = useCallback(async (sessionId = queueSessionId) => {
    if (!sessionId) return;
    const payload = await apiGet(`/api/queue-groups?session_id=${encodeURIComponent(sessionId)}`);
    setQueueGroups(payload.groups);
    setQueueSelectedGroup((current) => {
      if (!current) return current;
      return payload.groups.find((group) => group.group_id === current.group_id) || null;
    });
  }, [apiGet, queueSessionId]);

  const scanQueuePath = useCallback(async (path) => {
    const payload = await apiPost("/api/queue-scan", { path });
    setQueueSessionId(payload.session_id);
    setQueueGroups(payload.groups);
    resetQueueReview();
    showToast(`Queued ${payload.groups.length} group(s)`);
    await loadEvents();
  }, [apiPost, loadEvents, showToast]);

  const scanQueueFiles = async (files) => {
    if (!files.length) {
      showToast("Choose or drop images", "yellow");
      throw new Error("Missing queue source");
    }
    await scanQueuePath(files.length === 1 ? await uploadFile(files[0]) : await uploadFolder(files));
  };

  const queueDrop = async (event) => {
    event.preventDefault();
    const files = await droppedImageFiles(event.dataTransfer);
    if (!files.length) {
      showToast("Drop image files or a folder", "yellow");
      return;
    }
    await scanQueueFiles(files);
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
    const faceIds = selectedQueueFaceIds();
    setQueueAccepted(true);
    openQueueFollowup({ name: best.name, personId: best.person_id, decision: "existing", action: "existing", faceIds });
    showToast(`Fill details for ${best.name}`);
  };

  const queueNewPerson = async () => {
    if (!queueSelectedGroup) return;
    const faceIds = selectedQueueFaceIds();
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
    showToast(`Discarded ${faceIds.length} image(s)`);
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
    resetQueueDecision();
    showToast(`Queue details confirmed for ${entries.length} image(s)`);
    await Promise.all([loadQueueGroups(queueSelectedGroup.session_id), loadPeople(), loadEvents()]);
  };

  const openQueueGallery = async (personId) => {
    if (!personId) return;
    setQueueGallery(await apiGet(`/api/person?person_id=${encodeURIComponent(personId)}`));
    setQueueGalleryImage(null);
  };

  const queueGalleryBack = () => {
    if (queueGalleryImage) setQueueGalleryImage(null);
    else setQueueGallery(null);
  };

  function selectedQueueFaceIds() {
    if (!queueSelectedFaces.length) {
      showToast("Select images first", "yellow");
      throw new Error("No queue images selected");
    }
    return queueSelectedFaces;
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
      setQueueGalleryImage,
      queueGalleryBack,
      closeQueueReview,
    },
  };
}
