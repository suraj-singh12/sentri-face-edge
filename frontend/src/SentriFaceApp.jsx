import React, { useCallback, useEffect, useRef, useState } from "react";

const DUPLICATE_MATCH_SCORE = 0.9999;
const MATCH_TEXT_THRESHOLDS = {
  certain: 0.60,
  likely: 0.50,
  possible: 0.40,
  newPerson: 0.30,
};
const NEW_PERSON_IMPORTANCE_OPTIONS = ["Important", "Regular", "Suspicious"];
const VIEWS = ["recognize", "queue", "people", "debug"];

export default function SentriFaceApp() {
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
  const [toast, setToast] = useState("");
  const [queuePickerOpen, setQueuePickerOpen] = useState(false);

  const recognizeFileRef = useRef(null);
  const queueFilePickerRef = useRef(null);
  const queueFolderPickerRef = useRef(null);

  const showToast = useCallback((message) => {
    setToast(message);
    window.setTimeout(() => {
      setToast((current) => (current === message ? "" : current));
    }, 2400);
  }, []);

  const readResponse = useCallback(async (response) => {
    const contentType = response.headers.get("Content-Type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : { error: await response.text() || response.statusText };
    console.debug("[sentriface-ui] response", response.status, payload);
    if (!response.ok) {
      showToast(payload.error || "Request failed");
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
      body: JSON.stringify(body)
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
    console.debug("[sentriface-ui] uploaded", payload);
    return payload.path;
  }, [apiPost, showToast]);

  const uploadFolder = useCallback(async (files) => {
    showToast(`Uploading ${files.length} file(s)`);
    const payloadFiles = await Promise.all(files.map(async (file) => ({
      filename: file.name,
      relative_path: file.webkitRelativePath || file.name,
      data: await readFileAsDataUrl(file)
    })));
    const payload = await apiPost("/api/upload-batch", { files: payloadFiles });
    console.debug("[sentriface-ui] uploaded folder", payload);
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

  const scanQueuePath = useCallback(async (path) => {
    const payload = await apiPost("/api/queue-scan", { path });
    setQueueSessionId(payload.session_id);
    setQueueGroups(payload.groups);
    setQueueSelectedGroup(null);
    setQueueSelectedFaces([]);
    setQueueAccepted(false);
    setQueueFollowup(null);
    setQueueFollowupDone(false);
    setQueueGallery(null);
    setQueueGalleryImage(null);
    showToast(`Queued ${payload.groups.length} group(s)`);
    await loadEvents();
  }, [apiPost, loadEvents, showToast]);

  const scanQueueFiles = async (files) => {
    if (files.length) {
      await scanQueuePath(files.length === 1 ? await uploadFile(files[0]) : await uploadFolder(files));
      return;
    }
    showToast("Choose or drop images");
    throw new Error("Missing queue source");
  };

  const queueScanFiles = async () => {
    await scanQueueFiles(Array.from(queueFilePickerRef.current?.files || []));
    clearFile(queueFilePickerRef);
    setQueuePickerOpen(false);
  };

  const queueScanFolder = async () => {
    await scanQueueFiles(Array.from(queueFolderPickerRef.current?.files || []));
    clearFile(queueFolderPickerRef);
    setQueuePickerOpen(false);
  };

  const queueDrop = async (event) => {
    event.preventDefault();
    setQueuePickerOpen(false);
    const files = await droppedImageFiles(event.dataTransfer);
    if (!files.length) {
      showToast("Drop image files or a folder");
      return;
    }
    await scanQueueFiles(files);
  };

  const loadQueueGroups = useCallback(async (sessionId = queueSessionId) => {
    if (!sessionId) return;
    const payload = await apiGet(`/api/queue-groups?session_id=${encodeURIComponent(sessionId)}`);
    setQueueGroups(payload.groups);
    setQueueSelectedGroup((current) => {
      if (!current) return current;
      return payload.groups.find((group) => group.group_id === current.group_id) || null;
    });
  }, [apiGet, queueSessionId]);

  const openQueueGroup = (group) => {
    setQueueSelectedGroup(group);
    setQueueSelectedFaces([]);
    setQueueAccepted(false);
    setQueueFollowup(null);
    setQueueFollowupDone(false);
    setQueueGallery(null);
    setQueueGalleryImage(null);
  };

  const toggleQueueFace = (faceId) => {
    if (queueAccepted) return;
    setQueueSelectedFaces((current) => (
      current.includes(faceId) ? current.filter((item) => item !== faceId) : [...current, faceId]
    ));
  };

  const selectedQueueFaceIds = () => {
    if (!queueSelectedFaces.length) {
      showToast("Select images first");
      throw new Error("No queue images selected");
    }
    return queueSelectedFaces;
  };

  const queueAcceptExisting = async () => {
    const best = queueSelectedGroup?.matches?.[0];
    if (!queueSelectedGroup || !best) return;
    const faceIds = selectedQueueFaceIds();
    setQueueAccepted(true);
    openQueueFollowup({
      name: best.name,
      personId: best.person_id,
      decision: "existing",
      action: "existing",
      faceIds,
    });
    showToast(`Fill details for ${best.name}`);
  };

  const queueNewPerson = async () => {
    if (!queueSelectedGroup) return;
    const faceIds = selectedQueueFaceIds();
    setQueueAccepted(true);
    openQueueFollowup({
      name: "",
      personId: "",
      decision: "new",
      action: "new",
      faceIds,
    });
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
    setQueueSelectedFaces([]);
    setQueueAccepted(false);
    setQueueFollowup(null);
    setQueueFollowupDone(false);
    await Promise.all([loadQueueGroups(queueSelectedGroup.session_id), loadEvents()]);
  };

  const openQueueFollowup = ({ name, personId, decision, action, faceIds }) => {
    const { date, time } = currentDateTimeParts();
    setQueueFollowup({
      date,
      time,
      rank: "",
      placeSeen: "",
      individualCount: "",
      eventOccasion: "",
      country: "",
      importance: action === "new" ? "Regular" : "",
      addedBy: "",
      name,
      personId,
      decision,
      action,
      faceIds,
    });
    setQueueFollowupDone(false);
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
      importance: current.action === "new" ? "Regular" : "",
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
    setQueueFollowup(null);
    setQueueAccepted(false);
    setQueueSelectedFaces([]);
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

  const peopleBack = () => {
    if (peopleGalleryImage) setPeopleGalleryImage(null);
    else setPeopleGallery(null);
  };

  const recognitionAccept = async () => {
    const best = recognition?.face?.matches?.[0];
    if (!recognition?.inputPath || !best) return;
    if (best.score >= DUPLICATE_MATCH_SCORE) {
      setRecognitionAccepted(true);
      openRecognitionFollowup({
        name: best.name,
        personId: best.person_id,
        embeddingId: best.embedding_ids[0],
        decision: "duplicate",
      });
      showToast(`Duplicate image of ${best.name}`);
      return;
    }
    setRecognitionAccepted(true);
    openRecognitionFollowup({
      name: best.name,
      personId: best.person_id,
      decision: "existing",
      action: "existing",
    });
    showToast(`Fill details for ${best.name}`);
  };

  const recognitionNew = async () => {
    if (!recognition?.inputPath) return;
    setRecognitionAccepted(true);
    openRecognitionFollowup({
      name: "",
      personId: "",
      decision: "new",
      action: "new",
    });
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

  const openRecognitionFollowup = ({ name, personId, embeddingId, decision, action }) => {
    const { date, time } = currentDateTimeParts();
    setRecognitionFollowup({
      date,
      time,
      rank: "",
      placeSeen: "",
      individualCount: "",
      eventOccasion: "",
      country: "",
      importance: action === "new" ? "Regular" : "",
      addedBy: "",
      name,
      personId,
      embeddingId,
      imageId: imageIdFromPath(recognition?.inputPath || ""),
      decision,
      action,
    });
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
      importance: current.action === "new" ? "Regular" : "",
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

  const topMostMatch = recognition?.face?.matches?.[0] || null;
  const isExistingPerson = topMostMatch?.score > MATCH_TEXT_THRESHOLDS.newPerson;
  const shouldFadeRecognitionNewPerson = hasCertainMatch(topMostMatch);

  return (
    <>
      <header className="topbar">
        <div>
          <h1>SentriFace Edge</h1>
          <p id="profileLine">{profileLine(profile)}</p>
        </div>
        <div className="actions">
          <button onClick={guarded(refreshAll)} title="Refresh data">Refresh</button>
          <button onClick={guarded(backupDb)} title="Create DB backup">Backup DB</button>
        </div>
      </header>

      <main className="layout">
        <nav className="tabs" aria-label="Views">
          {VIEWS.map((view) => (
            <button key={view} className={`tab ${activeView === view ? "active" : ""}`} onClick={() => setActiveView(view)}>
              {tabLabel(view)}
            </button>
          ))}
        </nav>

        <View name="recognize" activeView={activeView}>
          <input ref={recognizeFileRef} className="hidden-file" type="file" accept="image/*" onChange={guarded(recognizeLoadedImage)} />
          <div className="recognition-workbench">
            <div className="recognition-stage">
              <div className="compare-pane input-pane">
                <div className="pane-head">
                  <div>
                    <div className="title">Input Image</div>
                    <div className="muted">{recognition?.inputPath || "Load one photo to recognize."}</div>
                  </div>
                  {recognition?.inputPath && <button onClick={() => recognizeFileRef.current?.click()}>Load Another</button>}
                </div>
                <div className="image-frame input-frame">
                  {recognition?.inputPath
                    ? <img className="preview-image" src={mediaUrl(recognition.inputPath)} alt="input" />
                    : <LoadImagePanel onClick={() => recognizeFileRef.current?.click()} />}
                </div>
                {recognition?.face?.quality && <InputImageQuality quality={recognition.face.quality} />}
              </div>
              <div className="compare-pane match-pane">
                <div className="pane-head">
                  <div>
                    <div className="title">Best Match</div>
                    <div className="muted">{recognition?.face ? `Face ${recognition.face.index}` : "No result yet."}</div>
                  </div>
                </div>
                {recognitionGallery
                  ? <GalleryPanel payload={recognitionGallery} selectedImage={recognitionGalleryImage} onImage={setRecognitionGalleryImage} onBack={recognitionGalleryBack} />
                  : <BestMatchPanel best={topMostMatch} face={recognition?.face} onGallery={guarded(openRecognitionGallery)} />}
              </div>
            </div>
            <div className={`decision-actions ${recognitionAccepted ? "accepted" : ""}`}>
              <button className="accept-btn" onClick={guarded(recognitionAccept)} disabled={!topMostMatch || !isExistingPerson || recognitionAccepted}>
                {topMostMatch && isExistingPerson ? `Accept as ${topMostMatch.name}` : "Accept"}
              </button>
              <button onClick={guarded(recognitionNew)} disabled={!recognition || recognitionAccepted || shouldFadeRecognitionNewPerson}>New Person</button>
              <button className="danger-btn" onClick={recognitionClear}>Clear</button>
            </div>
          </div>
          {recognitionFollowup && (
            <RecognitionFollowupForm
              values={recognitionFollowup}
              confirmed={recognitionFollowupDone}
              onChange={updateRecognitionFollowup}
              onSubmit={guarded(confirmRecognitionFollowup)}
              onClear={clearRecognitionFollowupForm}
            />
          )}
          {recognition?.metrics && <Metrics metrics={recognition.metrics} />}
        </View>

        <View name="queue" activeView={activeView}>
          <div className={`queue-layout ${queueSelectedGroup ? "is-reviewing" : ""}`}>
            <QueueInputPanel
              fileRef={queueFilePickerRef}
              folderRef={queueFolderPickerRef}
              pickerOpen={queuePickerOpen}
              sessionId={queueSessionId}
              onFileChange={guarded(queueScanFiles)}
              onFolderChange={guarded(queueScanFolder)}
              onTogglePicker={() => setQueuePickerOpen((current) => !current)}
              onDrop={guarded(queueDrop)}
              onRefresh={guarded(() => loadQueueGroups(queueSessionId))}
            />
            <div className="queue-main">
              {queueSelectedGroup ? (
                <QueueGroupReview
                  group={queueSelectedGroup}
                  selectedFaces={queueSelectedFaces}
                  accepted={queueAccepted}
                  followup={queueFollowup}
                  followupDone={queueFollowupDone}
                  gallery={queueGallery}
                  galleryImage={queueGalleryImage}
                  onToggleFace={toggleQueueFace}
                  onAcceptExisting={guarded(queueAcceptExisting)}
                  onNewPerson={guarded(queueNewPerson)}
                  onDiscard={guarded(queueDiscard)}
                  onFollowupChange={updateQueueFollowup}
                  onFollowupSubmit={guarded(confirmQueueFollowup)}
                  onFollowupClear={clearQueueFollowupForm}
                  onGallery={guarded(openQueueGallery)}
                  onGalleryImage={setQueueGalleryImage}
                  onGalleryBack={queueGalleryBack}
                  onBack={() => {
                    setQueueSelectedGroup(null);
                    setQueueSelectedFaces([]);
                    setQueueAccepted(false);
                    setQueueFollowup(null);
                    setQueueFollowupDone(false);
                    setQueueGallery(null);
                    setQueueGalleryImage(null);
                  }}
                />
              ) : (
                <QueueGroupList groups={queueGroups} onOpen={openQueueGroup} />
              )}
            </div>
          </div>
        </View>

        <View name="people" activeView={activeView}>
          {peopleGallery ? (
            <PeopleGalleryView payload={peopleGallery} selectedImage={peopleGalleryImage} onImage={setPeopleGalleryImage} onBack={peopleBack} />
          ) : (
            <>
              <div className="section-head">
                <h2>People</h2>
                <button onClick={guarded(loadPeople)}>Refresh</button>
              </div>
              <div className="people-grid">
                {people.length ? people.map((person) => <PersonCard key={person.person_id} person={person} onOpen={guarded(peopleOpen)} />) : <EmptyCard text="No people enrolled yet." />}
              </div>
            </>
          )}
        </View>

        <View name="debug" activeView={activeView}>
          <div className="section-head">
            <h2>Debug Events</h2>
            <button onClick={guarded(loadEvents)}>Refresh</button>
          </div>
          <pre id="debugLog">{events.map((event) => JSON.stringify(event)).join("\n")}</pre>
        </View>
      </main>

      <div id="toast" className={toast ? "show" : ""} role="status">{toast}</div>
    </>
  );
}

function View({ name, activeView, children }) {
  return <section id={name} className={`view ${activeView === name ? "active" : ""}`}>{children}</section>;
}

function PersonCard({ person, onOpen }) {
  return (
    <button className="person-card" onClick={() => onOpen(person.person_id)}>
      <div className="person-photo-frame">
        {person.representative_image ? <img src={mediaUrl(person.representative_image)} alt={person.name} /> : <span className="muted">No image</span>}
      </div>
      <div className="card-head">
        <div>
          <div className="title">{person.name}</div>
          <div className="muted person-id">{person.person_id}</div>
        </div>
        <span className="pill">{person.embedding_count} embedding(s)</span>
      </div>
      <div className="muted">Created {person.created_at}</div>
    </button>
  );
}

function PeopleGalleryView({ payload, selectedImage, onImage, onBack }) {
  const images = galleryImages(payload);
  return (
    <div className="people-viewer">
      <div className="section-head">
        <div>
          <h2>{payload.person.name}</h2>
          <div className="muted">{images.length} image(s) | {payload.person.person_id}</div>
        </div>
        <button onClick={onBack}>Back</button>
      </div>
      {selectedImage ? (
        <div className="people-full-frame"><img src={mediaUrl(selectedImage)} alt={payload.person.name} /></div>
      ) : (
        <div className="people-gallery-grid">
          {images.length ? images.map((path) => (
            <button key={path} className="people-gallery-thumb" onClick={() => onImage(path)}>
              <img src={mediaUrl(path)} alt={payload.person.name} />
            </button>
          )) : <EmptyCard text="No images saved for this person." />}
        </div>
      )}
    </div>
  );
}

function QueueInputPanel({
  fileRef,
  folderRef,
  pickerOpen,
  sessionId,
  onFileChange,
  onFolderChange,
  onTogglePicker,
  onDrop,
  onRefresh,
}) {
  return (
    <div className="queue-sidebar">
      <input
        ref={fileRef}
        className="hidden-file"
        type="file"
        accept="image/*"
        multiple
        onChange={onFileChange}
      />
      <input
        ref={folderRef}
        className="hidden-file"
        type="file"
        accept="image/*"
        webkitdirectory=""
        directory=""
        multiple
        onChange={onFolderChange}
      />
      <div
        className={`queue-dropzone ${pickerOpen ? "open" : ""}`}
        role="button"
        tabIndex="0"
        onClick={onTogglePicker}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") onTogglePicker();
        }}
        onDrop={onDrop}
        onDragOver={(event) => event.preventDefault()}
      >
        <div className="title">Drag & Drop Image / Folder</div>
        <div className="muted">Create embeddings, group similar photos, then review each group.</div>
        {pickerOpen && (
          <div className="queue-picker-actions">
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                fileRef.current?.click();
              }}
            >
              Select File
            </button>
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                folderRef.current?.click();
              }}
            >
              Select Folder
            </button>
          </div>
        )}
      </div>
      {sessionId && (
        <div className="queue-session">
          <div className="muted">Session</div>
          <div className="person-id">{sessionId}</div>
          <button onClick={onRefresh}>Refresh Groups</button>
        </div>
      )}
    </div>
  );
}

function QueueGroupList({ groups, onOpen }) {
  const pendingGroups = groups.filter((group) => group.status === "pending" && group.faces.length);
  return (
    <>
      <div className="section-head">
        <h2>Queue Groups</h2>
        <span className="pill">{pendingGroups.length} active</span>
      </div>
      <div className="queue-groups">
        {pendingGroups.length ? pendingGroups.map((group) => {
          const best = group?.matches?.[0] || null;
          const recogText = recognitionText(best);
          const noMatchFound = isNewPersonSuggestion(best);
          return (
            <button key={`${group.session_id}-${group.group_id}`} className="queue-group-card" onClick={() => onOpen(group)}>
              <div className="card-head">
                <div>
                  <div className="title">{recogText}</div>
                  <div className="muted">{group.group_id} | {group.faces.length} image(s)</div>
                </div>
                {best && <span className="pill strong">{best.score.toFixed(3)}</span>}
              </div>
              <div className="queue-card-thumbs">
                {!noMatchFound && group.faces.slice(0, 6).map((face) => <Thumb key={face.init_face_id} path={face.crop_path || face.source_image} />)}
              </div>
            </button>
          );
        }) : <EmptyCard text="No queue groups loaded." />}
      </div>
    </>
  );
}

function QueueGroupReview({
  group,
  selectedFaces,
  accepted,
  followup,
  followupDone,
  gallery,
  galleryImage,
  onToggleFace,
  onAcceptExisting,
  onNewPerson,
  onDiscard,
  onFollowupChange,
  onFollowupSubmit,
  onFollowupClear,
  onGallery,
  onGalleryImage,
  onGalleryBack,
  onBack,
}) {
  const best = group.matches?.[0] || null;
  const selectedCount = selectedFaces.length;
  const shouldFadeNewPerson = hasCertainMatch(best);
  return (
    <div className="queue-review">
      <div className="section-head">
        <div>
          <h2>{group.group_id}</h2>
          <div className="muted">{group.faces.length} image(s) left | {selectedCount} selected</div>
        </div>
        <button onClick={onBack}>Back</button>
      </div>
      <div className="queue-review-grid">
        <div>
          <div className="queue-select-grid">
            {group.faces.map((face) => {
              const selected = selectedFaces.includes(face.init_face_id);
              return (
                <button
                  key={face.init_face_id}
                  className={`queue-face-tile ${selected ? "selected" : ""}`}
                  disabled={accepted}
                  onClick={() => onToggleFace(face.init_face_id)}
                >
                  <img src={mediaUrl(face.crop_path || face.source_image)} alt="queue face" />
                  <span>{selected ? "Selected" : "Select"}</span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="compare-pane queue-match-pane">
          <div className="pane-head">
            <div>
              <div className="title">Suggested Match</div>
              <div className="muted">Select images before accepting.</div>
            </div>
          </div>
          {gallery
            ? <GalleryPanel payload={gallery} selectedImage={galleryImage} onImage={onGalleryImage} onBack={onGalleryBack} />
            : <BestMatchPanel best={best} face={{ index: 1 }} onGallery={onGallery} />}
          <div className={`decision-actions queue-actions ${accepted ? "accepted" : ""}`}>
            <button className="accept-btn" onClick={onAcceptExisting} disabled={!best || !selectedCount || accepted}>
              {best ? `Accept as ${best.name}` : "Accept"}
            </button>
            <button onClick={onNewPerson} disabled={!selectedCount || accepted || shouldFadeNewPerson}>New Person</button>
            <button onClick={onDiscard} disabled={!selectedCount || accepted}>Discard</button>
            <button className="danger-btn" onClick={onBack}>Back</button>
          </div>
        </div>
      </div>
      {followup && (
        <div className="queue-followup-panel">
          <div className="queue-followup-head">
            <div>
              <div className="title">{followup.name}</div>
              <div className="muted">{followup.faceIds.length} image(s)</div>
            </div>
          </div>
          <RecognitionFollowupForm
            values={followup}
            confirmed={followupDone}
            onChange={onFollowupChange}
            onSubmit={onFollowupSubmit}
            onClear={onFollowupClear}
          />
        </div>
      )}
    </div>
  );
}

function LoadImagePanel({ onClick }) {
  return (
    <button className="load-image-panel" onClick={onClick}>
      <span className="load-image-title">Load Image</span>
      <span className="muted">Recognition starts immediately after the photo is selected.</span>
    </button>
  );
}

function RecognitionFollowupForm({ values, confirmed, onChange, onSubmit, onClear }) {
  if (values.action === "new") {
    return (
      <form className="recognition-followup new-person-followup" onSubmit={onSubmit}>
        <div className="followup-grid new-person-grid">
          <label>
            <span>Rank</span>
            <input
              required
              value={values.rank}
              onChange={(event) => onChange("rank", event.target.value)}
            />
          </label>
          <label>
            <span>Name</span>
            <input
              required
              value={values.name}
              onChange={(event) => onChange("name", event.target.value)}
            />
          </label>
          <label>
            <span>Country</span>
            <input
              required
              value={values.country}
              onChange={(event) => onChange("country", event.target.value)}
            />
          </label>
          <label>
            <span>Importance (Strat pt of view)</span>
            <select
              required
              value={values.importance}
              onChange={(event) => onChange("importance", event.target.value)}
            >
              {NEW_PERSON_IMPORTANCE_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
          <label>
            <span>Place Seen</span>
            <input
              required
              value={values.placeSeen}
              onChange={(event) => onChange("placeSeen", event.target.value)}
            />
          </label>
          <label>
            <span>With how many indl</span>
            <input
              required
              min="0"
              step="1"
              type="number"
              value={values.individualCount}
              onChange={(event) => onChange("individualCount", event.target.value)}
            />
          </label>
          <label>
            <span>Date</span>
            <input
              required
              type="date"
              value={values.date}
              onChange={(event) => onChange("date", event.target.value)}
            />
          </label>
          <label>
            <span>Time</span>
            <input
              required
              type="time"
              value={values.time}
              onChange={(event) => onChange("time", event.target.value)}
            />
          </label>
          <label>
            <span>Event/Occasion</span>
            <input
              required
              value={values.eventOccasion}
              onChange={(event) => onChange("eventOccasion", event.target.value)}
            />
          </label>
          <label>
            <span>Added by</span>
            <input
              required
              placeholder="Your Name"
              value={values.addedBy}
              onChange={(event) => onChange("addedBy", event.target.value)}
            />
          </label>
        </div>
        <div className="followup-actions">
          <button className="primary" type="submit" disabled={confirmed}>Confirm</button>
          <button className="danger-btn" type="button" onClick={onClear}>Clear</button>
        </div>
      </form>
    );
  }

  return (
    <form className="recognition-followup" onSubmit={onSubmit}>
      <div className="followup-grid">
        <label>
          <span>Date</span>
          <input
            required
            type="date"
            value={values.date}
            onChange={(event) => onChange("date", event.target.value)}
          />
        </label>
        <label>
          <span>Time</span>
          <input
            required
            type="time"
            value={values.time}
            onChange={(event) => onChange("time", event.target.value)}
          />
        </label>
        <label>
          <span>Place Seen</span>
          <input
            required
            value={values.placeSeen}
            onChange={(event) => onChange("placeSeen", event.target.value)}
          />
        </label>
        <label>
          <span>With how many indl</span>
          <input
            required
            min="0"
            step="1"
            type="number"
            value={values.individualCount}
            onChange={(event) => onChange("individualCount", event.target.value)}
          />
        </label>
        <label className="followup-wide">
          <span>Event/Occasion</span>
          <input
            required
            value={values.eventOccasion}
            onChange={(event) => onChange("eventOccasion", event.target.value)}
          />
        </label>
      </div>
      <div className="followup-actions">
        <button className="primary" type="submit" disabled={confirmed}>Confirm</button>
        <button className="danger-btn" type="button" onClick={onClear}>Clear</button>
      </div>
    </form>
  );
}

function BestMatchPanel({ best, face, onGallery }) {
  if (!face) return <EmptyCard text="No recognition response." />;
  if (!best) {
    return <div className="best-match"><div className="decision-copy">No known person is close enough.</div></div>;
  }
  const recogText = recognitionText(best);
  const noMatchFound = isNewPersonSuggestion(best);
  return (
    <div className="best-match">
      <div className="decision-copy">{recogText}</div>
      { !noMatchFound && 
      <>
        <button className="match-photo-button" onClick={() => onGallery(best.person_id)}>
            {best.representative_image ? <img className="match-photo" src={mediaUrl(best.representative_image)} alt={best.name} /> : <span>No photo</span>}
        </button>
        <MatchIdentitySummary match={best} />
      </>
      }
    </div>
  );
}

function GalleryPanel({ payload, selectedImage, onImage, onBack }) {
  const images = galleryImages(payload);
  return (
    <div className="gallery-panel">
      <div className="section-head">
        <h2>{payload.person.name} Photos</h2>
        <button onClick={onBack}>Back</button>
      </div>
      {selectedImage ? (
        <div className="gallery-full-frame"><img src={mediaUrl(selectedImage)} alt={payload.person.name} /></div>
      ) : (
        <div className="gallery-grid">
          {images.length ? images.map((path) => (
            <button key={path} className="gallery-thumb" onClick={() => onImage(path)}>
              <img src={mediaUrl(path)} alt={payload.person.name} />
            </button>
          )) : <EmptyCard text="No photos saved for this person." />}
        </div>
      )}
    </div>
  );
}

function InputImageQuality({ quality }) {
  const reasons = quality.reasons.length ? quality.reasons.join(", ") : "";
  return (
    <div className="input-quality">
      <hr />
      <div className="quality-line">
        <span className={`pill ${quality.status}`}>{quality.status}</span>
        <span className="quality-score">score: {quality.score.toFixed(3)}</span>
      </div>
      {reasons && <div className="quality-reasons">{reasons}</div>}
    </div>
  );
}

function MatchIdentitySummary({ match }) {
  return (
    <div className="match-identity">
      <div className="match-score">score: {match.score.toFixed(4)}</div>
      <div className="match-group-id">Group-id: {match.person_id}</div>
    </div>
  );
}

function Metrics({ metrics }) {
  return <div className="card"><div className="title">Metrics</div><pre>{JSON.stringify(metrics, null, 2)}</pre></div>;
}

function Thumb({ path }) {
  if (!path) return null;
  return <img className="thumb" src={mediaUrl(path)} alt="face crop" />;
}

function EmptyCard({ text }) {
  return <div className="card muted">{text}</div>;
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function droppedImageFiles(dataTransfer) {
  const items = Array.from(dataTransfer?.items || []);
  if (items.length && items[0].webkitGetAsEntry) {
    const files = [];
    await Promise.all(items.map(async (item) => {
      const entry = item.webkitGetAsEntry();
      if (entry) await collectEntryFiles(entry, files);
    }));
    return files.filter((file) => file.type.startsWith("image/") || /\.(jpe?g|png|bmp|webp)$/i.test(file.name));
  }
  return Array.from(dataTransfer?.files || []).filter((file) => file.type.startsWith("image/"));
}

async function collectEntryFiles(entry, files) {
  if (entry.isFile) {
    files.push(await entryFile(entry));
    return;
  }
  if (!entry.isDirectory) return;
  const reader = entry.createReader();
  let batch = await readEntries(reader);
  while (batch.length) {
    await Promise.all(batch.map((item) => collectEntryFiles(item, files)));
    batch = await readEntries(reader);
  }
}

function entryFile(entry) {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

function readEntries(reader) {
  return new Promise((resolve, reject) => reader.readEntries(resolve, reject));
}

function clearFile(ref) {
  if (ref.current) ref.current.value = "";
}

function galleryImages(payload) {
  return payload.embeddings.map((record) => record.crop_path || record.source_image).filter(Boolean);
}

function mediaUrl(path) {
  return `/media?path=${encodeURIComponent(path)}`;
}

function imageIdFromPath(path) {
  const parts = String(path || "").split(/[\\/]/).filter(Boolean);
  return parts.at(-1) || "unknown-image";
}

function currentDateTimeParts() {
  const now = new Date();
  const date = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
  const time = [
    String(now.getHours()).padStart(2, "0"),
    String(now.getMinutes()).padStart(2, "0"),
  ].join(":");
  return { date, time };
}

function recognitionText(match) {
  if (!match) return "New Person !";
  if (hasCertainMatch(match)) return `That's ${match.name}`;
  if (match.score >= MATCH_TEXT_THRESHOLDS.likely) return `Likely ${match.name}`;
  if (match.score >= MATCH_TEXT_THRESHOLDS.possible) return `Perhaps ${match.name}`;
  if (match.score > MATCH_TEXT_THRESHOLDS.newPerson) return `Is it ${match.name}?`;
  return `New Person !`;
}

function hasCertainMatch(match) {
  return Boolean(match && match.score >= MATCH_TEXT_THRESHOLDS.certain);
}

function isNewPersonSuggestion(match) {
  return !match || match.score <= MATCH_TEXT_THRESHOLDS.newPerson;
}

function profileLine(profile) {
  if (!profile) return "Starting local engine...";
  return `${profile.runtime} runtime | ${profile.hardware_tier} profile | ${profile.onnx_intra_threads} ONNX thread(s) | DB ${profile.db_path}`;
}

function tabLabel(view) {
  return {
    recognize: "Recognize",
    queue: "Queue",
    people: "People",
    debug: "Debug"
  }[view];
}
