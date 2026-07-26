import { useCallback } from "react";

import { readFileAsDataUrl } from "../utils.js";

export function useFileUploads({ apiPost, apiUpload, showToast }) {
  const uploadFile = useCallback(async (file, options = {}) => {
    showToast(`Uploading ${file.name}`);
    options.onProgress?.({ phase: "uploading", totalFiles: 1, uploadedFiles: 0 });
    const payload = await apiPost(
      "/api/upload",
      { filename: file.name, data: await readFileAsDataUrl(file) },
      { signal: options.signal },
    );
    options.onProgress?.({ phase: "uploading", totalFiles: 1, uploadedFiles: 1 });
    return payload.path;
  }, [apiPost, showToast]);

  const uploadFolder = useCallback(async (files, options = {}) => {
    showToast(`Uploading ${files.length} file(s)`);
    options.onProgress?.({ phase: "uploading", totalFiles: files.length, uploadedFiles: 0 });
    const uploadId = crypto.randomUUID();
    let uploadedFiles = 0;
    let uploadPath = "";
    try {
      for (const file of files) {
        if (options.signal?.aborted) throw new DOMException("Upload canceled", "AbortError");
        const query = new URLSearchParams({
          upload_id: uploadId,
          filename: file.name,
          relative_path: file.webkitRelativePath || file.name,
        });
        const payload = await apiUpload(`/api/upload-chunk?${query}`, file, { signal: options.signal });
        uploadPath = payload.path;
        uploadedFiles += 1;
        options.onProgress?.({ phase: "uploading", totalFiles: files.length, uploadedFiles });
      }
      return uploadPath;
    } catch (error) {
      if (uploadedFiles > 0) {
        try {
          await apiPost("/api/upload-batch-discard", { upload_id: uploadId });
        } catch (cleanupError) {
          console.debug("[sentriface-ui] partial upload cleanup unavailable", cleanupError);
        }
      }
      throw error;
    }
  }, [apiPost, apiUpload, showToast]);

  return { uploadFile, uploadFolder };
}
