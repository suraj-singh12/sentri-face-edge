import { useEffect, useState } from "react";
import { Button, Group, Modal, MultiSelect, Paper, Select, Stack, Text, TextInput, Textarea } from "@mantine/core";

import { SavedLocationInput } from "./SavedLocationInput.jsx";

import { activeMentionQuery, replaceMentionQuery } from "./RecognitionFollowupForm.jsx";
import { requiredFieldErrors } from "../utils.js";

export function encounterDetailsErrors(values, correction = false) {
  if (correction) return {};
  const precision = values?.timePrecision || "unknown";
  return requiredFieldErrors(values, [
    ["eventOccasion", "Event / occasion"], ["date", "Date"],
    ...(precision !== "unknown" ? [["time", precision === "approximate" ? "Approximate time" : "Start time"]] : []),
    ...(precision === "exact" ? [["endTime", "End time"]] : []),
    ["placeSeen", "Location"],
  ]);
}

export function EncounterDetailsModal({ opened, values, people = [], onChange: change, onConfirm, onClose, correction = false, busy = false, error = "", onReload }) {
  const [errors, setErrors] = useState({});
  useEffect(() => { if (!opened) setErrors({}); }, [opened]);
  if (!values) return null;
  const onChange = (field, value) => { setErrors((current) => ({ ...current, [field]: undefined })); change(field, value); };
  const submit = (event) => {
    const missing = encounterDetailsErrors(values, correction);
    setErrors(missing);
    if (Object.keys(missing).length) { event.preventDefault(); return; }
    onConfirm(event);
  };
  const query = activeMentionQuery(values.eventNotes);
  const suggestions = query.length < 3 ? [] : people.filter((person) => (
    !person.archived && [person.name, person.person_id, person.metadata?.rank]
      .filter(Boolean).some((item) => String(item).toLocaleLowerCase().includes(query.toLocaleLowerCase()))
  )).slice(0, 6);
  return (
    <Modal opened={opened} onClose={() => !busy && onClose?.()} withCloseButton={Boolean(onClose)} closeOnEscape={Boolean(onClose) && !busy} closeOnClickOutside={false} title={correction ? "Correct Event" : "Event details"} centered size="lg">
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <Text size="sm" c="dimmed">{correction ? "Correct the current Event details. Historical values and selected mentions remain in correction history." : "Confirm these details once for this Event. Person decisions follow on the page."}</Text>
          <TextInput required={!correction} label="Event / occasion" error={errors.eventOccasion} value={values.eventOccasion || ""} onChange={(event) => onChange("eventOccasion", event.currentTarget.value)} />
          <TextInput required={!correction} type="date" label="Date" error={errors.date} value={values.date || ""} onChange={(event) => onChange("date", event.currentTarget.value)} />
          <Select label="Time" data={[{ value: "exact", label: "Start and end" }, { value: "approximate", label: "Approximate" }, { value: "unknown", label: "Unknown" }]} value={values.timePrecision || "unknown"} onChange={(value) => onChange("timePrecision", value)} />
          {values.timePrecision !== "unknown" && <TextInput required={!correction} type="time" label={values.timePrecision === "approximate" ? "Approximate time" : "Start time"} error={errors.time} value={values.time || ""} onChange={(event) => onChange("time", event.currentTarget.value)} />}
          {values.timePrecision === "exact" && <TextInput required={!correction} type="time" label="End time" error={errors.endTime} min={values.time || undefined} value={values.endTime || ""} onChange={(event) => onChange("endTime", event.currentTarget.value)} />}
          <SavedLocationInput required={!correction} error={errors.placeSeen} value={values.placeSeen || ""} onChange={(value) => onChange("placeSeen", value)} />
          <Select label="Context" data={[{ value: "ordinary", label: "Ordinary / small" }, { value: "public", label: "Public / group" }, { value: "unknown", label: "Unknown" }]} value={values.eventContext || "unknown"} onChange={(value) => onChange("eventContext", value)} />
          <Textarea label="Event Notes" description="Type @ and three characters, then select a Person to record an explicit mention." value={values.eventNotes || ""} onChange={(event) => onChange("eventNotes", event.currentTarget.value)} />
          {suggestions.map((person) => <Paper key={person.person_id} component="button" type="button" withBorder p="xs" onClick={() => {
            onChange("eventNotes", replaceMentionQuery(values.eventNotes, person.name));
            onChange("eventMentionedPersonIds", [...new Set([...(values.eventMentionedPersonIds || []), person.person_id])]);
          }}>{person.name}{person.metadata?.rank ? ` · ${person.metadata.rank}` : ""}</Paper>)}
          {correction && <MultiSelect searchable label="Selected Event Note mentions" description="Selected Persons are mentioned, not automatically present or associated." data={people.map((person) => ({ value: person.person_id, label: person.name }))} value={values.eventMentionedPersonIds || []} onChange={(value) => onChange("eventMentionedPersonIds", value)} />}
          {error && (
            <Group justify="space-between" align="center" wrap="nowrap">
              <Text c="red" role="alert">{error}{/stale|changed|reload/i.test(error) ? " Reloading discards this unsaved correction." : ""}</Text>
              {/stale|changed|reload/i.test(error) && onReload && <Button type="button" size="compact-xs" variant="default" disabled={busy} onClick={onReload}>Reload current Event</Button>}
            </Group>
          )}
          <Group justify="flex-end">{onClose && <Button disabled={busy} variant="default" onClick={onClose}>Cancel</Button>}<Button loading={busy} type="submit">{correction ? "Save correction" : "Confirm Event"}</Button></Group>
        </Stack>
      </form>
    </Modal>
  );
}
