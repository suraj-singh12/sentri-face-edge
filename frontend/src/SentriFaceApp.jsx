import { ActionIcon, AppShell, Box, Button, Group, Loader, MantineProvider, Modal, Stack, Tabs, Text, Title, Tooltip, rem, useComputedColorScheme, useMantineColorScheme } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { IconDatabaseExport, IconMoon, IconRefresh, IconSun } from "@tabler/icons-react";

import { VIEWS } from "./constants.js";
import { useSentriFaceController } from "./hooks/useSentriFaceController.js";
import { profileLine, tabLabel } from "./utils.js";
import { DebugView } from "./views/DebugView.jsx";
import { PeopleView } from "./views/PeopleView.jsx";
import { QueueView } from "./views/QueueView.jsx";
import { RecognizeView } from "./views/RecognizeView.jsx";

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
            <Tooltip label={state.backupCreating ? "Creating backup..." : "Create DB backup"}>
              <ActionIcon
                variant="light"
                color="blue"
                size="lg"
                onClick={actions.requestBackup}
                disabled={state.backupCreating}
                aria-label={state.backupCreating ? "Creating backup..." : "Create DB backup"}
              >
                {state.backupCreating ? <Loader size={18} /> : <IconDatabaseExport size={18} />}
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <Tabs value={state.activeView} onChange={actions.setActiveView} keepMounted={false} className="sentriface-tabs">
          <Tabs.List mb="md">
            {VIEWS.map((view) => <Tabs.Tab key={view} value={view}>{tabLabel(view)}</Tabs.Tab>)}
          </Tabs.List>

          <Tabs.Panel value="recognize">
            <RecognizeView
              recognizeFileRef={refs.recognizeFileRef}
              recognition={state.recognition}
              recognitionGallery={state.recognitionGallery}
              recognitionGalleryImage={state.recognitionGalleryImage}
              recognitionAccepted={state.recognitionAccepted}
              recognitionFollowup={state.recognitionFollowup}
              recognitionFollowupDone={state.recognitionFollowupDone}
              onRecognizeFile={guarded(actions.recognizeLoadedImage)}
              onLoadAnother={() => refs.recognizeFileRef.current?.click()}
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
              onFiles={guarded((files) => actions.scanQueueFiles(Array.from(files || [])))}
              onFolder={guarded((files) => actions.scanQueueFiles(Array.from(files || [])))}
              onDrop={guarded(actions.queueDrop)}
              onCancelProcessing={actions.cancelQueueProcessing}
              onRefresh={guarded(() => actions.loadQueueGroups(state.queueSessionId))}
              onOpenGroup={actions.openQueueGroup}
              onToggleFace={actions.toggleQueueFace}
              onAcceptExisting={guarded(actions.queueAcceptExisting)}
              onNewPerson={guarded(actions.queueNewPerson)}
              onDiscard={guarded(actions.queueDiscard)}
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
              peopleGallery={state.peopleGallery}
              peopleGalleryImage={state.peopleGalleryImage}
              onRefresh={guarded(actions.loadPeople)}
              onOpen={guarded(actions.peopleOpen)}
              onImage={actions.setPeopleGalleryImage}
              onBack={actions.peopleBack}
              onSave={actions.savePeopleProfile}
            />
          </Tabs.Panel>

          <Tabs.Panel value="debug">
            <DebugView
              events={state.events}
              backups={state.backups}
              backupCreating={state.backupCreating}
              onRefresh={guarded(actions.loadEvents)}
              onCreateBackup={guarded(actions.createBackup)}
              onDeleteBackup={guarded(actions.deleteBackup)}
            />
          </Tabs.Panel>
        </Tabs>
        <Modal
          opened={state.backupModalOpen}
          onClose={actions.cancelBackup}
          title="Create database backup?"
          centered
          closeOnClickOutside={!state.backupCreating}
          closeOnEscape={!state.backupCreating}
        >
          <Stack gap="md">
            <Text size="sm" c="dimmed">
              A snapshot of the current people, embeddings, and application data will be saved in the managed backups folder.
            </Text>
            <Group justify="flex-end">
              <Button variant="default" onClick={actions.cancelBackup} disabled={state.backupCreating}>Cancel</Button>
              <Button onClick={guarded(actions.createBackup)} loading={state.backupCreating}>Create Backup</Button>
            </Group>
          </Stack>
        </Modal>
      </AppShell.Main>
    </AppShell>
  );
}
