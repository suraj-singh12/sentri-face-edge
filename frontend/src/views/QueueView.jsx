import { actionableQueueGroups } from "../reviewState.js";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  FileButton,
  Grid,
  Group,
  Image,
  Modal,
  NumberInput,
  Paper,
  Progress,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  TextInput,
  ThemeIcon,
  Title,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconArrowsHorizontal,
  IconCheck,
  IconChevronLeft,
  IconChevronRight,
  IconCopy,
  IconEye,
  IconExternalLink,
  IconFolderOpen,
  IconPhotoUp,
  IconRefresh,
  IconSearch,
  IconClock,
  IconBulb,
  IconFileText,
  IconInfoCircle,
  IconMaximize,
  IconMinus,
  IconPlus,
  IconTrash,
  IconUserPlus,
  IconX,
  IconUsers,
} from "@tabler/icons-react";

import { RecognitionFollowupForm } from "../components/RecognitionFollowupForm.jsx";
import { EncounterDetailsModal } from "../components/EncounterDetailsModal.jsx";
import { useIntentionalFormScroll } from "../hooks/useIntentionalFormScroll.js";
import { EmptyCard } from "../components/Shared.jsx";
import { isNewPersonSuggestion, matchDisplay, mediaUrl, qualityColor, recognitionText } from "../utils.js";
import { browsePeopleCandidates, PROFILE_BROWSE_MODES } from "../utils/profileBrowse.js";

export function QueueView({
  people = [],
  queueSessions,
  queueGroups,
  encounterMedia = [],
  encounterReviews = [],
  attachment = null,
  onRetryAttachment,
  onCancelAttachment,
  activeEncounter = null,
  visibleQueueGroups = [],
  queueSessionId,
  queueProgress,
  queueSelectedGroup,
  queueSelectedFaces,
  queueAccepted,
  queueFollowup,
  queueFollowupDone,
  proofOnlyDuplicateCandidates = [],
  queueGallery,
  queueGalleryImage,
  queueReviewStats,
  qualityOnly = true,
  onQualityOnlyChange,
  eventDetails,
  eventDraft,
  onEventChange,
  onEventConfirm,
  onPlanEncounters,
  onMediaExcluded,
  onCompleteIdentities,
  onDecideRelation,
  onCompleteEncounter,
  onDiscardEncounter,
  onFiles,
  onFolder,
  onDrop,
  onCancelProcessing,
  onRefresh,
  onSelectSession,
  onDiscardSession,
  onOpenGroup,
  onToggleFace,
  onSelectAllFaces,
  onClearFaces,
  onAcceptExisting,
  onNewPerson,
  onSelectExisting,
  onDiscard,
  onDiscardGroup,
  onSkip,
  onResumeSkipped,
  onRejectSuggestedMatch,
  onViewPeople,
  onLoadPeopleCandidates,
  onFollowupChange,
  onFollowupSubmit,
  onUseProofOnlyDuplicate,
  onCreateAfterProofOnlyCheck,
  onFollowupClear,
  onGallery,
  onGalleryImage,
  onGalleryBack,
  onBack,
}) {
  const [discardSessionOpen, setDiscardSessionOpen] = useState(false);
  const [groupPendingDiscard, setGroupPendingDiscard] = useState(null);
  return (
    <>
      <EncounterDetailsModal opened={Boolean(queueSelectedGroup && activeEncounter?.phase === "EVENT" && eventDetails?.reviewId !== activeEncounter.review_id)} values={eventDraft} people={people} onChange={onEventChange} onConfirm={onEventConfirm} />
      <Modal opened={proofOnlyDuplicateCandidates.length > 0} onClose={() => {}} title="Possible existing profile" centered>
        <Stack gap="md">
          <Text size="sm">A proof-only face may match an existing Person. It was not used in normal recognition.</Text>
          {proofOnlyDuplicateCandidates.map((candidate) => (
            <Card key={candidate.person_id} withBorder radius="md">
              <Group wrap="nowrap" align="center">
                {candidate.representative_image
                  ? <Image src={mediaUrl(candidate.representative_image)} alt={candidate.name} w={64} h={64} radius="sm" fit="cover" />
                  : <ThemeIcon size={64} variant="light" color="gray"><IconUsers size={30} /></ThemeIcon>}
                <Box style={{ flex: 1 }}><Group justify="space-between"><Text fw={700}>{candidate.name}</Text>{candidate.draft_created && <Badge>Drafted</Badge>}</Group><Text size="xs" c="dimmed">{candidate.metadata?.rank || "No role"} · {candidate.metadata?.country || "Country unknown"} · Proof-only face</Text></Box>
                <Button size="xs" variant="light" onClick={() => onUseProofOnlyDuplicate(candidate)}>Use Existing Person</Button>
              </Group>
            </Card>
          ))}
          <Button variant="default" onClick={onCreateAfterProofOnlyCheck}>Create new Person anyway</Button>
        </Stack>
      </Modal>
      <Paper withBorder radius="md" p="md" className="queue-workspace" data-followup-open={Boolean(queueFollowup)}>
        <Stack gap={4} mb="md" align="flex-start">
          <Switch checked={qualityOnly} onChange={(event) => onQualityOnlyChange?.(event.currentTarget.checked)} label="Prefer quality photos for recognition" className="queue-quality-switch" />
          {!qualityOnly && <Text size="xs" c="orange">Low-quality face samples may reduce recognition accuracy and may produce poorer or less reliable matches.</Text>}
        </Stack>
        <Grid gutter="lg" className="queue-shell-grid">
        {!queueSelectedGroup && (
          <Grid.Col span={{ base: 12, md: "content" }} className="queue-sidebar-col">
            <QueueInputPanel
              sessions={queueSessions}
              sessionId={queueSessionId}
              pendingCount={actionableQueueGroups(visibleQueueGroups, encounterMedia, encounterReviews.length > 0).filter((group) => group.status === "pending" && group.faces.length).length}
              onFiles={onFiles}
              onFolder={onFolder}
              onDrop={onDrop}
              onRefresh={onRefresh}
              onSelectSession={onSelectSession}
              onDiscardSession={() => setDiscardSessionOpen(true)}
            />
          </Grid.Col>
        )}
        <Grid.Col span={queueSelectedGroup ? 12 : "auto"} className="queue-main-col">
          {attachment && encounterReviews.length === 0 && !["running", "cancelling"].includes(queueProgress?.status) ? (
            <Paper withBorder p="md" radius="md">
              <Title order={2} size="h3">Attach Media draft</Title>
              <Text size="sm" mt="xs">These photos remain reserved for the selected Encounter. Retry revalidates its current state; Cancel abandons this attachment without creating Review Photos work.</Text>
              <Group mt="md"><Button onClick={onRetryAttachment}>Retry Attach Media</Button><Button variant="default" onClick={onCancelAttachment}>Cancel Attach Media</Button></Group>
            </Paper>
          ) : encounterMedia.length > 0 && encounterReviews.length === 0 && !["running", "cancelling"].includes(queueProgress?.status) ? (
            <EncounterGrouping key={queueSessionId} media={encounterMedia} onConfirm={onPlanEncounters} onExclude={onMediaExcluded} />
          ) : activeEncounter?.phase === "RELATIONS" ? (
            <EncounterRelations review={activeEncounter} onDecide={onDecideRelation} onComplete={onCompleteEncounter} onDiscard={onDiscardEncounter} />
          ) : queueSelectedGroup ? (
            <QueueGroupReview
              people={people}
              group={queueSelectedGroup}
              selectedFaces={queueSelectedFaces}
              accepted={queueAccepted}
              followup={queueFollowup}
              followupDone={queueFollowupDone}
              gallery={queueGallery}
              galleryImage={queueGalleryImage}
              groups={visibleQueueGroups.filter((group) => group.status === "pending" && group.faces.length)}
              onOpenGroup={onOpenGroup}
              onToggleFace={onToggleFace}
              onSelectAllFaces={onSelectAllFaces}
              onClearFaces={onClearFaces}
              onAcceptExisting={onAcceptExisting}
              onNewPerson={onNewPerson}
              onSelectExisting={onSelectExisting}
              onDiscard={onDiscard}
              onDiscardGroup={() => setGroupPendingDiscard(queueSelectedGroup)}
              onSkip={onSkip}
              onRejectSuggestedMatch={onRejectSuggestedMatch}
              onFollowupChange={onFollowupChange}
              onFollowupSubmit={onFollowupSubmit}
              onFollowupClear={onFollowupClear}
              onGallery={onGallery}
              onGalleryImage={onGalleryImage}
              onGalleryBack={onGalleryBack}
              onLoadPeopleCandidates={onLoadPeopleCandidates}
              onBack={onBack}
            />
          ) : (
            <Stack>
            {activeEncounter && <Card withBorder radius="md" p="md">
              <Group justify="space-between">
                <Box>
                  <Text fw={700}>Encounter {Number(activeEncounter.sequence_number || 0) + 1} of {encounterReviews.length}</Text>
                  <Text size="sm" c="dimmed">{activeEncounter.identity_resolved} of {activeEncounter.identity_total} faces resolved. Event details are saved once for this Encounter.</Text>
                </Box>
                <Group>
                  <Button variant="light" color="red" onClick={onDiscardEncounter}>Discard Encounter</Button>
                  <Button disabled={!activeEncounter.event_details_complete || activeEncounter.identity_resolved !== activeEncounter.identity_total} onClick={onCompleteIdentities}>Continue to Relations</Button>
                </Group>
              </Group>
            </Card>}
            <QueueGroupList
              groups={activeEncounter ? visibleQueueGroups : queueGroups}
              progress={queueProgress}
              sessionId={queueSessionId}
              stats={queueReviewStats}
              onCancelProcessing={onCancelProcessing}
              onOpen={onOpenGroup}
              onDiscardGroup={setGroupPendingDiscard}
              onResumeSkipped={onResumeSkipped}
              onViewPeople={onViewPeople}
              encounterReview={Boolean(activeEncounter)}
            />
            </Stack>
          )}
        </Grid.Col>
        </Grid>
      </Paper>
      <Modal
        opened={discardSessionOpen}
        onClose={() => setDiscardSessionOpen(false)}
        title="Discard this queue session?"
        centered
      >
        <Text size="sm" c="dimmed">
          All pending faces and temporary photos in this session will be removed. People already confirmed are kept.
        </Text>
        <Group justify="flex-end" mt="lg">
          <Button variant="default" onClick={() => setDiscardSessionOpen(false)}>Cancel</Button>
          <Button
            color="red"
            leftSection={<IconTrash size={16} />}
            onClick={async () => {
              setDiscardSessionOpen(false);
              await onDiscardSession();
            }}
          >
            Discard session
          </Button>
        </Group>
      </Modal>
      <Modal
        opened={Boolean(groupPendingDiscard)}
        onClose={() => setGroupPendingDiscard(null)}
        title="Discard this entire group?"
        centered
      >
        <Text size="sm" c="dimmed">
          This removes all {groupPendingDiscard?.faces?.length || 0} pending face{groupPendingDiscard?.faces?.length === 1 ? "" : "s"} in the group. Confirmed people are not affected.
        </Text>
        <Group justify="flex-end" mt="lg">
          <Button variant="default" onClick={() => setGroupPendingDiscard(null)}>Cancel</Button>
          <Button
            color="red"
            leftSection={<IconTrash size={16} />}
            onClick={async () => {
              const group = groupPendingDiscard;
              setGroupPendingDiscard(null);
              await onDiscardGroup(group);
            }}
          >
            Discard group
          </Button>
        </Group>
      </Modal>
    </>
  );
}

