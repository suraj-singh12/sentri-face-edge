import { useApiClient } from "./useApiClient.js";
import { useAppData } from "./useAppData.js";
import { useFileUploads } from "./useFileUploads.js";
import { usePersistentState } from "./usePersistentState.js";
import { usePeopleController } from "./usePeopleController.js";
import { useQueueController } from "./useQueueController.js";
import { useRecognizeController } from "./useRecognizeController.js";

export function useSentriFaceController({ capabilities = [] } = {}) {
  const [activeView, setActiveView] = usePersistentState("sentriface.activeView", "recognize");
  const api = useApiClient();
  const canAdd = capabilities.includes("add");
  const uploads = useFileUploads(api);
  const appData = useAppData({ activeView, capabilities, ...api });
  const people = usePeopleController({
    ...api,
    loadPeople: appData.loadPeople,
    loadDeletedFaces: appData.loadDeletedFaces,
  });
  const recognize = useRecognizeController({
    ...api,
    ...uploads,
    loadPeople: appData.loadPeople,
    onExistingPersonEnrolled: async (personId) => {
      await people.actions.refreshPeopleProfile(personId);
      setActiveView("people");
    },
  });
  const queue = useQueueController({
    enabled: canAdd && activeView === "queue",
    ...api,
    ...uploads,
    loadPeople: appData.loadPeople,
  });

  return {
    state: {
      activeView,
      profile: appData.profile,
      connectionError: appData.connectionError,
      refreshing: appData.refreshing,
      people: appData.people,
      archivedPeople: appData.archivedPeople,
      peopleReadModel: appData.peopleReadModel,
      deletedFaces: appData.deletedFaces,
      events: appData.events,
      backups: appData.backups,
      backupModalOpen: appData.backupModalOpen,
      backupCreating: appData.backupCreating,
      backupImporting: appData.backupImporting,
      backupRestoring: appData.backupRestoring,
      restoreBackupSelection: appData.restoreBackupSelection,
      ...recognize.state,
      ...queue.state,
      ...people.state,
    },
    refs: { ...recognize.refs },
    actions: {
      setActiveView,
      refreshAll: appData.refreshAll,
      reloadAppData: appData.reloadAppData,
      configureRecovery: appData.configureRecovery,
      loadPeople: appData.loadPeople,
      loadEvents: appData.loadEvents,
      loadDeletedFaces: appData.loadDeletedFaces,
      loadBackups: appData.loadBackups,
      requestBackup: appData.requestBackup,
      cancelBackup: appData.cancelBackup,
      createBackup: appData.createBackup,
      deleteBackup: appData.deleteBackup,
      importBackup: appData.importBackup,
      downloadBackup: appData.downloadBackup,
      downloadSupportPackage: appData.downloadSupportPackage,
      requestRestoreBackup: appData.requestRestoreBackup,
      cancelRestoreBackup: appData.cancelRestoreBackup,
      restoreBackup: appData.restoreBackup,
      ...recognize.actions,
      ...queue.actions,
      ...people.actions,
      guarded: api.guarded,
    },
  };
}
