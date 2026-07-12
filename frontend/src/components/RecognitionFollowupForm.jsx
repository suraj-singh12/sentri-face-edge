import { Button, Card, Group, NumberInput, Paper, Select, SimpleGrid, Stack, Text, TextInput, ThemeIcon } from "@mantine/core";
import {
  IconCalendar,
  IconCheck,
  IconInfoCircle,
  IconMapPin,
  IconRefresh,
  IconUsers,
} from "@tabler/icons-react";

import { NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";

export function RecognitionFollowupForm({ values, confirmed, onChange, onSubmit, onClear, embedded = false, showAddedBy = false }) {
  const isNew = values.action === "new";
  const needsAddedBy = isNew || showAddedBy;
  const form = (
    <form onSubmit={onSubmit}>
      <Stack gap="md">
        <Text fw={800}>{isNew ? "Add New Person Details" : "Add Event Details (for accepted person)"}</Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          {isNew && <TextInput required label="Rank" value={values.rank} onChange={(event) => onChange("rank", event.target.value)} />}
          {isNew && <TextInput required label="Name" value={values.name} onChange={(event) => onChange("name", event.target.value)} />}
          {isNew && <TextInput required label="Country" value={values.country} onChange={(event) => onChange("country", event.target.value)} />}
          {isNew && <Select required label="Importance (Strat pt of view)" data={NEW_PERSON_IMPORTANCE_OPTIONS} value={values.importance} onChange={(value) => onChange("importance", value)} />}
          <TextInput required label="Date" type="date" leftSection={<IconCalendar size={18} />} value={values.date} onChange={(event) => onChange("date", event.target.value)} />
          <TextInput required label="Time" type="time" leftSection={<IconCalendar size={18} />} value={values.time} onChange={(event) => onChange("time", event.target.value)} />
          <TextInput required label="Place Seen" leftSection={<IconMapPin size={18} />} placeholder="e.g., Office, Gate A, Reception, Building C" value={values.placeSeen} onChange={(event) => onChange("placeSeen", event.target.value)} />
          <NumberInput required min={0} step={1} label="With how many individuals" leftSection={<IconUsers size={18} />} placeholder="Select count" value={values.individualCount} onChange={(value) => onChange("individualCount", value)} />
          <TextInput required label="Event/Occasion" leftSection={<IconCalendar size={18} />} placeholder="e.g., Meeting, Visit, Delivery, Staff Interaction, Security Check" value={values.eventOccasion} onChange={(event) => onChange("eventOccasion", event.target.value)} />
          {needsAddedBy && <TextInput required label="Added by" placeholder="Your Name" value={values.addedBy} onChange={(event) => onChange("addedBy", event.target.value)} />}
        </SimpleGrid>
        <Paper withBorder radius="md" p="sm" className="followup-help">
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
  return embedded ? form : <Card withBorder radius="md" mt="md" className="followup-card">{form}</Card>;
}
