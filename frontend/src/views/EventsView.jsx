import { useState } from "react";
import { Badge, Box, Button, Card, Group, Image, Select, SimpleGrid, Stack, Text, TextInput, Title } from "@mantine/core";
import { mediaUrl } from "../utils.js";

const CONTEXT_OPTIONS = [
  { value: "ordinary", label: "Ordinary / small" },
  { value: "public", label: "Public / group" },
  { value: "unknown", label: "Unknown" },
];

export function EventsView({ page, detail, people = [], onQuery, onOpen, onClose }) {
  const [filters, setFilters] = useState({ search: "", date_from: "", date_to: "", location: "", context: "", participant_id: "", mentioned_person_id: "" });
  const [pageCursors, setPageCursors] = useState([""]);
  const personOptions = people.map((person) => ({ value: person.person_id, label: person.name }));
  const apply = async (nextFilters) => {
    setPageCursors([""]);
    await onQuery(nextFilters);
  };
  const update = (field, value) => setFilters((current) => ({ ...current, [field]: value || "" }));
  const next = async () => {
    const cursor = page?.next_cursor;
    if (!cursor) return;
    await onQuery({ ...filters, cursor });
    setPageCursors((current) => [...current, cursor]);
  };
  const previous = async () => {
    if (pageCursors.length < 2) return;
    const remaining = pageCursors.slice(0, -1);
    await onQuery({ ...filters, cursor: remaining.at(-1) });
    setPageCursors(remaining);
  };
  if (detail) return (
    <Stack gap="md">
      <Group justify="space-between"><Title order={2}>Event details</Title><Button variant="default" onClick={onClose}>Back to Events</Button></Group>
      <Card withBorder>
        <Title order={3}>{detail.occasion || "Unnamed Event"}</Title>
        <Text>{eventDateTime(detail)} · {detail.location || "Location unknown"}</Text>
        <Badge mt="sm" variant="light">{contextLabel(detail.context)}</Badge>
        <Text mt="md" fw={700}>Participants</Text>
        <Text>{detail.participants?.map((person) => person.name).join(", ") || "None recorded"}</Text>
        <Text mt="md" fw={700}>Event Note</Text>
        <Text style={{ whiteSpace: "pre-wrap" }}>{detail.event_notes || "No Event Note"}</Text>
        <Text mt="xs" size="sm">Selected mentions: {detail.mentioned_people?.map((person) => person.name).join(", ") || "None"}</Text>
        <Text mt="md" fw={700}>Sighting Notes</Text>
        {(detail.sighting_notes || []).length ? detail.sighting_notes.map((note, index) => (
          <Text key={`${note.person_id}-${index}`} size="sm" style={{ whiteSpace: "pre-wrap" }}>{note.content}</Text>
        )) : <Text size="sm" c="dimmed">None recorded</Text>}
      </Card>
      <Title order={4}>Supporting media ({detail.media?.length || 0})</Title>
      <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
        {(detail.media || []).map((item) => <Card key={item.media_id} withBorder>{item.media_path ? <Image src={mediaUrl(item.media_path)} alt="Event media" fit="contain" /> : <Text>Media unavailable</Text>}</Card>)}
      </SimpleGrid>
    </Stack>
  );
  return (
    <Stack gap="md">
      <Box><Title order={2}>Events</Title><Text size="sm" c="dimmed">Read-only history of finalized Encounters. Mentions are shown separately from attendance.</Text></Box>
      <Card withBorder>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
          <TextInput label="Event or location" value={filters.search} onChange={(event) => update("search", event.currentTarget.value)} />
          <TextInput label="From date" type="date" value={filters.date_from} onChange={(event) => update("date_from", event.currentTarget.value)} />
          <TextInput label="To date" type="date" value={filters.date_to} onChange={(event) => update("date_to", event.currentTarget.value)} />
          <TextInput label="Location" value={filters.location} onChange={(event) => update("location", event.currentTarget.value)} />
          <Select clearable label="Context" data={CONTEXT_OPTIONS} value={filters.context || null} onChange={(value) => update("context", value)} />
          <Select clearable searchable label="Participant" data={personOptions} value={filters.participant_id || null} onChange={(value) => update("participant_id", value)} />
          <Select clearable searchable label="Mentioned Person" data={personOptions} value={filters.mentioned_person_id || null} onChange={(value) => update("mentioned_person_id", value)} />
        </SimpleGrid>
        <Group mt="md"><Button onClick={() => apply(filters)}>Search Events</Button><Button variant="default" onClick={() => { const empty = { search: "", date_from: "", date_to: "", location: "", context: "", participant_id: "", mentioned_person_id: "" }; setFilters(empty); apply(empty); }}>Clear</Button></Group>
      </Card>
      {(page?.events || []).map((event) => (
        <Card key={event.observation_id} component="button" withBorder onClick={() => onOpen(event.observation_id)} style={{ textAlign: "left" }}>
          <Group justify="space-between"><Text fw={800}>{event.occasion || "Unnamed Event"}</Text><Badge variant="light">{contextLabel(event.context)}</Badge></Group>
          <Text size="sm">{eventDateTime(event)} · {event.location || "Location unknown"}</Text>
          <Text size="sm">Participants: {event.participants?.map((person) => person.name).join(", ") || "None recorded"}</Text>
          {!!event.mentioned_people?.length && <Text size="sm">Mentioned: {event.mentioned_people.map((person) => person.name).join(", ")}</Text>}
          <Text size="xs" c="dimmed">{event.media_count} supporting media item(s)</Text>
        </Card>
      ))}
      {!page?.events?.length && <Text c="dimmed">No Events match these filters.</Text>}
      <Group><Button variant="default" disabled={pageCursors.length < 2} onClick={previous}>Previous</Button><Button variant="default" disabled={!page?.next_cursor} onClick={next}>Next</Button></Group>
    </Stack>
  );
}

export function eventDateTime(event) {
  const date = event.observed_at?.slice(0, 10) || "Date unknown";
  if (event.time_precision === "unknown") return `${date} · Time unknown`;
  if (event.time_precision === "approximate") return `${date} · About ${event.start_time || "an unknown time"}`;
  return `${date}${event.start_time ? ` · ${event.start_time}${event.end_time ? `–${event.end_time}` : ""}` : ""}`;
}

function contextLabel(context) {
  return CONTEXT_OPTIONS.find((item) => item.value === context)?.label || "Unknown";
}
