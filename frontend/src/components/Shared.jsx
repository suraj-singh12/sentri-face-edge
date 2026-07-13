import { useMemo, useState } from "react";

import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Group,
  Image,
  Menu,
  Paper,
  ScrollArea,
  Stack,
  Text,
  Textarea,
  TextInput,
  ThemeIcon,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconCheck,
  IconCode,
  IconCopy,
  IconChevronDown,
  IconFilter,
  IconGridDots,
  IconLayoutList,
  IconPhotoUp,
  IconSearch,
  IconSortDescending,
  IconUserCircle,
} from "@tabler/icons-react";

import {
  detailsForEmbedding,
  galleryImages,
  isNewPersonSuggestion,
  mediaUrl,
  qualityColor,
  recognitionText,
} from "../utils.js";

export function Surface({ title, subtitle, action, children, step }) {
  return (
    <Card withBorder radius="md" h="100%" className="surface-card">
      <Stack gap="sm" h="100%">
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <Box miw={0} className="surface-title-block" data-step={step}>
            <Text fw={800}>{title}</Text>
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
      <Stack align="center" gap="lg">
        <ThemeIcon size={64} radius="md" variant="light" color="teal"><IconPhotoUp size={32} /></ThemeIcon>
        <Box ta="center">
          <Title order={3} size="h4">Drag & drop an image here</Title>
          <Text size="md" c="teal.3">or click to browse</Text>
        </Box>
        <Text size="sm" c="dimmed">Supports: JPG, PNG, JPEG&nbsp;&nbsp;•&nbsp;&nbsp;Max size: 10 MB</Text>
      </Stack>
    </Paper>
  );
}

export function BestMatchPanel({ best, face, onGallery, selectedImage }) {
  if (!face) {
    return (
      <Stack className="best-match-panel no-result-panel">
        <Paper withBorder radius="md" className="result-photo-card result-photo-placeholder" p="xl">
          <Stack align="center" gap="md">
            <ThemeIcon size={76} radius="xl" variant="light" color="blue"><IconUserCircle size={46} /></ThemeIcon>
            <Title order={2} size="h3">No result yet</Title>
            <Text size="sm" c="dimmed">Load an image on the left to start recognition.</Text>
          </Stack>
        </Paper>
        {/* <MatchIdentityPlaceholder /> */}
      </Stack>
    );
  }
  if (!best) {
    return (
      <Stack className="best-match-panel">
        <Title order={2} size="h3">No known person is close enough</Title>
        <Paper withBorder radius="md" className="result-photo-card result-photo-placeholder">
          <Text size="sm" c="dimmed">No match photo</Text>
        </Paper>
        <MatchIdentityPlaceholder />
      </Stack>
    );
  }

  const noMatchFound = isNewPersonSuggestion(best);
  const matchImage = selectedImage || best.source_image || best.image_path || best.representative_source_image || best.representative_image;
  return (
    <Stack className="best-match-panel">
      <Group gap="md" align="center">
        {!noMatchFound && <ThemeIcon size={44} radius="xl" color="teal"><IconCheck size={26} /></ThemeIcon>}
        <Box miw={0}>
          <Title order={2} size="h2" className="match-title">{recognitionText(best)}</Title>
          {!noMatchFound && (
            <Group gap="xs" mt={2}>
              <Badge color="green" variant="light">Strong Match</Badge>
              <Text size="sm" c="green.4">★★★★★</Text>
              <Text size="xs" c="dimmed">({(best.score * 100).toFixed(1)}% confidence)</Text>
            </Group>
          )}
        </Box>
      </Group>
      {noMatchFound ? (
        <>
          <Paper withBorder radius="md" className="result-photo-card result-photo-placeholder">
            <Text size="sm" c="dimmed">No match photo</Text>
          </Paper>
          <MatchIdentityPlaceholder />
        </>
      ) : (
        <>
          <Card withBorder p={0} component="button" className="mantine-click-card result-photo-card--match" onClick={() => onGallery(best.person_id)}>
            {matchImage ? (
              <img
                src={mediaUrl(matchImage)}
                alt={best.name}
                className="match-result-image"
                style={{ objectFit: "contain", objectPosition: "center center" }}
              />
            ) : <Text p="md">No photo</Text>}
          </Card>
          <MatchIdentitySummary match={best} />
        </>
      )}
    </Stack>
  );
}

