import { Badge, Box, Divider, Group, Modal, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconPhoto } from "@tabler/icons-react";

import { mediaUrl } from "../utils.js";
import { SafeImage } from "./Shared.jsx";

export function WorldMediaPreview({ item, origin, opened, onClose }) {
  return (
    <Modal opened={opened} onClose={onClose} title="World media inspection" centered size="lg" classNames={{ content: "world-media-modal", body: "world-media-modal-body" }}>
      {item ? (
        <Stack gap="sm">
          <Group gap="xs"><Badge size="xs" variant="light" color={origin?.type === "EVIDENCE" ? "blue" : "teal"}>{originLabel(origin)}</Badge><Text size="xs" c="dimmed">Inspection only</Text></Group>
          <Box className="world-media-preview-frame">
            <SafeImage src={item.media_reference ? mediaUrl(item.media_reference) : ""} alt={`Media ${item.media_id}`} fit="contain" className="world-media-preview-image" fallback={<Stack align="center" gap="xs"><ThemeIcon size={54} variant="light" color="gray"><IconPhoto size={28} /></ThemeIcon><Text size="sm" fw={700}>Media preview unavailable</Text><Text size="xs" c="dimmed">The authoritative reference exists, but no displayable asset was returned.</Text></Stack>} />
          </Box>
          <Divider />
          <Stack gap={4} className="world-media-preview-facts">
            <PreviewRow label="Media ID" value={item.media_id} />
            <PreviewRow label="Occurred" value={formatDateTime(item.occurred_at)} />
            <PreviewRow label="Source" value={item.source || "Not supplied"} />
            <PreviewRow label="Supporting event" value={item.supporting_event_id || "Not supplied"} />
            <PreviewRow label="Supporting evidence" value={item.supporting_evidence_id || "Not supplied"} />
            <PreviewRow label="Origin" value={originDescription(origin)} />
          </Stack>
          <Text size="10px" c="dimmed">This preview uses the existing authorized media-serving path. It does not run recognition or create World identity, evidence, participant, or relationship state.</Text>
        </Stack>
      ) : null}
    </Modal>
  );
}

function PreviewRow({ label, value }) {
  return <Group justify="space-between" align="flex-start" gap="md" wrap="nowrap"><Text size="xs" c="dimmed">{label}</Text><Text size="xs" fw={700} ta="right">{value}</Text></Group>;
}

function originLabel(origin) {
  return origin?.type === "EVIDENCE" ? "Supporting Evidence media" : "Event media";
}

function originDescription(origin) {
  if (origin?.type === "EVIDENCE") return `Opened as supporting media for Evidence ${origin.evidenceId || "—"}`;
  return `Opened from Event ${origin?.eventId || "—"}`;
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
