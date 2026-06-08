import { Button, Card, Group, NumberInput, Select, SimpleGrid, Stack, TextInput } from "@mantine/core";

import { NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";

export function RecognitionFollowupForm({ values, confirmed, onChange, onSubmit, onClear, embedded = false }) {
  const isNew = values.action === "new";
  const form = (
    <form onSubmit={onSubmit}>
      <Stack>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          {isNew && <TextInput required label="Rank" value={values.rank} onChange={(event) => onChange("rank", event.target.value)} />}
          {isNew && <TextInput required label="Name" value={values.name} onChange={(event) => onChange("name", event.target.value)} />}
          {isNew && <TextInput required label="Country" value={values.country} onChange={(event) => onChange("country", event.target.value)} />}
          {isNew && <Select required label="Importance (Strat pt of view)" data={NEW_PERSON_IMPORTANCE_OPTIONS} value={values.importance} onChange={(value) => onChange("importance", value)} />}
          <TextInput required label="Date" type="date" value={values.date} onChange={(event) => onChange("date", event.target.value)} />
          <TextInput required label="Time" type="time" value={values.time} onChange={(event) => onChange("time", event.target.value)} />
          <TextInput required label="Place Seen" value={values.placeSeen} onChange={(event) => onChange("placeSeen", event.target.value)} />
          <NumberInput required min={0} step={1} label="With how many indl" value={values.individualCount} onChange={(value) => onChange("individualCount", value)} />
          <TextInput required label="Event/Occasion" value={values.eventOccasion} onChange={(event) => onChange("eventOccasion", event.target.value)} />
          {isNew && <TextInput required label="Added by" placeholder="Your Name" value={values.addedBy} onChange={(event) => onChange("addedBy", event.target.value)} />}
        </SimpleGrid>
        <Group justify="center">
          <Button type="submit" disabled={confirmed}>Confirm</Button>
          <Button color="red" variant="light" type="button" onClick={onClear}>Clear</Button>
        </Group>
      </Stack>
    </form>
  );
  return embedded ? form : <Card withBorder radius="md" mt="md">{form}</Card>;
}
