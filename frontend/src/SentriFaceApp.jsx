import { useState } from "react";
import { ActionIcon, AppShell, Avatar, Box, Button, Group, Loader, MantineProvider, Menu, Modal, PasswordInput, Stack, Tabs, Text, Title, Tooltip, UnstyledButton, rem, useComputedColorScheme, useMantineColorScheme } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconChevronDown, IconDatabaseExport, IconKey, IconLogout, IconMoon, IconRefresh, IconSun } from "@tabler/icons-react";

import { AuthGate } from "./components/AuthGate.jsx";
import { ModelGate } from "./components/ModelGate.jsx";
import { RecoveryGate } from "./components/RecoveryGate.jsx";
import { VIEWS } from "./constants.js";
import { useSentriFaceController } from "./hooks/useSentriFaceController.js";
import { profileLine, tabLabel } from "./utils.js";
import { DebugView } from "./views/DebugView.jsx";
import { PeopleView } from "./views/PeopleView.jsx";
import { QueueView } from "./views/QueueView.jsx";
import { RecognizeView } from "./views/RecognizeView.jsx";

function ShellNotice({ color, title, children, action }) {
  return (
    <Box role="alert" className="shell-notice" data-color={color}>
      <IconAlertTriangle className="shell-notice-icon" size={16} aria-hidden="true" />
      <Text component="div" size="xs" className="shell-notice-copy">
        <Text component="span" inherit fw={700}>{title}</Text>
        <Text component="span" inherit c="dimmed"> — {children}</Text>
      </Text>
      {action}
    </Box>
  );
}

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
      <AuthGate>{(auth) => (
        <ModelGate user={auth.user} logout={auth.logout}>
          <RecoveryGate user={auth.user} logout={auth.logout}>
            <SentriFaceShell {...auth} />
          </RecoveryGate>
        </ModelGate>
      )}</AuthGate>
    </MantineProvider>
  );
}

