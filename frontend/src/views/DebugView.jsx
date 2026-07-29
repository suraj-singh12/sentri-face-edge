import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Group,
  Menu,
  Modal,
  Paper,
  PasswordInput,
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
  IconCpu,
  IconDatabase,
  IconDatabaseExport,
  IconDownload,
  IconInfoCircle,
  IconPlayerPause,
  IconRefresh,
  IconRestore,
  IconSearch,
  IconTrash,
  IconUpload,
  IconUsers,
} from "@tabler/icons-react";
import { AccountsPanel } from "./AccountsPanel.jsx";
import { MachineProfilePanel } from "./MachineProfilePanel.jsx";

export function DebugView({
  capabilities = [],
  currentUser,
  profile,
  onConfigureRecovery,
  events,
  backups = [],
  backupCreating = false,
  backupImporting = false,
  onRefresh,
  onCreateBackup,
  onDeleteBackup,
  onImportBackup,
  onDownloadBackup,
  onRestoreBackup,
}) {
  const capabilitySet = useMemo(() => new Set(capabilities), [capabilities]);
  const navItems = useMemo(() => [
    capabilitySet.has("technical") ? { key: "events", label: "Events Log", icon: IconInfoCircle } : null,
    capabilitySet.has("backups") ? { key: "database", label: "Database", icon: IconDatabase } : null,
    capabilitySet.has("technical") ? { key: "profile", label: "Machine Profile", icon: IconCpu } : null,
    capabilitySet.has("administer") ? { key: "accounts", label: "Accounts & Roles", icon: IconUsers } : null,
  ].filter(Boolean), [capabilitySet]);
  const [section, setSection] = useState(navItems[0]?.key || "database");
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
    if (!navItems.some((item) => item.key === section)) setSection(navItems[0]?.key || "database");
  }, [navItems, section]);

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

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

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
        <DebugSidebar section={section} onSection={setSection} summary={summary} onRefresh={refreshEvents} navItems={navItems} showSummary={capabilitySet.has("technical")} />
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
          ) : section === "profile" ? (
            <MachineProfilePanel profile={profile} onConfigureRecovery={onConfigureRecovery} canConfigureRecovery={capabilitySet.has("recovery")} />
          ) : section === "accounts" ? (
            <AccountsPanel currentUser={currentUser} />
          ) : (
            <DatabaseBackupsPanel
              backups={backups}
              creating={backupCreating}
              importing={backupImporting}
              onCreate={onCreateBackup}
              onDelete={onDeleteBackup}
              onImport={onImportBackup}
              onDownload={onDownloadBackup}
              onRestore={onRestoreBackup}
              canImport={capabilitySet.has("database_restore")}
              canRestore={capabilitySet.has("database_restore")}
              canDelete={capabilitySet.has("backup_delete")}
            />
          )}
        </Box>
      </Box>
    </Paper>
  );
}

function DebugSidebar({ section, onSection, summary, onRefresh, navItems, showSummary }) {
  return (
    <Stack className="debug-sidebar">
      <Card withBorder radius="md" className="debug-side-card">
        <Text size="xs" c="dimmed" fw={800} tt="uppercase" mb="sm">Advanced</Text>
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
      {showSummary ? <Card withBorder radius="md" className="debug-side-card debug-summary-card">
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
      </Card> : null}
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
          <Button variant="default" leftSection={<IconTrash size={16} />} onClick={onClear}>Clear view</Button>
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
            {visiblePageNumbers(page, totalPages).map((item, index) => item === "ellipsis"
              ? <Text key={`ellipsis-${index}`} c="dimmed">...</Text>
              : (
                <ActionIcon
                  key={item}
                  variant={item === page ? "filled" : "light"}
                  onClick={() => onPage(item)}
                  aria-label={`Page ${item}`}
                  aria-current={item === page ? "page" : undefined}
                >
                  {item}
                </ActionIcon>
              ))}
            <ActionIcon variant="default" disabled={page >= totalPages} onClick={() => onPage(Math.min(totalPages, page + 1))} aria-label="Next page"><IconChevronRight size={16} /></ActionIcon>
          </Group>
        </Group>
      </Paper>
    </Stack>
  );
}

