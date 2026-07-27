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
  Paper,
  Progress,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Text,
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
import { EmptyCard } from "../components/Shared.jsx";
import { isNewPersonSuggestion, matchDisplay, mediaUrl, qualityColor, recognitionText } from "../utils.js";

export function QueueView({
  queueSessions,
  queueGroups,
  queueSessionId,
  queueProgress,
  queueSelectedGroup,
  queueSelectedFaces,
  queueAccepted,
  queueFollowup,
  queueFollowupDone,
  queueGallery,
  queueGalleryImage,
  queueReviewStats,
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
  onDiscard,
  onDiscardGroup,
  onSkip,
  onResumeSkipped,
  onRejectSuggestedMatch,
  onViewPeople,
  onFollowupChange,
  onFollowupSubmit,
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
      <Paper withBorder radius="md" p="md" className="queue-workspace" data-followup-open={Boolean(queueFollowup)}>
        <Grid gutter="lg" className="queue-shell-grid">
        {!queueSelectedGroup && (
          <Grid.Col span={{ base: 12, md: "content" }} className="queue-sidebar-col">
            <QueueInputPanel
              sessions={queueSessions}
              sessionId={queueSessionId}
              pendingCount={queueGroups.filter((group) => group.status === "pending" && group.faces.length).length}
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
          {queueSelectedGroup ? (
            <QueueGroupReview
              group={queueSelectedGroup}
              selectedFaces={queueSelectedFaces}
              accepted={queueAccepted}
              followup={queueFollowup}
              followupDone={queueFollowupDone}
              gallery={queueGallery}
              galleryImage={queueGalleryImage}
              groups={queueGroups.filter((group) => group.status === "pending" && group.faces.length)}
              onOpenGroup={onOpenGroup}
              onToggleFace={onToggleFace}
              onSelectAllFaces={onSelectAllFaces}
              onClearFaces={onClearFaces}
              onAcceptExisting={onAcceptExisting}
              onNewPerson={onNewPerson}
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
              onBack={onBack}
            />
          ) : (
            <QueueGroupList
              groups={queueGroups}
              progress={queueProgress}
              sessionId={queueSessionId}
              stats={queueReviewStats}
              onCancelProcessing={onCancelProcessing}
              onOpen={onOpenGroup}
              onDiscardGroup={setGroupPendingDiscard}
              onResumeSkipped={onResumeSkipped}
              onViewPeople={onViewPeople}
            />
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
          <Box>
            <Text fw={800} size="lg">Add Photos</Text>
            <Text size="xs" c="dimmed" mt={2}>Every detected face becomes a review item.</Text>
          </Box>
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
              label: `${session.session_id.slice(0, 8)} · ${session.face_count} face${session.face_count === 1 ? "" : "s"}`,
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

function QueueGroupList({ groups, progress, sessionId, stats, onCancelProcessing, onOpen, onDiscardGroup, onResumeSkipped, onViewPeople }) {
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("confidence");
  const pendingGroups = groups.filter((group) => group.status === "pending" && group.faces.length);
  const skippedGroups = groups.filter((group) => group.status === "skipped" && group.faces.length);
  const isProcessing = progress && progress.status === "running";
  const visibleGroups = useMemo(() => {
    const filtered = pendingGroups.filter((group) => {
      const score = group.matches?.[0]?.score || 0;
      if (filter === "high") return score >= 0.62;
      if (filter === "review") return score < 0.62;
      return true;
    });
    return [...filtered].sort((left, right) => {
      if (sort === "faces") return right.faces.length - left.faces.length;
      if (sort === "oldest") return String(left.group_id).localeCompare(String(right.group_id));
      return (right.matches?.[0]?.score || 0) - (left.matches?.[0]?.score || 0);
    });
  }, [filter, pendingGroups, sort]);

  if (sessionId && !isProcessing && pendingGroups.length === 0 && (stats?.totalGroups || skippedGroups.length)) {
    return <QueueReviewComplete stats={stats} skippedCount={skippedGroups.length || stats?.skippedGroups || 0} onResumeSkipped={onResumeSkipped} onViewPeople={onViewPeople} />;
  }

  return (
    <Stack className="queue-review-list">
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
              {[["all", "All"], ["high", "High confidence"], ["review", "Needs review"]].map(([value, label]) => (
                <Button key={value} size="xs" variant={filter === value ? "filled" : "subtle"} color={filter === value ? "teal" : "gray"} onClick={() => setFilter(value)}>{label}</Button>
              ))}
            </Group>
            <Select
              size="xs"
              value={sort}
              onChange={(value) => setSort(value || "confidence")}
              data={[
                { value: "confidence", label: "Highest confidence" },
                { value: "faces", label: "Most photos" },
                { value: "oldest", label: "Oldest first" },
              ]}
              w={185}
            />
          </Group>
          <ScrollArea.Autosize mah="calc(100vh - 330px)" className="queue-groups-scroll">
            <Stack gap="sm">
              {visibleGroups.length ? visibleGroups.map((group) => {
                const best = group.matches?.[0] || null;
                const score = best?.score || 0;
                const display = matchDisplay(score);
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
                            {best && <Badge color={display.color} variant="outline">{Math.round(score * 100)}% match</Badge>}
                          </Group>
                        </Box>
                      </Group>
                      <Group gap="xs" wrap="nowrap" className="queue-row-actions">
                        <Button color="red" variant="light" leftSection={<IconTrash size={16} />} onClick={(event) => { event.stopPropagation(); onDiscardGroup(group); }}>Discard</Button>
                        <Button className="queue-row-action" variant="default" rightSection={<IconChevronRight size={17} />} onClick={(event) => { event.stopPropagation(); onOpen(group); }}>Review</Button>
                      </Group>
                    </Group>
                  </Card>
                );
              }) : <EmptyCard text="No groups match this filter." />}
            </Stack>
          </ScrollArea.Autosize>
          <Text size="sm" c="dimmed">Showing {visibleGroups.length} of {pendingGroups.length} groups</Text>
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
      <Stack gap="lg">
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
                <ThemeIcon size={42} radius="xl" variant={active || complete ? "light" : "default"} color={complete ? "teal" : active ? "blue" : "gray"}>
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
          {[0, 1, 2, 3].map((item) => (
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

const phaseOrder = ["uploading", "detecting", "matching", "clustering", "preparing", "done"];

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
      <Image src={mediaUrl(primary.crop_path || primary.source_image)} alt="group preview" fit="cover" className="queue-preview-main" radius="sm" />
      <Box className="queue-preview-thumbs">
        {thumbnails.map((face, index) => (
          <Box key={face.init_face_id} className="queue-thumb-wrap">
            <Image src={mediaUrl(face.crop_path || face.source_image)} alt="group thumbnail" fit="cover" radius="sm" />
            {overflowCount > 0 && index === thumbnails.length - 1 && <Box className="queue-thumb-more">+{overflowCount}</Box>}
          </Box>
        ))}
      </Box>
    </Group>
  );
}

function QueueGroupReview({
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
  onDiscard,
  onDiscardGroup,
  onSkip,
  onRejectSuggestedMatch,
  onFollowupChange,
  onFollowupSubmit,
  onFollowupClear,
  onGallery,
  onBack,
}) {
  const followupRef = useRef(null);
  const galleryEndRef = useRef(null);
  const [mode, setMode] = useState("summary");
  const [focused, setFocused] = useState(false);
  const [incomingIndex, setIncomingIndex] = useState(0);
  const [referenceIndex, setReferenceIndex] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [syncZoom, setSyncZoom] = useState(true);
  const best = group.matches?.[0] || null;
  const selectedCount = selectedFaces.length;
  const currentIndex = Math.max(0, groups.findIndex((item) => item.group_id === group.group_id));
  const references = gallery?.embeddings || [];

  useEffect(() => {
    setMode("summary");
    setFocused(false);
    setIncomingIndex(0);
    setReferenceIndex(0);
    setZoom(1);
  }, [group.group_id]);

  useEffect(() => {
    if (!followup) return;
    followupRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [followup]);

  const openCompare = async () => {
    if (best?.person_id && !gallery) await onGallery(best.person_id);
    setMode("compare");
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
        <Button size="xs" variant={mode === "compare" ? "filled" : "subtle"} color={mode === "compare" ? "teal" : "gray"} onClick={openCompare} disabled={!best || isNewPersonSuggestion(best)}>Compare</Button>
      </Group>

      {mode === "summary" ? (
        <Grid gutter="md" className="queue-review-content">
          <Grid.Col span={{ base: 12, md: 7 }}>
            <Card withBorder radius="md" className="queue-review-panel">
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
            <QueueSuggestedMatch best={best} face={group.faces[0]} onCompare={openCompare} />
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
        <Card withBorder radius="md" ref={followupRef} className="queue-followup-card">
          <Text fw={700}>{followup.name || "New person"}</Text>
          <Text size="xs" c="dimmed" mb="sm">{followup.faceIds.length} photo{followup.faceIds.length === 1 ? "" : "s"}</Text>
          <RecognitionFollowupForm values={followup} confirmed={followupDone} onChange={onFollowupChange} onSubmit={onFollowupSubmit} onClear={onFollowupClear} embedded showAddedBy />
        </Card>
      )}

      <Group grow className="queue-review-actionbar">
        <Button leftSection={<IconCheck size={18} />} onClick={onAcceptExisting} disabled={!best || isNewPersonSuggestion(best) || !selectedCount || accepted}>
          {best && !isNewPersonSuggestion(best) ? `Accept ${selectedCount} as ${best.name}` : "Accept suggested match"}
        </Button>
        <Button variant="light" leftSection={<IconUserPlus size={18} />} onClick={onNewPerson} disabled={!selectedCount || accepted}>Create new person</Button>
        <Button variant="light" color="red" leftSection={<IconTrash size={18} />} onClick={onDiscard} disabled={!selectedCount || accepted}>Discard selected</Button>
        <Button variant="default" color="orange" leftSection={<IconX size={18} />} onClick={onRejectSuggestedMatch} disabled={!best || isNewPersonSuggestion(best) || accepted}>Reject suggested match</Button>
        <Button variant="subtle" color="gray" rightSection={<IconChevronRight size={17} />} onClick={onSkip} disabled={accepted}>Skip for now</Button>
      </Group>
    </Stack>
  );
}

function QueueIncomingGrid({ faces, selectedFaces, accepted, onToggleFace }) {
  return (
    <SimpleGrid cols={{ base: 2, sm: 3 }} className="queue-photo-selection-grid">
      {faces.map((face) => {
        const selected = selectedFaces.includes(face.init_face_id);
        return (
          <Card
            key={face.init_face_id}
            withBorder
            radius="md"
            p="xs"
            component="button"
            className="mantine-click-card queue-selection-card"
            data-selected={selected}
            disabled={accepted}
            onClick={() => onToggleFace(face.init_face_id)}
          >
            <Box pos="relative">
              <Image src={mediaUrl(face.crop_path || face.source_image)} alt="incoming face" fit="cover" h={132} radius="sm" />
              <ThemeIcon className="queue-selection-check" color={selected ? "teal" : "gray"} radius="xl" size="sm">{selected ? <IconCheck size={14} /> : <IconX size={13} />}</ThemeIcon>
            </Box>
            <Group justify="space-between" mt={7}>
              <Text size="xs" fw={800}>{selected ? "Included" : "Excluded"}</Text>
              <Badge size="xs" variant="light" color={qualityColor(face.quality?.status)}>{face.quality?.status || "unknown"}</Badge>
            </Group>
          </Card>
        );
      })}
    </SimpleGrid>
  );
}

function QueueSuggestedMatch({ best, face, onCompare }) {
  const known = best && !isNewPersonSuggestion(best);
  const display = matchDisplay(best?.score || 0);
  const suggestionImage = best?.representative_image || best?.image_path || face?.crop_path || face?.source_image;
  return (
    <Card withBorder radius="md" className="queue-review-panel queue-suggestion-panel">
      <Text fw={800}>Suggested match</Text>
      <Text size="xs" c="dimmed" mb="md">Best result from your People database.</Text>
      <Group align="stretch" wrap="nowrap" className="queue-suggestion-body">
        <Box className="queue-suggestion-hero">
          <Image src={mediaUrl(suggestionImage)} alt="suggested person" fit="contain" radius="md" />
        </Box>
        <Stack justify="space-between" gap="sm" className="queue-suggestion-copy">
          <Box>
            <Group justify="space-between" align="flex-start" wrap="nowrap">
              <Text size="xl" fw={900}>{known ? best.name : "Unknown person"}</Text>
              {best && <Badge color={display.color} size="lg">{Math.round(best.score * 100)}%</Badge>}
            </Group>
            <Text size="xs" c="dimmed" mt={4}>{known ? `ID ${best.person_id}` : "No confident match found"}</Text>
          </Box>
          {known && <Button variant="default" fullWidth leftSection={<IconArrowsHorizontal size={17} />} onClick={onCompare}>View reference photos</Button>}
        </Stack>
      </Group>
    </Card>
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
          <Badge color={matchDisplay(best?.score || 0).color} size="lg">{Math.round((best?.score || 0) * 100)}% match</Badge>
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
