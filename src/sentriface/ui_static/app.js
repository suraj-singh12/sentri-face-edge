const state = {
  activeView: "recognize",
  profile: null,
  people: [],
  pending: [],
  events: [],
  recognizeResults: "",
  initGroups: [],
  initSessionId: "",
  toast: "",
};

const root = document.getElementById("root");

const React = {
  component(renderFn) {
    return renderFn;
  },
};

const App = React.component(() => `
  <header class="topbar">
    <div>
      <h1>SentriFace Edge</h1>
      <p id="profileLine">${profileLine()}</p>
    </div>
    <div class="actions">
      <button data-action="refresh-all" title="Refresh data">Refresh</button>
      <button data-action="backup-db" title="Create DB backup">Backup DB</button>
    </div>
  </header>

  <main class="layout">
    ${Tabs()}
    ${View("recognize", RecognizeView())}
    ${View("add", AddView())}
    ${View("people", PeopleView())}
    ${View("init", InitView())}
    ${View("debug", DebugView())}
  </main>

  <div id="toast" class="${state.toast ? "show" : ""}" role="status">${escapeHtml(state.toast)}</div>
`);

function Tabs() {
  return `
    <nav class="tabs" aria-label="Views">
      ${["recognize", "add", "people", "init", "debug"].map((view) => `
        <button class="tab ${state.activeView === view ? "active" : ""}" data-view="${view}">
          ${tabLabel(view)}
        </button>
      `).join("")}
    </nav>
  `;
}

function View(name, body) {
  return `<section id="${name}" class="view ${state.activeView === name ? "active" : ""}">${body}</section>`;
}

function RecognizeView() {
  return `
    <div class="toolbar stack">
      ${FileField("recognizeFile", "Choose image")}
      ${PathField("recognizePath", "Or use image/folder path", "Optional local image or folder path")}
      <div class="button-row">
        <button class="primary" data-action="recognize">Recognize</button>
        <button data-action="recognize-batch">Batch</button>
      </div>
    </div>
    <div class="results">${state.recognizeResults || ""}</div>
  `;
}

function AddView() {
  return `
    <div class="split">
      <div>
        <h2>Queue Face</h2>
        <div class="toolbar stack">
          ${FileField("queueFile", "Choose image")}
          ${PathField("queuePath", "Or use image path", "Optional local image path")}
          <label class="check"><input id="forceBadQuality" type="checkbox" /> force bad quality</label>
          <button class="primary" data-action="queue-add">Queue</button>
        </div>
        <h2>Enroll Directly</h2>
        <div class="toolbar stack">
          ${TextField("enrollName", "Person name", "Person name")}
          ${FileField("enrollFile", "Choose image")}
          ${PathField("enrollPath", "Or use image path", "Optional local image path")}
          <button class="primary" data-action="enroll">Enroll</button>
        </div>
      </div>
      <div>
        <div class="section-head">
          <h2>Pending Review</h2>
          <button data-action="load-pending">Refresh</button>
        </div>
        <div class="results">${PendingList()}</div>
      </div>
    </div>
  `;
}

function PeopleView() {
  return `
    <div class="section-head">
      <h2>People</h2>
      <button data-action="load-people">Refresh</button>
    </div>
    <div class="grid">${state.people.length ? state.people.map(PersonCard).join("") : EmptyCard("No people enrolled yet.")}</div>
  `;
}

function InitView() {
  return `
    <div class="workflow-panel">
      <div>
        <h2>Initial Face Grouping</h2>
        <p class="muted">Choose a folder of images, scan faces, then review grouped identities.</p>
      </div>
      <div class="toolbar stack">
        ${FolderField("initFolder", "Choose folder")}
        ${PathField("initPath", "Or use folder path", "Optional local folder path")}
        <button class="primary" data-action="init-scan">Scan Folder</button>
      </div>
    </div>
    <div class="toolbar stack">
      ${PathField("initSessionId", "Session ID", "Session ID")}
      <button data-action="init-load">Load Groups</button>
    </div>
    <div class="results">${state.initGroups.length ? state.initGroups.map(InitGroupCard).join("") : EmptyCard("No init groups loaded.")}</div>
  `;
}

