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
import { IconArrowLeft, IconFolderOpen, IconPhotoUp, IconRefresh } from "@tabler/icons-react";

import { RecognitionFollowupForm } from "../components/RecognitionFollowupForm.jsx";
import { BestMatchPanel, EmptyCard, GalleryPanel, Surface, Thumb } from "../components/Shared.jsx";
import { hasCertainMatch, isNewPersonSuggestion, mediaUrl, recognitionText, scoreColor } from "../utils.js";

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
    <Paper withBorder radius="md" p="md">
      <Grid>
        {!queueSelectedGroup && (
          <Grid.Col span={{ base: 12, md: 4 }}>
            <QueueInputPanel
              sessionId={queueSessionId}
              onFiles={onFiles}
              onFolder={onFolder}
              onDrop={onDrop}
              onRefresh={onRefresh}
            />
          </Grid.Col>
        )}
        <Grid.Col span={queueSelectedGroup ? 12 : { base: 12, md: 8 }}>
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
    <Stack>
      <Paper
        withBorder
        radius="md"
        p="xl"
        className="queue-dropzone"
        onDrop={onDrop}
        onDragOver={(event) => event.preventDefault()}
      >
        <Stack align="center" gap="sm">
          <ThemeIcon size={44} variant="light"><IconPhotoUp size={24} /></ThemeIcon>
          <Box ta="center">
            <Text fw={700}>Drag & Drop Image / Folder</Text>
            <Text size="sm" c="dimmed">Create embeddings, group similar photos, then review each group.</Text>
          </Box>
          <Group>
            <FileButton onChange={onFiles} accept="image/*" multiple>
              {(props) => <Button {...props} variant="light" leftSection={<IconPhotoUp size={16} />}>Select File</Button>}
            </FileButton>
            <FileButton onChange={onFolder} accept="image/*" multiple inputProps={{ webkitdirectory: "", directory: "" }}>
              {(props) => <Button {...props} variant="light" leftSection={<IconFolderOpen size={16} />}>Select Folder</Button>}
            </FileButton>
          </Group>
        </Stack>
      </Paper>
      {sessionId && (
        <Card withBorder radius="md">
          <Text size="xs" c="dimmed" fw={700}>Session</Text>
          <Text size="xs" lineClamp={2}>{sessionId}</Text>
          <Button mt="sm" variant="light" fullWidth leftSection={<IconRefresh size={16} />} onClick={onRefresh}>Refresh Groups</Button>
        </Card>
      )}
    </Stack>
  );
}

function QueueGroupList({ groups, onOpen }) {
  const pendingGroups = groups.filter((group) => group.status === "pending" && group.faces.length);
  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3} size="h4">Queue Groups</Title>
        <Badge variant="light">{pendingGroups.length} active</Badge>
      </Group>
      <SimpleGrid cols={{ base: 1, sm: 2, xl: 3 }}>
        {pendingGroups.length ? pendingGroups.map((group) => {
          const best = group?.matches?.[0] || null;
          const noMatchFound = isNewPersonSuggestion(best);
          return (
            <Card key={`${group.session_id}-${group.group_id}`} withBorder radius="md" p="sm" component="button" className="mantine-click-card" onClick={() => onOpen(group)}>
              <Stack gap="sm">
                <Group justify="space-between" align="flex-start" wrap="nowrap">
                  <Box miw={0}>
                    <Text fw={700}>{recognitionText(best)}</Text>
                    <Text size="xs" c="dimmed">{group.group_id} | {group.faces.length} image(s)</Text>
                  </Box>
                  {best && <Badge color={scoreColor(best.score)}>{best.score.toFixed(3)}</Badge>}
                </Group>
                <SimpleGrid cols={3} spacing="xs">
                  {!noMatchFound && group.faces.slice(0, 6).map((face) => <Thumb key={face.init_face_id} path={face.crop_path || face.source_image} />)}
                </SimpleGrid>
              </Stack>
            </Card>
          );
        }) : <EmptyCard text="No queue groups loaded." />}
      </SimpleGrid>
    </Stack>
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
              : <BestMatchPanel best={best} face={{ index: 1 }} onGallery={onGallery} />}
            <SimpleGrid cols={{ base: 1, sm: 2 }} mt="md">
              <Button onClick={onAcceptExisting} disabled={!best || isNewPersonSuggestion(best) || !selectedCount || accepted}>
                {best && !isNewPersonSuggestion(best) ? `Accept as ${best.name}` : "Accept"}
              </Button>
              <Button variant="light" onClick={onNewPerson} disabled={!selectedCount || accepted || shouldFadeNewPerson}>New Person</Button>
              <Button color="red" variant="light" onClick={onDiscard} disabled={!selectedCount || accepted}>Discard</Button>
              <Button variant="subtle" onClick={onBack}>Back</Button>
            </SimpleGrid>
          </Surface>
        </Grid.Col>
      </Grid>
      {followup && (
        <Card withBorder radius="md">
          <Text fw={700}>{followup.name || "New person"}</Text>
          <Text size="xs" c="dimmed" mb="sm">{followup.faceIds.length} image(s)</Text>
          <RecognitionFollowupForm values={followup} confirmed={followupDone} onChange={onFollowupChange} onSubmit={onFollowupSubmit} onClear={onFollowupClear} embedded />
        </Card>
      )}
    </Stack>
  );
}
