import { useEffect, useMemo, useState } from "react";
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Group,
  Menu,
  Paper,
  Select,
  Stack,
  Text,
  TextInput,
  ThemeIcon,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconAlertCircle,
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconCircleCheck,
  IconDatabase,
  IconDatabaseExport,
  IconDownload,
  IconInfoCircle,
  IconPlayerPause,
  IconRefresh,
  IconSearch,
  IconServer,
  IconSettings,
  IconTrash,
  IconTrendingUp,
} from "@tabler/icons-react";

export function DebugView({ events, backups = [], backupCreating = false, onRefresh, onCreateBackup, onDeleteBackup }) {
  const [section, setSection] = useState("events");
  const [paused, setPaused] = useState(false);
  const [cleared, setCleared] = useState(false);
  const [snapshot, setSnapshot] = useState(events);
  const [query, setQuery] = useState("");
  const [levelFilter, setLevelFilter] = useState("all");
  const [eventFilter, setEventFilter] = useState("all");
  const [timeFilter, setTimeFilter] = useState("all");
  const [pageSize, setPageSize] = useState("25");
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (!paused && !cleared) setSnapshot(events);
  }, [cleared, events, paused]);

  const normalizedEvents = useMemo(() => snapshot.map(normalizeEvent), [snapshot]);
  const eventTypes = useMemo(() => Array.from(new Set(normalizedEvents.map((event) => event.event))).filter(Boolean).sort(), [normalizedEvents]);
  const summary = useMemo(() => summarizeEvents(normalizedEvents), [normalizedEvents]);
  const filteredEvents = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return normalizedEvents.filter((event) => {
      if (levelFilter !== "all" && event.level !== levelFilter) return false;
      if (eventFilter !== "all" && event.event !== eventFilter) return false;
      if (!matchesTimeFilter(event, timeFilter)) return false;
      if (!normalizedQuery) return true;
      return [event.event, event.level, event.details, event.raw]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery));
    });
  }, [eventFilter, levelFilter, normalizedEvents, query, timeFilter]);
  const size = Number(pageSize) || 25;
  const totalPages = Math.max(1, Math.ceil(filteredEvents.length / size));
  const pageEvents = filteredEvents.slice((page - 1) * size, page * size);

  useEffect(() => {
    setPage(1);
  }, [eventFilter, levelFilter, pageSize, query, timeFilter]);

  const refreshEvents = async () => {
    setCleared(false);
    setPaused(false);
    await onRefresh();
  };

  const clearEvents = () => {
    setCleared(true);
    setSnapshot([]);
    setPage(1);
  };

  const exportEvents = () => {
    const blob = new Blob([filteredEvents.map((event) => event.raw).join("\n")], { type: "application/jsonl" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `sentriface-events-${new Date().toISOString().replace(/[:.]/g, "-")}.jsonl`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Paper withBorder radius="md" p="md" className="debug-workspace">
      <Box className="debug-shell">
        <DebugSidebar section={section} onSection={setSection} summary={summary} onRefresh={refreshEvents} />
        <Box className="debug-main">
          {section === "events" ? (
            <EventsLogPanel
              events={pageEvents}
              eventTypes={eventTypes}
              filteredCount={filteredEvents.length}
              totalCount={normalizedEvents.length}
              page={page}
              totalPages={totalPages}
              pageSize={pageSize}
              query={query}
              levelFilter={levelFilter}
              eventFilter={eventFilter}
              timeFilter={timeFilter}
              paused={paused}
              onQuery={setQuery}
              onLevelFilter={setLevelFilter}
              onEventFilter={setEventFilter}
              onTimeFilter={setTimeFilter}
              onPageSize={setPageSize}
              onPage={setPage}
              onPause={() => setPaused((current) => !current)}
              onClear={clearEvents}
              onExport={exportEvents}
              onRefresh={refreshEvents}
            />
          ) : section === "database" ? (
            <DatabaseBackupsPanel
              backups={backups}
              creating={backupCreating}
              onCreate={onCreateBackup}
              onDelete={onDeleteBackup}
            />
          ) : (
            <DebugPlaceholderPanel section={section} summary={summary} totalEvents={normalizedEvents.length} />
          )}
        </Box>
      </Box>
    </Paper>
  );
}

function DebugSidebar({ section, onSection, summary, onRefresh }) {
  const navItems = [
    { key: "events", label: "Events Log", icon: IconInfoCircle },
    { key: "system", label: "System Info", icon: IconServer },
    { key: "performance", label: "Performance", icon: IconTrendingUp },
    { key: "database", label: "Database", icon: IconDatabase },
    { key: "settings", label: "Settings", icon: IconSettings },
  ];
  return (
    <Stack className="debug-sidebar">
      <Card withBorder radius="md" className="debug-side-card">
        <Text size="xs" c="dimmed" fw={800} tt="uppercase" mb="sm">Debug</Text>
        <Stack gap={4}>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Button
                key={item.key}
                variant={section === item.key ? "light" : "subtle"}
                color={section === item.key ? "teal" : "gray"}
                leftSection={<Icon size={16} />}
                justify="flex-start"
                onClick={() => onSection(item.key)}
                className="debug-nav-button"
              >
                {item.label}
              </Button>
            );
          })}
        </Stack>
      </Card>
      <Card withBorder radius="md" className="debug-side-card debug-summary-card">
        <Text fw={800} mb="md">Log Summary</Text>
        <DebugMetric label="Total Events" value={summary.total.toLocaleString()} />
        <DebugMetric label="Errors" value={summary.error} tone="red" />
        <DebugMetric label="Warnings" value={summary.warning} tone="yellow" />
        <DebugMetric label="Info" value={summary.info} tone="blue" />
        <Divider my="sm" />
        <Group justify="space-between" wrap="nowrap">
          <Box>
            <Text size="sm" c="dimmed">Last Updated</Text>
            <Text size="sm">{new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</Text>
          </Box>
          <Tooltip label="Refresh events">
            <ActionIcon variant="subtle" onClick={onRefresh} aria-label="Refresh events"><IconRefresh size={18} /></ActionIcon>
          </Tooltip>
        </Group>
      </Card>
    </Stack>
  );
}

