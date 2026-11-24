export function mediaUrl(path) {
  const session = document.querySelector('meta[name="sentriface-session-token"]')?.content || "";
  return `/media?path=${encodeURIComponent(path)}&session=${encodeURIComponent(session)}`;
}

export function imageIdFromPath(path) {
  const parts = String(path || "").split(/[\\/]/).filter(Boolean);
  return parts.at(-1) || "unknown-image";
}

export function currentDateTimeParts() {
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

export function recognitionText(match) {
  if (!match || !match.is_known) return "New Person";
  if (["strong", "duplicate"].includes(match.classification)) return `${match.name} - Strong Match`;
  if (match.classification === "likely") return `${match.name} - Likely Match`;
  if (match.classification === "possible") return `${match.name} - Maybe Match`;
  return `${match.name} - No Match`;
}

export function isNewPersonSuggestion(match) {
  return !match || !match.is_known;
}

export function matchDisplay(match) {
  switch (match?.classification) {
    case "draft": return { badge: "Event draft", color: "teal", guidance: "Proposed from a resolved face in this Event" };
    case "manual": return { badge: "Selected", color: "teal", guidance: "Chosen manually" };
    case "duplicate":
    case "strong": return { badge: "Strong Match", color: "green", guidance: "Strong match based on the calibrated model setting" };
    case "likely": return { badge: "Likely Match", color: "blue", guidance: "Review recommended" };
    case "possible": return { badge: "Maybe Match", color: "yellow", guidance: "Manual review required" };
    case "weak": return { badge: "No Match", color: "orange", guidance: "Treat as a new or unknown person" };
    default: return { badge: "No Match", color: "red", guidance: "Treat as a new or unknown person" };
  }
}
export function qualityColor(status) {
  return { good: "green", ambiguous: "yellow", unknown: "gray", bad: "red", warn: "yellow" }[status] || "gray";
}

export function profileLine(profile) {
  if (!profile) return "Starting...";
  if (profile.runtime === "dev") return "Demo mode · Test results only";
  return `Ready on this computer · ${titleCase(profile.hardware_tier)} performance`;
}

export function tabLabel(view) {
  return {
    recognize: "Check a photo",
    queue: "Review photos",
    people: "People",
    encounters: "Events",
    world: "World",
    debug: "Settings",
  }[view];
}

const STORED_DATE = /^(\d{4}-\d{2}-\d{2})(?:$|T(?!.*(?:Z|[+-]\d{2}:?\d{2})$))/;

function recordedDate(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  const stored = STORED_DATE.exec(text);
  if (stored) return stored[1];
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return null;
  const pad = (part) => String(part).padStart(2, "0");
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}`;
}

// The one formatter for when an Event happened. It shows only what was recorded.
export function formatEventWhen(time) {
  const date = recordedDate(time?.date);
  if (!date) return "Date unknown";
  const start = time.time_precision === "unknown" ? "" : time.start_time || "";
  if (!start) return `${date} · Time unknown`;
  if (time.time_precision === "approximate") return `${date} · About ${start}`;
  return `${date} · ${start}${time.end_time ? `–${time.end_time}` : ""}`;
}

export function formatEventDate(value) {
  return recordedDate(value) || "Date unknown";
}

export function formatSavedTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function formatOccurrence(item) {
  return item?.event_time ? formatEventWhen(item.event_time) : formatSavedTime(item?.occurred_at);
}

export function formatSeenDateTime(detail) {
  return formatEventWhen({
    date: detail.date,
    time_precision: detail.time_precision || (detail.time ? "exact" : "unknown"),
    start_time: detail.time,
    end_time: detail.end_time,
  });
}

export function plural(count, noun) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export function galleryImages(payload) {
  return payload.embeddings.map((record) => record.crop_path || record.source_image).filter(Boolean);
}

export function detailsForEmbedding(details, embeddingId) {
  return (details || []).filter((detail) => detail.embedding_id === embeddingId);
}

export function personProfile(payload, imageSelected = false) {
  const person = requirePersonContract(payload.person);
  const metadata = payload.person.metadata || {};
  return {
    personId: person.person_id,
    rank: metadata.rank || "",
    name: person.name,
    country: metadata.country || "",
    importance: metadata.importance || "Regular",
    tags: Array.isArray(person.tags) ? person.tags : Array.isArray(metadata.tags) ? metadata.tags : [],
    createdAt: person.created_at || "",
    addedBy: metadata.added_by || "",
    scopeLabel: imageSelected ? "Person summary · selected face shown" : "Person summary",
  };
}

export function requirePersonContract(person) {
  if (!person || !person.person_id || !person.name) throw new Error("Invalid person read contract");
  if (!["ACTIVE", "ARCHIVED", "DELETED", "MERGED"].includes(person.lifecycle_status)) {
    throw new Error(`Invalid person lifecycle contract for ${person.person_id}`);
  }
  if (!("canonical_person_id" in person) || !person.effective_person_id || !Array.isArray(person.allowed_actions)) {
    throw new Error(`Incomplete person identity contract for ${person.person_id}`);
  }
  return person;
}

export function personAllows(person, action) {
  return requirePersonContract(person).allowed_actions.includes(action);
}

export async function droppedImageFiles(dataTransfer) {
  const items = Array.from(dataTransfer?.items || []);
  if (items.length && items[0].webkitGetAsEntry) {
    const files = [];
    await Promise.all(items.map(async (item) => {
      const entry = item.webkitGetAsEntry();
      if (entry) await collectEntryFiles(entry, files);
    }));
    return files;
  }
  return Array.from(dataTransfer?.files || []);
}

export function uploadRelativePath(file) {
  return file.webkitRelativePath || file.droppedRelativePath || file.name;
}

export function clearFile(ref) {
  if (ref.current) ref.current.value = "";
}

async function collectEntryFiles(entry, files) {
  if (entry.isFile) {
    const file = await entryFile(entry);
    const relativePath = String(entry.fullPath || "").replace(/^\/+/, "");
    if (relativePath && !file.webkitRelativePath) Object.defineProperty(file, "droppedRelativePath", { value: relativePath });
    files.push(file);
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

function titleCase(value) {
  return String(value || "")
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function entryFile(entry) {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

function readEntries(reader) {
  return new Promise((resolve, reject) => reader.readEntries(resolve, reject));
}

const EVENT_CONTEXT_LABELS = { ordinary: "Ordinary / small", public: "Public / group", unknown: "Unknown" };

export function eventContextLabel(context) {
  return EVENT_CONTEXT_LABELS[context] || "Unknown";
}

export function requiredFieldErrors(values, fields) {
  const errors = {};
  for (const [key, label] of fields) {
    const value = values?.[key];
    if (value === null || value === undefined || !String(value).trim()) errors[key] = `${label} is required`;
  }
  return errors;
}

export function backupReminderDue(lastDataChange, backups = []) {
  const changed = Date.parse(lastDataChange || "");
  if (Number.isNaN(changed)) return false;
  const usable = backups.filter((backup) => backup.complete !== false && backup.restorable !== false);
  const latest = Math.max(...usable.map((backup) => Date.parse(backup.created_at || "")).filter((value) => !Number.isNaN(value)), -Infinity);
  return changed > latest;
}

const BACKUP_REASON_LABELS = [
  ["before-person-delete-", "Safety copy before deleting a person"],
  ["before-person-archive-", "Safety copy before archiving a person"],
  ["before-face-permanent-delete-", "Safety copy before erasing a face"],
  ["before-face-delete-", "Safety copy before removing a face"],
  ["before-expired-face-purge-", "Safety copy before 30-day face cleanup"],
  ["before-restore-", "Safety copy before restoring a backup"],
  ["before-schema-migration-", "Safety copy before upgrading SentriFace data"],
  ["automatic-recovery", "First recovery backup"],
];

export function backupLabel(backup) {
  const reason = String(backup?.reason || "");
  if (!reason) return backup?.imported_from_backup_id ? "Imported backup" : "Manual backup";
  const match = BACKUP_REASON_LABELS.find(([prefix]) => reason.startsWith(prefix));
  return match ? match[1] : "Backup";
}

export function formatBackupDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value || "-");
  return date.toLocaleString([], {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
