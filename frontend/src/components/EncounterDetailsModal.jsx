import { Button, Group, Modal, Paper, Select, Stack, Text, TextInput, Textarea } from "@mantine/core";

import { activeMentionQuery, replaceMentionQuery } from "./RecognitionFollowupForm.jsx";

export function EncounterDetailsModal({ opened, values, people = [], onChange, onConfirm }) {
  if (!values) return null;
  const query = activeMentionQuery(values.eventNotes);
  const suggestions = query.length < 3 ? [] : people.filter((person) => (
    !person.archived && [person.name, person.person_id, person.metadata?.rank]
      .filter(Boolean).some((item) => String(item).toLocaleLowerCase().includes(query.toLocaleLowerCase()))
  )).slice(0, 6);
  return (
    <Modal opened={opened} onClose={() => {}} withCloseButton={false} closeOnEscape={false} closeOnClickOutside={false} title="Event details" centered size="lg">
      <form onSubmit={onConfirm}>
        <Stack gap="sm">
          <Text size="sm" c="dimmed">Confirm these details once for this Encounter. Person decisions follow on the page.</Text>
          <TextInput required label="Event / occasion" value={values.eventOccasion || ""} onChange={(event) => onChange("eventOccasion", event.currentTarget.value)} />
          <TextInput required type="date" label="Date" value={values.date || ""} onChange={(event) => onChange("date", event.currentTarget.value)} />
          <Select label="Time" data={[{ value: "exact", label: "Start and end" }, { value: "approximate", label: "Approximate" }, { value: "unknown", label: "Unknown" }]} value={values.timePrecision || "unknown"} onChange={(value) => onChange("timePrecision", value)} />
          {values.timePrecision !== "unknown" && <TextInput required type="time" label={values.timePrecision === "approximate" ? "Approximate time" : "Start time"} value={values.time || ""} onChange={(event) => onChange("time", event.currentTarget.value)} />}
          {values.timePrecision === "exact" && <TextInput required type="time" label="End time" min={values.time || undefined} value={values.endTime || ""} onChange={(event) => onChange("endTime", event.currentTarget.value)} />}
          <TextInput required label="Location" value={values.placeSeen || ""} onChange={(event) => onChange("placeSeen", event.currentTarget.value)} />
          <Select label="Context" data={[{ value: "ordinary", label: "Ordinary / small" }, { value: "public", label: "Public / group" }, { value: "unknown", label: "Unknown" }]} value={values.eventContext || "unknown"} onChange={(value) => onChange("eventContext", value)} />
          <Textarea label="Event Notes" description="Type @ and three characters, then select a Person to record an explicit mention." value={values.eventNotes || ""} onChange={(event) => onChange("eventNotes", event.currentTarget.value)} />
          {suggestions.map((person) => <Paper key={person.person_id} component="button" type="button" withBorder p="xs" onClick={() => {
            onChange("eventNotes", replaceMentionQuery(values.eventNotes, person.name));
            onChange("eventMentionedPersonIds", [...new Set([...(values.eventMentionedPersonIds || []), person.person_id])]);
          }}>{person.name}{person.metadata?.rank ? ` · ${person.metadata.rank}` : ""}</Paper>)}
          <Group justify="flex-end"><Button type="submit">Confirm Event</Button></Group>
        </Stack>
      </form>
    </Modal>
  );
}