function DatabaseBackupsPanel({
  backups,
  creating,
  importing,
  onCreate,
  onDelete,
  onImport,
  onDownload,
  onRestore,
  canImport = false,
  canRestore = false,
  canDelete = false,
}) {
  const latest = backups[0] || null;
  const previous = backups.slice(1);
  const importInputRef = useRef(null);
  const [exportBackup, setExportBackup] = useState(null);
  const [encryptedImport, setEncryptedImport] = useState(null);
  const [passphrase, setPassphrase] = useState("");
  const [passphraseConfirmation, setPassphraseConfirmation] = useState("");
  const [securityBusy, setSecurityBusy] = useState(false);
  const isExport = Boolean(exportBackup);
  const closeSecurityDialog = () => {
    if (securityBusy) return;
    setExportBackup(null);
    setEncryptedImport(null);
    setPassphrase("");
    setPassphraseConfirmation("");
  };
  const confirmSecureBackup = async () => {
    if (passphrase.length < 12 || (isExport && passphrase !== passphraseConfirmation)) return;
    setSecurityBusy(true);
    try {
      if (isExport) await onDownload(exportBackup.backup_id, passphrase);
      else await onImport(encryptedImport, passphrase);
      setExportBackup(null);
      setEncryptedImport(null);
      setPassphrase("");
      setPassphraseConfirmation("");
    } catch (error) {
      console.error(error);
    } finally {
      setSecurityBusy(false);
    }
  };
  return (
    <Stack h="100%" gap="md">
      <Group justify="space-between" align="flex-start" wrap="nowrap" className="debug-main-header">
        <Box>
          <Title order={3} size="h4">Portable Backups</Title>
          <Text size="sm" c="dimmed">Verified database, original images, and face crops in one recoverable package</Text>
        </Box>
        <Group gap="xs" wrap="nowrap">
          <input
            ref={importInputRef}
            type="file"
            accept=".sfbackup.enc,application/octet-stream"
            hidden
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              event.currentTarget.value = "";
              if (file?.name.toLowerCase().endsWith(".sfbackup.enc")) {
                setEncryptedImport(file);
                setPassphrase("");
              } else if (file) onImport(file);
            }}
          />
          <Button
            variant="default"
            leftSection={<IconUpload size={16} />}
            loading={importing}
            disabled={creating || !canImport}
            onClick={() => importInputRef.current?.click()}
          >
            {importing ? "Verifying..." : "Import"}
          </Button>
          <Button leftSection={<IconDatabaseExport size={16} />} loading={creating} disabled={importing} onClick={onCreate}>
            {creating ? "Creating..." : "Create Backup"}
          </Button>
        </Group>
      </Group>

      <Paper withBorder radius="md" p="md" className="database-backup-summary">
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <Box>
            <Text size="xs" c="dimmed" fw={800} tt="uppercase">Last backup</Text>
            {latest ? (
              <>
                <Text fw={900} size="lg">{formatDateTime(latest.created_at)}</Text>
                <Text size="sm">{latest.reason || "Manual backup"}</Text>
                <Text size="sm" c="dimmed">
                  {formatBytes(latest.size_bytes)} · {latest.people_count.toLocaleString()} people · {latest.embedding_count.toLocaleString()} embeddings · {latest.file_count || 0} files
                </Text>
              </>
            ) : (
              <>
                <Text fw={900} size="lg">No backup yet</Text>
                <Text size="sm" c="dimmed">Create the first managed database snapshot.</Text>
              </>
            )}
          </Box>
          {latest && (
            <Group gap="xs">
              <Badge color={latest.verified ? "green" : "red"} variant="light">{latest.verified ? "Verified" : "Not verified"}</Badge>
              <Badge color={latest.complete ? "teal" : "yellow"} variant="light">{latest.complete ? "Complete" : `${latest.missing_file_count || 0} missing`}</Badge>
            </Group>
          )}
        </Group>
      </Paper>

      <Paper withBorder radius="md" className="debug-table-card">
        <Box className="debug-table-scroll">
          <table className="debug-table database-backup-table">
            <thead>
              <tr>
                <th>Backup</th>
                <th>Created</th>
                <th>Size</th>
                <th>People</th>
                <th>Embeddings</th>
                <th>Files</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {backups.length ? backups.map((backup) => (
                <tr key={backup.backup_id}>
                  <td>
                    <Text size="sm" fw={700}>{backup.reason || "Manual backup"}</Text>
                    <Text size="xs" c="dimmed">{backup.backup_id}</Text>
                  </td>
                  <td>{formatDateTime(backup.created_at)}</td>
                  <td>{formatBytes(backup.size_bytes)}</td>
                  <td>{backup.people_count.toLocaleString()}</td>
                  <td>{backup.embedding_count.toLocaleString()}</td>
                  <td>{(backup.file_count || 0).toLocaleString()}</td>
                  <td>
                    <Badge color={backup.complete ? "teal" : backup.portable ? "yellow" : "gray"} variant="light">
                      {backup.complete ? "Complete" : backup.portable ? "Incomplete" : "Legacy DB only"}
                    </Badge>
                  </td>
                  <td>
                    <Group gap={4} wrap="nowrap">
                    <Tooltip label={backup.portable ? "Export password-encrypted .sfbackup.enc archive" : "Legacy database-only backups cannot be exported"}>
                      <span>
                        <ActionIcon
                          variant="subtle"
                          disabled={!backup.portable}
                          onClick={() => {
                            setExportBackup(backup);
                            setPassphrase("");
                            setPassphraseConfirmation("");
                          }}
                          aria-label={`Download backup ${formatDateTime(backup.created_at)}`}
                        >
                          <IconDownload size={16} />
                        </ActionIcon>
                      </span>
                    </Tooltip>
                    <Tooltip label={backup.complete && backup.portable ? "Restore this verified backup" : "Only complete portable backups can be restored"}>
                      <span>
                        <ActionIcon
                          variant="subtle"
                          color="teal"
                          disabled={!canRestore || !backup.complete || !backup.portable || !backup.verified}
                          onClick={() => onRestore(backup)}
                          aria-label={`Restore backup ${formatDateTime(backup.created_at)}`}
                        >
                          <IconRestore size={16} />
                        </ActionIcon>
                      </span>
                    </Tooltip>
                    <Tooltip label="Delete backup">
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        disabled={!canDelete}
                        onClick={() => onDelete(backup.backup_id)}
                        aria-label={`Delete backup ${formatDateTime(backup.created_at)}`}
                      >
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Tooltip>
                    </Group>
                  </td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={8} className="debug-empty-row">No managed backups created yet.</td>
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
      <Modal
        opened={Boolean(exportBackup || encryptedImport)}
        onClose={closeSecurityDialog}
        title={isExport ? "Export encrypted backup" : "Unlock encrypted backup"}
        centered
        closeOnClickOutside={!securityBusy}
        closeOnEscape={!securityBusy}
      >
        <Stack gap="md">
          <Alert color="blue" title={isExport ? "The export will be encrypted" : "The file is encrypted"}>
            {isExport
              ? "Choose a passphrase you can store safely. SentriFace cannot recover the export if you lose it."
              : "Enter the passphrase used when this backup was exported. It is used only for this import."}
          </Alert>
          <PasswordInput
            label="Passphrase"
            description="At least 12 characters"
            value={passphrase}
            onChange={(event) => setPassphrase(event.currentTarget.value)}
            disabled={securityBusy}
            autoFocus
          />
          {isExport && (
            <PasswordInput
              label="Confirm passphrase"
              value={passphraseConfirmation}
              onChange={(event) => setPassphraseConfirmation(event.currentTarget.value)}
              error={passphraseConfirmation && passphrase !== passphraseConfirmation ? "Passphrases do not match" : undefined}
              disabled={securityBusy}
            />
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={closeSecurityDialog} disabled={securityBusy}>Cancel</Button>
            <Button
              onClick={confirmSecureBackup}
              loading={securityBusy}
              disabled={passphrase.length < 12 || (isExport && passphrase !== passphraseConfirmation)}
            >
              {isExport ? "Download encrypted backup" : "Unlock and import"}
            </Button>
          </Group>
        </Stack>
      </Modal>
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
  if (eventName === "input-rejected") return "warning";
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
  if (event.event === "input-rejected") {
    const count = Number(event.rejected_count || 0);
    const origin = event.source ? ` from ${event.source}` : "";
    return `${count} invalid input${count === 1 ? "" : "s"} skipped${origin}`;
  }
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