function EventsLogPanel({
  events,
  eventTypes,
  filteredCount,
  totalCount,
  page,
  totalPages,
  pageSize,
  query,
  levelFilter,
  eventFilter,
  timeFilter,
  paused,
  onQuery,
  onLevelFilter,
  onEventFilter,
  onTimeFilter,
  onPageSize,
  onPage,
  onPause,
  onClear,
  onExport,
  onRefresh,
}) {
  return (
    <Stack h="100%" gap="md">
      <Group justify="space-between" align="flex-start" wrap="nowrap" className="debug-main-header">
        <Box>
          <Title order={3} size="h4">Events Log</Title>
          <Text size="sm" c="dimmed">Real-time system events and application logs</Text>
        </Box>
        <Group gap="sm" wrap="nowrap" className="debug-actions">
          <Button variant="default" leftSection={<IconPlayerPause size={16} />} onClick={onPause}>{paused ? "Resume" : "Pause"}</Button>
          <Button variant="default" leftSection={<IconTrash size={16} />} onClick={onClear}>Clear</Button>
          <Button variant="default" leftSection={<IconDownload size={16} />} onClick={onExport}>Export</Button>
          <Button leftSection={<IconRefresh size={16} />} onClick={onRefresh}>Refresh</Button>
        </Group>
      </Group>
      <Paper withBorder radius="md" p="sm" className="debug-filter-panel">
        <Group gap="sm" wrap="nowrap" className="debug-filters">
          <TextInput
            value={query}
            onChange={(event) => onQuery(event.currentTarget.value)}
            placeholder="Search events..."
            leftSection={<IconSearch size={16} />}
            className="debug-search"
          />
          <Select value={levelFilter} onChange={(value) => onLevelFilter(value || "all")} data={[
            { value: "all", label: "All Levels" },
            { value: "info", label: "Info" },
            { value: "success", label: "Success" },
            { value: "warning", label: "Warning" },
            { value: "error", label: "Error" },
          ]} rightSection={<IconChevronDown size={14} />} className="debug-select" />
          <Select
            value={eventFilter}
            onChange={(value) => onEventFilter(value || "all")}
            data={[{ value: "all", label: "All Events" }, ...eventTypes.map((event) => ({ value: event, label: event }))]}
            rightSection={<IconChevronDown size={14} />}
            className="debug-select"
          />
          <Select value={timeFilter} onChange={(value) => onTimeFilter(value || "all")} data={[
            { value: "all", label: "All Time" },
            { value: "hour", label: "Last 1 hour" },
            { value: "day", label: "Last 24 hours" },
          ]} rightSection={<IconChevronDown size={14} />} className="debug-select" />
        </Group>
      </Paper>
      <Paper withBorder radius="md" className="debug-table-card">
        <Box className="debug-table-scroll">
          <table className="debug-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Level</th>
                <th>Event</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {events.length ? events.map((event) => (
                <tr key={event.key}>
                  <td>{event.timeLabel}</td>
                  <td><LevelBadge level={event.level} /></td>
                  <td>{event.event}</td>
                  <td className={event.level === "error" ? "debug-error-cell" : ""}>{event.details}</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={4} className="debug-empty-row">No events match the current filters.</td>
                </tr>
              )}
            </tbody>
          </table>
        </Box>
      </Paper>
      <Paper withBorder radius="md" p="sm" className="debug-pagination">
        <Group justify="space-between">
          <Group gap="sm">
            <Text size="sm" c="dimmed">Show</Text>
            <Select value={pageSize} onChange={(value) => onPageSize(value || "25")} data={["10", "25", "50"]} w={86} />
            <Text size="sm" c="dimmed">
              Showing {filteredCount ? `${(page - 1) * Number(pageSize) + 1} to ${Math.min(page * Number(pageSize), filteredCount)}` : "0"} of {filteredCount.toLocaleString()} events
              {filteredCount !== totalCount ? ` (${totalCount.toLocaleString()} total)` : ""}
            </Text>
          </Group>
          <Group gap="xs">
            <ActionIcon variant="default" disabled={page <= 1} onClick={() => onPage(Math.max(1, page - 1))} aria-label="Previous page"><IconChevronLeft size={16} /></ActionIcon>
            {visiblePageNumbers(page, totalPages).map((item) => item === "ellipsis"
              ? <Text key={item} c="dimmed">...</Text>
              : <Badge key={item} size="lg" variant={item === page ? "filled" : "light"}>{item}</Badge>)}
            <ActionIcon variant="default" disabled={page >= totalPages} onClick={() => onPage(Math.min(totalPages, page + 1))} aria-label="Next page"><IconChevronRight size={16} /></ActionIcon>
          </Group>
        </Group>
      </Paper>
    </Stack>
  );
}

function DebugPlaceholderPanel({ section, summary, totalEvents }) {
  const title = {
    system: "System Info",
    performance: "Performance",
    database: "Database",
    settings: "Settings",
  }[section];
  return (
    <Stack>
      <Title order={3} size="h4">{title}</Title>
      <SimpleDebugGrid
        items={[
          ["Captured Events", totalEvents.toLocaleString()],
          ["Errors", summary.error],
          ["Warnings", summary.warning],
          ["Last Updated", new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })],
        ]}
      />
    </Stack>
  );
}

