const state = {
  people: [],
  lastSessionId: "",
};

const $ = (id) => document.getElementById(id);

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".view").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    $(button.dataset.view).classList.add("active");
  });
});

$("refreshBtn").addEventListener("click", refreshAll);
$("peopleRefreshBtn").addEventListener("click", loadPeople);
$("pendingRefreshBtn").addEventListener("click", loadPending);
$("eventsRefreshBtn").addEventListener("click", loadEvents);
$("recognizeBtn").addEventListener("click", recognizeOne);
$("recognizeBatchBtn").addEventListener("click", recognizeBatch);
$("queueBtn").addEventListener("click", queueAdd);
$("enrollBtn").addEventListener("click", enroll);
$("initScanBtn").addEventListener("click", initScan);
$("initLoadBtn").addEventListener("click", loadInitGroups);
$("backupBtn").addEventListener("click", backupDb);

refreshAll();
setInterval(loadEvents, 5000);

async function refreshAll() {
  await Promise.all([loadProfile(), loadPeople(), loadPending(), loadEvents()]);
}

async function loadProfile() {
  const profile = await apiGet("/api/profile");
  $("profileLine").textContent =
    `${profile.runtime} runtime | ${profile.hardware_tier} profile | ` +
    `${profile.onnx_intra_threads} ONNX thread(s) | DB ${profile.db_path}`;
}

async function loadPeople() {
  const payload = await apiGet("/api/persons");
  state.people = payload.persons;
  $("peopleList").innerHTML = payload.persons.length
    ? payload.persons.map(renderPerson).join("")
    : `<div class="card muted">No people enrolled yet.</div>`;
}

async function loadPending() {
  const payload = await apiGet("/api/pending");
  $("pendingList").innerHTML = payload.pending.length
    ? payload.pending.map(renderPending).join("")
    : `<div class="card muted">No pending additions.</div>`;
}

async function loadEvents() {
  const payload = await apiGet("/api/events");
  $("debugLog").textContent = payload.events.map((event) => JSON.stringify(event)).join("\n");
}

async function recognizeOne() {
  const payload = await apiPost("/api/recognize", { path: $("recognizePath").value });
  $("recognizeResults").innerHTML = renderFaces(payload.faces, payload.metrics);
  toast(`Recognized ${payload.faces.length} face(s)`);
  await loadEvents();
}

async function recognizeBatch() {
  const payload = await apiPost("/api/recognize-batch", { path: $("recognizePath").value });
  $("recognizeResults").innerHTML = payload.batch.map((item) => `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="title">${escapeHtml(item.image)}</div>
          <div class="muted">${item.faces.length} face(s)</div>
        </div>
      </div>
      ${renderFaces(item.faces)}
    </div>
  `).join("") + renderMetrics(payload.metrics);
  toast(`Processed ${payload.batch.length} image(s)`);
  await loadEvents();
}

async function queueAdd() {
  const payload = await apiPost("/api/queue-add", {
    path: $("queuePath").value,
    force_bad_quality: $("forceBadQuality").checked,
  });
  toast(`Queued ${payload.pending.length}, rejected ${payload.rejected.length}`);
  $("pendingList").innerHTML = payload.pending.map(renderPending).join("") || `<div class="card muted">No accepted faces.</div>`;
  await Promise.all([loadPending(), loadEvents()]);
}

async function enroll() {
  const payload = await apiPost("/api/enroll", {
    path: $("enrollPath").value,
    name: $("enrollName").value,
  });
  toast(`Enrolled person ${payload.person_id}`);
  await Promise.all([loadPeople(), loadEvents()]);
}

async function confirmNew(pendingId) {
  const name = prompt("New person name");
  if (!name) return;
  await apiPost("/api/confirm-new", { pending_id: pendingId, name });
  toast("Pending face confirmed as new person");
  await Promise.all([loadPeople(), loadPending(), loadEvents()]);
}

async function confirmExisting(pendingId) {
  const personId = prompt("Existing person ID");
  if (!personId) return;
  await apiPost("/api/confirm-existing", { pending_id: pendingId, person_id: personId });
  toast("Pending face added to existing person");
  await Promise.all([loadPeople(), loadPending(), loadEvents()]);
}

async function rejectPending(pendingId) {
  await apiPost("/api/reject-pending", { pending_id: pendingId });
  toast("Pending face rejected");
  await Promise.all([loadPending(), loadEvents()]);
}

async function initScan() {
  const payload = await apiPost("/api/init-scan", { path: $("initPath").value });
  state.lastSessionId = payload.session_id;
  $("initSessionId").value = payload.session_id;
  $("initGroups").innerHTML = renderInitGroups(payload.groups);
  toast(`Init session created with ${payload.groups.length} group(s)`);
  await loadEvents();
}

async function loadInitGroups() {
  const sessionId = $("initSessionId").value || state.lastSessionId;
  const payload = await apiGet(`/api/init-groups?session_id=${encodeURIComponent(sessionId)}`);
  $("initGroups").innerHTML = renderInitGroups(payload.groups);
}