function groupingFolder(mediaPath) {
  const parts = String(mediaPath || "").replaceAll("\\", "/").split("/").filter(Boolean);
  const batchIndex = parts.lastIndexOf("batches");
  return batchIndex < 0 ? "" : parts.slice(batchIndex + 2, -1).join("/");
}

function EncounterGrouping({ media, onConfirm, onExclude }) {
  const [mode, setMode] = useState("one");
  const [assignment, setAssignment] = useState({});
  const [count, setCount] = useState(2);
  const [busy, setBusy] = useState(false);
  const ordered = [...media].sort((left, right) => String(left.media_path).localeCompare(String(right.media_path)));
  const usable = ordered.filter((item) => !item.excluded && !item.finalized_encounter);
  const faceMediaCount = usable.filter((item) => item.face_count === undefined || item.face_count > 0).length;
  const maxCount = Math.max(1, faceMediaCount);
  const encounterCount = Math.min(count, maxCount);
  const folders = [...new Set(usable.map((item) => groupingFolder(item.media_path)))];
  const canSuggest = folders.length > 1 && !folders.includes("") && folders.every((folder) =>
    usable.some((item) => groupingFolder(item.media_path) === folder && (item.face_count === undefined || item.face_count > 0)));
  const assigned = usable.map((item, index) => ({
    item,
    number: mode === "one" ? 1 : Math.min(encounterCount, Number(assignment[item.media_id] || (index % encounterCount) + 1)),
  }));
  const buckets = Array.from({ length: mode === "one" ? 1 : encounterCount }, (_, index) =>
    assigned.filter(({ number }) => number === index + 1).map(({ item }) => item));
  const validBuckets = buckets.every((bucket) => bucket.length && bucket.some((item) => item.face_count === undefined || item.face_count > 0));
  const confirm = async () => {
    setBusy(true);
    try { await onConfirm(buckets.map((bucket) => bucket.map((item) => item.media_id))); }
    finally { setBusy(false); }
  };
  return <Stack gap="md">
    <Box><Title order={2} size="h3">Group photos by Encounter</Title><Text size="sm" c="dimmed">Confirm which photos belong to each real-world occurrence before reviewing people.</Text></Box>
    <Group align="flex-end">
      <Button variant={mode === "one" ? "filled" : "light"} onClick={() => setMode("one")}>One Encounter</Button>
      <Group gap="xs" align="flex-end"><Button variant={mode === "multiple" ? "filled" : "light"} disabled={maxCount < 2} title={maxCount < 2 ? "At least two photos with detected faces are needed" : undefined} onClick={() => setMode("multiple")}>Multiple Encounters</Button>
        {mode === "multiple" && <NumberInput label="How many?" aria-label="Number of Encounters" min={2} max={maxCount} clampBehavior="strict" allowDecimal={false} allowNegative={false} w={95} value={encounterCount} onChange={(value) => setCount(Number(value) || 2)} />}</Group>
      <Button variant="default" disabled={!canSuggest} title={canSuggest ? "Suggest Encounters from the uploaded folder structure" : "No distinct uploaded subfolders with detected faces are available for this batch"} onClick={() => {
        const folderNumbers = new Map(folders.map((folder, index) => [folder, index + 1]));
        setCount(folders.length);
        setAssignment(Object.fromEntries(usable.map((item) => [item.media_id, folderNumbers.get(groupingFolder(item.media_path))])));
        setMode("multiple");
      }}>Suggest grouping</Button>
    </Group>
    {!canSuggest && <Text size="xs" c="dimmed">Suggestions need distinct uploaded subfolders. You can group these photos manually.</Text>}
    {ordered.some((item) => item.finalized_encounter) && <Text size="sm" c="red">Photos already in a finalized Encounter are automatically excluded. The other photos can continue.</Text>}
    {usable.length === 0 && <Text size="sm" c="orange">No usable photos remain for a new Encounter.</Text>}
    {mode === "multiple" && usable.length > 0 && <Group gap="xs">{buckets.map((bucket, index) => <Badge key={index} color={bucket.some((item) => item.face_count === undefined || item.face_count > 0) ? "teal" : "red"} variant="light">Encounter {index + 1}: {bucket.length} photo{bucket.length === 1 ? "" : "s"}</Badge>)}</Group>}
    <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
      {ordered.map((item) => <Card withBorder key={item.media_id} className="queue-encounter-media-card" data-conflict={Boolean(item.finalized_encounter) || undefined} data-removed={Boolean(item.excluded || item.finalized_encounter) || undefined}>
        <Group justify="space-between" align="flex-start"><Badge color={item.finalized_encounter ? "red" : item.excluded ? "gray" : "teal"} variant="light">{item.finalized_encounter ? "Already finalized — excluded" : item.excluded ? "Removed" : "Ready"}</Badge>{!item.finalized_encounter && <ActionIcon aria-label={`Remove photo ${String(item.media_path).split("/").pop()}`} color="red" variant="subtle" disabled={busy || item.excluded} onClick={async () => { setBusy(true); try { await onExclude(item.media_id, true); } finally { setBusy(false); } }}><IconX size={17} /></ActionIcon>}</Group>
        <Image src={mediaUrl(item.media_path)} h={145} fit="contain" alt="Queued media" />
        <Text size="xs" truncate mt="xs">{String(item.media_path).split("/").pop()}</Text>
        {item.finalized_encounter && <Text size="xs" c="red" mt="xs">In finalized Encounter {item.finalized_encounter.occasion || item.finalized_encounter.observation_id} {item.finalized_encounter.observed_at ? `· ${item.finalized_encounter.observed_at}` : ""}</Text>}
        {item.excluded && !item.finalized_encounter && <Button size="compact-xs" variant="subtle" disabled={busy} onClick={async () => { setBusy(true); try { await onExclude(item.media_id, false); } finally { setBusy(false); } }}>Restore photo</Button>}
        {mode === "multiple" && !item.excluded && !item.finalized_encounter && <Select mt="xs" label="Encounter" value={String(Math.min(encounterCount, Number(assignment[item.media_id] || (usable.findIndex((candidate) => candidate.media_id === item.media_id) % encounterCount) + 1)))} onChange={(value) => setAssignment((current) => ({ ...current, [item.media_id]: Number(value) }))} data={buckets.map((_, index) => ({ value: String(index + 1), label: `Encounter ${index + 1}` }))} />}
      </Card>)}
    </SimpleGrid>
    {!validBuckets && usable.length > 0 && <Text size="sm" c="red">Each Encounter needs a photo with a detected face. Adjust the allocations or Encounter count.</Text>}
    <Group justify="flex-end"><Button onClick={confirm} loading={busy} disabled={!usable.length || !validBuckets || (mode === "multiple" && encounterCount < 2)}>Confirm Encounter grouping</Button></Group>
  </Stack>;
}