function DatabaseBackupsPanel({ backups, creating, onCreate, onDelete }) {
  const latest = backups[0] || null;
  const previous = backups.slice(1);
  return (
    <Stack h="100%" gap="md">
      <Group justify="space-between" align="flex-start" wrap="nowrap" className="debug-main-header">
        <Box>
          <Title order={3} size="h4">Database Backups</Title>
          <Text size="sm" c="dimmed">Managed SQLite snapshots stored by the application</Text>
        </Box>
        <Button leftSection={<IconDatabaseExport size={16} />} loading={creating} onClick={onCreate}>
          {creating ? "Creating backup..." : "Create Backup"}
        </Button>
      </Group>

      <Paper withBorder radius="md" p="md" className="database-backup-summary">
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <Box>
            <Text size="xs" c="dimmed" fw={800} tt="uppercase">Last backup</Text>
            {latest ? (
              <>
                <Text fw={900} size="lg">{formatDateTime(latest.created_at)}</Text>
                <Text size="sm" c="dimmed">
                  {formatBytes(latest.size_bytes)} · {latest.people_count.toLocaleString()} people · {latest.embedding_count.toLocaleString()} embeddings
                </Text>
              </>
            ) : (
              <>
                <Text fw={900} size="lg">No backup yet</Text>
                <Text size="sm" c="dimmed">Create the first managed database snapshot.</Text>
              </>
            )}
          </Box>
          {latest && <Badge color={latest.verified ? "green" : "red"} variant="light">{latest.verified ? "Verified" : "Not verified"}</Badge>}
        </Group>
      </Paper>

      <Paper withBorder radius="md" className="debug-table-card">
        <Box className="debug-table-scroll">
          <table className="debug-table database-backup-table">
            <thead>
              <tr>
                <th>Created</th>
                <th>Size</th>
                <th>People</th>
                <th>Embeddings</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {backups.length ? backups.map((backup) => (
                <tr key={backup.backup_id}>
                  <td>{formatDateTime(backup.created_at)}</td>
                  <td>{formatBytes(backup.size_bytes)}</td>
                  <td>{backup.people_count.toLocaleString()}</td>
                  <td>{backup.embedding_count.toLocaleString()}</td>
                  <td>
                    <Tooltip label="Delete backup">
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        onClick={() => onDelete(backup.backup_id)}
                        aria-label={`Delete backup ${formatDateTime(backup.created_at)}`}
                      >
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Tooltip>
                  </td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={5} className="debug-empty-row">No managed backups created yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </Box>
      </Paper>

      {previous.length > 0 && (
        <Text size="sm" c="dimmed">
          Previous backups: {previous.slice(0, 3).map((backup) => `${formatDateTime(backup.created_at)} ${formatBytes(backup.size_bytes)}`).join(" · ")}
        </Text>
      )}
    </Stack>
  );
}

function SimpleDebugGrid({ items }) {
  return (
    <Box className="debug-info-grid">
      {items.map(([label, value]) => (
        <Paper key={label} withBorder radius="md" p="md" className="debug-info-card">
          <Text size="xs" c="dimmed" fw={800}>{label}</Text>
          <Text fw={900} size="lg">{value}</Text>
        </Paper>
      ))}
    </Box>
  );
}

function LevelBadge({ level }) {
  const config = {
    info: { color: "blue", icon: IconInfoCircle },
    success: { color: "green", icon: IconCircleCheck },
    warning: { color: "yellow", icon: IconAlertCircle },
    error: { color: "red", icon: IconAlertCircle },
  }[level] || { color: "gray", icon: IconInfoCircle };
  const Icon = config.icon;
  return <Badge color={config.color} variant="light" leftSection={<Icon size={12} />}>{level}</Badge>;
}

function DebugMetric({ label, value, tone }) {
  return (
    <Group justify="space-between" mb="xs">
      <Text size="sm" c="dimmed">{label}</Text>
      <Text size="sm" fw={900} c={tone ? `${tone}.4` : undefined}>{value}</Text>
    </Group>
  );
}

function normalizeEvent(event, index) {
  const eventName = String(event.event || event.type || "event");
  const level = event.level || inferLevel(event);
  const timestamp = event.timestamp || event.created_at || event.time || event.ts || "";
  const parsedTime = timestamp ? new Date(timestamp) : null;
  const timeLabel = parsedTime && !Number.isNaN(parsedTime.getTime())
    ? parsedTime.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "-";
  return {
    key: `${index}-${eventName}-${timestamp || JSON.stringify(event).slice(0, 40)}`,
    event: eventName,
    level,
    time: parsedTime && !Number.isNaN(parsedTime.getTime()) ? parsedTime : null,
    timeLabel,
    details: summarizeEventDetails(event),
    raw: JSON.stringify(event),
  };
}

function inferLevel(event) {
  const eventName = String(event.event || "").toLowerCase();
  const message = JSON.stringify(event).toLowerCase();
  if (eventName.includes("error") || message.includes("error") || message.includes("not found") || message.includes("no acceptable")) return "error";
  if (eventName.includes("warn")) return "warning";
  if (eventName.includes("recognize") && Number(event.faces || 0) > 0) return "success";
  return "info";
}

function summarizeEventDetails(event) {
  if (event.message) return event.message;
  if (event.error) return event.error;
  if (event.event === "upload") {
    const size = event.stored_size ? ` (${formatBytes(event.stored_size)})` : "";
    return `${event.filename || "file"}${size} uploaded to ${event.path || "-"}`;
  }
  if (event.event === "recognize") return `${event.faces ?? 0} face${Number(event.faces) === 1 ? "" : "s"} detected and processed`;
  if (event.event === "queue-scan") return `Session: ${event.session_id || "-"}, Groups: ${event.groups ?? "-"}`;
  if (event.event === "upload-batch") return `${event.files ?? 0} file(s) uploaded to ${event.path || "-"}`;
  if (event.event === "startup") return `${event.runtime || "runtime"} initialized at ${event.address || "-"}`;
  return Object.entries(event)
    .filter(([key]) => key !== "event" && key !== "level")
    .map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`)
    .join(", ") || "-";
}

function summarizeEvents(events) {
  return events.reduce((summary, event) => {
    summary.total += 1;
    summary[event.level] = (summary[event.level] || 0) + 1;
    return summary;
  }, { total: 0, error: 0, warning: 0, info: 0, success: 0 });
}

function matchesTimeFilter(event, filter) {
  if (filter === "all") return true;
  if (!event.time) return true;
  const age = Date.now() - event.time.getTime();
  if (filter === "hour") return age <= 60 * 60 * 1000;
  if (filter === "day") return age <= 24 * 60 * 60 * 1000;
  return true;
}

function visiblePageNumbers(page, totalPages) {
  if (totalPages <= 3) return Array.from({ length: totalPages }, (_, index) => index + 1);
  if (page <= 2) return [1, 2, 3, "ellipsis", totalPages];
  if (page >= totalPages - 1) return [1, "ellipsis", totalPages - 2, totalPages - 1, totalPages];
  return [1, "ellipsis", page, "ellipsis", totalPages];
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value || "-");
  return date.toLocaleString([], {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