function DebugView() {
  return `
    <div class="section-head">
      <h2>Debug Events</h2>
      <button data-action="load-events">Refresh</button>
    </div>
    <pre id="debugLog">${state.events.map((event) => escapeHtml(JSON.stringify(event))).join("\n")}</pre>
  `;
}

function FileField(id, label) {
  return `
    <label class="field-label" for="${id}">${label}</label>
    <div class="input-action">
      <input id="${id}" type="file" accept="image/*" />
      <button type="button" data-action="clear-file" data-target="${id}">Clear</button>
    </div>
  `;
}

function FolderField(id, label) {
  return `
    <label class="field-label" for="${id}">${label}</label>
    <div class="input-action">
      <input id="${id}" type="file" accept="image/*" webkitdirectory directory multiple />
      <button type="button" data-action="clear-file" data-target="${id}">Clear</button>
    </div>
  `;
}

function PathField(id, label, placeholder) {
  return `
    <label class="field-label" for="${id}">${label}</label>
    <div class="input-action">
      <input id="${id}" data-keep-value="1" placeholder="${escapeHtml(placeholder)}" />
      <button type="button" data-action="clear-input" data-target="${id}">Clear</button>
    </div>
  `;
}

function TextField(id, label, placeholder) {
  return `
    <label class="field-label" for="${id}">${label}</label>
    <div class="input-action">
      <input id="${id}" data-keep-value="1" placeholder="${escapeHtml(placeholder)}" />
      <button type="button" data-action="clear-input" data-target="${id}">Clear</button>
    </div>
  `;
}

function PendingList() {
  return state.pending.length ? state.pending.map(PendingCard).join("") : EmptyCard("No pending additions.");
}

function PendingCard(item) {
  return `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="title">${escapeHtml(item.pending_id)}</div>
          <div class="muted">${escapeHtml(item.source_image)}</div>
        </div>
        <span class="pill ${item.decision}">${escapeHtml(item.decision)}</span>
      </div>
      ${Thumb(item.crop_path)}
      ${Quality(item.quality)}
      ${Matches(item.matches)}
      <div class="row">
        <button data-action="confirm-new" data-pending-id="${escapeHtml(item.pending_id)}">New</button>
        <button data-action="confirm-existing" data-pending-id="${escapeHtml(item.pending_id)}">Existing</button>
        <button data-action="reject-pending" data-pending-id="${escapeHtml(item.pending_id)}">Reject</button>
      </div>
    </div>
  `;
}

function PersonCard(person) {
  return `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="title">${escapeHtml(person.name)}</div>
          <div class="muted">${escapeHtml(person.person_id)}</div>
        </div>
        <span class="pill">${person.embedding_count} embedding(s)</span>
      </div>
      <div class="muted">Created ${escapeHtml(person.created_at)}</div>
    </div>
  `;
}

function InitGroupCard(group) {
  return `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="title">${escapeHtml(group.group_id)}</div>
          <div class="muted">session ${escapeHtml(group.session_id)} | ${group.faces.length} face(s)</div>
        </div>
        <span class="pill">${escapeHtml(group.status)}</span>
      </div>
      <div class="thumbs">${group.faces.map((face) => Thumb(face.crop_path)).join("")}</div>
      <div class="row">
        <button data-action="init-confirm" data-session-id="${escapeHtml(group.session_id)}" data-group-id="${escapeHtml(group.group_id)}">New</button>
        <button data-action="init-confirm-existing" data-session-id="${escapeHtml(group.session_id)}" data-group-id="${escapeHtml(group.group_id)}">Existing</button>
        <button data-action="init-reject" data-session-id="${escapeHtml(group.session_id)}" data-group-id="${escapeHtml(group.group_id)}">Reject</button>
        <button data-action="init-reset" data-session-id="${escapeHtml(group.session_id)}" data-group-id="${escapeHtml(group.group_id)}">Reset</button>
      </div>
    </div>
  `;
}

