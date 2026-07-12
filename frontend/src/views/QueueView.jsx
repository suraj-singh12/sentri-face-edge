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
} from "@tabler/icons-react";

import { RecognitionFollowupForm } from "../components/RecognitionFollowupForm.jsx";
import { BestMatchPanel, EmptyCard, GalleryPanel, Surface } from "../components/Shared.jsx";
import { hasCertainMatch, isNewPersonSuggestion, mediaUrl, recognitionText } from "../utils.js";

export function QueueView({
  queueGroups,
  queueSessionId,
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
    <Paper withBorder radius="md" p="md" className="queue-workspace">
      <Grid gutter="lg" className="queue-shell-grid">
        {!queueSelectedGroup && (
          <Grid.Col span={{ base: 12, md: "content" }} className="queue-sidebar-col">
            <QueueInputPanel
              sessionId={queueSessionId}
              onFiles={onFiles}
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
            <QueueGroupList groups={queueGroups} onOpen={onOpenGroup} />
          )}
        </Grid.Col>
      </Grid>
    </Paper>
  );
}

function QueueInputPanel({ sessionId, onFiles, onFolder, onDrop, onRefresh }) {
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
            <Text fw={800} size="lg">Upload Images</Text>
            <Text size="sm" c="dimmed" mt={6}>Add images to find similar faces and create groups for review.</Text>
          </Box>
          <FileButton onChange={onFolder} accept="image/*" multiple inputProps={{ webkitdirectory: "", directory: "" }}>
            {(props) => <Button {...props} fullWidth leftSection={<IconFolderOpen size={16} />}>Select Folder</Button>}
          </FileButton>
          <FileButton onChange={onFiles} accept="image/*" multiple>
            {(props) => <Button {...props} fullWidth variant="default" leftSection={<IconPhotoUp size={16} />}>Select Files</Button>}
          </FileButton>
        </Stack>
      </Paper>
      {sessionId && (
        <Card withBorder radius="md" className="queue-side-card">
          <Group justify="space-between" wrap="nowrap">
            <Text fw={700}>Session</Text>
            <ThemeIcon variant="subtle" color="gray" size="sm"><IconCopy size={15} /></ThemeIcon>
          </Group>
          <Text size="xs" c="dimmed" lineClamp={2} mt={6}>{sessionId}</Text>
          <Button mt="md" variant="default" fullWidth leftSection={<IconRefresh size={16} />} onClick={onRefresh}>Refresh Groups</Button>
        </Card>
      )}
      <Card withBorder radius="md" className="queue-side-card">
        <Text fw={700} mb="md">How it works</Text>
        <Stack gap="sm">
          {["Upload images", "Similar faces are grouped", "Review groups and take action", "Confirm to save to your people list"].map((step, index) => (
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

function QueueGroupList({ groups, onOpen }) {
  const pendingGroups = groups.filter((group) => group.status === "pending" && group.faces.length);
  return (
    <Stack className="queue-review-list">
      <Group align="center" gap="md">
        <Box>
          <Title order={2} size="h3">Review Queue</Title>
          <Text size="sm" c="dimmed">Review the groups below and take action.</Text>
        </Box>
        <Badge variant="light" size="lg">{pendingGroups.length} Active</Badge>
      </Group>
      <Box className="queue-list-divider" />
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
    </Stack>
  );
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
  const best = group.matches?.[0] || null;
  const selectedCount = selectedFaces.length;
  const shouldFadeNewPerson = hasCertainMatch(best);
  return (
    <Stack className="queue-review-shell">
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
          <Surface title="Suggested Match" subtitle="Select images before accepting.">
            {gallery
              ? <GalleryPanel payload={gallery} selectedImage={galleryImage} onImage={onGalleryImage} onBack={onGalleryBack} />
              : <BestMatchPanel best={best} face={{ index: 1 }} selectedImage={galleryImage} onGallery={onGallery} />}
            <Group grow mt="md" className="queue-decision-actions">
              <Button onClick={onAcceptExisting} disabled={!best || isNewPersonSuggestion(best) || !selectedCount || accepted}>
                {best && !isNewPersonSuggestion(best) ? `Accept as ${best.name}` : "Accept"}
              </Button>
              <Button variant="light" onClick={onNewPerson} disabled={!selectedCount || accepted || shouldFadeNewPerson}>New Person</Button>
              <Button color="red" variant="light" leftSection={<IconTrash size={17} />} onClick={onDiscard} disabled={!selectedCount || accepted}>
                Reject selected
              </Button>
            </Group>
          </Surface>
        </Grid.Col>
      </Grid>
      {followup && (
        <Card withBorder radius="md">
          <Text fw={700}>{followup.name || "New person"}</Text>
          <Text size="xs" c="dimmed" mb="sm">{followup.faceIds.length} image(s)</Text>
          <RecognitionFollowupForm values={followup} confirmed={followupDone} onChange={onFollowupChange} onSubmit={onFollowupSubmit} onClear={onFollowupClear} embedded showAddedBy />
        </Card>
      )}
    </Stack>
  );
}
