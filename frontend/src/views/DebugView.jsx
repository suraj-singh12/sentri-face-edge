import { Button, Group, Paper, Textarea, Title } from "@mantine/core";
import { IconRefresh } from "@tabler/icons-react";

export function DebugView({ events, onRefresh }) {
  return (
    <Paper withBorder radius="md" p="md">
      <Group justify="space-between" mb="sm">
        <Title order={3} size="h4">Debug Events</Title>
        <Button variant="light" leftSection={<IconRefresh size={16} />} onClick={onRefresh}>Refresh</Button>
      </Group>
      <Textarea
        value={events.map((event) => JSON.stringify(event)).join("\n")}
        readOnly
        autosize
        minRows={16}
        styles={{ input: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" } }}
      />
    </Paper>
  );
}
