import { useEffect, useRef } from "react";

import {
  Badge,
  Box,
  Button,
  Card,
  FileButton,
  Grid,
  Group,
  Image,
  Paper,
  Progress,
  ScrollArea,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconChevronRight,
  IconCopy,
  IconTrash,
  IconEye,
  IconFolderOpen,
  IconPhotoUp,
  IconRefresh,
  IconClock,
  IconBulb,
  IconFileText,
  IconInfoCircle,
  IconX,
  IconUsers,
} from "@tabler/icons-react";

import { RecognitionFollowupForm } from "../components/RecognitionFollowupForm.jsx";
import { BestMatchPanel, EmptyCard, GalleryPanel, Surface } from "../components/Shared.jsx";
import { hasCertainMatch, isNewPersonSuggestion, mediaUrl, recognitionText } from "../utils.js";

export function QueueView({
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
  onFiles,
  onFolder,
  onDrop,
  onCancelProcessing,
  onRefresh,
  onOpenGroup,
  onToggleFace,
  onAcceptExisting,
  onNewPerson,
  onDiscard,
  onFollowupChange,
  onFollowupSubmit,
  onFollowupClear,
  onGallery,
  onGalleryImage,
  onGalleryBack,
  onBack,
}) {
  return (
    <Paper withBorder radius="md" p="md" className="queue-workspace" data-followup-open={Boolean(queueFollowup)}>
      <Grid gutter="lg" className="queue-shell-grid">
        {!queueSelectedGroup && (
          <Grid.Col span={{ base: 12, md: "content" }} className="queue-sidebar-col">
            <QueueInputPanel
              sessionId={queueSessionId}
              onFolder={onFolder}
              onDrop={onDrop}
              onRefresh={onRefresh}
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
              onToggleFace={onToggleFace}
              onAcceptExisting={onAcceptExisting}
              onNewPerson={onNewPerson}
              onDiscard={onDiscard}
              onFollowupChange={onFollowupChange}
              onFollowupSubmit={onFollowupSubmit}
              onFollowupClear={onFollowupClear}
              onGallery={onGallery}
              onGalleryImage={onGalleryImage}
              onGalleryBack={onGalleryBack}
              onBack={onBack}
            />
          ) : (
            <QueueGroupList groups={queueGroups} progress={queueProgress} onCancelProcessing={onCancelProcessing} onOpen={onOpenGroup} />
          )}
        </Grid.Col>
      </Grid>
    </Paper>
  );
}

function QueueInputPanel({ sessionId, onFolder, onDrop, onRefresh }) {
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
        <Stack gap="md">
          <Box>
            <Text fw={800} size="lg">Upload Folder</Text>
            <Text size="sm" c="dimmed" mt={4}>Build review groups from local photos.</Text>
          </Box>
          <Box className="queue-folder-drop-target">
            <ThemeIcon size={42} radius="md" variant="light" color="teal" className="queue-folder-drop-icon">
              <IconFolderOpen size={25} />
            </ThemeIcon>
            <Text fw={700} size="sm">Drop folder here</Text>
            <FileButton onChange={onFolder} accept="image/*" multiple inputProps={{ webkitdirectory: "", directory: "" }}>
              {(props) => <Button {...props} fullWidth leftSection={<IconFolderOpen size={16} />}>Select Folder</Button>}
            </FileButton>
            <Group gap={6} wrap="nowrap" justify="center" className="queue-drop-note">
              <IconInfoCircle size={14} />
              <Text size="xs" c="dimmed">Stays on this device.</Text>
            </Group>
          </Box>
        </Stack>
      </Paper>
      {sessionId && (
        <Card withBorder radius="md" className="queue-side-card queue-session-card">
          <Group justify="space-between" wrap="nowrap">
            <Text fw={700}>Session</Text>
            <ThemeIcon variant="subtle" color="gray" size="sm"><IconCopy size={15} /></ThemeIcon>
          </Group>
          <Text size="xs" c="dimmed" lineClamp={1} mt={4}>{sessionId}</Text>
          <Button mt="xs" size="sm" variant="default" fullWidth leftSection={<IconRefresh size={15} />} onClick={onRefresh}>Refresh</Button>
        </Card>
      )}
      <Card withBorder radius="md" className="queue-side-card queue-side-card--steps">
        <Text fw={700} mb="xs">Flow</Text>
        <Stack gap={7}>
          {["Upload folder", "Group faces", "Review matches", "Confirm people"].map((step, index) => (
            <Group key={step} gap="sm" wrap="nowrap">
              <ThemeIcon radius="xl" size="sm" color="teal">{index + 1}</ThemeIcon>
              <Text size="sm" c="dimmed">{step}</Text>
            </Group>
          ))}
        </Stack>
      </Card>
    </Stack>
  );
}

