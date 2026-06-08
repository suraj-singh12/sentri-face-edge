import { useEffect, useState } from "react";
import {
  Badge,
  Box,
  Button,
  Card,
  Grid,
  Group,
  Image,
  Paper,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { IconArrowLeft, IconRefresh } from "@tabler/icons-react";

import { EmptyCard, ImageFrame } from "../components/Shared.jsx";
import { NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import {
  detailsForEmbedding,
  formatSeenDateTime,
  galleryImageRecords,
  mediaUrl,
  personProfile,
} from "../utils.js";

export function PeopleView({
  people,
  peopleGallery,
  peopleGalleryImage,
  onRefresh,
  onOpen,
  onImage,
  onBack,
  onSave,
}) {
  return (
    <Paper withBorder radius="md" p="md">
      {peopleGallery ? (
        <PeopleGalleryView
          payload={peopleGallery}
          selectedImage={peopleGalleryImage}
          onImage={onImage}
          onBack={onBack}
          onSave={onSave}
        />
      ) : (
        <Stack>
          <Group justify="space-between">
            <Title order={3} size="h4">People</Title>
            <Button variant="light" leftSection={<IconRefresh size={16} />} onClick={onRefresh}>Refresh</Button>
          </Group>
          <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }}>
            {people.length ? people.map((person) => <PersonCard key={person.person_id} person={person} onOpen={onOpen} />) : <EmptyCard text="No people enrolled yet." />}
          </SimpleGrid>
        </Stack>
      )}
    </Paper>
  );
}

function PersonCard({ person, onOpen }) {
  return (
    <Card withBorder radius="md" p="sm" component="button" className="mantine-click-card" onClick={() => onOpen(person.person_id)}>
      <Stack gap="sm" align="stretch">
        <ImageFrame variant="peopleCard">
          {person.representative_image ? <Image src={mediaUrl(person.representative_image)} alt={person.name} fit="cover" h="100%" /> : <Text size="sm" c="dimmed">No image</Text>}
        </ImageFrame>
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <Box miw={0}>
            <Text fw={700} lineClamp={1}>{person.name}</Text>
            <Text size="xs" c="dimmed" lineClamp={2}>{person.person_id}</Text>
          </Box>
          <Badge variant="light">{person.embedding_count}</Badge>
        </Group>
        <Text size="xs" c="dimmed">Created {person.created_at}</Text>
      </Stack>
    </Card>
  );
}