function EncounterRelations({ review, onDecide, onComplete, onDiscard }) {
  const decisions = new Map((review.relations || []).map((item) => [`${item.first_ref}|${item.second_ref}`, item.disposition]));
  const candidates = review.relation_candidates || [];
  const complete = candidates.every((item) => decisions.has(`${item.first_ref}|${item.second_ref}`));
  return <Stack gap="md">
    <Box><Title order={2} size="h3">Review Relations</Title><Text size="sm" c="dimmed">{decisions.size} of {candidates.length} pairs decided. Choose which confirmed participant pairs this Encounter supports.</Text></Box>
    {candidates.length === 0 && <Card withBorder>{review.target_observation_id ? "No new participant pairs need a decision. Existing Encounter Relations are retained." : "Only one effective participant. There are no pairs to decide."}</Card>}
    {candidates.map((candidate) => {
      const key = `${candidate.first_ref}|${candidate.second_ref}`;
      return <Card withBorder key={key}>
        <Group justify="space-between" align="center">
          <Box><Text fw={700}>{candidate.first_name} ↔ {candidate.second_name}</Text><Text size="xs" c="dimmed">{candidate.support === "SHARED_FRAME" ? "Shared frame" : "Same Encounter only"}</Text></Box>
          <Group><Button aria-pressed={decisions.get(key) === "INCLUDE"} leftSection={decisions.get(key) === "INCLUDE" ? <IconCheck size={16} /> : null} variant={decisions.get(key) === "INCLUDE" ? "filled" : "outline"} onClick={() => onDecide(candidate.first_ref, candidate.second_ref, "INCLUDE")}>Include</Button><Button aria-pressed={decisions.get(key) === "EXCLUDE"} leftSection={decisions.get(key) === "EXCLUDE" ? <IconCheck size={16} /> : null} color="red" variant={decisions.get(key) === "EXCLUDE" ? "filled" : "outline"} onClick={() => onDecide(candidate.first_ref, candidate.second_ref, "EXCLUDE")}>Exclude</Button></Group>
        </Group>
      </Card>;
    })}
    <Group justify="flex-end"><Button variant="light" color="red" onClick={onDiscard}>Discard Encounter</Button><Button disabled={!complete} onClick={onComplete}>Complete Review</Button></Group>
  </Stack>;
}

function QueueInputPanel({ sessions, sessionId, pendingCount, onFiles, onFolder, onDrop, onRefresh, onSelectSession, onDiscardSession }) {
  const [uploadInputVersion, setUploadInputVersion] = useState(0);
  const chooseFiles = (handler) => (selection) => {
    const files = Array.from(selection || []);
    // Remount the native file input after every choice so selecting the same
    // image or folder again always emits a change event.
    setUploadInputVersion((current) => current + 1);
    handler(files);
  };
  const flow = [
    { label: "Upload", complete: Boolean(sessionId) },
    { label: "Review groups", complete: Boolean(sessionId) && pendingCount === 0, detail: pendingCount ? `${pendingCount} remaining` : "" },
    { label: "Confirm people", complete: Boolean(sessionId) && pendingCount === 0 },
  ];
  return (
    <Stack className="queue-sidebar">
      <Paper
        withBorder
        radius="md"
        p="md"
        className="queue-upload-card"
        onDrop={onDrop}
        onDragOver={(event) => event.preventDefault()}
      >
        <Stack gap="sm">
          <Group justify="space-between" align="flex-start" gap="sm">
          <Box>
            <Text fw={800} size="lg">Add Photos</Text>
            <Text size="xs" c="dimmed" mt={2}>Every detected face becomes a review item.</Text>
          </Box>
          </Group>
          <Box className="queue-folder-drop-target">
            <Group gap="sm" wrap="nowrap" className="queue-folder-drop-heading">
              <ThemeIcon size={36} radius="md" variant="light" color="teal" className="queue-folder-drop-icon">
                <IconFolderOpen size={21} />
              </ThemeIcon>
              <Box ta="left">
                <Text fw={700} size="sm">Drop folder here</Text>
                <Text size="xs" c="dimmed">Images stay on this device</Text>
              </Box>
            </Group>
            <Group grow w="100%" gap="xs" wrap="nowrap">
              <FileButton key={`images-${uploadInputVersion}`} onChange={chooseFiles(onFiles)} accept="image/*" multiple>
                {(props) => <Button {...props} size="xs" variant="light" leftSection={<IconPhotoUp size={15} />}>Images</Button>}
              </FileButton>
              <FileButton
                key={`folder-${uploadInputVersion}`}
                onChange={chooseFiles(onFolder)}
                accept="image/*"
                multiple
                inputProps={{ webkitdirectory: "", directory: "" }}
              >
                {(props) => <Button {...props} size="xs" leftSection={<IconFolderOpen size={15} />}>Folder</Button>}
              </FileButton>
            </Group>
          </Box>
        </Stack>
      </Paper>
      {sessionId && (
        <Card withBorder radius="md" className="queue-side-card queue-session-card">
          <Group justify="space-between" wrap="nowrap">
            <Text fw={700}>Session</Text>
            <ActionIcon
              variant="subtle"
              color="gray"
              size="sm"
              aria-label="Copy session ID"
              onClick={() => navigator.clipboard?.writeText(sessionId)}
            >
              <IconCopy size={15} />
            </ActionIcon>
          </Group>
          <Select
            mt="xs"
            size="xs"
            label="Active session"
            value={sessionId}
            onChange={onSelectSession}
            data={(sessions || []).map((session) => ({
              value: session.session_id,
              label: `${session.session_id.slice(0, 8)} | ${session.face_count} face${session.face_count === 1 ? "" : "s"}`,
            }))}
            allowDeselect={false}
          />
          <Text size="xs" c="dimmed" mt="xs" className="queue-session-id">{sessionId}</Text>
          <Group mt="xs" grow gap="xs" wrap="nowrap">
            <Button size="xs" variant="default" leftSection={<IconRefresh size={14} />} onClick={onRefresh}>Refresh</Button>
            <Button size="xs" variant="light" color="red" leftSection={<IconTrash size={14} />} onClick={onDiscardSession}>Discard session</Button>
          </Group>
        </Card>
      )}
      <Card withBorder radius="md" className="queue-side-card queue-side-card--steps">
        <Text fw={700} mb="xs">Flow</Text>
        <Stack gap={7}>
          {flow.map((step, index) => (
            <Group key={step.label} gap="sm" wrap="nowrap">
              <ThemeIcon radius="xl" size="sm" color={step.complete || (index === 1 && pendingCount) ? "teal" : "gray"}>
                {step.complete ? <IconCheck size={14} /> : index + 1}
              </ThemeIcon>
              <Box>
                <Text size="sm" c={index === 1 && pendingCount ? "teal.3" : "dimmed"}>{step.label}</Text>
                {step.detail && <Text size="xs" c="teal.4">{step.detail}</Text>}
              </Box>
            </Group>
          ))}
        </Stack>
      </Card>
    </Stack>
  );
}