function Faces(faces, metrics) {
  const body = faces.length ? faces.map((face) => `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="title">Face ${face.index}</div>
          <div class="muted">box ${face.box.width}x${face.box.height}, detector ${face.box.confidence.toFixed(3)}</div>
        </div>
        <span class="pill ${face.decision}">${escapeHtml(face.decision)}</span>
      </div>
      ${Quality(face.quality)}
      ${Matches(face.matches)}
    </div>
  `).join("") : EmptyCard("No faces detected.");
  return body + (metrics ? Metrics(metrics) : "");
}

function BatchResults(batch, metrics) {
  return batch.map((item) => `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="title">${escapeHtml(item.image)}</div>
          <div class="muted">${item.faces.length} face(s)</div>
        </div>
      </div>
      ${Faces(item.faces)}
    </div>
  `).join("") + Metrics(metrics);
}

function Quality(quality) {
  if (!quality) return "";
  const reasons = quality.reasons.length ? ` | ${quality.reasons.map(escapeHtml).join(", ")}` : "";
  return `<div class="muted"><span class="pill ${quality.status}">${quality.status}</span> score ${quality.score.toFixed(3)}${reasons}</div>`;
}

function Matches(matches) {
  if (!matches.length) return `<div class="muted">No matches.</div>`;
  return `<div class="matches">${matches.map((match) => `
    <div class="match">
      <div class="title">#${match.rank} ${escapeHtml(match.name)} <span class="muted">${match.score.toFixed(4)}</span></div>
      <div class="muted">${escapeHtml(match.person_id)} | ${match.embeddings_matched} embedding(s)</div>
    </div>
  `).join("")}</div>`;
}

function Metrics(metrics) {
  return `<div class="card"><div class="title">Metrics</div><pre>${escapeHtml(JSON.stringify(metrics, null, 2))}</pre></div>`;
}

function Thumb(path) {
  if (!path) return "";
  return `<img class="thumb" src="/media?path=${encodeURIComponent(path)}" alt="face crop" />`;
}

function EmptyCard(text) {
  return `<div class="card muted">${escapeHtml(text)}</div>`;
}

function render() {
  const values = snapshotValues();
  root.innerHTML = App();
  restoreValues(values);
  bindEvents();
}

function snapshotValues() {
  const values = {};
  document.querySelectorAll("[data-keep-value]").forEach((input) => {
    values[input.id] = input.type === "checkbox" ? input.checked : input.value;
  });
  return values;
}

function restoreValues(values) {
  Object.entries(values).forEach(([id, value]) => {
    const input = document.getElementById(id);
    if (!input) return;
    if (input.type === "checkbox") input.checked = value;
    else input.value = value;
  });
  if (state.initSessionId && document.getElementById("initSessionId")) {
    document.getElementById("initSessionId").value = state.initSessionId;
  }
}

function bindEvents() {
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeView = button.dataset.view;
      render();
    });
  });
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => handleAction(button));
  });
}

async function handleAction(target) {
  const action = target.dataset.action;
  try {
    if (action === "refresh-all") await refreshAll();
    if (action === "backup-db") await backupDb();
    if (action === "load-people") await loadPeople();
    if (action === "load-pending") await loadPending();
    if (action === "load-events") await loadEvents();
    if (action === "recognize") await recognizeOne();
    if (action === "recognize-batch") await recognizeBatch();
    if (action === "queue-add") await queueAdd();
    if (action === "enroll") await enroll();
    if (action === "init-scan") await initScan();
    if (action === "init-load") await loadInitGroups();
    if (action === "clear-input") clearInput(target.dataset.target);
    if (action === "clear-file") clearFile(target.dataset.target);
    if (action === "confirm-new") await confirmNew(target.dataset.pendingId);
    if (action === "confirm-existing") await confirmExisting(target.dataset.pendingId);
    if (action === "reject-pending") await rejectPending(target.dataset.pendingId);
    if (action === "init-confirm") await initConfirm(target.dataset.sessionId, target.dataset.groupId);
    if (action === "init-confirm-existing") await initConfirmExisting(target.dataset.sessionId, target.dataset.groupId);
    if (action === "init-reject") await initReject(target.dataset.sessionId, target.dataset.groupId);
    if (action === "init-reset") await initReset(target.dataset.sessionId, target.dataset.groupId);
  } catch (error) {
    console.error(error);
  }
}