function PeopleGalleryView({ payload, selectedImage, onImage, onBack, onSave }) {
  const imageRecords = galleryImageRecords(payload);
  const [mode, setMode] = useState("info");
  const selectedRecord = selectedImage ? imageRecords.find((record) => record.path === selectedImage) : null;
  const selectedDetails = selectedRecord ? detailsForEmbedding(payload.details || [], selectedRecord.embeddingId) : payload.details || [];
  const profile = personProfile(payload, selectedDetails, Boolean(selectedRecord));
  const [editValues, setEditValues] = useState(profile);

  useEffect(() => {
    setEditValues(profile);
    setMode("info");
  }, [payload.person.person_id, payload.person.name, payload.person.metadata]);

  const updateEditValue = (field, value) => setEditValues((current) => ({ ...current, [field]: value }));
  const saveEdit = async (event) => {
    event.preventDefault();
    try {
      if (await onSave(editValues)) setMode("info");
    } catch (error) {
      console.error(error);
    }
  };

  return (
    <Stack className="people-gallery-shell">
      <Group justify="space-between" align="flex-start">
        <Box>
          <Title order={3} size="h4">{payload.person.name}</Title>
          <Text size="xs" c="dimmed">{imageRecords.length} image(s) | {payload.person.person_id}</Text>
        </Box>
        <Button variant="light" leftSection={<IconArrowLeft size={16} />} onClick={onBack}>Back</Button>
      </Group>
      <Grid className="people-gallery-grid">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Stack className="library-image-stack">
            <Box className="library-selected-slot">
              {selectedImage ? (
                <ImageFrame variant="librarySelected">
                  <Image src={mediaUrl(selectedImage)} alt={payload.person.name} fit="contain" h="100%" />
                </ImageFrame>
              ) : (
                <Paper withBorder radius="md" className="library-empty-selected">
                  <Text size="sm" c="dimmed">Select a photo</Text>
                </Paper>
              )}
            </Box>
            {imageRecords.length ? (
              <ScrollArea type="auto" offsetScrollbars className="library-thumb-strip">
                <Group wrap="nowrap" gap="sm" pb="xs">
                  {imageRecords.map((record) => (
                    <Card key={record.embeddingId} withBorder p={4} miw={128} w={128} component="button" className="mantine-click-card" data-selected={selectedImage === record.path} onClick={() => onImage(record.path)}>
                      <Image src={mediaUrl(record.path)} alt={payload.person.name} fit="cover" h={96} radius="sm" />
                    </Card>
                  ))}
                </Group>
              </ScrollArea>
            ) : <EmptyCard text="No images saved for this person." />}
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card withBorder radius="md">
            {mode === "changes" ? (
              <PeopleChangesPanel payload={payload} profile={profile} onBack={() => setMode("info")} />
            ) : mode === "edit" ? (
              <form onSubmit={saveEdit}>
                <Stack>
                  <Group justify="space-between" align="flex-start">
                    <Box>
                      <Text fw={700}>Edit Details</Text>
                      <Text size="xs" c="dimmed">Editor name is asked before saving.</Text>
                    </Box>
                    <Group gap="xs">
                      <Button size="xs" type="submit">Save</Button>
                      <Button size="xs" variant="light" type="button" onClick={() => setMode("info")}>Cancel</Button>
                    </Group>
                  </Group>
                  <PeopleEditableFields values={editValues} onChange={updateEditValue} />
                </Stack>
              </form>
            ) : (
              <Stack>
                <Group justify="space-between" align="flex-start">
                  <Box>
                    <Text fw={700}>Info</Text>
                    <Text size="xs" c="dimmed">{selectedRecord ? selectedRecord.embeddingId : payload.person.person_id}</Text>
                  </Box>
                  <Group gap="xs">
                    <Button size="xs" variant="light" onClick={() => setMode("changes")}>Changes</Button>
                    <Button size="xs" onClick={() => setMode("edit")}>Edit</Button>
                  </Group>
                </Group>
                <PeopleInfoFields profile={profile} details={selectedDetails} />
              </Stack>
            )}
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}

function PeopleEditableFields({ values, onChange }) {
  return (
    <SimpleGrid cols={{ base: 1, sm: 2 }}>
      <TextInput required label="Rank" value={values.rank} onChange={(event) => onChange("rank", event.target.value)} />
      <TextInput required label="Name" value={values.name} onChange={(event) => onChange("name", event.target.value)} />
      <TextInput required label="Country" value={values.country} onChange={(event) => onChange("country", event.target.value)} />
      <Select required label="Importance (Strat pt of view)" data={NEW_PERSON_IMPORTANCE_OPTIONS} value={values.importance} onChange={(value) => onChange("importance", value)} />
    </SimpleGrid>
  );
}

function PeopleInfoFields({ profile, details }) {
  return (
    <Stack>
      <Badge size="lg" variant="light">{profile.scopeLabel}</Badge>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <InfoLine label="Rank" value={profile.rank} />
        <InfoLine label="Name" value={profile.name} />
        <InfoLine label="Country" value={profile.country} />
        <InfoLine label="Importance" value={profile.importance} />
      </SimpleGrid>
      <Card withBorder radius="md">
        <Text fw={700} mb="sm">Seen At</Text>
        <SeenAtList details={details} />
      </Card>
    </Stack>
  );
}

function PeopleChangesPanel({ payload, profile, onBack }) {
  const changes = payload.changes || [];
  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <Box>
          <Text fw={700}>Changes</Text>
          <Text size="xs" c="dimmed">Latest changes first</Text>
        </Box>
        <Button size="xs" variant="light" leftSection={<IconArrowLeft size={14} />} onClick={onBack}>Back</Button>
      </Group>
      <PeopleInfoFields profile={profile} details={payload.details || []} />
      {changes.length ? changes.map((change) => (
        <Card key={change.change_id} withBorder radius="md">
          <Text size="xs" c="dimmed" mb="xs">{change.created_at}</Text>
          <Stack gap={6}>
            <ChangeLine label="Rank" from={change.previous_rank} to={change.new_rank} editor={change.editor_name} />
            <ChangeLine label="Name" from={change.previous_name} to={change.new_name} editor={change.editor_name} />
            <ChangeLine label="Country" from={change.previous_country} to={change.new_country} editor={change.editor_name} />
            <ChangeLine label="Importance (Strat pt of view)" from={change.previous_importance} to={change.new_importance} editor={change.editor_name} />
          </Stack>
        </Card>
      )) : <EmptyCard text="No changes recorded yet." />}
    </Stack>
  );
}

function InfoLine({ label, value }) {
  return (
    <Paper withBorder radius="md" p="sm">
      <Text size="xs" c="dimmed" fw={700}>{label}</Text>
      <Text fw={700}>{value || "-"}</Text>
    </Paper>
  );
}

function ChangeLine({ label, from, to, editor }) {
  if ((from || "") === (to || "")) return null;
  return (
    <Text size="sm">
      <Text span fw={700}>{label}: </Text>{from || "-"} -&gt; {to || "-"} <Text span c="dimmed">(By {editor || "-"})</Text>
    </Text>
  );
}

function SeenAtList({ details }) {
  const items = (details || []).filter((detail) => detail.place_seen || detail.date || detail.time || detail.event_occasion || detail.added_by);
  if (!items.length) return <Text size="sm" c="dimmed">No seen-at details saved.</Text>;
  return (
    <Stack gap="xs">
      {items.map((detail) => (
        <Paper key={detail.detail_id} withBorder radius="md" p="sm" bg="gray.0">
          <Text fw={700}>{detail.place_seen || "-"}</Text>
          <Text size="xs" c="dimmed">
            [AT] {formatSeenDateTime(detail)} | [Event] {detail.event_occasion || "-"} | [Added by] - {detail.added_by || "-"}
          </Text>
        </Paper>
      ))}
    </Stack>
  );
}