function QueueGroupList({ groups, progress, sessionId, stats, onCancelProcessing, onOpen, onDiscardGroup, onResumeSkipped, onViewPeople, encounterReview = false }) {
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("confidence");
  const pendingGroups = groups.filter((group) => group.status === "pending" && group.faces.length);
  const skippedGroups = groups.filter((group) => group.status === "skipped" && group.faces.length);
  const isProcessing = progress && ["running", "cancelling"].includes(progress.status);
  const visibleGroups = useMemo(() => {
    const filtered = pendingGroups.filter((group) => {
      const classification = group.matches?.[0]?.classification || "unknown";
      const strongSimilarity = ["strong", "duplicate"].includes(classification);
      if (filter === "high") return strongSimilarity;
      if (filter === "review") return !strongSimilarity;
      return true;
    });
    return [...filtered].sort((left, right) => {
      if (sort === "faces") return right.faces.length - left.faces.length;
      if (sort === "oldest") return String(left.group_id).localeCompare(String(right.group_id));
      return (right.matches?.[0]?.score || 0) - (left.matches?.[0]?.score || 0);
    });
  }, [filter, pendingGroups, sort]);

  if (!encounterReview && sessionId && !isProcessing && pendingGroups.length === 0 && (stats?.totalGroups || skippedGroups.length)) {
    return <QueueReviewComplete stats={stats} skippedCount={skippedGroups.length || stats?.skippedGroups || 0} onResumeSkipped={onResumeSkipped} onViewPeople={onViewPeople} />;
  }

  return (
    <Stack className="queue-review-list" data-processing={isProcessing || undefined} gap={isProcessing ? "sm" : "md"}>
      <Group align="flex-start" justify="space-between" gap="md">
        <Group align="center" gap="md">
          <Box>
            <Title order={2} size="h3">Review Queue</Title>
            <Text size="sm" c="dimmed">{isProcessing ? "Processing your photos into review groups." : "Review each face group and confirm who it belongs to."}</Text>
          </Box>
          <Badge variant="light" color="teal" size="lg">{isProcessing ? "Processing" : `${pendingGroups.length} group${pendingGroups.length === 1 ? "" : "s"}`}</Badge>
        </Group>
        {isProcessing && <Button variant="default" leftSection={<IconX size={16} />} onClick={onCancelProcessing}>Cancel Processing</Button>}
      </Group>
      <Box className="queue-list-divider" />
      {progress?.status === "failed" && (
        <Paper withBorder p="md" className="queue-processing-error">
          <Group justify="space-between" align="flex-start" wrap="nowrap">
            <Box>
              <Text fw={700} c="red.4">Processing stopped</Text>
              <Text size="sm" c="dimmed" mt={3}>{progress.error || "The folder could not be processed. Select it again to retry."}</Text>
            </Box>
            <Button size="xs" variant="default" onClick={onCancelProcessing}>Dismiss</Button>
          </Group>
        </Paper>
      )}
      {isProcessing ? (
        <>
          <QueueProcessingPanel progress={progress} />
          <QueueGroupsPendingPlaceholder />
          <QueueProcessingTip />
        </>
      ) : (
        <>
          <Group justify="space-between" className="queue-filter-bar">
            <Group gap={6}>
              {[["all", "All"], ["high", "Strong similarity"], ["review", "Needs review"]].map(([value, label]) => (
                <Button key={value} size="xs" variant={filter === value ? "filled" : "subtle"} color={filter === value ? "teal" : "gray"} onClick={() => setFilter(value)}>{label}</Button>
              ))}
            </Group>
            <Select
              size="xs"
              value={sort}
              onChange={(value) => setSort(value || "confidence")}
              data={[
                { value: "confidence", label: "Highest similarity" },
                { value: "faces", label: "Most photos" },
                { value: "oldest", label: "Oldest first" },
              ]}
              w={185}
            />
          </Group>
          <Box className="queue-groups-scroll">
            <Stack gap="sm">
              {visibleGroups.length ? visibleGroups.map((group) => {
                const best = group.matches?.[0] || null;
                const score = best?.score || 0;
                const display = matchDisplay(best);
                return (
                  <Card key={`${group.session_id}-${group.group_id}`} withBorder radius="md" p="md" className="queue-group-row" onClick={() => onOpen(group)}>
                    <Group justify="space-between" wrap="nowrap" align="center">
                      <Group gap="lg" wrap="nowrap" className="queue-row-media">
                        <QueuePreviewMosaic faces={group.faces} />
                        <Box miw={0} className="queue-row-copy">
                          <Group gap="xs">
                            <Text fw={800} size="lg" className="queue-row-title">{recognitionText(best)}</Text>
                            <Badge color={best ? display.color : "orange"} variant="light">{best ? display.badge : "Needs review"}</Badge>
                          </Group>
                          <Text size="sm" c="dimmed">{group.faces.length} photo{group.faces.length === 1 ? "" : "s"} grouped together</Text>
                          <Group gap="sm" mt="sm">
                            <Text size="xs" c="dimmed">Suggested identity</Text>
                            <Text size="sm" fw={700}>{best && !isNewPersonSuggestion(best) ? best.name : "Unknown person"}</Text>
                            {best && <Badge color={display.color} variant="outline">{display.badge}</Badge>}
                          </Group>
                        </Box>
                      </Group>
                      <Group gap="xs" wrap="nowrap" className="queue-row-actions">
                        {best?.draft_created && <Badge>Drafted</Badge>}
                        <Button color="red" variant="light" leftSection={<IconTrash size={16} />} onClick={(event) => { event.stopPropagation(); onDiscardGroup(group); }}>Discard</Button>
                        <Button className="queue-row-action" variant="default" rightSection={<IconChevronRight size={17} />} onClick={(event) => { event.stopPropagation(); onOpen(group); }}>Review</Button>
                      </Group>
                    </Group>
                  </Card>
                );
              }) : <EmptyCard text={skippedGroups.length ? "Deferred groups will return after other groups are resolved." : "No groups match this filter."} />}
            </Stack>
          </Box>
          <Text size="sm" c="dimmed">Showing {visibleGroups.length} of {pendingGroups.length} pending groups{skippedGroups.length ? ` · ${skippedGroups.length} deferred` : ""}</Text>
        </>
      )}
    </Stack>
  );
}

function QueueReviewComplete({ stats, skippedCount, onResumeSkipped, onViewPeople }) {
  const activities = stats?.activities || [];
  return (
    <Stack align="center" justify="center" className="queue-complete-shell">
      <ThemeIcon size={72} radius="xl" color="teal" variant="light"><IconCheck size={38} /></ThemeIcon>
      <Box ta="center">
        <Title order={2}>Review complete</Title>
        <Text c="dimmed" mt={5}>Every active face group has been handled.</Text>
      </Box>
      <SimpleGrid cols={{ base: 2, sm: 4 }} className="queue-complete-stats">
        <QueueCompleteStat value={stats?.reviewedGroups || 0} label="Groups reviewed" />
        <QueueCompleteStat value={stats?.processedFaces || 0} label="Photos processed" />
        <QueueCompleteStat value={stats?.personsUpdated || 0} label="People updated" />
        <QueueCompleteStat value={skippedCount} label="Skipped" />
      </SimpleGrid>
      {activities.length > 0 && (
        <Card withBorder radius="md" className="queue-complete-activity">
          <Text fw={800} mb="xs">Recent activity</Text>
          {activities.slice(-4).reverse().map((activity, index) => (
            <Group key={`${activity.label}-${index}`} justify="space-between"><Text size="sm">{activity.label}</Text><Text size="xs" c="dimmed">{activity.detail}</Text></Group>
          ))}
        </Card>
      )}
      <Group>
        <Button leftSection={<IconUsers size={17} />} onClick={onViewPeople}>View People</Button>
        {skippedCount > 0 && <Button variant="default" leftSection={<IconRefresh size={17} />} onClick={onResumeSkipped}>Review skipped ({skippedCount})</Button>}
      </Group>
    </Stack>
  );
}