async function refreshAll() {
  await Promise.all([loadProfile(), loadPeople(), loadPending(), loadEvents()]);
}

async function loadProfile() {
  state.profile = await apiGet("/api/profile");
  render();
}

async function loadPeople() {
  const payload = await apiGet("/api/persons");
  state.people = payload.persons;
  render();
}

async function loadPending() {
  const payload = await apiGet("/api/pending");
  state.pending = payload.pending;
  render();
}

async function loadEvents() {
  const payload = await apiGet("/api/events");
  state.events = payload.events;
  render();
}

async function recognizeOne() {
  const path = await resolveImagePath("recognizeFile", "recognizePath");
  const payload = await apiPost("/api/recognize", { path });
  state.recognizeResults = Faces(payload.faces, payload.metrics);
  showToast(`Recognized ${payload.faces.length} face(s)`);
  await loadEvents();
  render();
}

async function recognizeBatch() {
  const path = await resolveImagePath("recognizeFile", "recognizePath");
  const payload = await apiPost("/api/recognize-batch", { path });
  state.recognizeResults = BatchResults(payload.batch, payload.metrics);
  showToast(`Processed ${payload.batch.length} image(s)`);
  await loadEvents();
  render();
}

async function queueAdd() {
  const path = await resolveImagePath("queueFile", "queuePath");
  const payload = await apiPost("/api/queue-add", {
    path,
    force_bad_quality: Boolean(document.getElementById("forceBadQuality")?.checked),
  });
  showToast(`Queued ${payload.pending.length}, rejected ${payload.rejected.length}`);
  await Promise.all([loadPending(), loadEvents()]);
}

async function enroll() {
  const name = valueOf("enrollName");
  if (!name) {
    showToast("Enter person name");
    return;
  }
  const path = await resolveImagePath("enrollFile", "enrollPath");
  const payload = await apiPost("/api/enroll", { path, name });
  showToast(`Enrolled ${name}`);
  await Promise.all([loadPeople(), loadEvents()]);
  console.debug("[sentriface-ui] enrolled", payload);
}

async function confirmNew(pendingId) {
  const name = prompt("New person name");
  if (!name) return;
  await apiPost("/api/confirm-new", { pending_id: pendingId, name });
  showToast("Pending face confirmed as new person");
  await Promise.all([loadPeople(), loadPending(), loadEvents()]);
}

async function confirmExisting(pendingId) {
  const personId = prompt("Existing person ID");
  if (!personId) return;
  await apiPost("/api/confirm-existing", { pending_id: pendingId, person_id: personId });
  showToast("Pending face added to existing person");
  await Promise.all([loadPeople(), loadPending(), loadEvents()]);
}

async function rejectPending(pendingId) {
  await apiPost("/api/reject-pending", { pending_id: pendingId });
  showToast("Pending face rejected");
  await Promise.all([loadPending(), loadEvents()]);
}

async function initScan() {
  const path = await resolveFolderPath("initFolder", "initPath");
  const payload = await apiPost("/api/init-scan", { path });
  state.initSessionId = payload.session_id;
  state.initGroups = payload.groups;
  showToast(`Init session created with ${payload.groups.length} group(s)`);
  await loadEvents();
  render();
}

async function loadInitGroups() {
  const sessionId = valueOf("initSessionId") || state.initSessionId;
  const payload = await apiGet(`/api/init-groups?session_id=${encodeURIComponent(sessionId)}`);
  state.initSessionId = sessionId;
  state.initGroups = payload.groups;
  render();
}

async function initConfirm(sessionId, groupId) {
  const name = prompt("New person name");
  if (!name) return;
  await apiPost("/api/init-confirm", { session_id: sessionId, group_id: groupId, name });
  showToast("Init group confirmed");
  await Promise.all([loadInitGroups(), loadPeople(), loadEvents()]);
}

