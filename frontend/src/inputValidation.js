export const MAX_IMAGE_FILE_BYTES = 100_000_000;

const EXTENSION_FORMATS = new Map([
  [".jpg", "jpeg"],
  [".jpeg", "jpeg"],
  [".png", "png"],
  [".bmp", "bmp"],
  [".webp", "webp"],
]);

const MIME_FORMATS = new Map([
  ["image/jpeg", "jpeg"],
  ["image/jpg", "jpeg"],
  ["image/png", "png"],
  ["image/bmp", "bmp"],
  ["image/webp", "webp"],
]);

export async function partitionImageFiles(files) {
  const validFiles = [];
  const rejected = [];
  for (const file of Array.from(files || [])) {
    let reason = "";
    try {
      reason = await invalidImageReason(file);
    } catch {
      reason = "unreadable_file";
    }
    if (reason) rejected.push({ file, reason });
    else validFiles.push(file);
  }
  return {
    validFiles,
    rejected,
    reasons: countReasons(rejected),
  };
}

export function skippedInputMessage(rejectedCount, acceptedCount) {
  const files = rejectedCount === 1 ? "file was" : "files were";
  if (acceptedCount > 0) {
    return `${rejectedCount} invalid ${files} skipped. ${acceptedCount} valid image${acceptedCount === 1 ? "" : "s"} will continue.`;
  }
  return `${rejectedCount} invalid ${files} skipped. No usable images were found.`;
}

async function invalidImageReason(file) {
  if (!file || typeof file.name !== "string" || typeof file.slice !== "function") {
    return "invalid_file";
  }
  const name = file.name.trim();
  if (!name || name.length > 255 || name.includes("\0")) return "invalid_name";
  if (!Number.isFinite(file.size) || file.size <= 0) return "empty_file";
  if (file.size > MAX_IMAGE_FILE_BYTES) return "file_too_large";

  const extension = name.includes(".") ? name.slice(name.lastIndexOf(".")).toLowerCase() : "";
  const expectedFormat = EXTENSION_FORMATS.get(extension);
  if (!expectedFormat) return "unsupported_extension";

  const declaredType = String(file.type || "").trim().toLowerCase();
  const declaredFormat = MIME_FORMATS.get(declaredType);
  if (declaredType && declaredType !== "application/octet-stream" && !declaredFormat) {
    return "unsupported_media_type";
  }
  if (declaredFormat && declaredFormat !== expectedFormat) return "media_type_mismatch";

  try {
    const header = new Uint8Array(await file.slice(0, 16).arrayBuffer());
    const detectedFormat = detectHeaderFormat(header);
    if (!detectedFormat) return "invalid_image_content";
    if (detectedFormat !== expectedFormat) return "content_type_mismatch";
  } catch {
    return "unreadable_file";
  }
  return "";
}

function detectHeaderFormat(bytes) {
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
    return "jpeg";
  }
  if (
    bytes.length >= 8
    && bytes[0] === 0x89
    && bytes[1] === 0x50
    && bytes[2] === 0x4e
    && bytes[3] === 0x47
    && bytes[4] === 0x0d
    && bytes[5] === 0x0a
    && bytes[6] === 0x1a
    && bytes[7] === 0x0a
  ) {
    return "png";
  }
  if (bytes.length >= 2 && bytes[0] === 0x42 && bytes[1] === 0x4d) return "bmp";
  if (
    bytes.length >= 12
    && String.fromCharCode(...bytes.slice(0, 4)) === "RIFF"
    && String.fromCharCode(...bytes.slice(8, 12)) === "WEBP"
  ) {
    return "webp";
  }
  return "";
}

function countReasons(rejected) {
  return rejected.reduce((counts, item) => {
    counts[item.reason] = (counts[item.reason] || 0) + 1;
    return counts;
  }, {});
}
