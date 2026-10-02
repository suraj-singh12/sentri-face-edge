import { useRef, useState } from "react";
import { Badge, Box, Button, Card, FileButton, Group, Image, Select, SimpleGrid, Stack, Text, TextInput, Title, UnstyledButton } from "@mantine/core";
import { mediaUrl } from "../utils.js";

import { EncounterDetailsModal } from "../components/EncounterDetailsModal.jsx";
import { EncounterManagementModal } from "../components/EncounterManagementModal.jsx";

const CONTEXT_OPTIONS = [
  { value: "ordinary", label: "Ordinary / small" },
  { value: "public", label: "Public / group" },
  { value: "unknown", label: "Unknown" },
];

export function EventsView({ page, detail, people = [], onQuery, onOpen, onClose, canAttach = false, canCorrect = false, onCorrect, onAttach }) {
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
  if (detail) return <EncounterDetail key={detail.observation_id} detail={detail} people={people} onClose={onClose} canAttach={canAttach} canCorrect={canCorrect} onCorrect={onCorrect} onAttach={onAttach} />;
  return (
    <Stack gap="md">
      <Box><Title order={2}>Events</Title><Text size="sm" c="dimmed">Finalized Encounters, newest first. Mentions are shown separately from attendance.</Text></Box>
      <Box>
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
      </Box>
      <Stack gap={0}>
      {(page?.events || []).map((event) => (
        <UnstyledButton key={event.observation_id} onClick={() => onOpen(event.observation_id)} className="encounter-list-row">
          <Group justify="space-between"><Text fw={800}>{event.occasion || "Unnamed Event"}</Text><Badge variant="light">{contextLabel(event.context)}</Badge></Group>
          <Text size="sm">{eventDateTime(event)} · {event.location || "Location unknown"}</Text>
          <Text size="sm">Participants: {event.participants?.map((person) => person.name).join(", ") || "None recorded"}</Text>
          {!!event.mentioned_people?.length && <Text size="sm">Mentioned: {event.mentioned_people.map((person) => person.name).join(", ")}</Text>}
          <Text size="xs" c="dimmed">{event.participant_ids?.length || 0} participants · {event.media_count} media · {event.mentioned_person_ids?.length || 0} mentions</Text>
        </UnstyledButton>
      ))}
      </Stack>
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

function EncounterDetail({ detail, people, onClose, canAttach, canCorrect, onCorrect, onAttach }) {
  const [mode, setMode] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [values, setValues] = useState(null);
  const operationRef = useRef(null);
  const names = Object.fromEntries([...people, ...(detail.participants || []), ...(detail.mentioned_people || []), ...(detail.historical_people || [])].map((p) => [p.person_id, p.name]));
  const open = (next) => {
    setMode(next); setError(""); operationRef.current = null;
    if (next === "metadata") {
      const event = detail.event_details;
      setValues({ date: event.date, time: event.time, endTime: event.end_time, timePrecision: event.time_precision,
        placeSeen: event.place_seen, eventOccasion: event.event_occasion, eventContext: event.event_context,
        eventNotes: event.event_notes, eventMentionedPersonIds: event.event_mentioned_person_ids });
    }
  };
  const save = async (changes) => {
    const fingerprint = JSON.stringify(changes);
    if (!operationRef.current || operationRef.current.fingerprint !== fingerprint) operationRef.current = { fingerprint, id: crypto.randomUUID() };
    await onCorrect(detail, { ...changes, operation_id: operationRef.current.id });
  };
  const saveMetadata = async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await save({ event_details: { date: values.date, time: values.timePrecision === "unknown" ? "" : values.time,
        end_time: values.timePrecision === "exact" ? values.endTime : "", time_precision: values.timePrecision,
        place_seen: values.placeSeen, event_occasion: values.eventOccasion, event_context: values.eventContext,
        event_notes: values.eventNotes, event_mentioned_person_ids: values.eventMentionedPersonIds } });
      setMode(null);
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  };
  return <Stack gap="md" className="encounter-detail">
    <Group justify="space-between"><Title order={2}>{detail.occasion || "Unnamed Encounter"}</Title><Button variant="default" onClick={onClose}>Back to Events</Button></Group>
    <Group gap="sm"><Text>{eventDateTime(detail)} · {detail.location || "Location unknown"}</Text><Badge variant="light">{contextLabel(detail.context)}</Badge></Group>
    <Group gap="xs">
      {canAttach && <FileButton multiple accept="image/*" onChange={async (files) => { if (!files?.length) return; setBusy(true); setError(""); try { await onAttach(detail, files); } catch (failure) { setError(failure.message); } finally { setBusy(false); } }}>{(props) => <Button {...props} disabled={busy}>Attach Media</Button>}</FileButton>}
      {canCorrect && <><Button variant="default" onClick={() => open("metadata")}>Correct Encounter</Button><Button variant="default" onClick={() => open("participants")}>Correct Participants</Button><Button variant="default" onClick={() => open("relations")}>Correct Relations</Button></>}
    </Group>
    {error && !mode && <Text c="red" role="alert">{error}</Text>}
    <Box><Text fw={700}>Participants ({detail.participants?.length || 0})</Text><Group gap="xs">{(detail.participants || []).map((p) => <Text key={p.person_id} size="sm">{p.name}{p.lifecycle_status && p.lifecycle_status !== "ACTIVE" ? ` (${p.lifecycle_status.toLowerCase()})` : ""}</Text>)}</Group></Box>
    <Box><Text fw={700}>Event Note</Text><Text style={{ whiteSpace: "pre-wrap" }}>{detail.event_notes || "No Event Note"}</Text><Text size="sm" c="dimmed">Selected mentions: {detail.mentioned_people?.map((p) => p.name).join(", ") || "None"}</Text></Box>
    <Box><Text fw={700}>Sighting Notes</Text>{detail.sighting_notes?.length ? detail.sighting_notes.map((note, index) => <Text key={index} size="sm">{names[note.person_id] || "Historical Person"}: {note.content}</Text>) : <Text size="sm" c="dimmed">None recorded</Text>}</Box>
    <Box><Text fw={700}>Relations</Text>{(detail.relations || []).map((r) => <Group key={`${r.first_person_id}:${r.second_person_id}`} justify="space-between" className="encounter-list-row"><Text size="sm">{names[r.first_person_id]} · {names[r.second_person_id]}</Text><Group gap="xs"><Badge color={r.disposition === "INCLUDE" ? "teal" : "gray"}>{r.disposition}</Badge><Text size="xs" c="dimmed">{r.support === "SHARED_FRAME" ? "Shared frame" : "Same Encounter only"}</Text></Group></Group>)}{!detail.relations?.length && <Text size="sm" c="dimmed">No explicit pair decisions recorded.</Text>}</Box>
    <Text fw={700}>All Encounter media ({detail.media?.length || 0})</Text>
    <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>{(detail.media || []).map((item) => <Box key={item.media_id}>{item.media_path ? <Image src={mediaUrl(item.media_path)} alt="Encounter media" fit="contain" mah={300} /> : <Text>Media unavailable</Text>}</Box>)}</SimpleGrid>
    <details><summary>Correction and provenance history</summary><Stack gap="xs" mt="sm">{(detail.history || []).map((entry) => <Box key={entry.operation_id} className="encounter-list-row"><Text size="xs" c="dimmed">{entry.created_at?.slice(0, 10)} · {entry.actor?.display_name || entry.actor?.username || "Operator"}</Text><Text size="sm">{historyDescription(entry, names)}</Text></Box>)}{detail.history_has_more && <Text size="xs">Showing the latest 100 operations.</Text>}</Stack></details>
    {mode === "metadata" && <EncounterDetailsModal opened correction values={values} people={[...people, ...(detail.mentioned_people || []).filter((p) => !people.some((candidate) => candidate.person_id === p.person_id))]} busy={busy} error={error} onChange={(field, value) => setValues((old) => ({ ...old, [field]: value }))} onClose={() => setMode(null)} onConfirm={saveMetadata} />}
    {(mode === "participants" || mode === "relations") && <EncounterManagementModal key={mode} detail={detail} people={people} mode={mode} onClose={() => setMode(null)} onSave={save} />}
  </Stack>;
}

function historyDescription(entry, names) {
  const result = entry.result || {};
  if (entry.operation_type === "review.complete") return "Encounter review completed; media and identity decisions accepted.";
  if (entry.operation_type === "identity.observation.correct") return `Participant corrected: ${names[result.from_person_id] || "Historical Person"} → ${names[result.to_person_id] || "Historical Person"}`;
  if (entry.operation_type !== "encounter.correct") return entry.operation_type.replaceAll(".", " ");
  const before = result.historical_value || {};
  const after = result.effective_value || {};
  const changes = ["occasion", "observed_at", "start_time", "end_time", "time_precision", "location", "context", "event_notes"].filter((field) => before[field] !== after[field]).map((field) => `${({ occasion: "Occasion", observed_at: "Date/time", start_time: "Start time", end_time: "End time", time_precision: "Time precision", location: "Location", context: "Context", event_notes: "Event Note" })[field]}: ${before[field] || "Unknown"} → ${after[field] || "Unknown"}`);
  if (JSON.stringify(before.mentioned_person_ids) !== JSON.stringify(after.mentioned_person_ids)) changes.push("Selected Event Note mentions corrected");
  if (result.participant_correction) {
    const change = result.participant_correction;
    changes.push(`Participant ${change.action.toLowerCase()}: ${names[change.person_id] || "Historical Person"}${change.to_person_id ? ` → ${names[change.to_person_id] || "Historical Person"}` : ""}`);
  }
  for (const relation of result.effective_relations || []) {
    const previous = (result.historical_relations || []).find((r) => r.first_person_id === relation.first_person_id && r.second_person_id === relation.second_person_id);
    if (!previous || previous.disposition !== relation.disposition) changes.push(`${names[relation.first_person_id] || "Person"} · ${names[relation.second_person_id] || "Person"}: ${previous?.disposition || "Undecided"} → ${relation.disposition}`);
  }
  return changes.join("; ") || "Encounter interpretation reviewed";
}
