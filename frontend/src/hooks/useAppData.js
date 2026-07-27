import { useCallback, useEffect, useRef, useState } from "react";

export function useAppData({ activeView, apiGet, apiPost, apiUpload, apiDelete, showToast }) {
  const [profile, setProfile] = useState(null);
  const [people, setPeople] = useState([]);
  const [archivedPeople, setArchivedPeople] = useState([]);
  const [deletedFaces, setDeletedFaces] = useState([]);
  const [events, setEvents] = useState([]);
  const [backups, setBackups] = useState([]);
  const [backupModalOpen, setBackupModalOpen] = useState(false);
  const [backupCreating, setBackupCreating] = useState(false);
  const [backupImporting, setBackupImporting] = useState(false);
  const [backupRestoring, setBackupRestoring] = useState(false);
  const [restoreBackupSelection, setRestoreBackupSelection] = useState(null);
  const backupInFlight = useRef(false);
  const restoreInFlight = useRef(false);

  const loadProfile = useCallback(async () => setProfile(await apiGet("/api/profile")), [apiGet]);
  const loadPeople = useCallback(async () => {
    const payload = await apiGet("/api/persons");
    setPeople(payload.persons || []);
    setArchivedPeople(payload.archived_persons || []);
  }, [apiGet]);
  const loadEvents = useCallback(async () => setEvents((await apiGet("/api/events")).events), [apiGet]);
  const loadDeletedFaces = useCallback(async () => {
    setDeletedFaces((await apiGet("/api/deleted-faces")).deleted_faces || []);
  }, [apiGet]);
  const loadBackups = useCallback(async () => setBackups((await apiGet("/api/backups")).backups), [apiGet]);
  const refreshAll = useCallback(
    async () => Promise.all([loadProfile(), loadPeople(), loadDeletedFaces(), loadEvents(), loadBackups()]),
    [loadProfile, loadPeople, loadDeletedFaces, loadEvents, loadBackups],
  );
  const reloadAppData = useCallback(async () => {
    await refreshAll();
    showToast("App data reloaded");
  }, [refreshAll, showToast]);

  useEffect(() => {
    refreshAll().catch((error) => console.error(error));
  }, [refreshAll]);

  useEffect(() => {
    const restored = window.sessionStorage.getItem("sentriface.restoreNotice");
    if (!restored) return;
    window.sessionStorage.removeItem("sentriface.restoreNotice");
    showToast(restored, "teal", {
      title: "Portable backup restored",
      autoClose: 8500,
    });
  }, [showToast]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (activeView === "debug") loadEvents().catch((error) => console.error(error));
    }, 5000);
    return () => window.clearInterval(timer);
  }, [activeView, loadEvents]);

  const requestBackup = () => {
    if (!backupCreating) setBackupModalOpen(true);
  };

  const cancelBackup = () => {
    if (!backupCreating) setBackupModalOpen(false);
  };

  const createBackup = async () => {
    if (backupInFlight.current) return;
    backupInFlight.current = true;
    setBackupCreating(true);
    setBackupModalOpen(false);
    try {
      const payload = await apiPost("/api/backups", {});
      const backup = payload.backup;
      setBackups((current) => [backup, ...current.filter((item) => item.backup_id !== backup.backup_id)].slice(0, 10));
      showToast(
        `${formatBackupDateTime(backup.created_at)} · ${formatBytes(backup.size_bytes)} · ${backup.file_count || 0} referenced file${backup.file_count === 1 ? "" : "s"}`,
        "teal",
        {
          title: backup.complete ? "Portable backup created" : "Backup created with missing files",
          autoClose: 7500,
        },
      );
      await Promise.all([loadBackups(), loadEvents()]);
    } catch (error) {
      showToast(
        `${error.message || "Portable backup could not be created."}\nYour current data was not changed.`,
        "red",
        { title: "Portable backup could not be created.", autoClose: 7500 },
      );
      throw error;
    } finally {
      backupInFlight.current = false;
      setBackupCreating(false);
    }
  };

  const deleteBackup = async (backupId) => {
    if (!backupId) return;
    const confirmed = window.confirm("Delete this portable backup? This cannot be undone.");
    if (!confirmed) return;
    await apiDelete(`/api/backups/${encodeURIComponent(backupId)}`);
    setBackups((current) => current.filter((item) => item.backup_id !== backupId));
    showToast("Portable backup deleted", "yellow");
    await loadEvents();
  };

  const importBackup = async (file) => {
    if (!file || backupImporting) return;
    if (!String(file.name || "").toLowerCase().endsWith(".sfbackup")) {
      showToast("Choose a SentriFace .sfbackup file.", "yellow", {
        title: "Invalid backup skipped",
      });
      return;
    }
    if (!Number.isFinite(file.size) || file.size <= 0 || file.size > 20_000_000_000) {
      showToast("The selected backup is empty or exceeds the 20 GB import limit.", "yellow", {
        title: "Invalid backup skipped",
      });
      return;
    }
    setBackupImporting(true);
    try {
      const query = new URLSearchParams({ filename: file.name });
      const payload = await apiUpload(
        `/api/backups/import?${query}`,
        file,
        { silent: true, timeoutMs: 30 * 60 * 1000 },
      );
      await Promise.all([loadBackups(), loadEvents()]);
      showToast(
        `${formatBytes(payload.backup.size_bytes)} · ${payload.backup.file_count || 0} referenced file${payload.backup.file_count === 1 ? "" : "s"}`,
        payload.backup.complete ? "teal" : "yellow",
        {
          title: payload.backup.complete
            ? "Portable backup imported and verified"
            : "Backup imported with missing historical files",
          autoClose: 8000,
        },
      );
    } catch (error) {
      showToast(error.message || "Portable backup import failed.", "red", {
        title: "Backup was not imported",
        autoClose: 8000,
      });
      throw error;
    } finally {
      setBackupImporting(false);
    }
  };

  const downloadBackup = (backupId) => {
    if (!backupId) return;
    const link = document.createElement("a");
    link.href = `/api/backups/${encodeURIComponent(backupId)}/download`;
    link.download = `${backupId}.sfbackup`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const requestRestoreBackup = (backup) => {
    if (!backupRestoring && backup?.verified && backup?.portable && backup?.complete) {
      setRestoreBackupSelection(backup);
    }
  };

  const cancelRestoreBackup = () => {
    if (!backupRestoring) setRestoreBackupSelection(null);
  };

  const restoreBackup = async () => {
    const backup = restoreBackupSelection;
    if (!backup || restoreInFlight.current) return;
    restoreInFlight.current = true;
    setBackupRestoring(true);
    try {
      const payload = await apiPost("/api/backups/restore", {
        backup_id: backup.backup_id,
        operation_id: crypto.randomUUID(),
        allow_incomplete: false,
      });
      const result = payload.restore;
      window.sessionStorage.setItem(
        "sentriface.restoreNotice",
        `Restored ${result.restored_files} referenced file${result.restored_files === 1 ? "" : "s"}. A safety backup of the previous state was created automatically.`,
      );
      clearPersistedApplicationState();
      window.location.reload();
    } catch (error) {
      showToast(
        `${error.message || "Restore failed."}\nThe previous application state was kept or restored automatically.`,
        "red",
        { title: "Portable backup was not restored", autoClose: 9000 },
      );
      throw error;
    } finally {
      restoreInFlight.current = false;
      setBackupRestoring(false);
    }
  };

  return {
    profile,
    people,
    archivedPeople,
    deletedFaces,
    events,
    backups,
    backupModalOpen,
    backupCreating,
    backupImporting,
    backupRestoring,
    restoreBackupSelection,
    loadPeople,
    loadEvents,
    loadDeletedFaces,
    loadBackups,
    refreshAll,
    reloadAppData,
    requestBackup,
    cancelBackup,
    createBackup,
    deleteBackup,
    importBackup,
    downloadBackup,
    requestRestoreBackup,
    cancelRestoreBackup,
    restoreBackup,
  };
}

function clearPersistedApplicationState() {
  const keys = [];
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    if (key?.startsWith("sentriface.")) keys.push(key);
  }
  keys.forEach((key) => window.localStorage.removeItem(key));
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatBackupDateTime(value) {
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
