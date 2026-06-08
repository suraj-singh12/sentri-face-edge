import { useCallback } from "react";

import { readFileAsDataUrl } from "../utils.js";

export function useFileUploads({ apiPost, showToast }) {
  const uploadFile = useCallback(async (file) => {
    showToast(`Uploading ${file.name}`);
    const payload = await apiPost("/api/upload", { filename: file.name, data: await readFileAsDataUrl(file) });
    return payload.path;
  }, [apiPost, showToast]);

  const uploadFolder = useCallback(async (files) => {
    showToast(`Uploading ${files.length} file(s)`);
    const payloadFiles = await Promise.all(files.map(async (file) => ({
      filename: file.name,
      relative_path: file.webkitRelativePath || file.name,
      data: await readFileAsDataUrl(file),
    })));
    const payload = await apiPost("/api/upload-batch", { files: payloadFiles });
    return payload.path;
  }, [apiPost, showToast]);

  return { uploadFile, uploadFolder };
}