function QueueCompleteStat({ value, label }) {
  return (
    <Card withBorder radius="md" ta="center">
      <Text size="xl" fw={900}>{value}</Text>
      <Text size="xs" c="dimmed">{label}</Text>
    </Card>
  );
}

function QueueProcessingPanel({ progress }) {
  const phaseIndex = Math.max(0, phaseOrder.indexOf(progress.phase));
  const percent = queueProgressPercent(progress);
  const elapsed = formatElapsed(progress);
  const stages = [
    { phase: "uploading", label: "Uploading", detail: `${progress.uploadedFiles} / ${progress.totalFiles || "-"} files`, icon: IconPhotoUp },
    { phase: "detecting", label: "Detecting Faces", detail: `${progress.imagesScanned} / ${progress.totalImages || "-"} images`, icon: IconEye },
    { phase: "matching", label: "Generating Embeddings", detail: `${progress.embeddingsGenerated || "-"} / ${progress.facesDetected || "-"} faces`, icon: IconRefresh },
    { phase: "clustering", label: "Clustering Faces", detail: progress.groups ? `${progress.groups} groups` : "- / -", icon: IconUsers },
    { phase: "preparing", label: "Preparing Results", detail: progress.groups ? `${progress.groups} groups` : "- / -", icon: IconFileText },
  ];
  return (
    <Card withBorder radius="md" className="queue-processing-card">
      <Stack gap="md">
        <Group justify="space-between" wrap="nowrap" className="queue-processing-source">
          <Group gap="sm" wrap="nowrap" miw={0}>
            <ThemeIcon size="lg" variant="default" color="gray"><IconFolderOpen size={22} /></ThemeIcon>
            <Box miw={0}>
              <Text fw={800} size="sm" truncate>Selected Photos</Text>
              <Text size="xs" c="dimmed" truncate>Local folder upload</Text>
            </Box>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <ThemeIcon variant="subtle" size="sm" color="teal"><IconPhotoUp size={15} /></ThemeIcon>
            <Text fw={700} size="sm">{progress.totalFiles || 0} files</Text>
          </Group>
        </Group>
        <Box className="queue-processing-steps">
          {stages.map((stage, index) => {
            const Icon = stage.icon;
            const active = index === phaseIndex || (progress.phase === "done" && index === stages.length - 1);
            const complete = index < phaseIndex || progress.phase === "done";
            return (
              <Box key={stage.phase} className="queue-processing-step" data-active={active} data-complete={complete}>
                <ThemeIcon size={36} radius="xl" variant={active || complete ? "light" : "default"} color={complete ? "teal" : active ? "blue" : "gray"}>
                  <Icon size={20} />
                </ThemeIcon>
                <Text fw={700} size="sm">{stage.label}</Text>
                <Text size="xs" c="dimmed">{stage.detail}</Text>
              </Box>
            );
          })}
        </Box>
        <Group gap="md" wrap="nowrap">
          <Progress value={percent} size="sm" radius="xl" className="queue-processing-progress" />
          <Text fw={700} size="sm" className="queue-processing-percent">{Math.round(percent)}%</Text>
        </Group>
        <Box className="queue-processing-stats">
          <QueueProgressStat icon={IconPhotoUp} value={progress.totalFiles || 0} label="Total Files" />
          <QueueProgressStat icon={IconEye} value={progress.imagesScanned || 0} label="Images Scanned" />
          <QueueProgressStat icon={IconPhotoUp} value={progress.facesDetected || 0} label="Faces Detected" />
          <QueueProgressStat icon={IconUsers} value={progress.groups || "-"} label="Groups (so far)" />
          <QueueProgressStat icon={IconClock} value={elapsed} label="Elapsed Time" />
        </Box>
        <Box className="queue-processing-note">
          <Group gap="sm" wrap="nowrap" align="flex-start">
            <ThemeIcon variant="subtle" color="blue" size="sm"><IconInfoCircle size={16} /></ThemeIcon>
            <Box>
              <Text size="sm" fw={700}>You can continue using the app.</Text>
              <Text size="sm" c="dimmed">We'll notify you when the groups are ready to review.</Text>
            </Box>
          </Group>
        </Box>
      </Stack>
    </Card>
  );
}

function QueueGroupsPendingPlaceholder() {
  return (
    <Card withBorder radius="md" className="queue-groups-pending-card">
      <Group justify="space-between" wrap="nowrap" align="center">
        <Box miw={0}>
          <Title order={3} size="h4">Groups will appear here</Title>
          <Text size="sm" c="dimmed">As processing completes, groups will be shown automatically in this area.</Text>
        </Box>
        <Box className="queue-pending-skeleton" aria-hidden="true">
          {[0, 1, 2].map((item) => (
            <Box key={item} className="queue-pending-skeleton-card">
              <ThemeIcon variant="default" color="gray" radius="xl" size="sm"><IconUsers size={14} /></ThemeIcon>
              <Box className="queue-pending-line-stack">
                <Box />
                <Box />
              </Box>
            </Box>
          ))}
        </Box>
      </Group>
    </Card>
  );
}

function QueueProcessingTip() {
  return (
    <Card withBorder radius="md" className="queue-processing-tip">
      <Group gap="sm" wrap="nowrap">
        <ThemeIcon variant="subtle" color="teal" size="sm"><IconBulb size={16} /></ThemeIcon>
        <Text size="sm">Tip: Larger folders may take a few minutes to process depending on the number of images and your system performance.</Text>
      </Group>
    </Card>
  );
}

function QueueProgressStat({ icon: Icon, value, label }) {
  return (
    <Group gap="sm" justify="center" wrap="nowrap" className="queue-processing-stat">
      <ThemeIcon variant="subtle" size="sm"><Icon size={16} /></ThemeIcon>
      <Box>
        <Text fw={800} ta="center">{value}</Text>
        <Text size="xs" c="dimmed" ta="center">{label}</Text>
      </Box>
    </Group>
  );
}

const phaseOrder = ["uploading", "scanning", "detecting", "matching", "clustering", "preparing", "cancelling", "done"];

function queueProgressPercent(progress) {
  if (!progress) return 0;
  if (progress.status === "done" || progress.phase === "done") return 100;
  const baseByPhase = {
    uploading: 0,
    detecting: 25,
    matching: 62,
    clustering: 78,
    preparing: 90,
  };
  const spanByPhase = {
    uploading: 25,
    detecting: 37,
    matching: 16,
    clustering: 12,
    preparing: 10,
  };
  const phase = progress.phase || "uploading";
  const base = baseByPhase[phase] ?? 0;
  const span = spanByPhase[phase] ?? 10;
  let ratio = 0;
  if (phase === "uploading") {
    ratio = progress.totalFiles ? progress.uploadedFiles / progress.totalFiles : 0.08;
  } else if (phase === "detecting") {
    ratio = progress.totalImages ? progress.imagesScanned / progress.totalImages : 0.15;
  } else if (phase === "matching") {
    ratio = progress.facesDetected ? progress.embeddingsGenerated / progress.facesDetected : 0.4;
  } else if (phase === "clustering") {
    ratio = progress.groups ? 0.85 : 0.4;
  } else if (phase === "preparing") {
    ratio = 0.8;
  }
  return Math.max(0, Math.min(99, base + span * Math.max(0, Math.min(1, ratio))));
}

