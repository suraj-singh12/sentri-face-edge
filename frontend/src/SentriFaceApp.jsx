import { useEffect, useState } from "react";
import { ActionIcon, Alert, AppShell, Avatar, Box, Button, Group, Loader, MantineProvider, Menu, Modal, PasswordInput, Popover, Stack, Tabs, Text, Title, Tooltip, UnstyledButton, rem, useComputedColorScheme, useMantineColorScheme } from "@mantine/core";
import { IconAlertTriangle, IconBell, IconChevronDown, IconDatabaseExport, IconKey, IconLogout, IconMoon, IconRefresh, IconSun } from "@tabler/icons-react";

import { AuthGate } from "./components/AuthGate.jsx";
import { ConfirmDialog } from "./components/ConfirmDialog.jsx";
import { ToastStack } from "./components/ToastStack.jsx";
import { ModelGate } from "./components/ModelGate.jsx";
import { RecoveryGate } from "./components/RecoveryGate.jsx";
import { VIEWS } from "./constants.js";
import { useSentriFaceController } from "./hooks/useSentriFaceController.js";
import { useLicenseController } from "./hooks/useLicenseController.js";
import { backupLabel, backupReminderDue, formatBackupDateTime, profileLine, tabLabel } from "./utils.js";
import { DebugView } from "./views/DebugView.jsx";
import { EventsView } from "./views/EventsView.jsx";
import { PeopleView } from "./views/PeopleView.jsx";
import { QueueView } from "./views/QueueView.jsx";
import { RecognizeView } from "./views/RecognizeView.jsx";
import { WorldWorkspace } from "./views/WorldWorkspace.jsx";

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
        components: {
          PasswordInput: { defaultProps: { visibilityToggleButtonProps: { tabIndex: 0, "aria-label": "Show or hide password" } } },
        },
      }}
    >
      <ToastStack />
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
  const license = useLicenseController();
  const { state, refs, actions } = useSentriFaceController({ capabilities: user?.capabilities || [] });
  const { guarded } = actions;
  const { setColorScheme } = useMantineColorScheme();
  const computedColorScheme = useComputedColorScheme("light", { getInitialValueInEffect: true });
  const nextColorScheme = computedColorScheme === "dark" ? "light" : "dark";
  const capabilities = new Set(user?.capabilities || []);
  const can = (capability) => capabilities.has(capability);
  const licenseRestricted = Boolean(license.status?.enforced && !license.status?.licensed);
  const visibleViews = (licenseRestricted ? ["debug"] : VIEWS)
    .filter((view) => view !== "queue" || can("add"))
    .filter((view) => view !== "debug" || licenseRestricted || can("technical") || can("backups") || can("administer") || can("recovery") || can("license_administer"));
  const selectedView = visibleViews.includes(state.activeView) ? state.activeView : visibleViews[0];
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const canBackups = can("backups");
  const showBackupReminder = canBackups && !licenseRestricted && backupReminderDue(state.lastDataChange, state.backups);
  const canOpenSettings = visibleViews.includes("debug");
  const showRecoveryWarning = state.profile && !state.profile.recovery_readiness?.ready;
  const shellNotifications = [
    showRecoveryWarning ? { color: "red", title: "Your safety copy needs attention", body: "Your latest external backup is not available. The owner can check it under Settings.", action: canOpenSettings ? <Button variant="subtle" color="red" size="compact-xs" onClick={() => { setNotificationsOpen(false); actions.setActiveView("debug"); }}>Settings</Button> : null } : null,
    showBackupReminder ? { color: "blue", title: "Backup recommended", body: "You have changes since your last backup.", action: <Button variant="subtle" size="compact-xs" loading={state.backupCreating} onClick={() => { setNotificationsOpen(false); actions.requestBackup(); }}>Back up</Button> } : null,
    state.profile?.runtime === "dev" ? { color: "yellow", title: "Demo mode", body: "Results are simulated for testing and are not real face matches." } : null,
    state.profile?.model_usage?.research_only ? { color: "orange", title: "Personal or research use only", body: "The selected model files are not approved here for business or paid use." } : null,
    state.profile?.index?.degraded_reason ? { color: "yellow", title: "Compatibility mode", body: "Face search is still available, but may be slower than usual." } : null,
  ].filter(Boolean);
  useEffect(() => {
    if (!canBackups) return undefined;
    const refreshBackups = () => actions.loadBackups({ silent: true, dedupe: false }).catch(() => {});
    refreshBackups();
    const timer = window.setInterval(refreshBackups, 120000);
    return () => window.clearInterval(timer);
  }, [canBackups, selectedView]);
  useEffect(() => {
    if (licenseRestricted && state.activeView !== "debug") actions.setActiveView("debug");
  }, [actions, licenseRestricted, state.activeView]);
  const submitPassword = guarded(async () => {
    await changePassword(currentPassword, newPassword);
    setPasswordOpen(false);
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
  });

  return (
    <AppShell header={{ height: 72 }} padding="sm" className="sentriface-shell">
      <AppShell.Header className="sentriface-header">
        <Group h="100%" px="xl" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap" miw={0} className="brand-lockup">
            <img src="/sentriface-icon-64.png" alt="" className="brand-icon" aria-hidden="true" />
            <Box miw={0} className="brand-text">
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
              {shellNotifications.length ? (
                <Popover opened={notificationsOpen} onChange={setNotificationsOpen} width={360} position="bottom-end" offset={8} shadow="md">
                  <Popover.Target>
                    <ActionIcon variant="subtle" size={36} onClick={() => setNotificationsOpen((open) => !open)} aria-label={`${shellNotifications.length} notifications`} aria-expanded={notificationsOpen} className="shell-notification-button">
                      <IconBell size={18} />
                      <span className="shell-notification-count">{shellNotifications.length}</span>
                    </ActionIcon>
                  </Popover.Target>
                  <Popover.Dropdown className="shell-notification-popover">
                    <Text size="xs" fw={800} mb={6}>Notifications</Text>
                    {shellNotifications.map((notice) => (
                      <Box key={notice.title} className="shell-notification-row" data-color={notice.color}>
                        <Group align="flex-start" wrap="nowrap" gap="sm">
                          <IconAlertTriangle size={16} className="shell-notification-icon" aria-hidden="true" />
                          <Box style={{ flex: 1 }}>
                            <Text size="xs" fw={800}>{notice.title}</Text>
                            <Text size="xs" c="dimmed">{notice.body}</Text>
                          </Box>
                          {notice.action}
                        </Group>
                      </Box>
                    ))}
                  </Popover.Dropdown>
                </Popover>
              ) : null}
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
          {licenseRestricted ? (
            <ShellNotice color="orange" title="Activation required">
              Product operations are disabled. License activation, backups, restore, integrity recovery, model prerequisites, and support remain available.
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
              recognitionFaceDecisions={state.recognitionFaceDecisions}
              recognitionReviewReady={state.recognitionReviewReady}
              recognitionFollowup={state.recognitionFollowup}
              recognitionFollowupDone={state.recognitionFollowupDone}
              proofOnlyDuplicateCandidates={state.recognitionProofOnlyDuplicateCandidates}
              targetPerson={state.recognitionTargetPerson}
              qualityOnly={state.recognitionQualityOnly}
              onQualityOnlyChange={actions.setRecognitionQualityOnly}
              eventDraft={state.recognitionEventDraft}
              onEventChange={actions.updateRecognitionEvent}
              onEventConfirm={actions.confirmRecognitionEvent}
              onRecognizeFile={guarded(actions.recognizeLoadedImage)}
              onLoadAnother={() => refs.recognizeFileRef.current?.click()}
              onSelectFace={actions.selectRecognitionFace}
              onAccept={guarded(actions.recognitionAccept)}
              onEnrollTarget={guarded(actions.enrollTargetFace)}
              onNew={guarded(actions.recognitionNew)}
              onSelectExisting={actions.recognitionSelectExisting}
              onSkip={guarded(actions.skipRecognitionFace)}
              onDiscard={guarded(actions.discardRecognitionFace)}
              onComplete={guarded(actions.completeRecognitionReview)}
              onClear={actions.recognitionClear}
              onGallery={guarded(actions.openRecognitionGallery)}
              onGalleryImage={actions.setRecognitionGalleryImage}
              onGalleryBack={actions.recognitionGalleryBack}
              onLoadPeopleCandidates={guarded(actions.loadRecognitionPeopleCandidates)}
              onFollowupChange={actions.updateRecognitionFollowup}
              onFollowupSubmit={guarded(actions.confirmRecognitionFollowup)}
              onUseProofOnlyDuplicate={actions.useProofOnlyDuplicatePerson}
              onCreateAfterProofOnlyCheck={guarded(actions.createAfterProofOnlyDuplicateCheck)}
              onFollowupClear={actions.clearRecognitionFollowupForm}
              onCancelTarget={actions.cancelExistingPersonEnrollment}
            />
          </Tabs.Panel>

          <Tabs.Panel value="queue">
            <QueueView
              people={state.people}
              queueSessions={state.queueSessions}
              queueGroups={state.queueGroups}
              encounterMedia={state.queueEncounterMedia}
              encounterReviews={state.queueEncounterReviews}
              attachment={state.queueAttachment}
              onRetryAttachment={guarded(actions.retryQueueAttachment)}
              onCancelAttachment={actions.cancelQueueAttachment}
              activeEncounter={state.queueActiveEncounter}
              visibleQueueGroups={state.queueVisibleGroups}
              queueSessionId={state.queueSessionId}
              queueProgress={state.queueProgress}
              queueSelectedGroup={state.queueSelectedGroup}
              queueSelectedFaces={state.queueSelectedFaces}
              queueAccepted={state.queueAccepted}
              queueFollowup={state.queueFollowup}
              queueFollowupDone={state.queueFollowupDone}
              proofOnlyDuplicateCandidates={state.queueProofOnlyDuplicateCandidates}
              queueGallery={state.queueGallery}
              queueGalleryImage={state.queueGalleryImage}
              queueReviewStats={state.queueReviewStats}
              qualityOnly={state.queueQualityOnly}
              onQualityOnlyChange={guarded(actions.setQueueQualityOnly)}
              eventDetails={state.queueEvent}
              eventDraft={state.queueEventDraft}
              onEventChange={actions.updateQueueEvent}
              onEventConfirm={actions.confirmQueueEvent}
              onPlanEncounters={guarded(actions.planQueueEncounters)}
              onMediaExcluded={guarded(actions.setQueueMediaExcluded)}
              onCompleteIdentities={guarded(actions.completeQueueIdentities)}
              onDecideRelation={guarded(actions.decideQueueRelation)}
              onCompleteEncounter={guarded(actions.completeQueueEncounter)}
              onDiscardEncounter={guarded(actions.discardQueueEncounter)}
              onFiles={guarded((files) => actions.scanQueueFiles(Array.from(files || [])))}
              onFolder={guarded((files) => actions.scanQueueFiles(Array.from(files || [])))}
              onDrop={guarded(actions.queueDrop)}
              onCancelProcessing={actions.cancelQueueProcessing}
              onRefresh={guarded(() => actions.loadQueueGroups(state.queueSessionId))}
              onSelectSession={guarded(actions.selectQueueSession)}
              onDiscardSession={actions.discardQueueSession}
              onOpenGroup={actions.openQueueGroup}
              onToggleFace={actions.toggleQueueFace}
              onSelectAllFaces={actions.selectAllQueueFaces}
              onClearFaces={actions.clearQueueFaces}
              onAcceptExisting={guarded(actions.queueAcceptExisting)}
              onNewPerson={guarded(actions.queueNewPerson)}
              onSelectExisting={actions.queueSelectExisting}
              onDiscard={guarded(actions.queueDiscard)}
              onDiscardGroup={actions.discardQueueGroup}
              onSkip={guarded(actions.queueSkipGroup)}
              onResumeSkipped={guarded(actions.queueResumeSkipped)}
              onRejectSuggestedMatch={guarded(actions.queueRejectSuggestedMatch)}
              onViewPeople={() => actions.setActiveView("people")}
              onLoadPeopleCandidates={guarded(actions.loadQueuePeopleCandidates)}
              onFollowupChange={actions.updateQueueFollowup}
              onFollowupSubmit={guarded(actions.confirmQueueFollowup)}
              onUseProofOnlyDuplicate={actions.useQueueProofOnlyDuplicatePerson}
              onCreateAfterProofOnlyCheck={guarded(actions.createQueueAfterProofOnlyDuplicateCheck)}
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
              peopleReadModel={state.peopleReadModel}
              deletedFaces={state.deletedFaces}
              peopleGallery={state.peopleGallery}
              peopleGalleryImage={state.peopleGalleryImage}
              personGraph={state.personGraph}
              onRefresh={guarded(() => actions.refreshAll({ force: true }))}
              onPeopleRefresh={guarded(() => actions.loadPeople({ dedupe: false }))}
              onOpen={guarded(actions.peopleOpen)}
              onCreateIdentifiedPerson={guarded(actions.createIdentifiedPerson)}
              onOpenGraph={guarded(actions.openPersonGraph)}
              onOpenGraphNode={guarded(actions.openPersonGraphNode)}
              onRefreshGraph={guarded(actions.refreshPersonGraph)}
              onCloseGraph={actions.closePersonGraph}
              onImage={actions.setPeopleGalleryImage}
              onBack={actions.peopleBack}
              onSave={actions.savePeopleProfile}
              onSaveNotes={guarded(actions.savePersonNotes)}
              onQueryEncounters={actions.queryEncounters}
              onOpenEncounter={guarded(async (id) => { await actions.loadEncounterDetail(id); actions.setActiveView("encounters"); })}
              onCreateAssociation={actions.createManualAssociation}
              onRetireAssociation={actions.retireManualAssociation}
              referenceActions={{prepare: actions.referencePrepare, confirm: actions.referenceConfirm,
                cancel: actions.referenceCancel, lifecycle: actions.referenceLifecycle}}
              onFavorite={guarded(actions.setPeopleFavorite)}
              onSetRepresentative={guarded(actions.setRepresentativePhoto)}
              onArchive={actions.archivePerson}
              onRestore={actions.restorePerson}
              onDelete={actions.permanentlyDeletePerson}
              onMerge={actions.mergePeople}
              onMovePhoto={actions.movePersonPhoto}
              onDeletePhoto={actions.deletePersonPhoto}
              onRestoreDeletedFace={actions.restoreDeletedFace}
              onPermanentlyDeleteFace={actions.permanentlyDeleteFace}
            />
          </Tabs.Panel>

          <Tabs.Panel value="world">
            <WorldWorkspace apiGet={actions.worldApiGet} active={state.activeView === "world"}
              state={state.world}
              onRefresh={guarded(actions.refreshWorld)}
              onApplyScope={guarded(actions.applyWorldScope)}
              onCollection={guarded(actions.selectWorldCollection)}
              onNextPage={guarded(actions.nextWorldPage)}
              onFirstPage={guarded(actions.firstWorldPage)}
              onOpenCluster={guarded(actions.openWorldCluster)}
              onCloseCluster={actions.closeWorldCluster}
              onRefreshCluster={guarded(actions.refreshWorldCluster)}
              onClusterCollection={guarded(actions.selectWorldClusterCollection)}
              onNextClusterPage={guarded(actions.nextWorldClusterPage)}
              onOpenPerson={guarded(actions.openWorldPerson)}
              onClosePerson={actions.closeWorldPerson}
              onRefreshPerson={guarded(actions.refreshWorldPerson)}
              onPersonCollection={guarded(actions.selectWorldPersonCollection)}
              onNextPersonPage={guarded(actions.nextWorldPersonPage)}
              onOpenEvent={guarded(actions.openWorldEvent)}
              onCloseEvent={actions.closeWorldEvent}
              onRefreshEvent={guarded(actions.refreshWorldEvent)}
              onEventCollection={guarded(actions.selectWorldEventCollection)}
              onNextEventPage={guarded(actions.nextWorldEventPage)}
              onOpenEvidence={guarded(actions.openWorldEvidence)}
              onCloseEvidence={actions.closeWorldEvidence}
              onRefreshEvidence={guarded(actions.refreshWorldEvidence)}
              onEvidenceCollection={guarded(actions.selectWorldEvidenceCollection)}
              onNextEvidencePage={guarded(actions.nextWorldEvidencePage)}
              onValidateMediaOrigin={actions.validateWorldMediaOrigin}
            />
          </Tabs.Panel>

          <Tabs.Panel value="encounters">
            <EventsView
              page={state.encounters}
              detail={state.encounterDetail}
              canAttach={can("add")}
              canCorrect={can("destroy")}
              onCorrect={actions.correctEncounter}
              onNoChanges={actions.notifyNoCorrectionChanges}
              onAttach={actions.attachEncounterMedia}
              people={state.people}
              onQuery={guarded(actions.loadEncounters)}
              onOpen={guarded(actions.loadEncounterDetail)}
              onClose={actions.closeEncounterDetail}
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
              onDeleteBackup={actions.requestDeleteBackup}
              onImportBackup={guarded(actions.importBackup)}
              onDownloadBackup={actions.downloadBackup}
              onRestoreBackup={actions.requestRestoreBackup}
              onExportSupportPackage={guarded(actions.downloadSupportPackage)}
              recovery={state.recovery}
              recoveryActions={actions.recovery}
              license={license}
            />
          </Tabs.Panel>
        </Tabs>
        <ConfirmDialog
          opened={state.backupModalOpen}
          tone="safe"
          title="Create a backup?"
          message="Saves all people, photos and face data, then checks the backup is complete."
          actionLabel="Create backup"
          failureNote="Nothing changed."
          busy={state.backupCreating}
          onClose={actions.cancelBackup}
          onConfirm={actions.createBackup}
        />
        <ConfirmDialog
          opened={Boolean(state.duplicateImport)}
          tone="caution"
          title="Import a second copy?"
          message="This backup is already in your list. You can delete either copy later."
          item={backupItem(state.duplicateImport?.existing)}
          note={state.duplicateImport?.retentionRemoves?.length ? { tone: "caution", text: retentionWarning(state.duplicateImport) } : null}
          actionLabel="Import anyway"
          failureNote="Nothing was imported."
          busy={state.backupImporting}
          onClose={actions.cancelDuplicateImport}
          onConfirm={actions.confirmDuplicateImport}
        />
        <ConfirmDialog
          opened={Boolean(state.restoreBackupSelection)}
          tone="caution"
          title="Restore this backup?"
          message="Current data is replaced. A safety copy is made first, so you can go back."
          item={backupItem(state.restoreBackupSelection)}
          actionLabel="Restore backup"
          failureNote="Your current data was kept."
          busy={state.backupRestoring}
          onClose={actions.cancelRestoreBackup}
          onConfirm={actions.restoreBackup}
        />
        <ConfirmDialog
          opened={Boolean(state.backupDeleteTarget)}
          title="Delete this backup?"
          message="The backup file is deleted from this computer. This can't be undone."
          item={backupItem(state.backupDeleteTarget)}
          note={backupDeleteNote(state.backups, state.backupDeleteTarget)}
          typed="DELETE"
          actionLabel="Delete backup"
          failureNote="Nothing was deleted."
          onClose={actions.cancelDeleteBackup}
          onConfirm={actions.deleteBackup}
        />
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

function backupItem(backup) {
  if (!backup) return null;
  return { name: backupLabel(backup), detail: backup.created_at ? formatBackupDateTime(backup.created_at) : "" };
}

function retentionWarning(duplicate) {
  const names = duplicate.retentionRemoves
    .map((backup) => [backupLabel(backup), backup.created_at ? formatBackupDateTime(backup.created_at) : ""].filter(Boolean).join(" · "))
    .join("; ");
  const full = duplicate.retentionLimit ? `The list is full (${duplicate.retentionLimit})` : "The list is full";
  return `${full}, so ${names} ${duplicate.retentionRemoves.length === 1 ? "is" : "are"} deleted.`;
}

function backupDeleteNote(backups = [], target) {
  if (!target) return null;
  const usable = (backup) => backup.verified && backup.complete && backup.portable && backup.restorable;
  if (backups.some((backup) => backup.backup_id !== target.backup_id && usable(backup))) {
    return { tone: "safe", text: "You still have another verified backup." };
  }
  return usable(target)
    ? { tone: "danger", text: "This is your only verified backup. Without it, you can't restore." }
    : { tone: "danger", text: "You have no other verified backup to restore from." };
}
