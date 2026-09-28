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

export function formatSeenDateTime(detail) {
  const date = detail.date || "-";
  const time = detail.time || "-";
  return `${date} & ${time}`;
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

export function clearFile(ref) {
  if (ref.current) ref.current.value = "";
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
