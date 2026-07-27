import { useCallback } from "react";

import { partitionImageFiles, skippedInputMessage } from "../inputValidation.js";

export function useFileUploads({ apiPost, apiUpload, showToast }) {
  const reportInputRejections = useCallback(async (source, rejectedCount, acceptedCount, reasons) => {
    if (!rejectedCount) return;
    try {
      await apiPost("/api/input-rejections", {
        source,
        rejected_count: rejectedCount,
        accepted_count: acceptedCount,
        reasons,
      }, { silent: true });
    } catch {
      // Input rejection reporting must never interrupt valid work.
    }
  }, [apiPost]);

  const prepareImageFiles = useCallback(async (files, source) => {
    const result = await partitionImageFiles(files);
    await reportInputRejections(
      source,
      result.rejected.length,
      result.validFiles.length,
      result.reasons,
    );
    return result;
  }, [reportInputRejections]);

  const notifySkippedInputs = useCallback((rejectedCount, acceptedCount) => {
    if (!rejectedCount) return;
    showToast(
      skippedInputMessage(rejectedCount, acceptedCount),
      "yellow",
      { title: "Invalid input skipped", autoClose: 5000 },
    );
  }, [showToast]);

  const uploadFile = useCallback(async (file, options = {}) => {
    showToast(`Uploading ${file.name}`);
    options.onProgress?.({ phase: "uploading", totalFiles: 1, uploadedFiles: 0 });
    const uploadId = crypto.randomUUID();
    const query = new URLSearchParams({
      upload_id: uploadId,
      filename: file.name,
      relative_path: file.webkitRelativePath || file.name,
    });
    try {
      const payload = await apiUpload(
        `/api/upload-chunk?${query}`,
        file,
        { signal: options.signal, silent: true },
      );
      options.onProgress?.({ phase: "uploading", totalFiles: 1, uploadedFiles: 1 });
      return {
        path: payload.stored_path,
        uploadedFiles: 1,
        rejectedFiles: 0,
        rejectionReasons: {},
      };
    } catch (error) {
      if (error?.code !== "invalid_input") {
        if (error?.name === "AbortError") throw error;
        showToast(error?.message || "The image could not be uploaded", "red", {
          title: "Upload failed",
          autoClose: 5000,
        });
        throw error;
      }
      return {
        path: "",
        uploadedFiles: 0,
        rejectedFiles: 1,
        rejectionReasons: { [error.reason || "invalid_image_content"]: 1 },
      };
    }
  }, [apiUpload, showToast]);

  const uploadFolder = useCallback(async (files, options = {}) => {
    showToast(`Uploading ${files.length} file(s)`);
    options.onProgress?.({ phase: "uploading", totalFiles: files.length, uploadedFiles: 0 });
    const uploadId = crypto.randomUUID();
    let uploadedFiles = 0;
    let uploadPath = "";
    let rejectedFiles = 0;
    const rejectionReasons = {};
    try {
      for (const file of files) {
        if (options.signal?.aborted) throw new DOMException("Upload canceled", "AbortError");
        const query = new URLSearchParams({
          upload_id: uploadId,
          filename: file.name,
          relative_path: file.webkitRelativePath || file.name,
        });
        try {
          const payload = await apiUpload(
            `/api/upload-chunk?${query}`,
            file,
            { signal: options.signal, silent: true },
          );
          uploadPath = payload.path;
          uploadedFiles += 1;
          options.onProgress?.({ phase: "uploading", totalFiles: files.length, uploadedFiles });
        } catch (error) {
          if (error?.code !== "invalid_input") throw error;
          rejectedFiles += 1;
          const reason = error.reason || "invalid_image_content";
          rejectionReasons[reason] = (rejectionReasons[reason] || 0) + 1;
        }
      }
      return { path: uploadPath, uploadedFiles, rejectedFiles, rejectionReasons };
    } catch (error) {
      if (uploadedFiles > 0) {
        try {
          await apiPost("/api/upload-batch-discard", { upload_id: uploadId }, { silent: true });
        } catch {}
      }
      if (error?.name !== "AbortError") {
        showToast(error?.message || "The image batch could not be uploaded", "red", {
          title: "Upload failed",
          autoClose: 5000,
        });
      }
      throw error;
    }
  }, [apiPost, apiUpload, showToast]);

  return {
    notifySkippedInputs,
    prepareImageFiles,
    reportInputRejections,
    uploadFile,
    uploadFolder,
  };
}
