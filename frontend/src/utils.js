import { MATCH_TEXT_THRESHOLDS } from "./constants.js";

export function mediaUrl(path) {
  return `/media?path=${encodeURIComponent(path)}`;
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
  if (!match) return "New Person !";
  if (hasCertainMatch(match)) return `That's ${match.name}`;
  if (match.score >= MATCH_TEXT_THRESHOLDS.likely) return `Likely ${match.name}`;
  if (match.score >= MATCH_TEXT_THRESHOLDS.possible) return `Perhaps ${match.name}`;
  if (match.score > MATCH_TEXT_THRESHOLDS.newPerson) return `Is it ${match.name}?`;
  return "New Person !";
}

export function hasCertainMatch(match) {
  return Boolean(match && match.score >= MATCH_TEXT_THRESHOLDS.certain);
}

export function isNewPersonSuggestion(match) {
  return !match || match.score <= MATCH_TEXT_THRESHOLDS.newPerson;
}

export function scoreColor(score) {
  if (score >= MATCH_TEXT_THRESHOLDS.certain) return "green";
  if (score >= MATCH_TEXT_THRESHOLDS.likely) return "blue";
  if (score >= MATCH_TEXT_THRESHOLDS.possible) return "yellow";
  return "red";
}

export function matchDisplay(score) {
  if (score >= MATCH_TEXT_THRESHOLDS.certain) {
    return {
      badge: "Strong Match",
      color: "green",
      stars: "★★★★★",
      confidence: "Very High Confidence",
    };
  }
  if (score >= MATCH_TEXT_THRESHOLDS.likely) {
    return {
      badge: "Good Match",
      color: "blue",
      stars: "★★★★☆",
      confidence: "High Confidence",
    };
  }
  if (score >= MATCH_TEXT_THRESHOLDS.possible) {
    return {
      badge: "Possible Match",
      color: "yellow",
      stars: "★★☆☆☆",
      confidence: "Possible Match",
    };
  }
  if (score > MATCH_TEXT_THRESHOLDS.newPerson) {
    return {
      badge: "Weak Match",
      color: "orange",
      stars: "★☆☆☆☆",
      confidence: "Low Confidence",
    };
  }
  return {
    badge: "No Match",
    color: "red",
    stars: "☆☆☆☆☆",
    confidence: "No Reliable Match",
  };
}

export function qualityColor(status) {
  return { good: "green", ambiguous: "yellow", unknown: "gray", bad: "red", warn: "yellow" }[status] || "gray";
}

export function profileLine(profile) {
  if (!profile) return "Starting local engine...";
  return `${profile.runtime.toUpperCase()} Runtime • ${titleCase(profile.hardware_tier)} Profile • ${profile.onnx_intra_threads} Threads • DB: ${profile.db_path}`;
}

export function tabLabel(view) {
  return {
    recognize: "Recognize",
    queue: "Queue",
    people: "People",
    debug: "Debug",
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

export function galleryImageRecords(payload) {
  return payload.embeddings
    .map((record) => ({
      embeddingId: record.embedding_id,
      path: record.crop_path || record.source_image,
    }))
    .filter((record) => record.path);
}

export function detailsForEmbedding(details, embeddingId) {
  return (details || []).filter((detail) => detail.embedding_id === embeddingId);
}

export function personProfile(payload, scopedDetails = payload.details || [], imageSelected = false) {
  const details = scopedDetails.length ? scopedDetails : payload.details || [];
  const metadata = payload.person.metadata || {};
  const latestDetail = details.find((detail) => detail.rank || detail.country || detail.importance || detail.name) || {};
  const hasScopedDetails = scopedDetails.length > 0;
  return {
    personId: payload.person.person_id,
    rank: hasScopedDetails ? latestDetail.rank || metadata.rank || "" : metadata.rank || latestDetail.rank || "",
    name: payload.person.name || latestDetail.name || "",
    country: hasScopedDetails ? latestDetail.country || metadata.country || "" : metadata.country || latestDetail.country || "",
    importance: hasScopedDetails ? latestDetail.importance || metadata.importance || "Regular" : metadata.importance || latestDetail.importance || "Regular",
    tags: Array.isArray(payload.person.tags) ? payload.person.tags : Array.isArray(metadata.tags) ? metadata.tags : [],
    createdAt: payload.person.created_at || "",
    addedBy: metadata.added_by || "",
    scopeLabel: hasScopedDetails ? "Selected image details" : imageSelected ? "Selected image has no saved details" : "Person summary",
  };
}

export function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
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
