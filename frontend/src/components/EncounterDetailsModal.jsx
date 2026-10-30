import { Button, Group, Modal, MultiSelect, Paper, Select, Stack, Text, TextInput, Textarea } from "@mantine/core";

import { SavedLocationInput } from "./SavedLocationInput.jsx";

import { activeMentionQuery, replaceMentionQuery } from "./RecognitionFollowupForm.jsx";

export function EncounterDetailsModal({ opened, values, people = [], onChange, onConfirm, onClose, correction = false, busy = false, error = "" }) {
  if (!values) return null;
  const query = activeMentionQuery(values.eventNotes);
  const suggestions = query.length < 3 ? [] : people.filter((person) => (
    !person.archived && [person.name, person.person_id, person.metadata?.rank]
      .filter(Boolean).some((item) => String(item).toLocaleLowerCase().includes(query.toLocaleLowerCase()))
  )).slice(0, 6);
  return (
    <Modal opened={opened} onClose={() => !busy && onClose?.()} withCloseButton={Boolean(onClose)} closeOnEscape={Boolean(onClose) && !busy} closeOnClickOutside={false} title={correction ? "Correct Encounter" : "Event details"} centered size="lg">
      <form onSubmit={onConfirm}>
        <Stack gap="sm">
          <Text size="sm" c="dimmed">{correction ? "Correct the current Event details. Historical values and selected mentions remain in correction history." : "Confirm these details once for this Encounter. Person decisions follow on the page."}</Text>
          <TextInput required={!correction} label="Event / occasion" value={values.eventOccasion || ""} onChange={(event) => onChange("eventOccasion", event.currentTarget.value)} />
          <TextInput required={!correction} type="date" label="Date" value={values.date || ""} onChange={(event) => onChange("date", event.currentTarget.value)} />
          <Select label="Time" data={[{ value: "exact", label: "Start and end" }, { value: "approximate", label: "Approximate" }, { value: "unknown", label: "Unknown" }]} value={values.timePrecision || "unknown"} onChange={(value) => onChange("timePrecision", value)} />
          {values.timePrecision !== "unknown" && <TextInput required={!correction} type="time" label={values.timePrecision === "approximate" ? "Approximate time" : "Start time"} value={values.time || ""} onChange={(event) => onChange("time", event.currentTarget.value)} />}
          {values.timePrecision === "exact" && <TextInput required={!correction} type="time" label="End time" min={values.time || undefined} value={values.endTime || ""} onChange={(event) => onChange("endTime", event.currentTarget.value)} />}
          <SavedLocationInput required={!correction} value={values.placeSeen || ""} onChange={(value) => onChange("placeSeen", value)} />
          <Select label="Context" data={[{ value: "ordinary", label: "Ordinary / small" }, { value: "public", label: "Public / group" }, { value: "unknown", label: "Unknown" }]} value={values.eventContext || "unknown"} onChange={(value) => onChange("eventContext", value)} />
          <Textarea label="Event Notes" description="Type @ and three characters, then select a Person to record an explicit mention." value={values.eventNotes || ""} onChange={(event) => onChange("eventNotes", event.currentTarget.value)} />
          {suggestions.map((person) => <Paper key={person.person_id} component="button" type="button" withBorder p="xs" onClick={() => {
            onChange("eventNotes", replaceMentionQuery(values.eventNotes, person.name));
            onChange("eventMentionedPersonIds", [...new Set([...(values.eventMentionedPersonIds || []), person.person_id])]);
          }}>{person.name}{person.metadata?.rank ? ` · ${person.metadata.rank}` : ""}</Paper>)}
          {correction && <MultiSelect searchable label="Selected Event Note mentions" description="Selected Persons are mentioned, not automatically present or associated." data={people.map((person) => ({ value: person.person_id, label: person.name }))} value={values.eventMentionedPersonIds || []} onChange={(value) => onChange("eventMentionedPersonIds", value)} />}
          {error && <Text c="red" role="alert">{error}</Text>}
          <Group justify="flex-end">{onClose && <Button disabled={busy} variant="default" onClick={onClose}>Cancel</Button>}<Button loading={busy} type="submit">{correction ? "Save correction" : "Confirm Event"}</Button></Group>
        </Stack>
      </form>
    </Modal>
  );
}
