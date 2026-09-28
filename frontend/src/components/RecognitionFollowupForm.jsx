import { Button, Card, Group, Image, NumberInput, Paper, Select, SimpleGrid, Stack, Text, TextInput, Textarea, ThemeIcon } from "@mantine/core";
import {
  IconCalendar,
  IconCheck,
  IconInfoCircle,
  IconMapPin,
  IconRefresh,
  IconUser,
  IconUsers,
} from "@tabler/icons-react";

import { NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import { CountrySelect } from "./CountrySelect.jsx";
import { mediaUrl } from "../utils.js";

export function RecognitionFollowupForm({ values, people = [], confirmed, onChange, onSubmit, onClear, embedded = false, showAddedBy = false, addFaceOnly = false }) {
  if (addFaceOnly) return <Card withBorder radius="md" mt="md" p="sm"><form onSubmit={onSubmit}><Stack gap="sm"><Text fw={800}>Add Face to {values.name}</Text><Text size="sm" c="dimmed">This adds a reference face to the existing Person. It creates no Encounter or sighting.</Text><Button type="submit" disabled={confirmed}>Confirm Add Face</Button></Stack></form></Card>;
  const isNew = values.action === "new";
  const needsAddedBy = isNew || showAddedBy;
  const mentionQuery = activeMentionQuery(values.notes);
  const mentionSuggestions = mentionQuery.length < 3 ? [] : people.filter((person) => (
    person.person_id !== values.personId
    && !person.archived
    && [person.name, person.person_id, person.metadata?.rank, person.metadata?.country]
      .filter(Boolean)
      .some((value) => String(value).toLocaleLowerCase().includes(mentionQuery.toLocaleLowerCase()))
  )).slice(0, 6);
  const form = (
    <form onSubmit={onSubmit}>
      <Stack gap="xs">
        <Text fw={800}>{isNew ? "Add New Person Details" : "Existing Person Sighting"}</Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs" verticalSpacing="xs">
          {isNew && <TextInput required label="Rank" value={values.rank} onChange={(event) => onChange("rank", event.target.value)} />}
          {isNew && <TextInput required label="Name" value={values.name} onChange={(event) => onChange("name", event.target.value)} />}
          {isNew && <CountrySelect value={values.country} onChange={(value) => onChange("country", value)} />}
          {isNew && <Select required label="Tag" data={NEW_PERSON_IMPORTANCE_OPTIONS} value={values.importance} onChange={(value) => onChange("importance", value)} />}
          <NumberInput required min={0} step={1} label="With how many individuals" leftSection={<IconUsers size={18} />} placeholder="Select count" value={values.individualCount} onChange={(value) => onChange("individualCount", value)} />
          {needsAddedBy && <TextInput required label="Added by" placeholder="Your Name" value={values.addedBy} onChange={(event) => onChange("addedBy", event.target.value)} />}
        </SimpleGrid>
        <Paper withBorder p="xs"><Text size="sm" fw={700}>Inherited Encounter</Text><Text size="sm">{values.eventOccasion || "Unknown occasion"} · {values.date || "Unknown date"} · {values.timePrecision === "unknown" ? "Unknown time" : `${values.time || ""}${values.endTime ? `–${values.endTime}` : ""}${values.timePrecision === "approximate" ? " (approximate)" : ""}`} · {values.placeSeen || "Unknown location"} · {values.eventContext || "unknown"}</Text></Paper>
        <Textarea
          autosize
          minRows={2}
          label="Sighting Notes"
          description="Saved with this person in this Encounter"
          value={values.notes || ""}
          onChange={(event) => onChange("notes", event.currentTarget.value)}
        />
        {mentionSuggestions.length > 0 && (
          <Stack gap={4} className="people-note-mention-suggestions">
            {mentionSuggestions.map((person) => (
              <Paper
                key={person.person_id}
                withBorder
                radius="md"
                p="xs"
                component="button"
                type="button"
                className="mantine-click-card"
                onClick={() => {
                  onChange("notes", replaceMentionQuery(values.notes, person.name));
                  onChange("mentionedPersonIds", [...new Set([...(values.mentionedPersonIds || []), person.person_id])]);
                }}
              >
                <Group gap="sm" wrap="nowrap">
                  {person.representative_image
                    ? <Image src={mediaUrl(person.representative_image)} alt={person.name} h={36} w={36} radius="xl" fit="cover" />
                    : <ThemeIcon size={36} radius="xl" variant="light" color="gray"><IconUser size={19} /></ThemeIcon>}
                  <Stack gap={0} align="flex-start">
                    <Text size="sm" fw={700}>{person.name}</Text>
                    <Text size="xs" c="dimmed">ID {String(person.person_id).slice(0, 8)} · {person.metadata?.rank || "No role"}</Text>
                  </Stack>
                </Group>
              </Paper>
            ))}
          </Stack>
        )}
        {(values.poorFaces || []).map((face, index) => (
          <Paper key={face.id} withBorder p="xs">
            <Text size="sm" fw={700}>Face {index + 1} has low quality</Text>
            <Text size="xs" c="orange">Low-quality face samples may reduce recognition accuracy. Its media and face remain historical proof regardless of this choice.</Text>
            <Select
              label="Accept this low-quality face for recognition use?"
              data={[{ value: "PROOF_ONLY", label: "No — proof only" }, { value: "POOR_ACCEPTED", label: "Yes — accept for recognition" }]}
              value={values.poorFaceChoices?.[face.id] || "PROOF_ONLY"}
              onChange={(value) => onChange("poorFaceChoices", { ...(values.poorFaceChoices || {}), [face.id]: value })}
            />
          </Paper>
        ))}
        <Paper withBorder radius="md" p="xs" className="followup-help">
          <Group gap="sm">
            <ThemeIcon variant="light" color="blue" size="sm"><IconInfoCircle size={16} /></ThemeIcon>
            <Text size="sm" c="dimmed">This information helps you keep a context of when and where this person was seen.</Text>
          </Group>
        </Paper>
        <Group justify="center" gap="md">
          <Button type="submit" leftSection={<IconCheck size={18} />} disabled={confirmed}>Confirm</Button>
          <Button variant="default" type="button" leftSection={<IconRefresh size={18} />} onClick={onClear}>Clear</Button>
        </Group>
      </Stack>
    </form>
  );
  return embedded ? form : <Card withBorder radius="md" mt="md" p="sm" className="followup-card">{form}</Card>;
}

export function activeMentionQuery(notes) {
  const match = String(notes || "").match(/(?:^|\s)@([^@,\n]*)$/);
  return match ? match[1].trim() : "";
}

export function replaceMentionQuery(notes, name) {
  return String(notes || "").replace(/(^|\s)@([^@,\n]*)$/, (_, prefix) => `${prefix}@${name}, `);
}