async function initConfirm(sessionId, groupId) {
  const name = prompt("New person name");
  if (!name) return;
  await apiPost("/api/init-confirm", { session_id: sessionId, group_id: groupId, name });
  toast("Init group confirmed as new person");
  await Promise.all([loadInitGroups(), loadPeople(), loadEvents()]);
}

async function initConfirmExisting(sessionId, groupId) {
  const personId = prompt("Existing person ID");
  if (!personId) return;
  await apiPost("/api/init-confirm-existing", { session_id: sessionId, group_id: groupId, person_id: personId });
  toast("Init group added to existing person");
  await Promise.all([loadInitGroups(), loadPeople(), loadEvents()]);
}

async function initReject(sessionId, groupId) {
  await apiPost("/api/init-reject", { session_id: sessionId, group_id: groupId });
  toast("Init group rejected");
  await Promise.all([loadInitGroups(), loadEvents()]);
}

async function initReset(sessionId, groupId) {
  await apiPost("/api/init-reset", { session_id: sessionId, group_id: groupId });
  toast("Init group reset");
  await Promise.all([loadInitGroups(), loadEvents()]);
}

async function backupDb() {
  const path = prompt("Backup target path", "backups/sentriface.db");
  if (!path) return;
  await apiPost("/api/backup-db", { path });
  toast("Database backup created");
  await loadEvents();
}

function renderPerson(person) {
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

function renderPending(item) {
  return `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="title">${escapeHtml(item.pending_id)}</div>
          <div class="muted">${escapeHtml(item.source_image)}</div>
        </div>
        <span class="pill ${item.decision}">${item.decision}</span>
      </div>
      ${renderThumb(item.crop_path)}
      ${renderQuality(item.quality)}
      ${renderMatches(item.matches)}
      <div class="row">
        <button onclick="confirmNew('${item.pending_id}')">New</button>
        <button onclick="confirmExisting('${item.pending_id}')">Existing</button>
        <button onclick="rejectPending('${item.pending_id}')">Reject</button>
      </div>
    </div>
  `;
}

function renderFaces(faces, metrics) {
  const body = faces.length ? faces.map((face) => `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="title">Face ${face.index}</div>
          <div class="muted">box ${face.box.width}x${face.box.height}, detector ${face.box.confidence.toFixed(3)}</div>
        </div>
        <span class="pill ${face.decision}">${face.decision}</span>
      </div>
      ${renderQuality(face.quality)}
      ${renderMatches(face.matches)}
    </div>
  `).join("") : `<div class="card muted">No faces detected.</div>`;
  return body + (metrics ? renderMetrics(metrics) : "");
}

function renderInitGroups(groups) {
  return groups.length ? groups.map((group) => `
    <div class="card">
      <div class="card-head">
        <div>
          <div class="title">${escapeHtml(group.group_id)}</div>
          <div class="muted">session ${escapeHtml(group.session_id)} | ${group.faces.length} face(s)</div>
        </div>
        <span class="pill">${escapeHtml(group.status)}</span>
      </div>
      <div class="thumbs">${group.faces.map((face) => renderThumb(face.crop_path)).join("")}</div>
      <div class="row">
        <button onclick="initConfirm('${group.session_id}', '${group.group_id}')">New</button>
        <button onclick="initConfirmExisting('${group.session_id}', '${group.group_id}')">Existing</button>
        <button onclick="initReject('${group.session_id}', '${group.group_id}')">Reject</button>
        <button onclick="initReset('${group.session_id}', '${group.group_id}')">Reset</button>
      </div>
    </div>
  `).join("") : `<div class="card muted">No groups.</div>`;
}

function renderQuality(quality) {
  if (!quality) return "";
  const reasons = quality.reasons.length ? ` | ${quality.reasons.map(escapeHtml).join(", ")}` : "";
  return `<div class="muted"><span class="pill ${quality.status}">${quality.status}</span> score ${quality.score.toFixed(3)}${reasons}</div>`;
}

function renderMatches(matches) {
  if (!matches.length) return `<div class="muted">No matches.</div>`;
  return `<div class="matches">${matches.map((match) => `
    <div class="match">
      <div class="title">#${match.rank} ${escapeHtml(match.name)} <span class="muted">${match.score.toFixed(4)}</span></div>
      <div class="muted">${escapeHtml(match.person_id)} | ${match.embeddings_matched} embedding(s)</div>
    </div>
  `).join("")}</div>`;
}

function renderMetrics(metrics) {
  if (!metrics) return "";
  return `<div class="card"><div class="title">Metrics</div><pre>${escapeHtml(JSON.stringify(metrics, null, 2))}</pre></div>`;
}

function renderThumb(path) {
  if (!path) return "";
  return `<img src="/media?path=${encodeURIComponent(path)}" alt="face crop" />`;
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
    toast(payload.error || "Request failed");
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.classList.add("show");
  setTimeout(() => node.classList.remove("show"), 2400);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
