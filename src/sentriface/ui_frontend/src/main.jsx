import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const DUPLICATE_MATCH_SCORE = 0.9999;
const VIEWS = ["recognize", "add", "people", "init", "debug"];

function App() {
  const [activeView, setActiveView] = useState("recognize");
  const [profile, setProfile] = useState(null);
  const [people, setPeople] = useState([]);
  const [peopleGallery, setPeopleGallery] = useState(null);
  const [peopleGalleryImage, setPeopleGalleryImage] = useState(null);
  const [pending, setPending] = useState([]);
  const [events, setEvents] = useState([]);
  const [recognition, setRecognition] = useState(null);
  const [recognitionGallery, setRecognitionGallery] = useState(null);
  const [recognitionGalleryImage, setRecognitionGalleryImage] = useState(null);
  const [recognitionAccepted, setRecognitionAccepted] = useState(false);
  const [initGroups, setInitGroups] = useState([]);
  const [initSessionId, setInitSessionId] = useState("");
  const [toast, setToast] = useState("");
  const [forceBadQuality, setForceBadQuality] = useState(false);

  const recognizeFileRef = useRef(null);
  const queueFileRef = useRef(null);
  const queuePathRef = useRef(null);
  const enrollNameRef = useRef(null);
  const enrollFileRef = useRef(null);
  const enrollPathRef = useRef(null);
  const initFolderRef = useRef(null);
  const initPathRef = useRef(null);
  const initSessionRef = useRef(null);

  const showToast = useCallback((message) => {
    setToast(message);
    window.setTimeout(() => {
      setToast((current) => (current === message ? "" : current));
    }, 2400);
  }, []);

  const readResponse = useCallback(async (response) => {
    const payload = await response.json();
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
  const loadPending = useCallback(async () => setPending((await apiGet("/api/pending")).pending), [apiGet]);
  const loadEvents = useCallback(async () => setEvents((await apiGet("/api/events")).events), [apiGet]);
  const refreshAll = useCallback(async () => Promise.all([loadProfile(), loadPeople(), loadPending(), loadEvents()]), [loadProfile, loadPeople, loadPending, loadEvents]);

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
    showToast(`Recognized ${payload.faces.length} face(s)`);
    await loadEvents();
  }, [apiPost, loadEvents, showToast]);

  const recognizeLoadedImage = useCallback(async () => {
    const file = recognizeFileRef.current?.files?.[0];
    if (!file) return;
    await runRecognition(await uploadFile(file));
  }, [runRecognition, uploadFile]);

  const queueAdd = async () => {
    const path = await resolveImagePath(queueFileRef, queuePathRef, uploadFile, showToast);
    const payload = await apiPost("/api/queue-add", { path, force_bad_quality: forceBadQuality });
    showToast(`Queued ${payload.pending.length}, rejected ${payload.rejected.length}`);
    await Promise.all([loadPending(), loadEvents()]);
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

  const initScan = async () => {
    const path = await resolveFolderPath(initFolderRef, initPathRef, uploadFolder, showToast);
    const payload = await apiPost("/api/init-scan", { path });
    setInitSessionId(payload.session_id);
    setInitGroups(payload.groups);
    if (initSessionRef.current) initSessionRef.current.value = payload.session_id;
    showToast(`Init session created with ${payload.groups.length} group(s)`);
    await loadEvents();
  };

  const loadInitGroups = useCallback(async () => {
    const sessionId = initSessionRef.current?.value.trim() || initSessionId;
    const payload = await apiGet(`/api/init-groups?session_id=${encodeURIComponent(sessionId)}`);
    setInitSessionId(sessionId);
    setInitGroups(payload.groups);
  }, [apiGet, initSessionId]);

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
      showToast(`Duplicate image of ${best.name}`);
      return;
    }
    const payload = await apiPost("/api/recognition-accept-existing", { path: recognition.inputPath, person_id: best.person_id });
    setRecognitionAccepted(true);
    showToast(payload.duplicate ? `Duplicate image of ${payload.name || best.name}` : `Accepted as ${best.name}`);
    await Promise.all([loadPeople(), loadEvents()]);
  };

  const recognitionNew = async () => {
    if (!recognition?.inputPath) return;
    const name = window.prompt("New person name");
    if (!name) return;
    await apiPost("/api/recognition-new", { path: recognition.inputPath, name });
    setRecognitionAccepted(true);
    showToast(`Saved as ${name}`);
    await Promise.all([loadPeople(), loadEvents()]);
  };

  const recognitionClear = () => {
    clearFile(recognizeFileRef);
    setRecognition(null);
    setRecognitionGallery(null);
    setRecognitionGalleryImage(null);
    setRecognitionAccepted(false);
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

  const confirmNew = async (pendingId) => {
    const name = window.prompt("New person name");
    if (!name) return;
    await apiPost("/api/confirm-new", { pending_id: pendingId, name });
    showToast("Pending face confirmed as new person");
    await Promise.all([loadPeople(), loadPending(), loadEvents()]);
  };

  const confirmExisting = async (pendingId) => {
    const personId = window.prompt("Existing person ID");
    if (!personId) return;
    await apiPost("/api/confirm-existing", { pending_id: pendingId, person_id: personId });
    showToast("Pending face added to existing person");
    await Promise.all([loadPeople(), loadPending(), loadEvents()]);
  };

  const rejectPending = async (pendingId) => {
    await apiPost("/api/reject-pending", { pending_id: pendingId });
    showToast("Pending face rejected");
    await Promise.all([loadPending(), loadEvents()]);
  };

  const initConfirm = async (sessionId, groupId) => {
    const name = window.prompt("New person name");
    if (!name) return;
    await apiPost("/api/init-confirm", { session_id: sessionId, group_id: groupId, name });
    showToast("Init group confirmed");
    await Promise.all([loadInitGroups(), loadPeople(), loadEvents()]);
  };

  const initConfirmExisting = async (sessionId, groupId) => {
    const personId = window.prompt("Existing person ID");
    if (!personId) return;
    await apiPost("/api/init-confirm-existing", { session_id: sessionId, group_id: groupId, person_id: personId });
    showToast("Init group added");
    await Promise.all([loadInitGroups(), loadPeople(), loadEvents()]);
  };

  const initReject = async (sessionId, groupId) => {
    await apiPost("/api/init-reject", { session_id: sessionId, group_id: groupId });
    showToast("Init group rejected");
    await Promise.all([loadInitGroups(), loadEvents()]);
  };

  const initReset = async (sessionId, groupId) => {
    await apiPost("/api/init-reset", { session_id: sessionId, group_id: groupId });
    showToast("Init group reset");
    await Promise.all([loadInitGroups(), loadEvents()]);
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
            <div className="decision-actions">
              <button className="accept-btn" onClick={guarded(recognitionAccept)} disabled={!best || recognitionAccepted}>
                {best ? `Accept as ${best.name}` : "Accept"}
              </button>
              <button onClick={guarded(recognitionNew)} disabled={!recognition || recognitionAccepted}>New Person</button>
              <button className="danger-btn" onClick={recognitionClear}>Clear</button>
            </div>
          </div>
          {recognition?.metrics && <Metrics metrics={recognition.metrics} />}
        </View>

        <View name="add" activeView={activeView}>
          <div className="split">
            <div>
              <h2>Queue Face</h2>
              <div className="toolbar stack">
                <FileField id="queueFile" label="Choose image" inputRef={queueFileRef} />
                <PathField id="queuePath" label="Or use image path" placeholder="Optional local image path" inputRef={queuePathRef} />
                <label className="check"><input type="checkbox" checked={forceBadQuality} onChange={(event) => setForceBadQuality(event.target.checked)} /> force bad quality</label>
                <button className="primary" onClick={guarded(queueAdd)}>Queue</button>
              </div>
              <h2>Enroll Directly</h2>
              <div className="toolbar stack">
                <TextField id="enrollName" label="Person name" placeholder="Person name" inputRef={enrollNameRef} />
                <FileField id="enrollFile" label="Choose image" inputRef={enrollFileRef} />
                <PathField id="enrollPath" label="Or use image path" placeholder="Optional local image path" inputRef={enrollPathRef} />
                <button className="primary" onClick={guarded(enroll)}>Enroll</button>
              </div>
            </div>
            <div>
              <div className="section-head">
                <h2>Pending Review</h2>
                <button onClick={guarded(loadPending)}>Refresh</button>
              </div>
              <div className="results">
                {pending.length ? pending.map((item) => (
                  <PendingCard key={item.pending_id} item={item} onNew={guarded(confirmNew)} onExisting={guarded(confirmExisting)} onReject={guarded(rejectPending)} />
                )) : <EmptyCard text="No pending additions." />}
              </div>
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

        <View name="init" activeView={activeView}>
          <div className="workflow-panel">
            <div>
              <h2>Initial Face Grouping</h2>
              <p className="muted">Choose a folder of images, scan faces, then review grouped identities.</p>
            </div>
            <div className="toolbar stack">
              <FolderField id="initFolder" label="Choose folder" inputRef={initFolderRef} />
              <PathField id="initPath" label="Or use folder path" placeholder="Optional local folder path" inputRef={initPathRef} />
              <button className="primary" onClick={guarded(initScan)}>Scan Folder</button>
            </div>
          </div>
          <div className="toolbar stack">
            <PathField id="initSessionId" label="Session ID" placeholder="Session ID" inputRef={initSessionRef} defaultValue={initSessionId} />
            <button onClick={guarded(loadInitGroups)}>Load Groups</button>
          </div>
          <div className="results">
            {initGroups.length ? initGroups.map((group) => (
              <InitGroupCard
                key={`${group.session_id}-${group.group_id}`}
                group={group}
                onConfirm={guarded(initConfirm)}
                onExisting={guarded(initConfirmExisting)}
                onReject={guarded(initReject)}
                onReset={guarded(initReset)}
              />
            )) : <EmptyCard text="No init groups loaded." />}
          </div>
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

function PendingCard({ item, onNew, onExisting, onReject }) {
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="title">{item.pending_id}</div>
          <div className="muted">{item.source_image}</div>
        </div>
        <span className={`pill ${item.decision}`}>{item.decision}</span>
      </div>
      <Thumb path={item.crop_path} />
      <Quality quality={item.quality} />
      <Matches matches={item.matches} />
      <div className="row">
        <button onClick={() => onNew(item.pending_id)}>New</button>
        <button onClick={() => onExisting(item.pending_id)}>Existing</button>
        <button onClick={() => onReject(item.pending_id)}>Reject</button>
      </div>
    </div>
  );
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

function InitGroupCard({ group, onConfirm, onExisting, onReject, onReset }) {
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="title">{group.group_id}</div>
          <div className="muted">session {group.session_id} | {group.faces.length} face(s)</div>
        </div>
        <span className="pill">{group.status}</span>
      </div>
      <div className="thumbs">{group.faces.map((face) => <Thumb key={face.init_face_id} path={face.crop_path} />)}</div>
      <div className="row">
        <button onClick={() => onConfirm(group.session_id, group.group_id)}>New</button>
        <button onClick={() => onExisting(group.session_id, group.group_id)}>Existing</button>
        <button onClick={() => onReject(group.session_id, group.group_id)}>Reject</button>
        <button onClick={() => onReset(group.session_id, group.group_id)}>Reset</button>
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

function BestMatchPanel({ best, face, onGallery }) {
  if (!face) return <EmptyCard text="No recognition response." />;
  if (!best) {
    return <div className="best-match"><div className="decision-copy">No known person is close enough.</div></div>;
  }
  if (best.score <= 0.42) {
    const closest = face.matches.slice(0, 2);
    return (
      <div className="best-match">
        <div className="decision-copy">{recognitionText(best)}</div>
        <div className="muted">Showing closest {closest.length} candidate(s)</div>
        <div className="closest-grid">{closest.map((match) => <CandidateCard key={match.person_id} match={match} onGallery={onGallery} />)}</div>
      </div>
    );
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

function CandidateCard({ match, onGallery }) {
  return (
    <button className="candidate-card" onClick={() => onGallery(match.person_id)}>
      {match.representative_image ? <img src={mediaUrl(match.representative_image)} alt={match.name} /> : <span className="muted">No photo</span>}
      <span className="title">{match.name}</span>
      <span className="candidate-score">score: {match.score.toFixed(4)}</span>
      <span className="candidate-id">Group-id: {match.person_id}</span>
    </button>
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

function Quality({ quality }) {
  if (!quality) return null;
  const reasons = quality.reasons.length ? ` | ${quality.reasons.join(", ")}` : "";
  return <div className="muted"><span className={`pill ${quality.status}`}>{quality.status}</span> score {quality.score.toFixed(3)}{reasons}</div>;
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

function Matches({ matches }) {
  if (!matches.length) return <div className="muted">No matches.</div>;
  return (
    <div className="matches">
      {matches.map((match) => (
        <div key={`${match.rank}-${match.person_id}`} className="match">
          <div className="title">#{match.rank} {match.name} <span className="muted">{match.score.toFixed(4)}</span></div>
          <div className="muted">{match.person_id} | {match.embeddings_matched} embedding(s)</div>
        </div>
      ))}
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

async function resolveFolderPath(fileRef, pathRef, uploadFolder, showToast) {
  const files = Array.from(fileRef.current?.files || []);
  if (files.length) {
    const path = await uploadFolder(files);
    if (pathRef.current) pathRef.current.value = path;
    return path;
  }
  const path = pathRef.current?.value.trim();
  if (!path) {
    showToast("Choose a folder or enter a folder path");
    throw new Error("Missing folder");
  }
  return path;
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

function recognitionText(match) {
  if (match.score >= 0.62) return `Looks ${match.name}`;
  if (match.score > 0.42) return `Maybe ${match.name}`;
  return `Can't say ${match.name}, but this is the closest we have`;
}

function profileLine(profile) {
  if (!profile) return "Starting local engine...";
  return `${profile.runtime} runtime | ${profile.hardware_tier} profile | ${profile.onnx_intra_threads} ONNX thread(s) | DB ${profile.db_path}`;
}

function tabLabel(view) {
  return {
    recognize: "Recognize",
    add: "Add Queue",
    people: "People",
    init: "Init Scan",
    debug: "Debug"
  }[view];
}

createRoot(document.getElementById("root")).render(<App />);
