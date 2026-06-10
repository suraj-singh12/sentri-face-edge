import {
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Group,
  Image,
  Paper,
  ScrollArea,
  Stack,
  Text,
  Textarea,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { IconArrowLeft, IconPhotoUp } from "@tabler/icons-react";

import {
  galleryImages,
  isNewPersonSuggestion,
  mediaUrl,
  qualityColor,
  recognitionText,
} from "../utils.js";

export function Surface({ title, subtitle, action, children }) {
  return (
    <Card withBorder radius="md" h="100%" className="surface-card">
      <Stack gap="sm" h="100%">
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <Box miw={0}>
            <Text fw={700}>{title}</Text>
            <Text size="xs" c="dimmed" truncate>{subtitle}</Text>
          </Box>
          {action}
        </Group>
        {children}
      </Stack>
    </Card>
  );
}

export function ImageFrame({ children, ratio, variant = "default" }) {
  const className = ["image-frame", `image-frame--${variant}`].join(" ");
  return (
    <Box className={className} style={{ aspectRatio: ratio }}>
      {children}
    </Box>
  );
}

export function LoadImagePanel({ onClick }) {
  return (
    <Paper withBorder radius="md" p="xl" className="load-image-panel" component="button" onClick={onClick}>
      <Stack align="center">
        <ThemeIcon size={52} variant="light" color="blue"><IconPhotoUp size={28} /></ThemeIcon>
        <Box ta="center">
          <Title order={3} size="h4">Load Image</Title>
          <Text size="sm" c="dimmed">Recognition starts immediately after the photo is selected.</Text>
        </Box>
      </Stack>
    </Paper>
  );
}

export function BestMatchPanel({ best, face, onGallery }) {
  if (!face) {
    return (
      <Stack className="best-match-panel">
        <Title order={2} size="h3">No result yet.</Title>
        <Paper withBorder radius="md" className="result-photo-card result-photo-placeholder">
          <Text size="sm" c="dimmed">Load an image</Text>
        </Paper>
        <MatchIdentityPlaceholder />
      </Stack>
    );
  }
  if (!best) {
    return (
      <Stack className="best-match-panel">
        <Title order={2} size="h3">No known person is close enough.</Title>
        <Paper withBorder radius="md" className="result-photo-card result-photo-placeholder">
          <Text size="sm" c="dimmed">No match photo</Text>
        </Paper>
        <MatchIdentityPlaceholder />
      </Stack>
    );
  }

  const noMatchFound = isNewPersonSuggestion(best);
  return (
    <Stack className="best-match-panel">
      <Title order={2} size="h3">{recognitionText(best)}</Title>
      {noMatchFound ? (
        <>
          <Paper withBorder radius="md" className="result-photo-card result-photo-placeholder">
            <Text size="sm" c="dimmed">No match photo</Text>
          </Paper>
          <MatchIdentityPlaceholder />
        </>
      ) : (
        <>
          <Card withBorder p={0} component="button" className="mantine-click-card result-photo-card" onClick={() => onGallery(best.person_id)}>
            {best.representative_image ? <Image src={mediaUrl(best.representative_image)} alt={best.name} fit="contain" h="100%" /> : <Text p="md">No photo</Text>}
          </Card>
          <MatchIdentitySummary match={best} />
        </>
      )}
    </Stack>
  );
}

export function GalleryPanel({ payload, selectedImage, onImage, onBack }) {
  const images = galleryImages(payload);
  return (
    <Stack h="100%" className="match-gallery-panel">
      <Group justify="space-between">
        <Text fw={700}>{payload.person.name} Photos</Text>
        <Button size="xs" variant="light" leftSection={<IconArrowLeft size={14} />} onClick={onBack}>Back</Button>
      </Group>
      <Box className="match-gallery-selected-slot">
        {selectedImage ? (
          <ImageFrame variant="matchGallerySelected">
            <Image src={mediaUrl(selectedImage)} alt={payload.person.name} fit="contain" h="100%" />
          </ImageFrame>
        ) : (
          <Paper withBorder radius="md" className="match-gallery-empty">
            <Text size="sm" c="dimmed">Select a photo</Text>
          </Paper>
        )}
      </Box>
      <ScrollArea type="auto" offsetScrollbars className="match-gallery-strip">
        <Group wrap="nowrap" gap="xs" pb="xs">
          {images.length ? images.map((path) => (
            <Card key={path} withBorder p={4} miw={92} w={92} component="button" className="mantine-click-card" data-selected={selectedImage === path} onClick={() => onImage(path)}>
              <Image src={mediaUrl(path)} alt={payload.person.name} fit="cover" h={72} radius="sm" />
            </Card>
          )) : <EmptyCard text="No photos saved for this person." />}
        </Group>
      </ScrollArea>
    </Stack>
  );
}

export function InputImageQuality({ quality }) {
  const reasons = quality.reasons.length ? quality.reasons.join(", ") : "";
  return (
    <Stack gap="xs">
      <Divider />
      <Group>
        <Badge color={qualityColor(quality.status)}>{quality.status}</Badge>
        <Text fw={700}>score: {quality.score.toFixed(3)}</Text>
      </Group>
      {reasons && <Text size="sm" c="dimmed">{reasons}</Text>}
    </Stack>
  );
}

export function Metrics({ metrics }) {
  return (
    <Card withBorder radius="md" mt="md">
      <Text fw={700} mb="xs">Metrics</Text>
      <Textarea
        value={JSON.stringify(metrics, null, 2)}
        readOnly
        minRows={4}
        maxRows={4}
        styles={{ input: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace", resize: "none" } }}
      />
    </Card>
  );
}

export function Thumb({ path }) {
  if (!path) return null;
  return <Image src={mediaUrl(path)} alt="face crop" fit="cover" h={88} radius="sm" />;
}

export function EmptyCard({ text }) {
  return (
    <Card withBorder radius="md" p="md">
      <Text size="sm" c="dimmed">{text}</Text>
    </Card>
  );
}

function MatchIdentitySummary({ match }) {
  return (
    <Paper withBorder radius="md" p="sm" className="match-identity-summary">
      <Text fw={800} className="match-identity-score">score: {match.score.toFixed(4)}</Text>
      <Text size="sm" fw={700}>Group-id: {match.person_id}</Text>
    </Paper>
  );
}

function MatchIdentityPlaceholder() {
  return (
    <Paper withBorder radius="md" p="sm" className="match-identity-placeholder">
      <Text fw={800} c="dimmed">score: -</Text>
      <Text size="sm" fw={700} c="dimmed">Group-id: -</Text>
    </Paper>
  );
}