function formatElapsed(progress) {
  const seconds = progress.elapsedSeconds || Math.max(0, Math.floor((Date.now() - Number(progress.startedAt || Date.now())) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

function QueuePreviewMosaic({ faces }) {
  const primary = faces[0];
  const thumbnails = faces.slice(1, 5);
  const overflowCount = Math.max(0, faces.length - 5);
  return (
    <Group gap="md" wrap="nowrap" className="queue-preview-mosaic">
      <Image src={mediaUrl(primary.image_path || primary.crop_path || primary.source_image)} alt="group preview" fit="cover" className="queue-preview-main" radius="sm" />
      <Box className="queue-preview-thumbs">
        {thumbnails.map((face, index) => (
          <Box key={face.init_face_id} className="queue-thumb-wrap">
            <Image src={mediaUrl(face.image_path || face.crop_path || face.source_image)} alt="group thumbnail" fit="cover" radius="sm" />
            {overflowCount > 0 && index === thumbnails.length - 1 && <Box className="queue-thumb-more">+{overflowCount}</Box>}
          </Box>
        ))}
      </Box>
    </Group>
  );
}

function QueueGroupReview({
  people,
  group,
  groups,
  selectedFaces,
  accepted,
  followup,
  followupDone,
  gallery,
  onOpenGroup,
  onToggleFace,
  onSelectAllFaces,
  onClearFaces,
  onAcceptExisting,
  onNewPerson,
  onSelectExisting,
  onDiscard,
  onDiscardGroup,
  onSkip,
  onRejectSuggestedMatch,
  onFollowupChange,
  onFollowupSubmit,
  onFollowupClear,
  onGallery,
  onGalleryBack,
  onLoadPeopleCandidates,
  onBack,
}) {
  const [followupRef, scrollToFollowup] = useIntentionalFormScroll(followup?.identityOperationId);
  const galleryEndRef = useRef(null);
  const [mode, setMode] = useState("summary");
  const [focused, setFocused] = useState(false);
  const [incomingIndex, setIncomingIndex] = useState(0);
  const [referenceIndex, setReferenceIndex] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [syncZoom, setSyncZoom] = useState(true);
  const [peoplePickerOpen, setPeoplePickerOpen] = useState(false);
  const [peopleLoading, setPeopleLoading] = useState(false);
  const [peopleQuery, setPeopleQuery] = useState("");
  const [peoplePickerMode, setPeoplePickerMode] = useState("biometric");
  const [peopleCandidates, setPeopleCandidates] = useState([]);
  const [peopleCandidatesGroupId, setPeopleCandidatesGroupId] = useState("");
  const [manualPerson, setManualPerson] = useState(null);
  const automaticBest = group.matches?.[0] || null;
  const automaticKnown = automaticBest && !isNewPersonSuggestion(automaticBest);
  const best = manualPerson || (automaticKnown ? automaticBest : null);
  const weakMatch = automaticBest && !automaticKnown ? automaticBest : null;
  const selectedCount = selectedFaces.length;
  const currentIndex = Math.max(0, groups.findIndex((item) => item.group_id === group.group_id));
  const references = gallery?.embeddings || [];

  useEffect(() => {
    setMode("summary");
    setFocused(false);
    setIncomingIndex(0);
    setReferenceIndex(0);
    setZoom(1);
    setPeoplePickerOpen(false);
    setPeopleQuery("");
    setPeopleCandidates([]);
    setPeopleCandidatesGroupId("");
    setManualPerson(null);
  }, [group.group_id]);

  const openCompare = async () => {
    if (best?.draft) return;
    if (best?.person_id && gallery?.person?.person_id !== best.person_id) await onGallery(best.person_id);
    setMode("compare");
  };

  const openPeoplePicker = async () => {
    setPeoplePickerOpen(true);
    setPeoplePickerMode("biometric");
    if (peopleCandidatesGroupId === group.group_id) return;
    setPeopleLoading(true);
    try {
      const payload = await onLoadPeopleCandidates(group.session_id, group.group_id);
      setPeopleCandidates(payload.candidates || []);
      setPeopleCandidatesGroupId(group.group_id);
    } finally {
      setPeopleLoading(false);
    }
  };

  const choosePerson = (person) => {
    onSelectExisting();
    setManualPerson({
      ...person,
      classification: "manual",
      is_known: true,
      manual_selection: true,
    });
    setPeoplePickerOpen(false);
    setPeopleQuery("");
    setMode("summary");
    setFocused(false);
    onGalleryBack();
  };

  return (
    <Stack className="queue-group-review-v2" data-followup-open={Boolean(followup)}>
      <Group justify="space-between" align="center" className="queue-review-header">
        <Group gap="md">
          <ActionIcon variant="default" size="lg" aria-label="Back to review queue" onClick={onBack}><IconArrowLeft size={18} /></ActionIcon>
          <Box>
            <Group gap="xs">
              <Title order={2} size="h3">Review {group.group_id}</Title>
              <Badge color="teal" variant="light">{group.faces.length} photo{group.faces.length === 1 ? "" : "s"}</Badge>
            </Group>
            <Text size="sm" c="dimmed">Decide which photos belong to the suggested person.</Text>
          </Box>
        </Group>
        <Group gap="xs">
          <Button size="xs" color="red" variant="light" leftSection={<IconTrash size={15} />} onClick={onDiscardGroup} disabled={accepted}>Discard group</Button>
          <Text size="sm" c="dimmed">Group {currentIndex + 1} of {groups.length}</Text>
          <ActionIcon variant="default" disabled={currentIndex <= 0} onClick={() => onOpenGroup(groups[currentIndex - 1])}><IconChevronLeft size={18} /></ActionIcon>
          <ActionIcon variant="default" disabled={currentIndex >= groups.length - 1} onClick={() => onOpenGroup(groups[currentIndex + 1])}><IconChevronRight size={18} /></ActionIcon>
        </Group>
      </Group>

      <Group className="queue-review-tabs" gap={4}>
        <Button size="xs" variant={mode === "summary" ? "filled" : "subtle"} color={mode === "summary" ? "teal" : "gray"} onClick={() => { setMode("summary"); setFocused(false); }}>Summary</Button>
        <Button size="xs" variant={mode === "compare" ? "filled" : "subtle"} color={mode === "compare" ? "teal" : "gray"} onClick={openCompare} disabled={!best || best.draft || isNewPersonSuggestion(best)}>Compare</Button>
      </Group>

      {mode === "summary" ? (
        <Grid gutter="md" className="queue-review-content">
          <Grid.Col span={{ base: 12, md: 7 }}>
            <Card withBorder radius="md" className="queue-review-panel queue-incoming-panel">
              <Group justify="space-between" mb="md">
                <Box>
                  <Text fw={800}>Incoming photos</Text>
                  <Text size="xs" c="dimmed">Only selected photos are included in your decision.</Text>
                </Box>
                <Group gap={6}>
                  <Button size="compact-xs" variant="subtle" onClick={onSelectAllFaces} disabled={accepted}>Select all</Button>
                  <Button size="compact-xs" variant="subtle" color="gray" onClick={onClearFaces} disabled={accepted}>Clear</Button>
                </Group>
              </Group>
              <QueueIncomingGrid faces={group.faces} selectedFaces={selectedFaces} accepted={accepted} onToggleFace={onToggleFace} />
            </Card>
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 5 }}>
            <QueueSuggestedMatch
              best={best}
              weakMatch={weakMatch}
              manual={Boolean(manualPerson)}
              onBrowse={openPeoplePicker}
              onCompare={openCompare}
            />
          </Grid.Col>
        </Grid>
      ) : focused ? (
        <QueueFocusedCompare
          faces={group.faces}
          references={references}
          incomingIndex={incomingIndex}
          referenceIndex={referenceIndex}
          zoom={zoom}
          syncZoom={syncZoom}
          onIncoming={setIncomingIndex}
          onReference={setReferenceIndex}
          onZoom={setZoom}
          onSyncZoom={setSyncZoom}
          onOverview={() => setFocused(false)}
          galleryEndRef={galleryEndRef}
        />
      ) : (
        <QueueCompareOverview
          best={best}
          faces={group.faces}
          references={references}
          onFocusIncoming={(index) => { setIncomingIndex(index); setFocused(true); }}
          onFocusReference={(index) => { setReferenceIndex(index); setFocused(true); }}
        />
      )}

      {followup && (
        <Card withBorder radius="md" ref={followupRef} className="queue-followup-card followup-scroll-target">
          <Text fw={700}>{followup.name || "New person"}</Text>
          <Text size="xs" c="dimmed" mb="sm">{followup.faceIds.length} photo{followup.faceIds.length === 1 ? "" : "s"}</Text>
          <RecognitionFollowupForm people={people} values={followup} confirmed={followupDone} onChange={onFollowupChange} onSubmit={onFollowupSubmit} onClear={onFollowupClear} embedded showAddedBy />
        </Card>
      )}

      <Group grow className="queue-review-actionbar">
        <Button leftSection={<IconCheck size={18} />} onClick={() => { scrollToFollowup(); onAcceptExisting(best); }} disabled={!best || !selectedCount || accepted}>
          {best ? `Accept ${selectedCount} as ${best.name}` : "Choose a person to accept"}
        </Button>
        <Button variant="light" leftSection={<IconUserPlus size={18} />} onClick={() => { scrollToFollowup(); onNewPerson(); }} disabled={!selectedCount || accepted}>Create new person</Button>
        <Button variant="light" color="red" leftSection={<IconTrash size={18} />} onClick={onDiscard} disabled={!selectedCount || accepted}>Discard selected</Button>
        <Button variant="default" color="orange" leftSection={<IconX size={18} />} onClick={onRejectSuggestedMatch} disabled={!automaticKnown || automaticBest?.draft_created || Boolean(manualPerson) || accepted}>Reject suggested match</Button>
        <Button variant="subtle" color="gray" rightSection={<IconChevronRight size={17} />} onClick={onSkip} disabled={accepted}>Skip for now</Button>
      </Group>

      <PeoplePicker
        opened={peoplePickerOpen}
        people={peopleCandidates}
        allPeople={people}
        mode={peoplePickerMode}
        onMode={setPeoplePickerMode}
        loading={peopleLoading}
        query={peopleQuery}
        onQuery={setPeopleQuery}
        onClose={() => setPeoplePickerOpen(false)}
        onNewPerson={() => {
          setManualPerson(null);
          setPeoplePickerOpen(false);
          setPeopleQuery("");
          setMode("summary");
          setFocused(false);
          onGalleryBack();
          scrollToFollowup();
          onNewPerson();
        }}
        onSelect={choosePerson}
      />
    </Stack>
  );
}

function QueueIncomingGrid({ faces, selectedFaces, accepted, onToggleFace }) {
  const [peek, setPeek] = useState(null);
  return (
    <>
    <Modal opened={Boolean(peek)} onClose={() => setPeek(null)} title="Face preview" centered size={300}>
      {peek && <QueueFacePeek face={peek} />}
    </Modal>
    <SimpleGrid cols={{ base: 2, sm: 3 }} className="queue-photo-selection-grid">
      {faces.map((face) => {
        const selected = selectedFaces.includes(face.init_face_id);
        return (
          <Card
            key={face.init_face_id}
            withBorder
            radius="md"
            p="xs"
            className="mantine-click-card queue-selection-card"
            data-selected={selected}
          >
            <Box component="button" type="button" disabled={accepted} onClick={() => onToggleFace(face.init_face_id)} pos="relative" className="queue-selection-image" style={{ border: 0, padding: 0, background: "transparent", width: "100%", cursor: "pointer" }} aria-label={`Select face ${face.init_face_id}`}>
              <QueueFaceWithBox face={face} />
              <ThemeIcon className="queue-selection-check" color={selected ? "teal" : "gray"} radius="xl" size="sm">{selected ? <IconCheck size={14} /> : <IconX size={13} />}</ThemeIcon>
            </Box>
            <Group justify="space-between" mt={7}>
              <Text size="xs" fw={800}>{selected ? "Included" : "Excluded"}</Text>
              <Badge size="xs" variant="light" color={qualityColor(face.quality?.status)}>{face.quality?.status || "unknown"}</Badge>
            </Group>
            <Button size="compact-xs" variant="light" mt="xs" onClick={() => setPeek(face)}>Peek In</Button>
          </Card>
        );
      })}
    </SimpleGrid>
    </>
  );
}

function QueueFacePeek({ face }) {
  const box = face.box;
  const scale = box?.width > 0 && box?.height > 0 ? Math.min(250 / box.width, 250 / box.height) : null;
  return <Box w={250} h={250} mx="auto" style={{ position: "relative", overflow: "hidden", background: "var(--mantine-color-gray-1)" }}>
    {face.crop_path || !scale
      ? <Image src={mediaUrl(face.crop_path || face.image_path || face.source_image)} alt="Selected face" w={250} h={250} fit="contain" />
      : <Box style={{ position: "absolute", overflow: "hidden", width: box.width * scale, height: box.height * scale, left: (250 - box.width * scale) / 2, top: (250 - box.height * scale) / 2 }}><img src={mediaUrl(face.source_image)} alt="Selected face" style={{ position: "absolute", maxWidth: "none", transformOrigin: "top left", transform: `scale(${scale})`, left: -box.x * scale, top: -box.y * scale }} /></Box>}
  </Box>;
}

function QueueFaceWithBox({ face }) {
  const [dimensions, setDimensions] = useState(null);
  const source = mediaUrl(face.source_image || face.image_path || face.crop_path);
  const box = face.box;
  const hasBox = dimensions?.width > 0 && dimensions?.height > 0 && box?.width > 0 && box?.height > 0;
  return <span className="queue-face-image-wrap">
    <img src={source} alt="Incoming photo with current face marked" onLoad={(event) => setDimensions({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} />
    {hasBox && <span className="queue-face-boundary" aria-label="Current face boundary" style={{
      left: `${100 * box.x / dimensions.width}%`,
      top: `${100 * box.y / dimensions.height}%`,
      width: `${100 * box.width / dimensions.width}%`,
      height: `${100 * box.height / dimensions.height}%`,
    }} />}
  </span>;
}

function QueueSuggestedMatch({ best, weakMatch, manual, onBrowse, onCompare }) {
  const display = best ? matchDisplay(best) : null;
  const suggestionImage = best?.representative_image || best?.image_path;
  return (
    <Card withBorder radius="md" className="queue-review-panel queue-suggestion-panel">
      <Group justify="space-between" align="flex-start" wrap="nowrap" mb="md">
        <Box>
          <Text fw={800}>{best ? (manual ? "Selected person" : "Suggested match") : "Weak match"}</Text>
          <Text size="xs" c="dimmed">
            {best ? (manual ? "Chosen manually for these faces." : "Best matching identity for these faces.") : "No reliable automatic match. Choose the correct person yourself."}
          </Text>
        </Box>
        <Button size="xs" variant="light" leftSection={<IconUsers size={16} />} onClick={onBrowse}>Browse People</Button>
      </Group>
      <Group align="stretch" wrap="nowrap" className="queue-suggestion-body">
        <Box className="queue-suggestion-hero">
          {suggestionImage ? (
            <Image src={mediaUrl(suggestionImage)} alt={best.name} fit="contain" radius="md" />
          ) : (
            <ThemeIcon size={64} radius="xl" variant="light" color="orange"><IconUsers size={32} /></ThemeIcon>
          )}
        </Box>
        <Stack justify="space-between" gap="sm" className="queue-suggestion-copy">
          <Box>
            <Group justify="space-between" align="flex-start" wrap="nowrap">
              <Text size="xl" fw={900}>{best ? best.name : "Human review needed"}</Text>
              <Group gap="xs" wrap="nowrap">
              <Badge color={best ? (manual ? "teal" : display.color) : "orange"} size="lg">
                {best ? (manual ? "Selected" : display.badge) : "Weak match"}
              </Badge>
              {best?.draft_created && <Badge>Drafted</Badge>}
              </Group>
            </Group>
            <Text size="xs" c="dimmed" mt={4}>
              {best ? (best.draft ? "Pending Person in this Encounter" : `ID ${best.person_id}`) : weakMatch ? "The closest result did not meet the matching threshold." : "No candidate was found in People."}
            </Text>
          </Box>
          {best && !best.draft && <Button variant="default" fullWidth leftSection={<IconArrowsHorizontal size={17} />} onClick={onCompare}>View reference photos</Button>}
        </Stack>
      </Group>
    </Card>
  );
}

function PeoplePicker({ opened, people, allPeople, mode, onMode, loading, query, onQuery, onClose, onNewPerson, onSelect }) {
  const normalizedQuery = query.trim().toLowerCase();
  const visiblePeople = browsePeopleCandidates(people, allPeople, mode).filter((person) => (
    !normalizedQuery
    || person.name?.toLowerCase().includes(normalizedQuery)
    || person.person_id?.toLowerCase().includes(normalizedQuery)
  ));
  return (
    <Modal opened={opened} onClose={onClose} title="Browse People" size="xl" centered>
      <Text size="sm" c="dimmed" mb="md">Choose who the selected incoming photos belong to.</Text>
      <Group align="end" mb="md">
      <TextInput
        value={query}
        onChange={(event) => onQuery(event.currentTarget.value)}
        leftSection={<IconSearch size={16} />}
        placeholder="Search people by name or ID"
        style={{ flex: 1 }}
      />
      <Select data={PROFILE_BROWSE_MODES} value={mode} onChange={(value) => onMode(value || "biometric")} aria-label="Profile type" w={250} />
      </Group>
      <ScrollArea.Autosize mah="60dvh" type="auto" offsetScrollbars>
        {mode === "no_face" ? <Stack gap="xs">
          <Button variant="light" leftSection={<IconUserPlus size={17} />} onClick={onNewPerson}>New person</Button>
          {visiblePeople.map((person) => <Paper key={person.person_id} component="button" type="button" withBorder p="sm" radius="md" className="mantine-click-card" onClick={() => onSelect(person)}>
            <Group wrap="nowrap"><ThemeIcon variant="light" color="gray" radius="xl"><IconUsers size={18} /></ThemeIcon><Box style={{ flex: 1 }}><Text fw={700} size="sm">{person.name}</Text><Text size="xs" c="dimmed">{person.metadata?.rank || "No role"} · {person.metadata?.country || "Country unknown"}</Text></Box><Badge variant="light" color="gray">No face enrolled</Badge></Group>
          </Paper>)}
        </Stack> :
        <SimpleGrid cols={{ base: 2, sm: 3, md: 4 }} className="queue-people-picker-grid">
          <Card component="button" withBorder radius="md" className="queue-person-picker-card queue-person-picker-new" onClick={onNewPerson}>
            <ThemeIcon size={58} radius="xl" variant="light" color="teal"><IconUserPlus size={28} /></ThemeIcon>
            <Text fw={800}>New person</Text>
            <Text size="xs" c="dimmed">Create a profile from these photos</Text>
          </Card>
          {visiblePeople.map((person) => {
            const candidateDisplay = person.match?.classification === "unknown"
              ? { badge: "Weak match", color: "orange" }
              : matchDisplay(person.match);
            return (
              <Card key={person.person_id} component="button" withBorder radius="md" className="queue-person-picker-card" onClick={() => onSelect(person)}>
                <Box className="queue-person-picker-photo">
                  {person.representative_image ? (
                    <Image src={mediaUrl(person.representative_image)} alt={person.name} fit="contain" />
                  ) : (
                    <ThemeIcon size={54} radius="xl" variant="light" color="gray"><IconUsers size={27} /></ThemeIcon>
                  )}
                  {person.match && <Badge className="queue-person-picker-rank" color={candidateDisplay.color}>#{person.match.rank}</Badge>}
                </Box>
                <Group justify="space-between" wrap="nowrap" gap={6}>
                  <Text fw={800} truncate>{person.name}</Text>
                  {person.draft_created && <Badge size="xs">Drafted</Badge>}
                  <Badge size="xs" variant="light" color={person.match ? candidateDisplay.color : "gray"}>
                    {mode === "no_face" ? "No face enrolled" : person.match ? candidateDisplay.badge : "No references"}
                  </Badge>
                </Group>
                <Text size="xs" c="dimmed">{person.embedding_count || 0} reference photo{Number(person.embedding_count || 0) === 1 ? "" : "s"}</Text>
              </Card>
            );
          })}
        </SimpleGrid>}
        {!loading && !visiblePeople.length && (
          <Text ta="center" c="dimmed" py="xl">No existing people match this search.</Text>
        )}
        {loading && <Text ta="center" c="dimmed" py="xl">Loading People…</Text>}
      </ScrollArea.Autosize>
    </Modal>
  );
}

function QueueCompareOverview({ best, faces, references, onFocusIncoming, onFocusReference }) {
  return (
    <Stack className="queue-compare-overview">
      <Card withBorder radius="md" className="queue-reference-person">
        <Group justify="space-between">
          <Group>
            <ThemeIcon size={42} radius="xl" color="teal"><IconUsers size={21} /></ThemeIcon>
            <Box><Text fw={900}>{best?.name}</Text><Text size="xs" c="dimmed">{references.length} saved reference photo{references.length === 1 ? "" : "s"}</Text></Box>
          </Group>
          <Badge color={matchDisplay(best).color} size="lg">{matchDisplay(best).badge}</Badge>
        </Group>
      </Card>
      <Grid gutter="xl" align="center">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Text fw={800} mb="sm">Incoming photos</Text>
          <SimpleGrid cols={{ base: 2, sm: 3 }}>
            {faces.map((face, index) => <CompareThumbnail key={face.init_face_id} src={face.crop_path || face.source_image} label={`Incoming ${index + 1}`} onClick={() => onFocusIncoming(index)} />)}
          </SimpleGrid>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 2 }}><ThemeIcon className="queue-compare-arrow" size={54} radius="xl" variant="light"><IconArrowsHorizontal size={25} /></ThemeIcon></Grid.Col>
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Text fw={800} mb="sm">Saved reference photos</Text>
          {references.length ? (
            <SimpleGrid cols={{ base: 2, sm: 3 }}>
              {references.map((reference, index) => <CompareThumbnail key={reference.embedding_id || index} src={reference.crop_path || reference.source_image} label={`Reference ${index + 1}`} onClick={() => onFocusReference(index)} />)}
            </SimpleGrid>
          ) : <EmptyCard text="No saved reference photos." />}
        </Grid.Col>
      </Grid>
    </Stack>
  );
}

function CompareThumbnail({ src, label, onClick }) {
  return (
    <Card component="button" withBorder radius="md" p={6} className="mantine-click-card queue-compare-thumb" onClick={onClick}>
      <Image src={mediaUrl(src)} alt={label} h={145} fit="cover" radius="sm" />
      <Text size="xs" fw={700} mt={5}>{label}</Text>
    </Card>
  );
}

function QueueFocusedCompare({
  faces,
  references,
  incomingIndex,
  referenceIndex,
  zoom,
  syncZoom,
  onIncoming,
  onReference,
  onZoom,
  onSyncZoom,
  onOverview,
  galleryEndRef,
}) {
  const incoming = faces[incomingIndex] || faces[0];
  const reference = references[referenceIndex] || references[0];
  return (
    <Stack className="queue-focused-shell">
      <Group justify="space-between" className="queue-focused-toolbar">
        <Button variant="subtle" leftSection={<IconArrowLeft size={16} />} onClick={onOverview}>Comparison overview</Button>
        <Group gap="xs">
          <ActionIcon variant="default" aria-label="Zoom out" onClick={() => onZoom(Math.max(0.7, zoom - 0.15))}><IconMinus size={17} /></ActionIcon>
          <Text size="sm" miw={48} ta="center">{Math.round(zoom * 100)}%</Text>
          <ActionIcon variant="default" aria-label="Zoom in" onClick={() => onZoom(Math.min(2, zoom + 0.15))}><IconPlus size={17} /></ActionIcon>
          <ActionIcon variant="default" aria-label="Fit images" onClick={() => onZoom(1)}><IconMaximize size={17} /></ActionIcon>
          <Switch checked={syncZoom} onChange={(event) => onSyncZoom(event.currentTarget.checked)} label="Sync" size="sm" />
        </Group>
      </Group>
      <Grid gutter="md">
        <Grid.Col span={{ base: 12, md: 6 }}>
          <FocusedImage title="Incoming photo" src={incoming?.crop_path || incoming?.source_image} zoom={zoom} />
          <Group className="queue-focused-thumbs" mt="sm">
            {faces.map((face, index) => <Image key={face.init_face_id} src={mediaUrl(face.crop_path || face.source_image)} alt={`incoming ${index + 1}`} data-active={index === incomingIndex} onClick={() => onIncoming(index)} />)}
          </Group>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <FocusedImage title="Saved reference" src={reference?.crop_path || reference?.source_image} zoom={syncZoom ? zoom : 1} />
          <Group className="queue-focused-thumbs" mt="sm">
            {references.map((item, index) => <Image key={item.embedding_id || index} src={mediaUrl(item.crop_path || item.source_image)} alt={`reference ${index + 1}`} data-active={index === referenceIndex} onClick={() => onReference(index)} />)}
          </Group>
        </Grid.Col>
      </Grid>
      <Box ref={galleryEndRef} className="queue-gallery-scroll-anchor" aria-hidden="true" />
    </Stack>
  );
}

function FocusedImage({ title, src, zoom }) {
  return (
    <Card withBorder radius="md" className="queue-focused-stage">
      <Text fw={800} mb="sm">{title}</Text>
      {src ? <Box className="queue-focused-image"><Image src={mediaUrl(src)} alt={title} fit="contain" style={{ transform: `scale(${zoom})` }} /></Box> : <EmptyCard text="No reference image." />}
    </Card>
  );
}
