import React, { useCallback, useEffect, useRef, useState } from "react";

const DUPLICATE_MATCH_SCORE = 0.9999;
const HIGH_CONFIDENCE_MATCH_SCORE = 0.9;
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
  const [events, setEvents] = useState([]);
  const [recognition, setRecognition] = useState(null);
  const [recognitionGallery, setRecognitionGallery] = useState(null);
  const [recognitionGalleryImage, setRecognitionGalleryImage] = useState(null);
  const [recognitionAccepted, setRecognitionAccepted] = useState(false);
  const [recognitionFollowup, setRecognitionFollowup] = useState(null);
  const [recognitionFollowupDone, setRecognitionFollowupDone] = useState(false);
  const [toast, setToast] = useState("");
  const [forceBadQuality, setForceBadQuality] = useState(false);

  const recognizeFileRef = useRef(null);
  const queueImageFileRef = useRef(null);
  const queueFolderFileRef = useRef(null);
  const queuePathRef = useRef(null);
  const enrollNameRef = useRef(null);
  const enrollFileRef = useRef(null);
  const enrollPathRef = useRef(null);

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
    const payload = await apiPost("/api/queue-scan", { path, force_bad_quality: forceBadQuality });
    setQueueSessionId(payload.session_id);
    setQueueGroups(payload.groups);
    setQueueSelectedGroup(null);
    setQueueSelectedFaces([]);
    showToast(`Queued ${payload.groups.length} group(s)`);
    await loadEvents();
  }, [apiPost, forceBadQuality, loadEvents, showToast]);

  const queueScan = async () => {
    const imageFile = queueImageFileRef.current?.files?.[0];
    if (imageFile) {
      await scanQueuePath(await uploadFile(imageFile));
      return;
    }
    const folderFiles = Array.from(queueFolderFileRef.current?.files || []);
    if (folderFiles.length) {
      await scanQueuePath(await uploadFolder(folderFiles));
      return;
    }
    const path = queuePathRef.current?.value.trim();
    if (!path) {
      showToast("Drop images, choose a folder, or enter a path");
      throw new Error("Missing queue source");
    }
    await scanQueuePath(path);
  };

  const queueDrop = async (event) => {
    event.preventDefault();
    const files = await droppedImageFiles(event.dataTransfer);
    if (!files.length) {
      showToast("Drop image files or a folder");
      return;
    }
    await scanQueuePath(files.length === 1 ? await uploadFile(files[0]) : await uploadFolder(files));
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
  };

  const toggleQueueFace = (faceId) => {
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
    showToast(`Updating ${best.name}`);
    const payload = await apiPost("/api/queue-confirm-existing", {
      session_id: queueSelectedGroup.session_id,
      group_id: queueSelectedGroup.group_id,
      face_ids: faceIds,
      person_id: best.person_id,
    });
    showToast(`Updated ${best.name} (${payload.embedding_ids.length})`);
    setQueueSelectedFaces([]);
    await Promise.all([loadQueueGroups(queueSelectedGroup.session_id), loadPeople(), loadEvents()]);
  };

  const queueNewPerson = async () => {
    if (!queueSelectedGroup) return;
    const faceIds = selectedQueueFaceIds();
    const name = window.prompt("New person name");
    if (!name) return;
    showToast(`Saving ${name}`);
    const payload = await apiPost("/api/queue-confirm-new", {
      session_id: queueSelectedGroup.session_id,
      group_id: queueSelectedGroup.group_id,
      face_ids: faceIds,
      name,
    });
    showToast(`Updated ${name} (${payload.embedding_ids.length})`);
    setQueueSelectedFaces([]);
    await Promise.all([loadQueueGroups(queueSelectedGroup.session_id), loadPeople(), loadEvents()]);
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
    await Promise.all([loadQueueGroups(queueSelectedGroup.session_id), loadEvents()]);
  };

  const enroll = async () => {
    const name = enrollNameRef.current?.value.trim();
    if (!name) return showToast("Enter person name");
    const path = await resolveImagePath(enrollFileRef, enrollPathRef, uploadFile, showToast);
    const payload = await apiPost("/api/enroll", { path, name });
    showToast(`Enrolled ${name}`);
    await Promise.all([loadPeople(), loadEvents()]);
    console.debug("[sentriface-ui] enrolled", payload);
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
    const payload = await apiPost("/api/recognition-accept-existing", { path: recognition.inputPath, person_id: best.person_id });
    setRecognitionAccepted(true);
    openRecognitionFollowup({
      name: payload.name || best.name,
      personId: best.person_id,
      embeddingId: payload.embedding_id,
      decision: "existing",
    });
    showToast(payload.duplicate ? `Duplicate image of ${payload.name || best.name}` : `Accepted as ${best.name}`);
    await Promise.all([loadPeople(), loadEvents()]);
  };

  const recognitionNew = async () => {
    if (!recognition?.inputPath) return;
    const name = window.prompt("New person name");
    if (!name) return;
    const payload = await apiPost("/api/recognition-new", { path: recognition.inputPath, name });
    setRecognitionAccepted(true);
    openRecognitionFollowup({
      name,
      personId: payload.person_id,
      embeddingId: payload.embedding_id,
      decision: "new",
    });
    showToast(`Saved as ${name}`);
    await Promise.all([loadPeople(), loadEvents()]);
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

  const openRecognitionFollowup = ({ name, personId, embeddingId, decision }) => {
    const { date, time } = currentDateTimeParts();
    setRecognitionFollowup({
      date,
      time,
      placeSeen: "",
      individualCount: "",
      eventOccasion: "",
      name,
      personId,
      embeddingId,
      imageId: imageIdFromPath(recognition?.inputPath || ""),
      decision,
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
      placeSeen: "",
      individualCount: "",
      eventOccasion: "",
    } : current);
    setRecognitionFollowupDone(false);
  };

  const confirmRecognitionFollowup = async (event) => {
    event.preventDefault();
    if (!recognitionFollowup || !recognition?.inputPath) return;
    await apiPost("/api/recognition-followup", {
      path: recognition.inputPath,
      name: recognitionFollowup.name,
      person_id: recognitionFollowup.personId,
      embedding_id: recognitionFollowup.embeddingId,
      image_id: recognitionFollowup.imageId,
      image_path: recognition.inputPath,
      decision: recognitionFollowup.decision,
      date: recognitionFollowup.date,
      time: recognitionFollowup.time,
      place_seen: recognitionFollowup.placeSeen,
      individual_count: Number(recognitionFollowup.individualCount),
      event_occasion: recognitionFollowup.eventOccasion,
    });
    setRecognitionFollowupDone(true);
    setRecognitionFollowup(null);
    showToast("Recognition details confirmed");
    await loadEvents();
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

  const best = recognition?.face?.matches?.[0] || null;
  const isHighConfidenceMatch = Boolean(best && best.score >= HIGH_CONFIDENCE_MATCH_SCORE);

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
                  : <BestMatchPanel best={best} face={recognition?.face} onGallery={guarded(openRecognitionGallery)} />}
              </div>
            </div>
            <div className={`decision-actions ${recognitionAccepted ? "accepted" : ""}`}>
              <button className="accept-btn" onClick={guarded(recognitionAccept)} disabled={!best || recognitionAccepted}>
                {best ? `Accept as ${best.name}` : "Accept"}
              </button>
              <button onClick={guarded(recognitionNew)} disabled={!recognition || recognitionAccepted || isHighConfidenceMatch}>New Person</button>
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
          <div className="queue-layout">
            <div className="queue-sidebar">
              <div className="queue-dropzone" onDrop={guarded(queueDrop)} onDragOver={(event) => event.preventDefault()}>
                <div className="title">Drag & Drop Image / Folder</div>
                <div className="muted">Create embeddings, group similar photos, then review each group.</div>
              </div>
              <div className="toolbar stack">
                <FileField id="queueImageFile" label="Choose image" inputRef={queueImageFileRef} />
                <FolderField id="queueFolderFile" label="Choose folder" inputRef={queueFolderFileRef} />
                <PathField id="queuePath" label="Or use image/folder path" placeholder="Optional local path" inputRef={queuePathRef} />
                <label className="check"><input type="checkbox" checked={forceBadQuality} onChange={(event) => setForceBadQuality(event.target.checked)} /> force bad quality</label>
                <button className="primary" onClick={guarded(queueScan)}>Create Queue</button>
              </div>
              {queueSessionId && (
                <div className="queue-session">
                  <div className="muted">Session</div>
                  <div className="person-id">{queueSessionId}</div>
                  <button onClick={guarded(() => loadQueueGroups(queueSessionId))}>Refresh Groups</button>
                </div>
              )}
              <h2>Enroll Directly</h2>
              <div className="toolbar stack">
                <TextField id="enrollName" label="Person name" placeholder="Person name" inputRef={enrollNameRef} />
                <FileField id="enrollFile" label="Choose image" inputRef={enrollFileRef} />
                <PathField id="enrollPath" label="Or use image path" placeholder="Optional local image path" inputRef={enrollPathRef} />
                <button className="primary" onClick={guarded(enroll)}>Enroll</button>
              </div>
            </div>
            <div className="queue-main">
              {queueSelectedGroup ? (
                <QueueGroupReview
                  group={queueSelectedGroup}
                  selectedFaces={queueSelectedFaces}
                  onToggleFace={toggleQueueFace}
                  onAcceptExisting={guarded(queueAcceptExisting)}
                  onNewPerson={guarded(queueNewPerson)}
                  onDiscard={guarded(queueDiscard)}
                  onBack={() => {
                    setQueueSelectedGroup(null);
                    setQueueSelectedFaces([]);
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

function FileField({ id, label, inputRef }) {
  return (
    <>
      <label className="field-label" htmlFor={id}>{label}</label>
      <div className="input-action">
        <input id={id} ref={inputRef} type="file" accept="image/*" />
        <button type="button" onClick={() => clearFile(inputRef)}>Clear</button>
      </div>
    </>
  );
}

function FolderField({ id, label, inputRef }) {
  return (
    <>
      <label className="field-label" htmlFor={id}>{label}</label>
      <div className="input-action">
        <input id={id} ref={inputRef} type="file" accept="image/*" webkitdirectory="" directory="" multiple />
        <button type="button" onClick={() => clearFile(inputRef)}>Clear</button>
      </div>
    </>
  );
}

function PathField({ id, label, placeholder, inputRef, defaultValue }) {
  return (
    <>
      <label className="field-label" htmlFor={id}>{label}</label>
      <div className="input-action">
        <input id={id} ref={inputRef} placeholder={placeholder} defaultValue={defaultValue} />
        <button type="button" onClick={() => clearInput(inputRef)}>Clear</button>
      </div>
    </>
  );
}

function TextField(props) {
  return <PathField {...props} />;
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
          const best = group.matches?.[0] || null;
          return (
            <button key={`${group.session_id}-${group.group_id}`} className="queue-group-card" onClick={() => onOpen(group)}>
              <div className="card-head">
                <div>
                  <div className="title">{best ? recognitionText(best) : "New person"}</div>
                  <div className="muted">{group.group_id} | {group.faces.length} image(s)</div>
                </div>
                {best && <span className="pill strong">{best.score.toFixed(3)}</span>}
              </div>
              <div className="queue-card-thumbs">
                {group.faces.slice(0, 6).map((face) => <Thumb key={face.init_face_id} path={face.crop_path || face.source_image} />)}
              </div>
            </button>
          );
        }) : <EmptyCard text="No queue groups loaded." />}
      </div>
    </>
  );
}

function QueueGroupReview({ group, selectedFaces, onToggleFace, onAcceptExisting, onNewPerson, onDiscard, onBack }) {
  const best = group.matches?.[0] || null;
  const selectedCount = selectedFaces.length;
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
          <BestMatchPanel best={best} face={{ index: 1 }} onGallery={() => {}} />
          <div className="decision-actions queue-actions">
            <button className="accept-btn" onClick={onAcceptExisting} disabled={!best || !selectedCount}>
              {best ? `Accept as ${best.name}` : "Accept"}
            </button>
            <button onClick={onNewPerson} disabled={!selectedCount}>New Person</button>
            <button onClick={onDiscard} disabled={!selectedCount}>Discard</button>
            <button className="danger-btn" onClick={onBack}>Back</button>
          </div>
        </div>
      </div>
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
  return (
    <div className="best-match">
      <div className="decision-copy">{recognitionText(best)}</div>
      <button className="match-photo-button" onClick={() => onGallery(best.person_id)}>
        {best.representative_image ? <img className="match-photo" src={mediaUrl(best.representative_image)} alt={best.name} /> : <span>No photo</span>}
      </button>
      <MatchIdentitySummary match={best} />
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

async function resolveImagePath(fileRef, pathRef, uploadFile, showToast) {
  const file = fileRef.current?.files?.[0];
  if (file) {
    const path = await uploadFile(file);
    if (pathRef.current) pathRef.current.value = path;
    return path;
  }
  const path = pathRef.current?.value.trim();
  if (!path) {
    showToast("Choose an image or enter a path");
    throw new Error("Missing image");
  }
  return path;
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

function clearInput(ref) {
  if (ref.current) ref.current.value = "";
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
  // if (match.score >= HIGH_CONFIDENCE_MATCH_SCORE) return `That's ${match.name}`;
  if (match.score >= 0.60) return `That's ${match.name}`;
  if (match.score >= 0.50) return `Likely ${match.name}`;
  if(match.score >= 0.40) return `Perhaps ${match.name}`;
  if (match.score < 0.30) return "New person";
  else return `No Match Found`
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