export function GalleryPanel({ payload, selectedImage, onImage, onBack }) {
  const images = galleryImages(payload);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("newest");
  const [viewMode, setViewMode] = useState("grid");
  const records = useMemo(() => payload.embeddings.map((embedding, index) => {
    const thumbPath = embedding.crop_path || embedding.source_image;
    const displayPath = embedding.source_image || embedding.crop_path;
    const detail = detailsForEmbedding(payload.details, embedding.embedding_id)[0];
    return {
      embeddingId: embedding.embedding_id,
      path: displayPath,
      thumbPath,
      index,
      date: detail?.date || "",
      label: detail?.date || "Saved photo",
      event: detail?.event_occasion || "",
      place: detail?.place_seen || "",
    };
  }).filter((record) => record.path && record.thumbPath), [payload.details, payload.embeddings]);
  const visibleRecords = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return records
      .filter((record) => {
        if (filter === "withDetails" && !record.date && !record.event && !record.place) return false;
        if (filter === "withoutDetails" && (record.date || record.event || record.place)) return false;
        if (!normalizedQuery) return true;
        return [record.path, record.label, record.event, record.place]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(normalizedQuery));
      })
      .sort((a, b) => {
        if (sort === "oldest") return compareDates(a.date, b.date) || a.index - b.index;
        if (sort === "name") return a.label.localeCompare(b.label) || a.index - b.index;
        return compareDates(b.date, a.date) || a.index - b.index;
      });
  }, [filter, query, records, sort]);
  const selectedPath = visibleRecords.some((record) => record.path === selectedImage)
    ? selectedImage
    : visibleRecords[0]?.path || null;
  const selectedRecord = visibleRecords.find((record) => record.path === selectedPath);
  const filterLabel = {
    all: "All",
    withDetails: "With Details",
    withoutDetails: "Without Details",
  }[filter];
  const sortLabel = {
    newest: "Newest",
    oldest: "Oldest",
    name: "Label",
  }[sort];

  return (
    <Stack h="100%" className="match-gallery-panel">
      <Group justify="space-between" align="center" className="gallery-topbar">
        <Group gap="sm" wrap="nowrap">
          <ActionIcon variant="subtle" onClick={onBack} aria-label="Back to results"><IconArrowLeft size={20} /></ActionIcon>
          <Text fw={800} size="lg">Recognition Result</Text>
        </Group>
        {/* <Button variant="default">View Details</Button> */}
      </Group>
      <Group gap="sm" wrap="nowrap" className="gallery-person-row">
        {selectedRecord?.thumbPath && <Image src={mediaUrl(selectedRecord.thumbPath)} alt={payload.person.name} fit="cover" h={68} w={68} radius="sm" />}
        <Box miw={0}>
          <Text fw={800} size="lg" truncate>{payload.person.name}</Text>
          <Text size="sm" c="dimmed">{images.length} reference photos</Text>
        </Box>
      </Group>
      <Group gap="sm" className="gallery-toolbar">
        <TextInput
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
          placeholder="Search photos..."
          leftSection={<IconSearch size={16} />}
          className="gallery-search"
        />
        <Menu withinPortal position="bottom-start">
          <Menu.Target>
            <Button variant="default" leftSection={<IconFilter size={16} />} rightSection={<IconChevronDown size={15} />}>{filterLabel}</Button>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item onClick={() => setFilter("all")}>All Photos</Menu.Item>
            <Menu.Item onClick={() => setFilter("withDetails")}>With Details</Menu.Item>
            <Menu.Item onClick={() => setFilter("withoutDetails")}>Without Details</Menu.Item>
          </Menu.Dropdown>
        </Menu>
        <Menu withinPortal position="bottom-start">
          <Menu.Target>
            <Button variant="default" leftSection={<IconSortDescending size={16} />} rightSection={<IconChevronDown size={15} />}>{sortLabel}</Button>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item onClick={() => setSort("newest")}>Newest first</Menu.Item>
            <Menu.Item onClick={() => setSort("oldest")}>Oldest first</Menu.Item>
            <Menu.Item onClick={() => setSort("name")}>Label</Menu.Item>
          </Menu.Dropdown>
        </Menu>
        <Group gap={0} className="gallery-view-toggle">
          <Tooltip label="Tile view">
            <ActionIcon variant={viewMode === "grid" ? "light" : "default"} onClick={() => setViewMode("grid")} aria-label="Tile view"><IconGridDots size={16} /></ActionIcon>
          </Tooltip>
          <Tooltip label="List view">
            <ActionIcon variant={viewMode === "list" ? "light" : "default"} onClick={() => setViewMode("list")} aria-label="List view"><IconLayoutList size={16} /></ActionIcon>
          </Tooltip>
        </Group>
      </Group>
      <ScrollArea type="auto" scrollbars="y" className="match-gallery-grid-scroll">
        <Box className={viewMode === "list" ? "match-gallery-list" : "match-gallery-grid"}>
          {visibleRecords.length ? visibleRecords.map((record) => {
            return (
            <Card key={`${record.embeddingId}-${record.thumbPath}`} withBorder p={4} component="button" className="mantine-click-card gallery-photo-card" data-selected={selectedPath === record.path} onClick={() => onImage(record.path)}>
              <Box className="gallery-photo-wrap">
                {selectedPath === record.path && <ThemeIcon size={22} radius="xl" color="teal" className="gallery-selected-check"><IconCheck size={14} /></ThemeIcon>}
                <Image src={mediaUrl(record.thumbPath)} alt={payload.person.name} fit="cover" className="gallery-photo-image" radius="sm" />
              </Box>
              <Box className="gallery-photo-meta">
                <Text size="xs" ta={viewMode === "list" ? "left" : "center"} mt={6}>{record.label}</Text>
                {viewMode === "list" && <Text size="xs" c="dimmed" truncate>{record.event || record.place || record.path}</Text>}
              </Box>
            </Card>
            );
          }) : <EmptyCard text="No photos saved for this person." />}
        </Box>
      </ScrollArea>
      <Group justify="space-between" c="dimmed">
        <Text size="sm">{visibleRecords.length ? `1–${visibleRecords.length}` : "0"} of {records.length} photos{selectedRecord ? ` • Selected ${selectedRecord.label}` : ""}</Text>
        <Group gap="sm"><Text>‹</Text><Badge variant="light">1</Badge><Text>›</Text></Group>
      </Group>
    </Stack>
  );
}