async function initConfirmExisting(sessionId, groupId) {
  const personId = prompt("Existing person ID");
  if (!personId) return;
  await apiPost("/api/init-confirm-existing", { session_id: sessionId, group_id: groupId, person_id: personId });
  showToast("Init group added");
  await Promise.all([loadInitGroups(), loadPeople(), loadEvents()]);
}

async function initReject(sessionId, groupId) {
  await apiPost("/api/init-reject", { session_id: sessionId, group_id: groupId });
  showToast("Init group rejected");
  await Promise.all([loadInitGroups(), loadEvents()]);
}

async function initReset(sessionId, groupId) {
  await apiPost("/api/init-reset", { session_id: sessionId, group_id: groupId });
  showToast("Init group reset");
  await Promise.all([loadInitGroups(), loadEvents()]);
}

async function backupDb() {
  const path = prompt("Backup target path", "backups/sentriface.db");
  if (!path) return;
  await apiPost("/api/backup-db", { path });
  showToast("Database backup created");
  await loadEvents();
}

async function resolveImagePath(fileInputId, pathInputId) {
  const fileInput = document.getElementById(fileInputId);
  if (fileInput?.files?.length) {
    const path = await uploadFile(fileInput.files[0]);
    const pathInput = document.getElementById(pathInputId);
    if (pathInput) pathInput.value = path;
    return path;
  }
  const path = valueOf(pathInputId);
  if (!path) {
    showToast("Choose an image or enter a path");
    throw new Error("Missing image");
  }
  return path;
}

async function uploadFile(file) {
  showToast(`Uploading ${file.name}`);
  const data = await readFileAsDataUrl(file);
  const payload = await apiPost("/api/upload", { filename: file.name, data });
  console.debug("[sentriface-ui] uploaded", payload);
  return payload.path;
}

async function resolveFolderPath(fileInputId, pathInputId) {
  const fileInput = document.getElementById(fileInputId);
  if (fileInput?.files?.length) {
    const path = await uploadFolder(Array.from(fileInput.files));
    const pathInput = document.getElementById(pathInputId);
    if (pathInput) pathInput.value = path;
    return path;
  }
  const path = valueOf(pathInputId);
  if (!path) {
    showToast("Choose a folder or enter a folder path");
    throw new Error("Missing folder");
  }
  return path;
}

async function uploadFolder(files) {
  showToast(`Uploading ${files.length} file(s)`);
  const payloadFiles = await Promise.all(files.map(async (file) => ({
    filename: file.name,
    relative_path: file.webkitRelativePath || file.name,
    data: await readFileAsDataUrl(file),
  })));
  const payload = await apiPost("/api/upload-batch", { files: payloadFiles });
  console.debug("[sentriface-ui] uploaded folder", payload);
  return payload.path;
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function apiGet(path) {
  console.debug("[sentriface-ui] GET", path);
  const response = await fetch(path);
  return readResponse(response);
}

async function apiPost(path, body) {
  console.debug("[sentriface-ui] POST", path, body);
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readResponse(response);
}

async function readResponse(response) {
  const payload = await response.json();
  console.debug("[sentriface-ui] response", response.status, payload);
  if (!response.ok) {
    showToast(payload.error || "Request failed");
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function clearInput(id) {
  const input = document.getElementById(id);
  if (input) input.value = "";
}

function clearFile(id) {
  const input = document.getElementById(id);
  if (input) input.value = "";
}

function valueOf(id) {
  return document.getElementById(id)?.value.trim() || "";
}

function showToast(message) {
  state.toast = message;
  render();
  setTimeout(() => {
    if (state.toast === message) {
      state.toast = "";
      render();
    }
  }, 2400);
}

function profileLine() {
  if (!state.profile) return "Starting local engine...";
  return `${state.profile.runtime} runtime | ${state.profile.hardware_tier} profile | ` +
    `${state.profile.onnx_intra_threads} ONNX thread(s) | DB ${state.profile.db_path}`;
}

function tabLabel(view) {
  return {
    recognize: "Recognize",
    add: "Add Queue",
    people: "People",
    init: "Init Scan",
    debug: "Debug",
  }[view];
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

render();
refreshAll();
setInterval(() => {
  if (state.activeView === "debug") loadEvents();
}, 5000);
