import { useCallback } from "react";

import { readFileAsDataUrl } from "../utils.js";

export function useFileUploads({ apiPost, showToast }) {
  const uploadFile = useCallback(async (file, options = {}) => {
    showToast(`Uploading ${file.name}`);
    options.onProgress?.({ phase: "uploading", totalFiles: 1, uploadedFiles: 0 });
    const payload = await apiPost("/api/upload", { filename: file.name, data: await readFileAsDataUrl(file) });
    options.onProgress?.({ phase: "uploading", totalFiles: 1, uploadedFiles: 1 });
    return payload.path;
  }, [apiPost, showToast]);

  const uploadFolder = useCallback(async (files, options = {}) => {
    showToast(`Uploading ${files.length} file(s)`);
    options.onProgress?.({ phase: "uploading", totalFiles: files.length, uploadedFiles: 0 });
    const payloadFiles = [];
    for (const file of files) {
      payloadFiles.push({
        filename: file.name,
        relative_path: file.webkitRelativePath || file.name,
        data: await readFileAsDataUrl(file),
      });
      options.onProgress?.({ phase: "uploading", totalFiles: files.length, uploadedFiles: payloadFiles.length });
    }
    const payload = await apiPost("/api/upload-batch", { files: payloadFiles });
    options.onProgress?.({ phase: "uploading", totalFiles: files.length, uploadedFiles: files.length });
    return payload.path;
  }, [apiPost, showToast]);

  return { uploadFile, uploadFolder };
}