function QueueGroupList({ groups, progress, onCancelProcessing, onOpen }) {
  const pendingGroups = groups.filter((group) => group.status === "pending" && group.faces.length);
  const isProcessing = progress && progress.status === "running";
  return (
    <Stack className="queue-review-list">
      <Group align="flex-start" justify="space-between" gap="md" wrap="nowrap">
        <Group align="center" gap="md">
          <Box>
            <Title order={2} size="h3">Review Queue</Title>
            <Text size="sm" c="dimmed">{isProcessing ? "We're processing your photos. This may take a few minutes." : "Review the groups below and take action."}</Text>
          </Box>
          <Badge variant="light" size="lg">{isProcessing ? "Processing" : `${pendingGroups.length} Active`}</Badge>
        </Group>
        {isProcessing && (
          <Button variant="default" leftSection={<IconX size={16} />} onClick={onCancelProcessing}>
            Cancel Processing
          </Button>
        )}
      </Group>
      <Box className="queue-list-divider" />
      {isProcessing ? (
        <>
          <QueueProcessingPanel progress={progress} />
          <QueueGroupsPendingPlaceholder />
          <QueueProcessingTip />
        </>
      ) : (
        <>
          <Stack gap="sm">
            {pendingGroups.length ? pendingGroups.map((group) => {
              const best = group?.matches?.[0] || null;
              const score = best?.score || 0;
              const scoreLabel = score >= 0.9 ? "Strong Match" : score >= 0.65 ? "Good Match" : "Possible Match";
              const scoreColorName = score >= 0.9 ? "green" : score >= 0.65 ? "blue" : "yellow";
              return (
                <Card key={`${group.session_id}-${group.group_id}`} withBorder radius="md" p="md" className="queue-group-row">
                  <Group justify="space-between" wrap="nowrap" align="center">
                    <Group gap="lg" wrap="nowrap" className="queue-row-media">
                      <QueuePreviewMosaic faces={group.faces} />
                      <Box miw={0} className="queue-row-copy">
                        <Text fw={800} size="lg" className="queue-row-title">{recognitionText(best)}</Text>
                        <Text size="sm" c="dimmed" className="queue-row-meta">{group.group_id} • {group.faces.length} image{group.faces.length === 1 ? "" : "s"}</Text>
                        <Group gap="sm" mt="md">
                          {best && <Badge color={scoreColorName} variant="light" size="lg">{scoreLabel}</Badge>}
                          {best && <Badge color={scoreColorName} variant="light" size="lg">{best.score.toFixed(3)}</Badge>}
                        </Group>
                      </Box>
                    </Group>
                    <Group gap="lg" wrap="nowrap">
                      <Button variant="default" leftSection={<IconEye size={17} />} onClick={() => onOpen(group)}>Review Group</Button>
                      <ThemeIcon variant="subtle" color="gray"><IconChevronRight size={22} /></ThemeIcon>
                    </Group>
                  </Group>
                </Card>
              );
            }) : <EmptyCard text="No queue groups loaded." />}
          </Stack>
          <Text size="sm" c="dimmed">Showing {pendingGroups.length} group{pendingGroups.length === 1 ? "" : "s"}</Text>
        </>
      )}
    </Stack>
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
  selectedFaces,
  accepted,
  followup,
  followupDone,
  gallery,
  galleryImage,
  onToggleFace,
  onAcceptExisting,
  onNewPerson,
  onDiscard,
  onFollowupChange,
  onFollowupSubmit,
  onFollowupClear,
  onGallery,
  onGalleryImage,
  onGalleryBack,
  onBack,
}) {
  const followupRef = useRef(null);
  const best = group.matches?.[0] || null;
  const selectedCount = selectedFaces.length;
  const actionScope = selectedCount ? `${selectedCount} selected` : "group";
  const shouldFadeNewPerson = hasCertainMatch(best);

  useEffect(() => {
    if (!followup) return;
    followupRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [followup]);

  return (
    <Stack className="queue-review-shell" data-followup-open={Boolean(followup)}>
      <Group justify="space-between" align="flex-start">
        <Box>
          <Title order={3} size="h4">{group.group_id}</Title>
          <Text size="xs" c="dimmed">{group.faces.length} image(s) left | {selectedCount} selected</Text>
        </Box>
        <Button variant="light" leftSection={<IconArrowLeft size={16} />} onClick={onBack}>Back</Button>
      </Group>
      <Grid className="queue-review-body">
        <Grid.Col span={{ base: 12, md: 7 }}>
          <ScrollArea.Autosize mah="100%" className="queue-face-scroll">
            <SimpleGrid cols={{ base: 2, sm: 3, lg: 4 }}>
              {group.faces.map((face) => {
                const selected = selectedFaces.includes(face.init_face_id);
                return (
                  <Card
                    key={face.init_face_id}
                    withBorder
                    radius="md"
                    p="xs"
                    component="button"
                    className="mantine-click-card queue-face-card"
                    data-selected={selected}
                    disabled={accepted}
                    onClick={() => onToggleFace(face.init_face_id)}
                  >
                    <Stack gap={6}>
                      <Image src={mediaUrl(face.crop_path || face.source_image)} alt="queue face" fit="cover" h={112} radius="sm" />
                      <Text size="xs" fw={700} c={selected ? "teal" : "dimmed"} ta="center">{selected ? "Selected" : "Select"}</Text>
                    </Stack>
                  </Card>
                );
              })}
            </SimpleGrid>
          </ScrollArea.Autosize>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Surface title="Suggested Match" subtitle={selectedCount ? `${selectedCount} selected` : `${group.faces.length} image${group.faces.length === 1 ? "" : "s"} in group`}>
            {gallery
              ? <GalleryPanel payload={gallery} selectedImage={galleryImage} onImage={onGalleryImage} onBack={onGalleryBack} />
              : <BestMatchPanel best={best} face={{ index: 1 }} selectedImage={galleryImage} onGallery={onGallery} />}
            <Group grow mt="md" className="queue-decision-actions">
              <Button onClick={onAcceptExisting} disabled={!best || isNewPersonSuggestion(best) || !group.faces.length || accepted}>
                {best && !isNewPersonSuggestion(best) ? `Accept ${actionScope} as ${best.name}` : "Accept"}
              </Button>
              <Button variant="light" onClick={onNewPerson} disabled={!group.faces.length || accepted || shouldFadeNewPerson}>
                {selectedCount ? `New from ${selectedCount}` : "New Person"}
              </Button>
              <Button color="red" variant="light" leftSection={<IconTrash size={17} />} onClick={onDiscard} disabled={!selectedCount || accepted}>
                Reject selected
              </Button>
            </Group>
          </Surface>
        </Grid.Col>
      </Grid>
      {followup && (
        <Card withBorder radius="md" ref={followupRef} className="queue-followup-card">
          <Text fw={700}>{followup.name || "New person"}</Text>
          <Text size="xs" c="dimmed" mb="sm">{followup.faceIds.length} image(s)</Text>
          <RecognitionFollowupForm values={followup} confirmed={followupDone} onChange={onFollowupChange} onSubmit={onFollowupSubmit} onClear={onFollowupClear} embedded showAddedBy />
        </Card>
      )}
    </Stack>
  );
}
