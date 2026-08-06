import { useCallback, useEffect, useRef, useState } from "react";

export function useAppData({ activeView, capabilities = [], apiGet, apiPost, apiUpload, apiDownload, apiDelete, showToast }) {
  const canTechnical = capabilities.includes("technical");
  const canDestroy = capabilities.includes("destroy");
  const canBackups = capabilities.includes("backups");
  const canRecovery = capabilities.includes("recovery");
  const [profile, setProfile] = useState(null);
  const [connectionError, setConnectionError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
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
  const profileLoaded = useRef(false);
  const loadedViews = useRef(new Set());

  const loadProfile = useCallback(async (options = {}) => setProfile(await apiGet("/api/profile", options)), [apiGet]);
  const loadPeople = useCallback(async (options = {}) => {
    const payload = await apiGet("/api/persons", options);
    setPeople(payload.persons || []);
    setArchivedPeople(payload.archived_persons || []);
  }, [apiGet]);
  const loadEvents = useCallback(async (options = {}) => {
    if (!canTechnical) { setEvents([]); return { events: [] }; }
    const payload = await apiGet("/api/events", options);
    setEvents(payload.events || []);
    return payload;
  }, [apiGet, canTechnical]);
  const loadDeletedFaces = useCallback(async (options = {}) => {
    if (!canDestroy) { setDeletedFaces([]); return { deleted_faces: [] }; }
    const payload = await apiGet("/api/deleted-faces", options);
    setDeletedFaces(payload.deleted_faces || []);
    return payload;
  }, [apiGet, canDestroy]);
  const loadBackups = useCallback(async (options = {}) => {
    if (!canBackups) { setBackups([]); return { backups: [] }; }
    const payload = await apiGet("/api/backups", options);
    setBackups(payload.backups || []);
    return payload;
  }, [apiGet, canBackups]);
  const refreshAll = useCallback(async (options = {}) => {
    setConnectionError("");
    try {
      if (!profileLoaded.current || options.includeProfile) {
        await loadProfile(options);
        profileLoaded.current = true;
      }
      if (activeView === "people" && (options.force || !loadedViews.current.has("people"))) {
        await loadPeople(options);
        await loadDeletedFaces(options);
        loadedViews.current.add("people");
      }
      if (activeView === "debug" && (options.force || !loadedViews.current.has("debug"))) {
        await loadEvents(options);
        await loadBackups(options);
        loadedViews.current.add("debug");
      }
    } catch (error) {
      setConnectionError(error?.message || "SentriFace server is unavailable");
      throw error;
    }
  }, [activeView, loadProfile, loadPeople, loadDeletedFaces, loadEvents, loadBackups]);

  const updatePerson = useCallback((personId, updater) => {
    const update = (items) => items.map((person) => (
      person.person_id === personId ? updater(person) : person
    ));
    setPeople(update);
    setArchivedPeople(update);
  }, []);

  const upsertPerson = useCallback((person) => {
    if (!person?.person_id) return;
    setPeople((current) => [person, ...current.filter((item) => item.person_id !== person.person_id)]);
    setArchivedPeople((current) => current.filter((item) => item.person_id !== person.person_id));
  }, []);

  const archivePersonLocally = useCallback((personId, archivedAt, metadata = {}) => {
    const person = people.find((item) => item.person_id === personId);
    if (!person) return;
    const archived = {
      ...person,
      archived: true,
      deleted_at: archivedAt || new Date().toISOString(),
      metadata: { ...(person.metadata || {}), ...metadata },
    };
    setPeople((current) => current.filter((item) => item.person_id !== personId));
    setArchivedPeople((current) => [archived, ...current.filter((item) => item.person_id !== personId)]);
  }, [people]);

  const restorePersonLocally = useCallback((personId) => {
    const person = archivedPeople.find((item) => item.person_id === personId);
    if (!person) return;
    const restored = { ...person, archived: false, deleted_at: null };
    setArchivedPeople((current) => current.filter((item) => item.person_id !== personId));
    setPeople((current) => [restored, ...current.filter((item) => item.person_id !== personId)]);
  }, [archivedPeople]);

  const removePersonLocally = useCallback((personId) => {
    setPeople((current) => current.filter((item) => item.person_id !== personId));
    setArchivedPeople((current) => current.filter((item) => item.person_id !== personId));
    setDeletedFaces((current) => current.filter((item) => item.person_id !== personId));
  }, []);

  const addDeletedFace = useCallback((face) => {
    if (!face?.embedding_id) return;
    setDeletedFaces((current) => [face, ...current.filter((item) => item.embedding_id !== face.embedding_id)]);
  }, []);

  const removeDeletedFace = useCallback((embeddingId) => {
    setDeletedFaces((current) => current.filter((item) => item.embedding_id !== embeddingId));
  }, []);
  const reloadAppData = useCallback(async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      await refreshAll({ timeoutMs: 8_000, silent: true, includeProfile: true, force: true });
      showToast("App data refreshed");
    } finally {
      setRefreshing(false);
    }
  }, [refreshAll, refreshing, showToast]);

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

  const configureRecovery = async (destination) => {
    if (!canRecovery) return null;
    const result = await apiPost("/api/recovery/configure", { destination });
    setProfile((current) => ({
      ...current,
      recovery: {
        configured: result.configured,
        destination: result.destination,
        destination_available: result.destination_available,
        recovery_kit_present: result.recovery_kit_present,
        last_external_backup: result.last_external_backup,
        last_external_backup_path: result.last_external_backup_path,
        external_backup_count: result.external_backup_count,
        external_retention_limit: result.external_retention_limit,
      },
      recovery_readiness: result.readiness || current?.recovery_readiness,
    }));
    showToast(
      result.initial_backup_error ? `Recovery kit saved, but the first backup failed: ${result.initial_backup_error}` : "Automatic encrypted disaster recovery is configured",
      result.initial_backup_error ? "yellow" : "teal",
    );
    return result;
  };
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
    const anotherVerified = backups.some((backup) => (
      backup.backup_id !== backupId && backup.verified && backup.complete
    ));
    const recoveryStatus = anotherVerified
      ? "Another verified complete backup will remain."
      : "No other verified complete backup will remain.";
    const typed = window.prompt(
      `${recoveryStatus}\n\nType the backup ID to delete it:\n${backupId}`,
      "",
    );
    if (typed !== backupId) {
      if (typed !== null) showToast("Backup ID did not match; nothing was deleted.", "yellow");
      return;
    }
    const query = new URLSearchParams({ confirm: backupId });
    await apiDelete(`/api/backups/${encodeURIComponent(backupId)}?${query}`);
    setBackups((current) => current.filter((item) => item.backup_id !== backupId));
    showToast("Portable backup deleted", "yellow");
  };

  const importBackup = async (file, passphrase = "") => {
    if (!file || backupImporting) return;
    if (!/\.sfbackup\.enc$/i.test(String(file.name || ""))) {
      showToast("Choose a password-encrypted SentriFace .sfbackup.enc file.", "yellow", {
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
        {
          silent: true,
          timeoutMs: 30 * 60 * 1000,
          headers: file.name.toLowerCase().endsWith(".enc")
            ? { "X-SentriFace-Backup-Passphrase": encodePassphrase(passphrase) }
            : {},
        },
      );
      setBackups((current) => [
        payload.backup,
        ...current.filter((item) => item.backup_id !== payload.backup.backup_id),
      ].slice(0, 10));
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

  const downloadBackup = async (backupId, passphrase) => {
    if (!backupId) return;
    const { blob } = await apiDownload(
      `/api/backups/${encodeURIComponent(backupId)}/encrypted-download`,
      { passphrase },
      { silent: true },
    );
    const url = URL.createObjectURL(blob);
    try {
      const link = document.createElement("a");
      link.href = url;
      link.download = `${backupId}.sfbackup.enc`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      showToast("Encrypted backup exported", "teal", {
        title: "Keep the passphrase safe",
        autoClose: 6000,
      });
    } finally {
      URL.revokeObjectURL(url);
    }
  };

  const downloadSupportPackage = async () => {
    const { blob, contentDisposition } = await apiDownload(
      "/api/support-package",
      {},
      { silent: true },
    );
    const match = contentDisposition.match(/filename="?([^";]+)"?/i);
    const url = URL.createObjectURL(blob);
    try {
      const link = document.createElement("a");
      link.href = url;
      link.download = match?.[1] || `sentriface-support-${new Date().toISOString().replace(/[:.]/g, "-")}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      showToast("Support package exported", "teal");
      return true;
    } finally {
      URL.revokeObjectURL(url);
    }
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
    refreshing,
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
    updatePerson,
    upsertPerson,
    archivePersonLocally,
    restorePersonLocally,
    removePersonLocally,
    addDeletedFace,
    removeDeletedFace,
    refreshAll,
    reloadAppData,
    configureRecovery,
    requestBackup,
    cancelBackup,
    createBackup,
    deleteBackup,
    importBackup,
    downloadBackup,
    downloadSupportPackage,
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

function encodePassphrase(value) {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
