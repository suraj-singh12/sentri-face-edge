import { useApiClient } from "./useApiClient.js";
import { useAppData } from "./useAppData.js";
import { useFileUploads } from "./useFileUploads.js";
import { usePersistentState } from "./usePersistentState.js";
import { usePeopleController } from "./usePeopleController.js";
import { useQueueController } from "./useQueueController.js";
import { useRecognizeController } from "./useRecognizeController.js";
import { useRecoveryController } from "./useRecoveryController.js";
import { useWorldController } from "./useWorldController.js";

export function useSentriFaceController({ capabilities = [] } = {}) {
  const [activeView, setActiveView] = usePersistentState("sentriface.activeView", "recognize");
  const api = useApiClient();
  const canAdd = capabilities.includes("add");
  const uploads = useFileUploads(api);
  const appData = useAppData({ activeView, capabilities, ...api });
  const world = useWorldController({ activeView, ...api });
  const people = usePeopleController({
    activeView,
    ...api,
    loadPeople: appData.loadPeople,
    loadDeletedFaces: appData.loadDeletedFaces,
    onWorldMutation: world.actions.invalidateWorld,
  });
  const recognize = useRecognizeController({
    ...api,
    ...uploads,
    loadPeople: appData.loadPeople,
    onExistingPersonEnrolled: async (personId) => {
      await people.actions.refreshPeopleProfile(personId);
      setActiveView("people");
    },
    onGraphMutation: people.actions.invalidatePersonGraph,
  });
  const queue = useQueueController({
    enabled: canAdd && activeView === "queue",
    ...api,
    ...uploads,
    loadPeople: appData.loadPeople,
    onGraphMutation: people.actions.invalidatePersonGraph,
  });
  const recovery = useRecoveryController({
    enabled: capabilities.includes("recovery"),
    ...api,
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
      encounters: appData.encounters,
      encounterDetail: appData.encounterDetail,
      backups: appData.backups,
      backupModalOpen: appData.backupModalOpen,
      backupCreating: appData.backupCreating,
      backupImporting: appData.backupImporting,
      backupRestoring: appData.backupRestoring,
      restoreBackupSelection: appData.restoreBackupSelection,
      ...recognize.state,
      ...queue.state,
      ...people.state,
      ...world.state,
      recovery: recovery.state,
    },
    refs: { ...recognize.refs },
    actions: {
      setActiveView,
      refreshAll: appData.refreshAll,
      reloadAppData: appData.reloadAppData,
      configureRecovery: appData.configureRecovery,
      loadPeople: appData.loadPeople,
      loadEvents: appData.loadEvents,
      queryEncounters: appData.queryEncounters,
      loadEncounters: appData.loadEncounters,
      loadEncounterDetail: appData.loadEncounterDetail,
      closeEncounterDetail: appData.closeEncounterDetail,
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
      ...world.actions,
      recovery: recovery.actions,
      guarded: api.guarded,
    },
  };
}