function SentriFaceShell({ user, logout, changePassword }) {
  const { state, refs, actions } = useSentriFaceController({ capabilities: user?.capabilities || [] });
  const { guarded } = actions;
  const { setColorScheme } = useMantineColorScheme();
  const computedColorScheme = useComputedColorScheme("light", { getInitialValueInEffect: true });
  const nextColorScheme = computedColorScheme === "dark" ? "light" : "dark";
  const capabilities = new Set(user?.capabilities || []);
  const can = (capability) => capabilities.has(capability);
  const visibleViews = VIEWS.filter((view) => view !== "queue" || can("add")).filter((view) => view !== "debug" || can("technical") || can("backups") || can("administer"));
  const selectedView = visibleViews.includes(state.activeView) ? state.activeView : "recognize";
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const submitPassword = guarded(async () => {
    await changePassword(currentPassword, newPassword);
    setPasswordOpen(false);
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
  });
  const beginPhotoEnrollment = (person) => {
    actions.startExistingPersonEnrollment(person);
    actions.setActiveView("recognize");
    window.setTimeout(() => refs.recognizeFileRef.current?.click(), 0);
  };

  return (
    <AppShell header={{ height: 72 }} padding="sm" className="sentriface-shell">
      <AppShell.Header className="sentriface-header">
        <Group h="100%" px="xl" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap" miw={0} className="brand-lockup">
            <img src="/sentriface-icon-64.png" alt="" className="brand-icon" aria-hidden="true" />
            <Box miw={0}>
              <Title order={2} size="h3" className="brand-title">SentriFace <Text span inherit c="teal.4">Edge</Text></Title>
              <Text size="xs" c="dimmed" truncate>{profileLine(state.profile)}</Text>
            </Box>
          </Group>
          <Group gap="sm" wrap="nowrap" className="header-actions">
            <Group gap={2} wrap="nowrap" className="header-utility-group">
              <Tooltip label={`Switch to ${nextColorScheme} mode`}>
                <ActionIcon
                  variant="subtle"
                  size={36}
                  onClick={() => setColorScheme(nextColorScheme)}
                  aria-label={`Switch to ${nextColorScheme} mode`}
                >
                  {computedColorScheme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
                </ActionIcon>
              </Tooltip>
              <Tooltip label="Refresh">
                <ActionIcon variant="subtle" size={36} onClick={guarded(actions.reloadAppData)} disabled={state.refreshing} aria-label={state.refreshing ? "Refreshing" : "Refresh"}>
                  {state.refreshing ? <Loader size={18} /> : <IconRefresh size={18} />}
                </ActionIcon>
              </Tooltip>
              {can("backups") ? (
                <Tooltip label={state.backupCreating ? "Creating backup..." : "Create backup now"}>
                  <ActionIcon
                    variant="subtle"
                    color="blue"
                    size={36}
                    onClick={actions.requestBackup}
                    disabled={state.backupCreating}
                    aria-label={state.backupCreating ? "Creating backup..." : "Create backup now"}
                  >
                    {state.backupCreating ? <Loader size={18} /> : <IconDatabaseExport size={18} />}
                  </ActionIcon>
                </Tooltip>
              ) : null}
            </Group>
            <Menu shadow="md" width={220} position="bottom-end" offset={8}>
              <Menu.Target>
                <UnstyledButton className="header-account-trigger" aria-label="Open account menu">
                  <Group gap="xs" wrap="nowrap">
                    <Avatar size={34} radius="xl" color="teal" variant="light">
                      {accountInitials(user.display_name || user.username)}
                    </Avatar>
                    <Box visibleFrom="sm" miw={0} className="header-user-chip">
                      <Text size="sm" fw={800} lh={1.15} truncate>{user.display_name || user.username}</Text>
                      <Text size="xs" c="dimmed" lh={1.15} tt="capitalize" truncate>{(user.roles || []).join(" · ")}</Text>
                    </Box>
                    <IconChevronDown size={15} className="header-account-chevron" aria-hidden="true" />
                  </Group>
                </UnstyledButton>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>Account</Menu.Label>
                <Menu.Item leftSection={<IconKey size={16} />} onClick={() => setPasswordOpen(true)}>Change password</Menu.Item>
                <Menu.Divider />
                <Menu.Item color="red" leftSection={<IconLogout size={16} />} onClick={logout}>Sign out</Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <Stack gap={6} mb={10} className="shell-notices">
          {state.connectionError ? (
            <ShellNotice color="red" title="SentriFace is not responding">
              Make sure SentriFace is still running, then click Refresh.
            </ShellNotice>
          ) : null}
          {state.profile && !state.profile.recovery_readiness?.ready ? (
            <ShellNotice
              color="red"
              title="Your safety copy needs attention"
              action={visibleViews.includes("debug") ? (
                <Button variant="subtle" color="red" size="compact-xs" onClick={() => actions.setActiveView("debug")}>Settings</Button>
              ) : null}
            >
              Your latest external backup is not available. The owner can check it under Settings.
            </ShellNotice>
          ) : null}
          {state.profile?.runtime === "dev" ? (
            <ShellNotice color="yellow" title="Demo mode is active">
              Results are simulated for testing and are not real face matches.
            </ShellNotice>
          ) : null}
          {state.profile?.model_usage?.research_only ? (
            <ShellNotice color="orange" title="Personal or research use only">
              The selected model files are not approved here for business or paid use.
            </ShellNotice>
          ) : null}
          {state.profile?.index?.degraded_reason ? (
            <ShellNotice color="yellow" title="Search is using compatibility mode">
              Face search is still available, but may be slower than usual.
            </ShellNotice>
          ) : null}
        </Stack>
        <Tabs value={selectedView} onChange={actions.setActiveView} keepMounted={false} className="sentriface-tabs">
          <Tabs.List mb="md">
            {visibleViews.map((view) => <Tabs.Tab key={view} value={view}>{tabLabel(view)}</Tabs.Tab>)}
          </Tabs.List>

          <Tabs.Panel value="recognize">
            <RecognizeView
              people={state.people}
              canAdd={can("add")}
              recognizeFileRef={refs.recognizeFileRef}
              recognition={state.recognition}
              selectedFaceIndex={state.selectedRecognitionFace}
              recognitionGallery={state.recognitionGallery}
              recognitionGalleryImage={state.recognitionGalleryImage}
              recognitionAcceptedFaces={state.recognitionAcceptedFaces}
              recognitionFollowup={state.recognitionFollowup}
              recognitionFollowupDone={state.recognitionFollowupDone}
              targetPerson={state.recognitionTargetPerson}
              onRecognizeFile={guarded(actions.recognizeLoadedImage)}
              onLoadAnother={() => refs.recognizeFileRef.current?.click()}
              onSelectFace={actions.selectRecognitionFace}
              onAccept={guarded(actions.recognitionAccept)}
              onNew={guarded(actions.recognitionNew)}
              onSkip={guarded(actions.skipRecognitionFace)}
              onComplete={guarded(actions.completeRecognitionReview)}
              onClear={actions.recognitionClear}
              onGallery={guarded(actions.openRecognitionGallery)}
              onGalleryImage={actions.setRecognitionGalleryImage}
              onGalleryBack={actions.recognitionGalleryBack}
              onLoadPeopleCandidates={guarded(actions.loadRecognitionPeopleCandidates)}
              onFollowupChange={actions.updateRecognitionFollowup}
              onFollowupSubmit={guarded(actions.confirmRecognitionFollowup)}
              onFollowupClear={actions.clearRecognitionFollowupForm}
              onCancelTarget={actions.cancelExistingPersonEnrollment}
            />
          </Tabs.Panel>

          <Tabs.Panel value="queue">
            <QueueView
              people={state.people}
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
              onLoadPeopleCandidates={guarded(actions.loadQueuePeopleCandidates)}
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
              canEdit={can("add")}
              canDestroy={can("destroy")}
              people={state.people}
              archivedPeople={state.archivedPeople}
              deletedFaces={state.deletedFaces}
              peopleGallery={state.peopleGallery}
              peopleGalleryImage={state.peopleGalleryImage}
              onRefresh={guarded(actions.refreshAll)}
              onOpen={guarded(actions.peopleOpen)}
              onCreateIdentifiedPerson={guarded(actions.createIdentifiedPerson)}
              onCreateAssociation={guarded(actions.createPersonAssociation)}
              onCreatePlaceholderAssociation={guarded(actions.createPlaceholderAssociation)}
              onRemoveAssociation={guarded(actions.removePersonAssociation)}
              onLoadGraphPerson={guarded(actions.loadRelationshipGraphPerson)}
              onImage={actions.setPeopleGalleryImage}
              onBack={actions.peopleBack}
              onSave={actions.savePeopleProfile}
              onSaveNotes={guarded(actions.savePersonNotes)}
              onAddPhoto={beginPhotoEnrollment}
              onFavorite={guarded(actions.setPeopleFavorite)}
              onSetRepresentative={guarded(actions.setRepresentativePhoto)}
              onArchive={actions.archivePerson}
              onRestore={actions.restorePerson}
              onDelete={actions.permanentlyDeletePerson}
              onMerge={actions.mergePeople}
              onUndoMerge={guarded(actions.undoPeopleMerge)}
              onMovePhoto={actions.movePersonPhoto}
              onDeletePhoto={actions.deletePersonPhoto}
              onRestoreDeletedFace={actions.restoreDeletedFace}
              onPermanentlyDeleteFace={actions.permanentlyDeleteFace}
            />
          </Tabs.Panel>

          <Tabs.Panel value="debug">
            <DebugView
              capabilities={user.capabilities || []}
              currentUser={user}
              profile={state.profile}
              onConfigureRecovery={guarded(actions.configureRecovery)}
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
              onExportSupportPackage={guarded(actions.downloadSupportPackage)}
            />
          </Tabs.Panel>
        </Tabs>
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
        <Modal opened={passwordOpen} onClose={() => setPasswordOpen(false)} title="Change password" centered>
          <Stack>
            <PasswordInput label="Current password" value={currentPassword} onChange={(event) => setCurrentPassword(event.currentTarget.value)} autoComplete="current-password" />
            <PasswordInput label="New password" description="At least 12 characters" value={newPassword} onChange={(event) => setNewPassword(event.currentTarget.value)} autoComplete="new-password" />
            <PasswordInput label="Confirm new password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.currentTarget.value)} autoComplete="new-password" />
            {confirmPassword && newPassword !== confirmPassword ? <Text c="red" size="sm">Passwords do not match</Text> : null}
            <Group justify="flex-end"><Button variant="default" onClick={() => setPasswordOpen(false)}>Cancel</Button><Button disabled={newPassword.length < 12 || newPassword !== confirmPassword || !currentPassword} onClick={submitPassword}>Change password</Button></Group>
          </Stack>
        </Modal>
      </AppShell.Main>    </AppShell>
  );
}

function accountInitials(value) {
  const words = String(value || "U").trim().split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((word) => word[0]).join("").toUpperCase() || "U";
}
