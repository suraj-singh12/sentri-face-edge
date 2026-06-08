import { useCallback, useEffect, useState } from "react";

export function useAppData({ activeView, apiGet, apiPost, showToast }) {
  const [profile, setProfile] = useState(null);
  const [people, setPeople] = useState([]);
  const [events, setEvents] = useState([]);

  const loadProfile = useCallback(async () => setProfile(await apiGet("/api/profile")), [apiGet]);
  const loadPeople = useCallback(async () => setPeople((await apiGet("/api/persons")).persons), [apiGet]);
  const loadEvents = useCallback(async () => setEvents((await apiGet("/api/events")).events), [apiGet]);
  const refreshAll = useCallback(async () => Promise.all([loadProfile(), loadPeople(), loadEvents()]), [loadProfile, loadPeople, loadEvents]);

  useEffect(() => {
    refreshAll().catch((error) => console.error(error));
  }, [refreshAll]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (activeView === "debug") loadEvents().catch((error) => console.error(error));
    }, 5000);
    return () => window.clearInterval(timer);
  }, [activeView, loadEvents]);

  const backupDb = async () => {
    const path = window.prompt("Backup target path", "backups/sentriface.db");
    if (!path) return;
    await apiPost("/api/backup-db", { path });
    showToast("Database backup created");
    await loadEvents();
  };

  return {
    profile,
    people,
    events,
    loadPeople,
    loadEvents,
    refreshAll,
    backupDb,
  };
}