export function InputImageQuality({ quality }) {
  const reasons = quality.reasons.length ? quality.reasons.join(", ") : "";
  return (
    <Stack gap="xs">
      <Divider />
      <Group>
        <Text fw={700}>Face Quality</Text>
        <Badge color={qualityColor(quality.status)}>{quality.status}</Badge>
        <Text fw={700}>score: {quality.score.toFixed(3)}</Text>
      </Group>
      {reasons && <Text size="sm" c="dimmed">{reasons}</Text>}
    </Stack>
  );
}

export function Metrics({ metrics }) {
  return (
    <Card component="details" withBorder radius="md" mt="sm" p={0} className="metrics-card">
      <summary className="metrics-toggle">
        <Group justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <ThemeIcon variant="light" color="dark"><IconCode size={18} /></ThemeIcon>
            <Text fw={700}>Recognition Metrics (for developers)</Text>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <IconCode size={16} />
            <Text size="sm" fw={700} className="metrics-show-text">Show Details</Text>
            <Text size="sm" fw={700} className="metrics-hide-text">Hide Details</Text>
            <IconChevronDown size={15} className="metrics-chevron" />
          </Group>
        </Group>
      </summary>
      <Box p="sm" pt={0}>
        <Textarea
          value={JSON.stringify(metrics ?? {}, null, 2)}
          readOnly
          autosize
          minRows={6}
          maxRows={6}
          styles={{ input: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace", resize: "none" } }}
        />
      </Box>
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
  const [copied, setCopied] = useState(false);
  const copyGroupId = async () => {
    await navigator.clipboard?.writeText(match.person_id);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  return (
    <Paper withBorder radius="md" p="sm" className="match-identity-summary">
      <Group grow>
        <Box>
          <Text size="sm" c="dimmed">Confidence Score</Text>
          <Text fw={900} size="xl" className="match-identity-score">{(match.score * 100).toFixed(1)}%</Text>
          <Text size="xs" c="dimmed">Very High Confidence</Text>
        </Box>
        <Box>
          <Text size="sm" c="dimmed">Group ID</Text>
          <Group gap={6} wrap="nowrap">
            <Tooltip label={copied ? "Copied" : "Copy Group ID"}>
              <ActionIcon size="sm" variant="subtle" color={copied ? "teal" : "gray"} onClick={copyGroupId} aria-label="Copy Group ID">
                {copied ? <IconCheck size={15} /> : <IconCopy size={15} />}
              </ActionIcon>
            </Tooltip>
            <Text size="xs" truncate>{match.person_id}</Text>
          </Group>
        </Box>
      </Group>
    </Paper>
  );
}

function compareDates(left, right) {
  if (!left && !right) return 0;
  if (!left) return 1;
  if (!right) return -1;
  return new Date(left).getTime() - new Date(right).getTime();
}

function MatchIdentityPlaceholder() {
  return (
    <Paper withBorder radius="md" p="sm" className="match-identity-placeholder">
      <Group grow>
        <Box>
          <Text size="sm">Confidence Score</Text>
          <Text fw={800} c="teal.8">-</Text>
          <Text size="xs" c="dimmed">N/A</Text>
        </Box>
        <Box>
          <Text size="sm">Group ID</Text>
          <Text fw={800} c="teal.8">-</Text>
          <Text size="xs" c="dimmed">N/A</Text>
        </Box>
      </Group>
    </Paper>
  );
}
