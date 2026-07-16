import { useState } from "react";

import { useApiClient } from "./useApiClient.js";
import { useAppData } from "./useAppData.js";
import { useFileUploads } from "./useFileUploads.js";
import { usePeopleController } from "./usePeopleController.js";
import { useQueueController } from "./useQueueController.js";
import { useRecognizeController } from "./useRecognizeController.js";

export function useSentriFaceController() {
  const [activeView, setActiveView] = useState("recognize");
  const api = useApiClient();
  const uploads = useFileUploads(api);
  const appData = useAppData({ activeView, ...api });
  const recognize = useRecognizeController({ ...api, ...uploads, loadEvents: appData.loadEvents, loadPeople: appData.loadPeople });
  const queue = useQueueController({ ...api, ...uploads, loadEvents: appData.loadEvents, loadPeople: appData.loadPeople });
  const people = usePeopleController({ ...api, loadEvents: appData.loadEvents, loadPeople: appData.loadPeople });

  return {
    state: {
      activeView,
      profile: appData.profile,
      people: appData.people,
      events: appData.events,
      backups: appData.backups,
      backupModalOpen: appData.backupModalOpen,
      backupCreating: appData.backupCreating,
      ...recognize.state,
      ...queue.state,
      ...people.state,
    },
    refs: { ...recognize.refs },
    actions: {
      setActiveView,
      refreshAll: appData.refreshAll,
      loadPeople: appData.loadPeople,
      loadEvents: appData.loadEvents,
      loadBackups: appData.loadBackups,
      requestBackup: appData.requestBackup,
      cancelBackup: appData.cancelBackup,
      createBackup: appData.createBackup,
      deleteBackup: appData.deleteBackup,
      ...recognize.actions,
      ...queue.actions,
      ...people.actions,
      guarded: api.guarded,
    },
  };
}
