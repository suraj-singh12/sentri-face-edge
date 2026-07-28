import { lazy, Suspense } from "react";
import { ActionIcon, Alert, AppShell, Box, Button, Group, Loader, MantineProvider, Modal, Stack, Tabs, Text, Title, Tooltip, rem, useComputedColorScheme, useMantineColorScheme } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { IconDatabaseExport, IconMoon, IconRefresh, IconSun } from "@tabler/icons-react";

import { VIEWS } from "./constants.js";
import { useSentriFaceController } from "./hooks/useSentriFaceController.js";
import { profileLine, tabLabel } from "./utils.js";
const DebugView = lazy(() => import("./views/DebugView.jsx").then((module) => ({ default: module.DebugView })));
const PeopleView = lazy(() => import("./views/PeopleView.jsx").then((module) => ({ default: module.PeopleView })));
const QueueView = lazy(() => import("./views/QueueView.jsx").then((module) => ({ default: module.QueueView })));
const RecognizeView = lazy(() => import("./views/RecognizeView.jsx").then((module) => ({ default: module.RecognizeView })));

export default function SentriFaceApp() {
  return (
    <MantineProvider
      defaultColorScheme="light"
      theme={{
        primaryColor: "teal",
        fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
        headings: { fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" },
        radius: { md: rem(8), lg: rem(8) },
      }}
    >
      <Notifications position="bottom-right" />
      <SentriFaceShell />
    </MantineProvider>
  );
}

function SentriFaceShell() {
  const { state, refs, actions } = useSentriFaceController();
  const { guarded } = actions;
  const { setColorScheme } = useMantineColorScheme();
  const computedColorScheme = useComputedColorScheme("light", { getInitialValueInEffect: true });
  const nextColorScheme = computedColorScheme === "dark" ? "light" : "dark";

  return (
    <AppShell header={{ height: 72 }} padding="sm" className="sentriface-shell">
      <AppShell.Header className="sentriface-header">
        <Group h="100%" px="xl" justify="space-between" wrap="nowrap">
          <Box miw={0}>
            <Title order={2} size="h3" className="brand-title">SentriFace <Text span inherit c="teal.4">Edge</Text></Title>
            <Text size="xs" c="dimmed" truncate>{profileLine(state.profile)}</Text>
          </Box>
          <Group gap="xs" wrap="nowrap">
            <Tooltip label={`Switch to ${nextColorScheme} mode`}>
              <ActionIcon
                variant="light"
                size="lg"
                onClick={() => setColorScheme(nextColorScheme)}
                aria-label={`Switch to ${nextColorScheme} mode`}
              >
                {computedColorScheme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
              </ActionIcon>
            </Tooltip>
            <Tooltip label="Reload app data">
              <ActionIcon variant="light" size="lg" onClick={guarded(actions.reloadAppData)} aria-label="Reload app data">
                <IconRefresh size={18} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label={state.backupCreating ? "Creating portable backup..." : "Create portable backup"}>
              <ActionIcon
                variant="light"
                color="blue"
                size="lg"
                onClick={actions.requestBackup}
                disabled={state.backupCreating}
                aria-label={state.backupCreating ? "Creating portable backup..." : "Create portable backup"}
              >
                {state.backupCreating ? <Loader size={18} /> : <IconDatabaseExport size={18} />}
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        {state.connectionError ? (
          <Alert color="red" title="SentriFace server is unavailable" mb="md">
            {state.connectionError}. Check that the local server is running, then use Reload app data.
          </Alert>
        ) : null}
        {state.profile?.runtime === "dev" ? (
          <Alert color="yellow" title="Development inference is active" mb="md">
            Results are synthetic and must not be trusted as real face recognition.
          </Alert>
        ) : null}
        {state.profile?.index?.degraded_reason ? (
          <Alert color="yellow" title="Search index is in safe fallback mode" mb="md">
            Using {state.profile.index.actual} instead of {state.profile.index.requested}: {state.profile.index.degraded_reason}
          </Alert>
        ) : null}        <Suspense fallback={<Stack align="center" py="xl"><Loader /><Text c="dimmed">Loading view...</Text></Stack>}>
        <Tabs value={state.activeView} onChange={actions.setActiveView} keepMounted={false} className="sentriface-tabs">
          <Tabs.List mb="md">
            {VIEWS.map((view) => <Tabs.Tab key={view} value={view}>{tabLabel(view)}</Tabs.Tab>)}
          </Tabs.List>

          <Tabs.Panel value="recognize">
            <RecognizeView
              recognizeFileRef={refs.recognizeFileRef}
              recognition={state.recognition}
              selectedFaceIndex={state.selectedRecognitionFace}
              recognitionGallery={state.recognitionGallery}
              recognitionGalleryImage={state.recognitionGalleryImage}
              recognitionAcceptedFaces={state.recognitionAcceptedFaces}
              recognitionFollowup={state.recognitionFollowup}
              recognitionFollowupDone={state.recognitionFollowupDone}
              onRecognizeFile={guarded(actions.recognizeLoadedImage)}
              onLoadAnother={() => refs.recognizeFileRef.current?.click()}
              onSelectFace={actions.selectRecognitionFace}
              onAccept={guarded(actions.recognitionAccept)}
              onNew={guarded(actions.recognitionNew)}
              onClear={actions.recognitionClear}
              onGallery={guarded(actions.openRecognitionGallery)}
              onGalleryImage={actions.setRecognitionGalleryImage}
              onGalleryBack={actions.recognitionGalleryBack}
              onFollowupChange={actions.updateRecognitionFollowup}
              onFollowupSubmit={guarded(actions.confirmRecognitionFollowup)}
              onFollowupClear={actions.clearRecognitionFollowupForm}
            />
          </Tabs.Panel>

          <Tabs.Panel value="queue">
            <QueueView
              queueSessions={state.queueSessions}
              queueGroups={state.queueGroups}
              queueSessionId={state.queueSessionId}
              queueProgress={state.queueProgress}
              queueSelectedGroup={state.queueSelectedGroup}
              queueSelectedFaces={state.queueSelectedFaces}
              queueAccepted={state.queueAccepted}
              queueFollowup={state.queueFollowup}
              queueFollowupDone={state.queueFollowupDone}
              queueGallery={state.queueGallery}
              queueGalleryImage={state.queueGalleryImage}
              queueReviewStats={state.queueReviewStats}
              onFiles={guarded((files) => actions.scanQueueFiles(Array.from(files || [])))}
              onFolder={guarded((files) => actions.scanQueueFiles(Array.from(files || [])))}
              onDrop={guarded(actions.queueDrop)}
              onCancelProcessing={actions.cancelQueueProcessing}
              onRefresh={guarded(() => actions.loadQueueGroups(state.queueSessionId))}
              onSelectSession={guarded(actions.selectQueueSession)}
              onDiscardSession={guarded(actions.discardQueueSession)}
              onOpenGroup={actions.openQueueGroup}
              onToggleFace={actions.toggleQueueFace}
              onSelectAllFaces={actions.selectAllQueueFaces}
              onClearFaces={actions.clearQueueFaces}
              onAcceptExisting={guarded(actions.queueAcceptExisting)}
              onNewPerson={guarded(actions.queueNewPerson)}
              onDiscard={guarded(actions.queueDiscard)}
              onDiscardGroup={guarded(actions.discardQueueGroup)}
              onSkip={guarded(actions.queueSkipGroup)}
              onResumeSkipped={guarded(actions.queueResumeSkipped)}
              onRejectSuggestedMatch={guarded(actions.queueRejectSuggestedMatch)}
              onViewPeople={() => actions.setActiveView("people")}
              onFollowupChange={actions.updateQueueFollowup}
              onFollowupSubmit={guarded(actions.confirmQueueFollowup)}
              onFollowupClear={actions.clearQueueFollowupForm}
              onGallery={guarded(actions.openQueueGallery)}
              onGalleryImage={actions.setQueueGalleryImage}
              onGalleryBack={actions.queueGalleryBack}
              onBack={actions.closeQueueReview}
            />
          </Tabs.Panel>

          <Tabs.Panel value="people">
            <PeopleView
              people={state.people}
              archivedPeople={state.archivedPeople}
              deletedFaces={state.deletedFaces}
              peopleGallery={state.peopleGallery}
              peopleGalleryImage={state.peopleGalleryImage}
              onRefresh={guarded(actions.refreshAll)}
              onOpen={guarded(actions.peopleOpen)}
              onImage={actions.setPeopleGalleryImage}
              onBack={actions.peopleBack}
              onSave={actions.savePeopleProfile}
              onFavorite={guarded(actions.setPeopleFavorite)}
              onSetRepresentative={guarded(actions.setRepresentativePhoto)}
              onArchive={actions.archivePerson}
              onRestore={actions.restorePerson}
              onMerge={actions.mergePeople}
              onMovePhoto={actions.movePersonPhoto}
              onDeletePhoto={actions.deletePersonPhoto}
              onRestoreDeletedFace={actions.restoreDeletedFace}
              onPermanentlyDeleteFace={actions.permanentlyDeleteFace}
            />
          </Tabs.Panel>

          <Tabs.Panel value="debug">
            <DebugView
              events={state.events}
              backups={state.backups}
              backupCreating={state.backupCreating}
              backupImporting={state.backupImporting}
              onRefresh={guarded(actions.loadEvents)}
              onCreateBackup={guarded(actions.createBackup)}
              onDeleteBackup={guarded(actions.deleteBackup)}
              onImportBackup={guarded(actions.importBackup)}
              onDownloadBackup={actions.downloadBackup}
              onRestoreBackup={actions.requestRestoreBackup}
            />
          </Tabs.Panel>
        </Tabs>
        </Suspense>
        <Modal
          opened={state.backupModalOpen}
          onClose={actions.cancelBackup}
          title="Create a complete portable backup?"
          centered
          closeOnClickOutside={!state.backupCreating}
          closeOnEscape={!state.backupCreating}
        >
          <Stack gap="md">
            <Text size="sm" c="dimmed">
              SentriFace will snapshot the database and copy every referenced original image and face crop. Files are deduplicated, checksummed, and verified before the backup is marked ready.
            </Text>
            <Group justify="flex-end">
              <Button variant="default" onClick={actions.cancelBackup} disabled={state.backupCreating}>Cancel</Button>
              <Button onClick={guarded(actions.createBackup)} loading={state.backupCreating}>Create Backup</Button>
            </Group>
          </Stack>
        </Modal>
        <Modal
          opened={Boolean(state.restoreBackupSelection)}
          onClose={actions.cancelRestoreBackup}
          title="Restore portable backup?"
          centered
          closeOnClickOutside={!state.backupRestoring}
          closeOnEscape={!state.backupRestoring}
        >
          <Stack gap="md">
            <Text size="sm">
              This replaces the current identity database with{" "}
              <Text span fw={800}>{state.restoreBackupSelection?.reason || "the selected backup"}</Text>
              {" "}and restores its {state.restoreBackupSelection?.file_count || 0} referenced files.
            </Text>
            <Text size="sm" c="dimmed">
              Before changing anything, SentriFace creates and verifies a complete safety backup of the current state. If restore or reload fails, it rolls back automatically.
            </Text>
            <Text size="sm" c="red" fw={700}>
              Active recognition and queue screen state will be cleared after a successful restore.
            </Text>
            <Group justify="flex-end">
              <Button variant="default" onClick={actions.cancelRestoreBackup} disabled={state.backupRestoring}>Cancel</Button>
              <Button color="teal" onClick={guarded(actions.restoreBackup)} loading={state.backupRestoring}>
                Restore Safely
              </Button>
            </Group>
          </Stack>
        </Modal>
      </AppShell.Main>
    </AppShell>
  );
}
