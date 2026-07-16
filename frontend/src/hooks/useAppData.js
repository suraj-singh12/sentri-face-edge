import { useCallback, useEffect, useRef, useState } from "react";

export function useAppData({ activeView, apiGet, apiPost, apiDelete, showToast }) {
  const [profile, setProfile] = useState(null);
  const [people, setPeople] = useState([]);
  const [events, setEvents] = useState([]);
  const [backups, setBackups] = useState([]);
  const [backupModalOpen, setBackupModalOpen] = useState(false);
  const [backupCreating, setBackupCreating] = useState(false);
  const backupInFlight = useRef(false);

  const loadProfile = useCallback(async () => setProfile(await apiGet("/api/profile")), [apiGet]);
  const loadPeople = useCallback(async () => setPeople((await apiGet("/api/persons")).persons), [apiGet]);
  const loadEvents = useCallback(async () => setEvents((await apiGet("/api/events")).events), [apiGet]);
  const loadBackups = useCallback(async () => setBackups((await apiGet("/api/backups")).backups), [apiGet]);
  const refreshAll = useCallback(async () => Promise.all([loadProfile(), loadPeople(), loadEvents(), loadBackups()]), [loadProfile, loadPeople, loadEvents, loadBackups]);
  const reloadAppData = useCallback(async () => {
    await refreshAll();
    showToast("App data reloaded");
  }, [refreshAll, showToast]);

  useEffect(() => {
    refreshAll().catch((error) => console.error(error));
  }, [refreshAll]);

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
        `${formatBackupDateTime(backup.created_at)} · ${formatBytes(backup.size_bytes)}`,
        "teal",
        { title: "Database backup created", autoClose: 6500 },
      );
      await Promise.all([loadBackups(), loadEvents()]);
    } catch (error) {
      showToast(
        `${error.message || "Database backup could not be created."}\nYour current database was not changed.`,
        "red",
        { title: "Database backup could not be created.", autoClose: 7500 },
      );
      throw error;
    } finally {
      backupInFlight.current = false;
      setBackupCreating(false);
    }
  };

  const deleteBackup = async (backupId) => {
    if (!backupId) return;
    const confirmed = window.confirm("Delete this database backup?");
    if (!confirmed) return;
    await apiDelete(`/api/backups/${encodeURIComponent(backupId)}`);
    setBackups((current) => current.filter((item) => item.backup_id !== backupId));
    showToast("Database backup deleted", "yellow");
    await loadEvents();
  };

  return {
    profile,
    people,
    events,
    backups,
    backupModalOpen,
    backupCreating,
    loadPeople,
    loadEvents,
    loadBackups,
    refreshAll,
    reloadAppData,
    requestBackup,
    cancelBackup,
    createBackup,
    deleteBackup,
  };
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
