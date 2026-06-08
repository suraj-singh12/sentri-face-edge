import { useCallback, useEffect, useRef, useState } from "react";
import { notifications } from "@mantine/notifications";

import { DUPLICATE_MATCH_SCORE, NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import {
  clearFile,
  currentDateTimeParts,
  droppedImageFiles,
  imageIdFromPath,
  isNewPersonSuggestion,
  readFileAsDataUrl,
} from "../utils.js";

export function useSentriFaceController() {
  const [activeView, setActiveView] = useState("recognize");
  const [profile, setProfile] = useState(null);
  const [people, setPeople] = useState([]);
  const [peopleGallery, setPeopleGallery] = useState(null);
  const [peopleGalleryImage, setPeopleGalleryImage] = useState(null);
  const [queueGroups, setQueueGroups] = useState([]);
  const [queueSessionId, setQueueSessionId] = useState("");
  const [queueSelectedGroup, setQueueSelectedGroup] = useState(null);
  const [queueSelectedFaces, setQueueSelectedFaces] = useState([]);
  const [queueAccepted, setQueueAccepted] = useState(false);
  const [queueFollowup, setQueueFollowup] = useState(null);
  const [queueFollowupDone, setQueueFollowupDone] = useState(false);
  const [queueGallery, setQueueGallery] = useState(null);
  const [queueGalleryImage, setQueueGalleryImage] = useState(null);
  const [events, setEvents] = useState([]);
  const [recognition, setRecognition] = useState(null);
  const [recognitionGallery, setRecognitionGallery] = useState(null);
  const [recognitionGalleryImage, setRecognitionGalleryImage] = useState(null);
  const [recognitionAccepted, setRecognitionAccepted] = useState(false);
  const [recognitionFollowup, setRecognitionFollowup] = useState(null);
  const [recognitionFollowupDone, setRecognitionFollowupDone] = useState(false);

  const recognizeFileRef = useRef(null);

  const showToast = useCallback((message, color = "teal") => {
    notifications.show({ message, color, autoClose: 2400 });
  }, []);

  const readResponse = useCallback(async (response) => {
    const contentType = response.headers.get("Content-Type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : { error: await response.text() || response.statusText };
    console.debug("[sentriface-ui] response", response.status, payload);
    if (!response.ok) {
      showToast(payload.error || "Request failed", "red");
      throw new Error(payload.error || "Request failed");
    }
    return payload;
  }, [showToast]);

  const apiGet = useCallback(async (path) => {
    console.debug("[sentriface-ui] GET", path);
    return readResponse(await fetch(path));
  }, [readResponse]);

  const apiPost = useCallback(async (path, body) => {
    console.debug("[sentriface-ui] POST", path, body);
    return readResponse(await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }));
  }, [readResponse]);

  const loadProfile = useCallback(async () => setProfile(await apiGet("/api/profile")), [apiGet]);
  const loadPeople = useCallback(async () => setPeople((await apiGet("/api/persons")).persons), [apiGet]);
  const loadEvents = useCallback(async () => setEvents((await apiGet("/api/events")).events), [apiGet]);
  const refreshAll = useCallback(async () => Promise.all([loadProfile(), loadPeople(), loadEvents()]), [loadProfile, loadPeople, loadEvents]);

  useEffect(() => {
    refreshAll().catch((error) => console.error(error));
  }, [refreshAll]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (activeView === "debug") loadEvents().catch((error) => console.error(error));
    }, 5000);
    return () => window.clearInterval(timer);
  }, [activeView, loadEvents]);

  const uploadFile = useCallback(async (file) => {
    showToast(`Uploading ${file.name}`);
    const payload = await apiPost("/api/upload", { filename: file.name, data: await readFileAsDataUrl(file) });
    return payload.path;
  }, [apiPost, showToast]);

  const uploadFolder = useCallback(async (files) => {
    showToast(`Uploading ${files.length} file(s)`);
    const payloadFiles = await Promise.all(files.map(async (file) => ({
      filename: file.name,
      relative_path: file.webkitRelativePath || file.name,
      data: await readFileAsDataUrl(file),
    })));
    const payload = await apiPost("/api/upload-batch", { files: payloadFiles });
    return payload.path;
  }, [apiPost, showToast]);

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

  const selectedQueueFaceIds = () => {
    if (!queueSelectedFaces.length) {
      showToast("Select images first", "yellow");
      throw new Error("No queue images selected");
    }
    return queueSelectedFaces;
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
    setRecognitionGalleryImage(null);
  };

  const recognitionGalleryBack = () => {
    if (recognitionGalleryImage) setRecognitionGalleryImage(null);
    else setRecognitionGallery(null);
  };

  const backupDb = async () => {
    const path = window.prompt("Backup target path", "backups/sentriface.db");
    if (!path) return;
    await apiPost("/api/backup-db", { path });
    showToast("Database backup created");
    await loadEvents();
  };

  const guarded = (fn) => async (...args) => {
    try {
      await fn(...args);
    } catch (error) {
      console.error(error);
    }
  };

  return {
    state: {
      activeView,
      profile,
      people,
      peopleGallery,
      peopleGalleryImage,
      queueGroups,
      queueSessionId,
      queueSelectedGroup,
      queueSelectedFaces,
      queueAccepted,
      queueFollowup,
      queueFollowupDone,
      queueGallery,
      queueGalleryImage,
      events,
      recognition,
      recognitionGallery,
      recognitionGalleryImage,
      recognitionAccepted,
      recognitionFollowup,
      recognitionFollowupDone,
    },
    refs: { recognizeFileRef },
    actions: {
      setActiveView,
      refreshAll,
      loadPeople,
      loadEvents,
      recognizeLoadedImage,
      recognitionAccept,
      recognitionNew,
      recognitionClear,
      openRecognitionGallery,
      setRecognitionGalleryImage,
      recognitionGalleryBack,
      updateRecognitionFollowup,
      confirmRecognitionFollowup,
      clearRecognitionFollowupForm,
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
      peopleOpen,
      setPeopleGalleryImage,
      peopleBack,
      savePeopleProfile,
      backupDb,
      guarded,
    },
  };

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
}
