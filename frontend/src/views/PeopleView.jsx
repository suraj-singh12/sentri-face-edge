import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Collapse,
  Divider,
  Drawer,
  Grid,
  Group,
  Image,
  Loader,
  Menu,
  Modal,
  NumberInput,
  Paper,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Tabs,
  TagsInput,
  Text,
  TextInput,
  Textarea,
  ThemeIcon,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconArchive,
  IconCalendar,
  IconChartDots,
  IconChevronDown,
  IconCopy,
  IconDots,
  IconEdit,
  IconFilter,
  IconEye,
  IconFlag,
  IconGlobe,
  IconGridDots,
  IconImageInPicture,
  IconLayoutList,
  IconMapPin,
  IconNotes,
  IconPhoto,
  IconPhotoStar,
  IconRefresh,
  IconSearch,
  IconSortDescending,
  IconStar,
  IconRestore,
  IconSwitchHorizontal,
  IconTrash,
  IconShield,
  IconUser,
  IconUserPlus,
  IconUsers,
} from "@tabler/icons-react";

import { EmptyCard, ImageFrame, SafeImage } from "../components/Shared.jsx";
import { CountrySelect } from "../components/CountrySelect.jsx";
import { NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import { PersonGraphView } from "./PersonGraphView.jsx";
import { RecognitionReferences } from "./RecognitionReferences.jsx";
import { eventDateTime } from "./EventsView.jsx";
import {
  currentDateTimeParts,
  detailsForEmbedding,
  formatSeenDateTime,
  mediaUrl,
  personProfile,
  personAllows,
  requirePersonContract,
} from "../utils.js";
export function PeopleView({
  canEdit = false,
  canDestroy = false,
  people,
  archivedPeople,
  peopleReadModel,
  deletedFaces = [],
  peopleGallery,
  peopleGalleryImage,
  personGraph,
  onRefresh,
  onOpen,
  onCreateIdentifiedPerson,
  onOpenGraph,
  onOpenGraphNode,
  onRefreshGraph,
  onCloseGraph,
  onImage,
  onBack,
  onSave,
  onSaveNotes,
  onQueryEncounters,
  onOpenEncounter,
  onCreateAssociation,
  onRetireAssociation,
  referenceActions,
  onFavorite,
  onSetRepresentative,
  onArchive,
  onRestore,
  onDelete,
  onMerge,
  onMovePhoto,
  onDeletePhoto,
  onRestoreDeletedFace,
  onPermanentlyDeleteFace,
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [groupBy, setGroupBy] = useState("country");
  const [sort, setSort] = useState("priority");
  const [viewMode, setViewMode] = useState("grid");
  const [pageSize, setPageSize] = useState("12");
  const [page, setPage] = useState(1);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [placeholderOpen, setPlaceholderOpen] = useState(false);
  const [placeholderBusy, setPlaceholderBusy] = useState(false);
  const [placeholderValues, setPlaceholderValues] = useState(() => newPlaceholderValues());
  const resultsRef = useRef(null);
  const normalizedQuery = query.trim().toLowerCase();
  const collectionKey = filter === "archived" ? "historical" : "active";
  const collectionStats = peopleReadModel?.statistics?.[collectionKey] || {};
  const visiblePeople = useMemo(() => {
    const collection = filter === "archived" ? archivedPeople : people;
    const filtered = collection
      .filter((person) => {
        if (filter === "favorites" && !person.favorite) return false;
        if (filter === "withPhotos" && !Number(person.embedding_count || 0)) return false;
        if (filter === "withoutPhotos" && Number(person.embedding_count || 0)) return false;
        if (!normalizedQuery) return true;
        return [
          person.name,
          person.person_id,
          person.created_at,
          person.metadata?.rank,
          person.metadata?.country,
          ...(person.tags || person.metadata?.tags || []),
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(normalizedQuery));
      });
    const order = peopleReadModel?.sort_orders?.[collectionKey]?.[sort] || [];
    const rank = new Map(order.map((personId, index) => [personId, index]));
    return [...filtered].sort((left, right) => (
      (rank.get(left.person_id) ?? Number.MAX_SAFE_INTEGER)
      - (rank.get(right.person_id) ?? Number.MAX_SAFE_INTEGER)
    ));
  }, [archivedPeople, collectionKey, filter, normalizedQuery, people, peopleReadModel, sort]);
  const pageCount = Number(pageSize);
  const totalPages = Math.max(1, Math.ceil(visiblePeople.length / pageCount));
  const safePage = Math.min(page, totalPages);
  const pageStart = (safePage - 1) * pageCount;
  const pagePeople = visiblePeople.slice(pageStart, pageStart + pageCount);
  const visibleDeletedFaces = useMemo(
    () => deletedFaces.filter((face) => [
      face.person_name,
      face.person_id,
      face.embedding_id,
    ].filter(Boolean).some((value) => String(value).toLowerCase().includes(normalizedQuery))),
    [deletedFaces, normalizedQuery],
  );

  useEffect(() => {
    setPage(1);
    resultsRef.current?.scrollTo({ top: 0 });
  }, [filter, groupBy, normalizedQuery, pageSize, sort, viewMode]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  useEffect(() => {
    resultsRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [safePage]);
  const toggleFavorite = (person) => { if (canEdit) onFavorite(person.person_id, !person.favorite); };

  return (
    <Paper withBorder radius="md" p="md" className="people-workspace">
      {personGraph?.active && personGraph.personId ? (
        <PersonGraphView
          state={personGraph}
          onBack={onCloseGraph}
          onRefresh={onRefreshGraph}
          onOpenNode={onOpenGraphNode}
        />
      ) : peopleGallery ? (
        <PeopleGalleryView
          payload={peopleGallery}
          people={people}
          selectedImage={peopleGalleryImage}
          onImage={onImage}
          onOpen={onOpen}
          onBack={onBack}
          canEdit={canEdit}
          canDestroy={canDestroy}
          onSave={onSave}
          onSaveNotes={onSaveNotes}
          onQueryEncounters={onQueryEncounters}
          onOpenEncounter={onOpenEncounter}
          onCreateAssociation={onCreateAssociation}
          onRetireAssociation={onRetireAssociation}
          referenceActions={referenceActions}
          onCreateIdentifiedPerson={onCreateIdentifiedPerson}
          onOpenGraph={onOpenGraph}
          onFavorite={onFavorite}
          onSetRepresentative={onSetRepresentative}
          onArchive={onArchive}
          onRestore={onRestore}
          onDelete={onDelete}
          onMerge={onMerge}
          onMovePhoto={onMovePhoto}
          onDeletePhoto={onDeletePhoto}
        />
      ) : (
        <Grid gutter="lg" className="people-library-shell">
          <Grid.Col span={{ base: 12, md: "content" }} className="people-library-sidebar-col">
            <PeopleLibrarySidebar
              people={people}
              archivedPeople={archivedPeople}
              deletedFaces={deletedFaces}
              activeFilter={filter}
              canDestroy={canDestroy}
              onFilter={setFilter}
              onRefresh={onRefresh}
            />
          </Grid.Col>
          <Grid.Col span="auto" className="people-library-main-col">
            <Stack gap="md" className="people-library-main">
              <Group justify="space-between" align="flex-start" gap="md" className="people-library-header">
                <Box>
                  <Group gap="xs" align="baseline">
                    <Title order={3} size="h4">{filter === "deleted" ? "Deleted Faces" : "People"}</Title>
                    <Text size="xs" c="dimmed">
                      ({filter === "deleted" ? deletedFaces.length : filter === "archived" ? archivedPeople.length : people.length})
                    </Text>
                  </Group>
                  <Text size="sm" c="dimmed">
                    {filter === "deleted"
                      ? "Restore faces or permanently delete them before automatic cleanup"
                      : filter === "archived"
                        ? "Restore archived identities or review their history"
                        : "Manage and browse all known identities"}
                  </Text>
                </Box>
                {filter === "deleted" ? (
                  <Group gap="sm">
                    <TextInput
                      value={query}
                      onChange={(event) => setQuery(event.currentTarget.value)}
                      placeholder="Search deleted faces..."
                      leftSection={<IconSearch size={18} />}
                      className="people-search"
                    />
                    <Button variant="default" leftSection={<IconRefresh size={16} />} onClick={onRefresh}>Refresh</Button>
                  </Group>
                ) : (
                  <Group gap="sm" align="flex-start">
                    <PeopleToolbar
                      query={query}
                      filter={filter}
                      groupBy={groupBy}
                      sort={sort}
                      viewMode={viewMode}
                      onQuery={setQuery}
                      onFilter={setFilter}
                      onGroupBy={setGroupBy}
                      onSort={setSort}
                      onViewMode={setViewMode}
                    />
                    {canEdit && filter !== "archived" && (
                      <Button leftSection={<IconUserPlus size={16} />} onClick={() => {
                        setPlaceholderValues(newPlaceholderValues());
                        setPlaceholderOpen(true);
                      }}>
                        Add without photo
                      </Button>
                    )}
                  </Group>
                )}
              </Group>
              {filter === "deleted" ? (
                <DeletedFacesPanel
                  faces={visibleDeletedFaces}
                  onOpenPerson={onOpen}
                  onRestore={onRestoreDeletedFace}
                  onPurge={onPermanentlyDeleteFace}
                />
              ) : (
                <>
                  <PeopleStatsStrip
                    statistics={collectionStats}
                    archived={filter === "archived"}
                  />
                  <Box ref={resultsRef} className="people-results-scroll">
                    {pagePeople.length ? (
                      <PeopleResults
                        people={pagePeople}
                        groupBy={groupBy}
                        viewMode={viewMode}
                        archived={filter === "archived"}
                        canDestroy={canDestroy}
                        onOpen={onOpen}
                        onFavorite={toggleFavorite}
                        onDelete={(person) => {
                          setDeleteTarget(person);
                          setDeleteConfirmation("");
                        }}
                      />
                    ) : (
                      <EmptyCard text="No people match the current search." />
                    )}
                  </Box>
                  <PeoplePagination
                    total={visiblePeople.length}
                    shown={pagePeople.length}
                    start={pageStart}
                    page={safePage}
                    pageSize={pageSize}
                    onPage={setPage}
                    onPageSize={setPageSize}
                  />
                </>
              )}
            </Stack>
          </Grid.Col>
        </Grid>
      )}
      <Modal
        opened={placeholderOpen}
        onClose={() => !placeholderBusy && setPlaceholderOpen(false)}
        title="Add person without a photograph"
        size="xl"
        centered
      >
        <form onSubmit={async (event) => {
          event.preventDefault();
          if (placeholderBusy || !placeholderValues.name.trim()) return;
          setPlaceholderBusy(true);
          try {
            await onCreateIdentifiedPerson(placeholderValues);
            setPlaceholderValues(newPlaceholderValues());
            setPlaceholderOpen(false);
          } finally {
            setPlaceholderBusy(false);
          }
        }}>
          <Stack>
            <Alert color="orange" title="This creates an identity without a face" icon={<IconUserPlus size={18} />}>
              No photograph or biometric data will be stored. Add only observation details you actually know; a face can be enrolled later.
            </Alert>
            <PlaceholderPersonFields values={placeholderValues} onChange={setPlaceholderValues} people={people} />
            <Group justify="flex-end">
              <Button type="button" variant="default" disabled={placeholderBusy} onClick={() => setPlaceholderOpen(false)}>Cancel</Button>
              <Button type="submit" loading={placeholderBusy} disabled={!placeholderValues.name.trim()}>Create person</Button>
            </Group>
          </Stack>
        </form>
      </Modal>
      <Modal
        opened={Boolean(deleteTarget)}
        onClose={() => {
          if (deleteBusy) return;
          setDeleteTarget(null);
          setDeleteConfirmation("");
        }}
        title="Delete entire profile permanently?"
        centered
      >
        <Stack>
          <Alert color="red" icon={<IconShield size={18} />} title="This tombstones the identity">
            {deleteTarget?.name} will leave active use. Historical identity, sightings, relationships, and operation provenance remain represented. A verified safety backup is created first.
          </Alert>
          <TextInput
            label="Type DELETE to confirm"
            value={deleteConfirmation}
            onChange={(event) => setDeleteConfirmation(event.currentTarget.value)}
            autoComplete="off"
          />
          <Group justify="flex-end">
            <Button variant="default" disabled={deleteBusy} onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button
              color="red"
              loading={deleteBusy}
              disabled={deleteConfirmation !== "DELETE"}
              leftSection={<IconTrash size={16} />}
              onClick={async () => {
                if (!deleteTarget || deleteBusy) return;
                setDeleteBusy(true);
                try {
                  await onDelete(deleteTarget.person_id);
                  setDeleteTarget(null);
                  setDeleteConfirmation("");
                } catch (error) {
                  console.error(error);
                } finally {
                  setDeleteBusy(false);
                }
              }}
            >
              Delete entire profile
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Paper>
  );
}

function PeopleToolbar({ query, filter, groupBy, sort, viewMode, onQuery, onFilter, onGroupBy, onSort, onViewMode }) {
  const filterLabel = {
    all: "Filter",
    favorites: "Favorites",
    withPhotos: "With Photos",
    withoutPhotos: "No Photos",
    archived: "Archived",
  }[filter];
  const groupLabel = {
    none: "None",
    country: "Country",
    rank: "Rank",
    priority: "Priority",
    frequency: "Sightings Frequency",
    frequent: "Frequently Seen",
  }[groupBy];
  const sortLabel = {
    recent: "Newest Added",
    name: "Name",
    country: "Country",
    rank: "Rank",
    priority: "Priority",
    sightings: "Most Sightings",
    frequency: "Sightings Frequency",
    seen: "Recently Seen",
    frequent: "Frequently Seen",
  }[sort];
  return (
    <Group gap="sm" className="people-toolbar">
      <TextInput
        value={query}
        onChange={(event) => onQuery(event.currentTarget.value)}
        placeholder="Search by name, ID or tag..."
        leftSection={<IconSearch size={18} />}
        className="people-search"
      />
      <Menu withinPortal position="bottom-start">
        <Menu.Target>
          <Button variant="default" leftSection={<IconFilter size={16} />} rightSection={<IconChevronDown size={15} />}>{filterLabel}</Button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item onClick={() => onFilter("all")}>All People</Menu.Item>
          <Menu.Item onClick={() => onFilter("favorites")}>Favorites</Menu.Item>
          <Menu.Item onClick={() => onFilter("withPhotos")}>With Photos</Menu.Item>
          <Menu.Item onClick={() => onFilter("withoutPhotos")}>No Photos</Menu.Item>
        </Menu.Dropdown>
      </Menu>
      <Menu withinPortal position="bottom-start">
        <Menu.Target>
          <Button variant="default" rightSection={<IconChevronDown size={15} />}>Group by: {groupLabel}</Button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item onClick={() => onGroupBy("none")}>None</Menu.Item>
          <Menu.Item onClick={() => onGroupBy("country")}>Country</Menu.Item>
          <Menu.Item onClick={() => onGroupBy("rank")}>Rank</Menu.Item>
          <Menu.Item onClick={() => onGroupBy("priority")}>Priority</Menu.Item>
          <Menu.Item onClick={() => onGroupBy("frequency")}>Sightings Frequency</Menu.Item>
          <Menu.Item onClick={() => onGroupBy("frequent")}>Frequently Seen</Menu.Item>
        </Menu.Dropdown>
      </Menu>
      <Menu withinPortal position="bottom-start">
        <Menu.Target>
          <Button variant="default" leftSection={<IconSortDescending size={16} />} rightSection={<IconChevronDown size={15} />}>Sort: {sortLabel}</Button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item onClick={() => onSort("recent")}>Newest Added</Menu.Item>
          <Menu.Item onClick={() => onSort("name")}>Name</Menu.Item>
          <Menu.Item onClick={() => onSort("country")}>Country</Menu.Item>
          <Menu.Item onClick={() => onSort("rank")}>Rank</Menu.Item>
          <Menu.Item onClick={() => onSort("priority")}>Priority</Menu.Item>
          <Menu.Item onClick={() => onSort("sightings")}>Most Sightings</Menu.Item>
          <Menu.Item onClick={() => onSort("frequency")}>Sightings Frequency</Menu.Item>
          <Menu.Item onClick={() => onSort("seen")}>Recently Seen</Menu.Item>
          <Menu.Item onClick={() => onSort("frequent")}>Frequently Seen</Menu.Item>
        </Menu.Dropdown>
      </Menu>
      <Group gap={0} className="people-view-toggle">
        <Tooltip label="Grid view">
          <ActionIcon variant={viewMode === "grid" ? "light" : "default"} onClick={() => onViewMode("grid")} aria-label="Grid view"><IconGridDots size={17} /></ActionIcon>
        </Tooltip>
        <Tooltip label="List view">
          <ActionIcon variant={viewMode === "list" ? "light" : "default"} onClick={() => onViewMode("list")} aria-label="List view"><IconLayoutList size={17} /></ActionIcon>
        </Tooltip>
      </Group>
    </Group>
  );
}

function PeopleLibrarySidebar({
  canDestroy,
  people,
  archivedPeople,
  deletedFaces,
  activeFilter,
  onFilter,
  onRefresh,
}) {
  const collectionItems = [
    { key: "all", label: "All People", icon: IconImageInPicture, count: people.length },
    { key: "favorites", label: "Favorites", icon: IconStar, count: people.filter((person) => person.favorite).length },
    { key: "withPhotos", label: "With Photos", icon: IconPhoto, count: people.filter((person) => Number(person.embedding_count || 0)).length },
    { key: "withoutPhotos", label: "No Photos", icon: IconUser, count: people.filter((person) => !Number(person.embedding_count || 0)).length },
    { key: "archived", label: "Archived", icon: IconArchive, count: archivedPeople.length },
    ...(canDestroy ? [{ key: "deleted", label: "Deleted Faces", icon: IconTrash, count: deletedFaces.length }] : []),
  ];
  return (
    <Stack className="people-library-sidebar">
      <Box>
        <Text size="xs" c="dimmed" fw={800} tt="uppercase" mb="sm">Collections</Text>
        <Stack gap={4}>
          {collectionItems.map((item) => {
            const Icon = item.icon;
            return (
              <Button
                key={item.key}
                variant={activeFilter === item.key ? "light" : "subtle"}
                color={activeFilter === item.key ? "teal" : "gray"}
                justify="space-between"
                leftSection={<Icon size={16} />}
                rightSection={<Text size="xs" c={activeFilter === item.key ? "teal.3" : "dimmed"}>{item.count}</Text>}
                onClick={() => onFilter(item.key)}
                className="people-sidebar-button"
              >
                {item.label}
              </Button>
            );
          })}
        </Stack>
      </Box>
      <Divider />
      <Paper withBorder radius="md" p="sm" className="people-refresh-card">
        <Group justify="space-between" wrap="nowrap">
          <Box>
            <Text size="xs" c="dimmed">Last refreshed</Text>
            <Text size="xs">{new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</Text>
          </Box>
          <ActionIcon variant="subtle" onClick={onRefresh} aria-label="Refresh people"><IconRefresh size={18} /></ActionIcon>
        </Group>
      </Paper>
    </Stack>
  );
}

function DeletedFacesPanel({ faces, onOpenPerson, onRestore, onPurge }) {
  const [pendingPurge, setPendingPurge] = useState(null);
  const [busyId, setBusyId] = useState("");
  const [purgeConfirmation, setPurgeConfirmation] = useState("");
  const run = async (face, action) => {
    setBusyId(face.embedding_id);
    try {
      await action();
      setPendingPurge(null);
      setPurgeConfirmation("");
    } catch (error) {
      console.error(error);
    } finally {
      setBusyId("");
    }
  };
  return (
    <>
      <Paper withBorder radius="md" p="md" className="deleted-faces-notice">
        <Group align="flex-start" wrap="nowrap">
          <ThemeIcon color="yellow" variant="light"><IconTrash size={18} /></ThemeIcon>
          <Box>
            <Text fw={800} size="sm">30-day recovery window</Text>
            <Text size="xs" c="dimmed">
              Deleted faces are excluded from recognition immediately. Their linked sightings remain intact until live-library erasure. Safety backups may retain recovery copies.
            </Text>
          </Box>
        </Group>
      </Paper>
      <Box className="people-results-scroll">
        {faces.length ? (
          <SimpleGrid cols={{ base: 1, sm: 2, xl: 3 }} spacing="md">
            {faces.map((face) => {
              const path = face.crop_path || face.source_image;
              const busy = busyId === face.embedding_id;
              return (
                <Card key={face.embedding_id} withBorder radius="md" className="deleted-face-card">
                  <Group align="flex-start" wrap="nowrap">
                    <Image
                      src={path ? mediaUrl(path) : ""}
                      alt={`Deleted face for ${face.person_name}`}
                      w={92}
                      h={92}
                      radius="md"
                      fit="cover"
                    />
                    <Box miw={0} style={{ flex: 1 }}>
                      <Group justify="space-between" gap="xs" wrap="nowrap">
                        <Text fw={900} truncate>{face.person_name}</Text>
                        <Badge color={face.days_remaining <= 3 ? "red" : "yellow"} variant="light">
                          {face.days_remaining} day{face.days_remaining === 1 ? "" : "s"} left
                        </Badge>
                      </Group>
                      <Text size="xs" c="dimmed" mt={4}>Deleted {compactChangeDate(face.deleted_at)}</Text>
                      <Text size="xs" c="dimmed">
                        Scheduled live erasure {compactChangeDate(face.purge_after)}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {face.sighting_count} linked sighting{face.sighting_count === 1 ? "" : "s"} retained
                      </Text>
                    </Box>
                  </Group>
                  {face.person_lifecycle_status !== "ACTIVE" && (
                    <Text size="xs" c="yellow.4" mt="sm">
                      This face belongs to a {String(face.person_lifecycle_status || "historical").toLowerCase()} identity and cannot be restored here.
                    </Text>
                  )}
                  <Group grow mt="md">
                    <Button
                      variant="default"
                      size="xs"
                      disabled={face.person_lifecycle_status !== "ACTIVE"}
                      onClick={() => onOpenPerson(face.person_id, { archived: false })}
                    >
                      View person
                    </Button>
                    <Button
                      variant="light"
                      size="xs"
                      leftSection={<IconRestore size={15} />}
                      disabled={face.person_lifecycle_status !== "ACTIVE"}
                      loading={busy}
                      onClick={() => run(face, () => onRestore(face.embedding_id, face.person_id))}
                    >
                      Restore
                    </Button>
                  </Group>
                  <Button
                    fullWidth
                    mt="xs"
                    color="red"
                    variant="subtle"
                    size="xs"
                    leftSection={<IconTrash size={15} />}
                    disabled={Boolean(busyId)}
                    onClick={() => { setPendingPurge(face); setPurgeConfirmation(""); }}
                  >
                    Erase from live library
                  </Button>
                </Card>
              );
            })}
          </SimpleGrid>
        ) : (
          <EmptyCard text="No deleted faces. Removed faces will remain recoverable here for 30 days." />
        )}
      </Box>
      <Modal
        opened={Boolean(pendingPurge)}
        onClose={() => { if (!busyId) { setPendingPurge(null); setPurgeConfirmation(""); } }}
        title="Erase this face from the live library?"
        centered
        closeOnClickOutside={!busyId}
        closeOnEscape={!busyId}
      >
        <Stack>
          <Text size="sm">
            This removes the active face record and {pendingPurge?.sighting_count || 0} linked sighting{pendingPurge?.sighting_count === 1 ? "" : "s"} from the live library.
          </Text>
          <Alert color="yellow" title="A recovery copy will still exist">
            SentriFace creates and verifies a safety backup before erasing the live data. That backup, older managed backups, and any exported backup files may still contain this face. Delete those copies separately if complete erasure is required.
          </Alert>
          <TextInput
            label='Type ERASE to confirm'
            value={purgeConfirmation}
            onChange={(event) => setPurgeConfirmation(event.currentTarget.value)}
            disabled={Boolean(busyId)}
            autoComplete="off"
          />
          <Group justify="flex-end">
            <Button variant="default" disabled={Boolean(busyId)} onClick={() => { setPendingPurge(null); setPurgeConfirmation(""); }}>Cancel</Button>
            <Button
              color="red"
              loading={Boolean(busyId)}
              disabled={purgeConfirmation !== "ERASE"}
              leftSection={<IconTrash size={16} />}
              onClick={() => pendingPurge && run(
                pendingPurge,
                () => onPurge(pendingPurge.embedding_id),
              )}
            >
              Erase from live library
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

function PeopleStatsStrip({ statistics, archived }) {
  const stats = archived ? [
    { label: "Archived Records", value: statistics.people_count || 0, icon: IconArchive, color: "gray" },
    { label: "Retained Photos", value: Number(statistics.embedding_count || 0).toLocaleString(), icon: IconImageInPicture, color: "violet" },
    { label: "Merged Records", value: statistics.merged_count || 0, icon: IconSwitchHorizontal, color: "blue" },
    { label: "Archived Today", value: statistics.archived_today_count || 0, icon: IconRefresh, color: "green" },
  ] : [
    { label: "Total People", value: statistics.people_count || 0, icon: IconUser, color: "teal" },
    { label: "With Photos", value: statistics.with_photos_count || 0, icon: IconImageInPicture, color: "violet" },
    { label: "No Photos", value: statistics.without_photos_count || 0, icon: IconUser, color: "indigo" },
    { label: "Favorites", value: statistics.favorite_count || 0, icon: IconStar, color: "yellow" },
    { label: "Seen in last 7 days", value: statistics.seen_last_7_days_count || 0, icon: IconEye, color: "blue" },
    { label: "Added Today", value: statistics.added_today_count || 0, icon: IconRefresh, color: "blue" },
  ];
  return (
    <SimpleGrid cols={{ base: 2, sm: 3, lg: archived ? 4 : 6 }} spacing="sm" className="people-stats-strip">
      {stats.map((item) => {
        const Icon = item.icon;
        return (
          <Paper key={item.label} withBorder radius="md" p="md" className="people-stat-card">
            <Group wrap="nowrap">
              <ThemeIcon size={42} radius="md" color={item.color} variant="light"><Icon size={24} /></ThemeIcon>
              <Box>
                <Text fw={900} size="xl">{item.value}</Text>
                <Text size="xs" c="dimmed">{item.label}</Text>
              </Box>
            </Group>
          </Paper>
        );
      })}
    </SimpleGrid>
  );
}

function PeopleResults({ people, groupBy, viewMode, archived, canDestroy, onOpen, onFavorite, onDelete }) {
  const groups = useMemo(() => groupPeople(people, groupBy), [groupBy, people]);
  const groupSignature = groups.map((group) => group.label).join("\u0000");
  const [closedGroups, setClosedGroups] = useState(new Set());

  useEffect(() => {
    setClosedGroups(new Set(groupBy === "none" ? [] : groups.slice(1).map((group) => group.label)));
  }, [groupBy, groupSignature]);

  const cards = (items) => (
    <Box className={viewMode === "list" ? "people-card-list" : "people-card-grid"}>
      {items.map((person) => {
        const lifecycleStatus = requirePersonContract(person).lifecycle_status;
        const isHistorical = lifecycleStatus !== "ACTIVE";
        return (
          <PersonCard
            key={person.person_id}
            person={person}
            favorite={Boolean(person.favorite)}
            archived={isHistorical}
            viewMode={viewMode}
            canDestroy={canDestroy}
            onOpen={() => onOpen(person.person_id, { archived: isHistorical })}
            onFavorite={() => onFavorite(person)}
            onDelete={() => onDelete(person)}
          />
        );
      })}
    </Box>
  );

  if (groupBy === "none") return cards(people);
  return (
    <Stack gap="xs" className="people-group-stack">
      {groups.map((group) => {
        const closed = closedGroups.has(group.label);
        return (
          <Paper key={group.label} withBorder radius="md" className="people-group-section">
            <Box
              component="button"
              type="button"
              className="people-group-header"
              onClick={() => setClosedGroups((current) => {
                const next = new Set(current);
                if (next.has(group.label)) next.delete(group.label);
                else next.add(group.label);
                return next;
              })}
              aria-expanded={!closed}
            >
              <Group gap="sm" wrap="nowrap">
                <IconGlobe size={16} />
                <Text fw={900} size="sm">{group.label}</Text>
                <Badge variant="light" color="gray" size="sm">{group.people.length} {group.people.length === 1 ? "person" : "people"}</Badge>
              </Group>
              <IconChevronDown size={18} className={closed ? "" : "people-group-chevron--open"} />
            </Box>
            <Collapse expanded={!closed}>
              <Box className="people-group-content">{cards(group.people)}</Box>
            </Collapse>
          </Paper>
        );
      })}
    </Stack>
  );
}

function PersonCard({ person, favorite, archived, viewMode, canDestroy, onOpen, onFavorite, onDelete }) {
  const cardClass = viewMode === "list" ? "people-person-card people-person-card--list" : "people-person-card";
  const lifecycleStatus = requirePersonContract(person).lifecycle_status;
  const historical = lifecycleStatus !== "ACTIVE";
  const canOpen = lifecycleStatus === "ACTIVE" || (lifecycleStatus === "ARCHIVED" && personAllows(person, "VIEW_HISTORY"));
  const openPerson = () => {
    if (canOpen) onOpen(person.person_id);
  };
  const toggleFavorite = (event) => {
    event.stopPropagation();
    onFavorite();
  };
  const photoCount = Number(person.embedding_count || 0);
  const sightings = sightingCount(person);
  const rank = profileValue(person, "rank") || "—";
  const priority = priorityDetails(person);
  const photoFallback = <ThemeIcon size={54} radius="xl" variant="light" color="gray"><IconUser size={32} /></ThemeIcon>;
  return (
    <Card withBorder radius="md" p="xs" className={cardClass}>
      <Stack gap="xs" align="stretch" className="people-person-card-inner">
        <Box component="button" type="button" className="people-card-main" onClick={openPerson} disabled={!canOpen} aria-label={`${historical ? "Historical identity" : "Open"} ${person.name}`}>
          <Box className="people-card-image-wrap">
            <ImageFrame variant="peopleCard">
              <SafeImage
                src={person.representative_image ? mediaUrl(person.representative_image) : ""}
                alt={person.name}
                fit="cover"
                h="100%"
                fallback={photoFallback}
              />
            </ImageFrame>
          </Box>
          <Box miw={0} className="people-card-copy">
            <Group justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
              <Text fw={800} lineClamp={1}>{person.name}</Text>
              {historical && <Badge color="gray" variant="light">{lifecycleStatusLabel(lifecycleStatus)}</Badge>}
            </Group>
            <Group gap="xs" mt={4} wrap="nowrap">
              <Text size="xs" c="dimmed" fw={700}>{rank}</Text>
              <Badge color={priority.color} variant="light" size="xs">{priority.label}</Badge>
            </Group>
            <Text size="xs" c="dimmed" mt={5}>
              {person.is_placeholder ? "No usable recognition sample" : <>{photoCount} {photoCount === 1 ? "photo" : "photos"} <Text span mx={5}>·</Text> {sightings} {sightings === 1 ? "sighting" : "sightings"}</>}
            </Text>
            <Text size="xs" c={person.last_seen_at ? "teal.4" : "dimmed"} mt={3}>{lastSeenLabelForCard(person.last_seen_at)}</Text>
          </Box>
        </Box>
        <ActionIcon
          size="sm"
          radius="xl"
          color={favorite ? "yellow" : "teal"}
          variant="filled"
          className="people-card-star"
          onClick={toggleFavorite}
          disabled={historical}
          aria-label={historical ? "Historical identity" : favorite ? "Remove favorite" : "Add favorite"}
        >
          {favorite ? <IconStar size={15} fill="currentColor" /> : <IconStar size={15} />}
        </ActionIcon>
        <Group justify="space-between" wrap="nowrap" className="people-card-actions">
          <Button fullWidth size="compact-xs" variant="subtle" disabled={!canOpen} onClick={(event) => { event.stopPropagation(); openPerson(); }}>
            {canOpen ? "Open profile" : lifecycleStatusLabel(lifecycleStatus)}
          </Button>
          <Menu withinPortal position="bottom-end">
            <Menu.Target>
              <ActionIcon variant="subtle" onClick={(event) => event.stopPropagation()} aria-label="More actions"><IconDots size={16} /></ActionIcon>
            </Menu.Target>
            <Menu.Dropdown onClick={(event) => event.stopPropagation()}>
              <Menu.Item leftSection={<IconCopy size={14} />} onClick={() => navigator.clipboard?.writeText(person.person_id)}>
                Copy ID
              </Menu.Item>
              <Menu.Divider />
              <Menu.Item color="red" leftSection={<IconTrash size={14} />} disabled={!canDestroy} onClick={onDelete}>
                Delete entire profile
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </Stack>
    </Card>
  );
}

function PeoplePagination({ total, shown, start, page, pageSize, onPage, onPageSize }) {
  const size = Number(pageSize) || 12;
  const totalPages = Math.max(1, Math.ceil(total / size));
  const firstVisiblePage = Math.max(1, Math.min(page - 2, totalPages - 4));
  const visiblePages = Array.from(
    { length: Math.min(totalPages, 5) },
    (_, index) => firstVisiblePage + index,
  );
  return (
    <Paper withBorder radius="md" p="sm" className="people-pagination">
      <Group justify="space-between">
        <Group gap="sm">
          <Text size="sm" c="dimmed">Show</Text>
          <Select value={pageSize} onChange={(value) => onPageSize(value || "12")} data={["8", "12", "24"]} w={80} />
          <Text size="sm" c="dimmed">Showing {shown ? `${start + 1} to ${start + shown}` : "0"} of {total} people</Text>
        </Group>
        <Group gap="xs">
          <ActionIcon variant="default" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page"><IconArrowLeft size={16} /></ActionIcon>
          {visiblePages.map((pageNumber) => (
            <ActionIcon
              key={pageNumber}
              variant={pageNumber === page ? "filled" : "light"}
              onClick={() => onPage(pageNumber)}
              aria-label={`Page ${pageNumber}`}
              aria-current={pageNumber === page ? "page" : undefined}
            >
              {pageNumber}
            </ActionIcon>
          ))}
          {totalPages > 5 && firstVisiblePage + visiblePages.length - 1 < totalPages && <Text c="dimmed">...</Text>}
          <ActionIcon variant="default" disabled={page >= totalPages} onClick={() => onPage(page + 1)} aria-label="Next page"><IconChevronDown size={16} style={{ transform: "rotate(-90deg)" }} /></ActionIcon>
        </Group>
      </Group>
    </Paper>
  );
}

function groupPeople(people, groupBy) {
  if (groupBy === "none") return [{ label: "All People", people }];
  const grouped = new Map();
  people.forEach((person) => {
    const label = groupLabelForPerson(person, groupBy);
    grouped.set(label, [...(grouped.get(label) || []), person]);
  });
  const preferredOrder = {
    priority: ["High Priority", "Watch Priority", "Regular Priority", "Unspecified Priority"],
    frequency: ["Very Frequent", "Frequent", "Occasional", "Rare", "Never Seen"],
    frequent: ["Frequently Seen", "Seen Occasionally", "Not Seen Yet"],
  }[groupBy];
  return [...grouped.entries()]
    .map(([label, groupedPeople]) => ({ label, people: groupedPeople }))
    .sort((left, right) => {
      if (preferredOrder) return preferredOrder.indexOf(left.label) - preferredOrder.indexOf(right.label);
      if (/^(Unknown|Unspecified)/.test(left.label)) return 1;
      if (/^(Unknown|Unspecified)/.test(right.label)) return -1;
      return compareText(left.label, right.label);
    });
}

function groupLabelForPerson(person, groupBy) {
  if (groupBy !== "none") return person.presentation?.group_labels?.[groupBy] || "Unspecified";
  return "All People";
}

function profileValue(person, key) {
  return String(person?.metadata?.[key] || "").trim();
}

function compareText(left, right) {
  return String(left || "").localeCompare(String(right || ""), undefined, { sensitivity: "base" });
}

function daysSince(value) {
  const timestamp = new Date(value || 0).getTime();
  if (!timestamp) return Number.POSITIVE_INFINITY;
  return Math.max(0, (Date.now() - timestamp) / 86_400_000);
}

function sightingCount(person) {
  return Number(person?.sighting_count || 0);
}

function priorityDetails(person) {
  const label = person.presentation?.priority_label || "UNSPECIFIED";
  const color = { HIGH: "red", WATCH: "orange", REGULAR: "yellow" }[label] || "gray";
  return { label, color };
}

function lastSeenLabelForCard(value) {
  const days = daysSince(value);
  if (!Number.isFinite(days)) return "Never seen";
  if (days < 1) return "Seen today";
  const rounded = Math.floor(days);
  return `Seen ${rounded} day${rounded === 1 ? "" : "s"} ago`;
}

function PeopleGalleryView({
  canEdit,
  canDestroy,
  payload,
  people,
  selectedImage,
  onImage,
  onOpen,
  onBack,
  onSave,
  onSaveNotes,
  onQueryEncounters,
  onOpenEncounter,
  onCreateAssociation,
  onRetireAssociation,
  referenceActions,
  onCreateIdentifiedPerson,
  onOpenGraph,
  onFavorite,
  onSetRepresentative,
  onArchive,
  onRestore,
  onDelete,
  onMerge,
  onMovePhoto,
  onDeletePhoto,
}) {
  const imageRecords = profileImageRecords(payload);
  const tabContentRef = useRef(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [referenceOpen, setReferenceOpen] = useState(false);
  const [referenceAdding, setReferenceAdding] = useState(false);
  const [personEvents, setPersonEvents] = useState({ events: [], next_cursor: null });
  const [personEventFilters, setPersonEventFilters] = useState({ search: "", date_from: "", date_to: "", location: "", context: "", person_status: "" });
  const [personEventPageCursors, setPersonEventPageCursors] = useState([""]);
  const [editOpen, setEditOpen] = useState(false);
  const [notesEditOpen, setNotesEditOpen] = useState(false);
  const [managementDialog, setManagementDialog] = useState(null);
  const [managementConflict, setManagementConflict] = useState(null);
  const [targetPersonId, setTargetPersonId] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const [profileDeleteConfirmation, setProfileDeleteConfirmation] = useState("");
  const normalizedPerson = requirePersonContract(payload.person);
  const profileNote = payload.profile_note || { content: "", mentioned_person_ids: [], mentions: [] };
  const [notesDraft, setNotesDraft] = useState(profileNote.content);
  const [notesBusy, setNotesBusy] = useState(false);
  const [selectedNoteMentionIds, setSelectedNoteMentionIds] = useState(profileNote.mentioned_person_ids || []);
  const [notePlaceholderOpen, setNotePlaceholderOpen] = useState(false);
  const [notePlaceholderBusy, setNotePlaceholderBusy] = useState(false);
  const [notePlaceholderValues, setNotePlaceholderValues] = useState(() => newPlaceholderValues());
  const lifecycleStatus = normalizedPerson.lifecycle_status;
  const archived = lifecycleStatus !== "ACTIVE";
  const canRestore = lifecycleStatus === "ARCHIVED";
  const mergedInto = normalizedPerson.canonical_person_id || "";
  const favorite = Boolean(payload.person.favorite || payload.person.metadata?.favorite);
  const selectedRecord = selectedImage
    ? imageRecords.find((record) => record.path === selectedImage || record.thumbPath === selectedImage) || imageRecords[0]
    : imageRecords[0] || null;
  const selectedPath = selectedRecord?.path || "";
  const selectedDetails = selectedRecord ? detailsForEmbedding(payload.details || [], selectedRecord.embeddingId) : [];
  const profile = personProfile(payload, Boolean(selectedRecord));
  const summaryProfile = personProfile(payload);
  const latestSightings = payload.sightings || [];
  const recentSightings = latestSightings.slice(0, 3);
  const latestSightingLabel = lastSeenLabel(latestSightings[0]);
  const activity = payload.activity || [];
  const relationships = payload.relationships || [];
  const activeMentionQuery = noteMentionQuery(notesDraft);
  const noteMentionSuggestions = useMemo(() => {
    if (!notesEditOpen || activeMentionQuery.length < 3) return [];
    const normalized = activeMentionQuery.toLocaleLowerCase();
    return people.filter((candidate) => (
      candidate.person_id !== payload.person.person_id
      && personAllows(candidate, "OPEN")
      && [candidate.name, candidate.person_id, candidate.metadata?.rank, candidate.metadata?.country]
        .filter(Boolean)
        .some((value) => String(value).toLocaleLowerCase().includes(normalized))
    )).slice(0, 6);
  }, [activeMentionQuery, notesEditOpen, payload.person.person_id, people]);
  const noteMentionHasExactPerson = activeMentionQuery.length >= 3 && people.some(
    (candidate) => candidate.name.trim().toLocaleLowerCase() === activeMentionQuery.toLocaleLowerCase(),
  );
  const noteMentionCanCreate = notesEditOpen
    && activeMentionQuery.length >= 3
    && !noteMentionHasExactPerson;
  const [editValues, setEditValues] = useState(summaryProfile);

  useEffect(() => {
    setActiveTab("overview");
    setPersonEvents({ events: [], next_cursor: null });
    setPersonEventPageCursors([""]);
    setEditOpen(false);
    setNotesEditOpen(false);
    setNotePlaceholderOpen(false);
    setManagementDialog(null);
    setManagementConflict(null);
    setTargetPersonId("");
    setProfileDeleteConfirmation("");
    setSelectedNoteMentionIds(profileNote.mentioned_person_ids || []);
  }, [payload.person.person_id]);

  useEffect(() => {
    if (activeTab !== "events" || !onQueryEncounters) return;
    let active = true;
    onQueryEncounters({ person_id: payload.person.person_id, ...personEventFilters, cursor: personEventPageCursors.at(-1) })
      .then((page) => { if (active) setPersonEvents(page); })
      .catch(() => { if (active) setPersonEvents({ events: [], next_cursor: null }); });
    return () => { active = false; };
  }, [activeTab, onQueryEncounters, payload.person.person_id, JSON.stringify(personEventFilters), JSON.stringify(personEventPageCursors)]);

  useEffect(() => {
    setNotesDraft(profileNote.content);
    setSelectedNoteMentionIds(profileNote.mentioned_person_ids || []);
  }, [payload.person.person_id, profileNote.content, JSON.stringify(profileNote.mentioned_person_ids || [])]);

  const openProfileEdit = () => {
    setEditValues({ ...summaryProfile, editorName: "" });
    setEditOpen(true);
  };
  const openNotesEdit = () => {
    setNotesDraft(profileNote.content);
    setSelectedNoteMentionIds(profileNote.mentioned_person_ids || []);
    setNotesEditOpen(true);
  };
  const cancelNotesEdit = () => {
    setNotesDraft(profileNote.content);
    setSelectedNoteMentionIds(profileNote.mentioned_person_ids || []);
    setNotesEditOpen(false);
  };
  const openNotePlaceholder = () => {
    setNotePlaceholderValues(newPlaceholderValues(activeMentionQuery));
    setNotePlaceholderOpen(true);
  };

  useEffect(() => {
    setEditValues({ ...summaryProfile, editorName: "" });
  }, [
    payload.person.person_id,
    payload.person.name,
    payload.person.metadata?.rank,
    payload.person.metadata?.country,
    payload.person.metadata?.importance,
    JSON.stringify(payload.person.tags || payload.person.metadata?.tags || []),
  ]);

  const updateEditValue = (field, value) => setEditValues((current) => ({ ...current, [field]: value }));
  const saveEdit = async (event) => {
    event.preventDefault();
    try {
      if (await onSave(editValues)) setEditOpen(false);
    } catch (error) {
      console.error(error);
    }
  };
  const saveNotes = async () => {
    if (notesBusy) return false;
    const previousNotes = profileNote.content;
    const previousMentionIds = profileNote.mentioned_person_ids || [];
    if (notesDraft.trim() === previousNotes && sameIds(selectedNoteMentionIds, previousMentionIds)) {
      setNotesEditOpen(false);
      return false;
    }
    setNotesBusy(true);
    try {
      const result = await onSaveNotes(
        payload.person.person_id, notesDraft, previousNotes, selectedNoteMentionIds,
      );
      if (result?.updated) {
        setNotesDraft(result.notes);
        setSelectedNoteMentionIds(result.mentioned_person_ids || []);
        setNotesEditOpen(false);
      }
      return Boolean(result?.updated);
    } finally {
      setNotesBusy(false);
    }
  };
  const selectPhoto = (path) => {
    onImage(path);
    if (activeTab === "overview") setActiveTab("photos");
  };
  const selectSightingPhoto = (detail) => {
    const record = imageRecords.find((item) => (
      item.embeddingId === detail.embedding_id
      || item.path === detail.image_path
      || item.thumbPath === detail.image_path
    ));
    if (record?.path) onImage(record.path);
    setActiveTab("photos");
    window.setTimeout(() => tabContentRef.current?.scrollIntoView({ block: "start", behavior: "smooth" }), 0);
  };
  const changeTab = (value) => {
    setActiveTab(value || "overview");
    if (value && value !== "overview") {
      window.setTimeout(() => tabContentRef.current?.scrollIntoView({ block: "start", behavior: "smooth" }), 0);
    }
  };
  const targetOptions = people
    .filter((person) => person.person_id !== payload.person.person_id && personAllows(person, "OPEN"))
    .map((person) => ({
      value: person.person_id,
      label: `${person.name} · ${person.embedding_count || 0} photos`,
    }));
  const runManagement = async (action) => {
    if (actionBusy) return;
    setManagementConflict(null);
    setActionBusy(true);
    try {
      await action();
      setManagementDialog(null);
      setTargetPersonId("");
    } catch (error) {
      if (error.code === "encounter_relation_conflict" && error.payload?.observation_id) {
        setManagementConflict(error.payload.observation_id);
      }
      console.error(error);
    } finally {
      setActionBusy(false);
    }
  };

  return (
    <Stack className="people-profile-shell">
      {referenceActions && <RecognitionReferences opened={referenceOpen} onClose={() => setReferenceOpen(false)}
        person={payload.person} data={payload.recognition_references} actions={referenceActions}
        canMutate={canEdit && lifecycleStatus === "ACTIVE"} startAdding={referenceAdding} />}
      <Group justify="space-between" align="flex-start" wrap="nowrap" className="people-profile-topbar">
        <Group gap="xs">
          <ActionIcon variant="subtle" onClick={onBack} aria-label="Back to people"><IconArrowLeft size={18} /></ActionIcon>
          <Text size="xs" c="dimmed">All People</Text>
          <Text size="xs" c="dimmed">/</Text>
          <Text size="xs">{payload.person.name}</Text>
        </Group>
        <Group gap="xs">
          <Button
            size="xs"
            variant="default"
            leftSection={<IconChartDots size={15} />}
            onClick={() => onOpenGraph(payload.person.person_id)}
          >
            Open Person Graph
          </Button>
          {personAllows(payload.person, "EDIT") && (
            <>
              {payload.person.is_placeholder && (
                <Button size="xs" leftSection={<IconPhoto size={14} />} disabled={!canEdit} onClick={() => {setReferenceAdding(true);setReferenceOpen(true);}}>
                  Add Face
                </Button>
              )}
              <Button size="xs" variant="default" leftSection={<IconPhoto size={14} />} disabled={!canEdit && !canDestroy} onClick={() => changeTab("photos")}>
                Manage faces
              </Button>
              <Menu withinPortal position="bottom-end">
                <Menu.Target>
                  <Button size="xs" disabled={!canEdit} rightSection={<IconChevronDown size={14} />}>Edit</Button>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Item leftSection={<IconEdit size={14} />} onClick={openProfileEdit}>Edit profile</Menu.Item>
                  <Menu.Item leftSection={<IconNotes size={14} />} onClick={openNotesEdit}>Edit notes</Menu.Item>
                </Menu.Dropdown>
              </Menu>
              <Button
                size="xs"
                variant="light"
                color="orange"
                leftSection={<IconArchive size={14} />}
                disabled={!canDestroy}
                onClick={() => setManagementDialog("archive")}
              >
                Archive
              </Button>
            </>
          )}
          <Button size="xs" variant="subtle" onClick={() => {setReferenceAdding(false);setReferenceOpen(true);}}>Manage Recognition References</Button>
          {canRestore && personAllows(payload.person, "RESTORE") && (
            <Button size="xs" leftSection={<IconRestore size={14} />} disabled={!canDestroy} onClick={() => setManagementDialog("restore")}>
              Restore
            </Button>
          )}
          {lifecycleStatus === "MERGED" && mergedInto && (
              <Button
                size="xs"
                variant="default"
                leftSection={<IconSwitchHorizontal size={14} />}
                onClick={() => onOpen(mergedInto)}
              >
                View merged person
              </Button>
          )}
          <Menu withinPortal position="bottom-end">
            <Menu.Target>
              <Button size="xs" variant="default" rightSection={<IconChevronDown size={14} />}>More</Button>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconCopy size={14} />} onClick={() => navigator.clipboard?.writeText(payload.person.person_id)}>Copy ID</Menu.Item>
              {personAllows(payload.person, "FAVORITE") && (
                <>
                  <Menu.Item leftSection={<IconStar size={14} />} disabled={!canEdit} onClick={() => onFavorite(payload.person.person_id, !favorite)}>
                    {favorite ? "Remove favorite" : "Add favorite"}
                  </Menu.Item>
                  <Menu.Item leftSection={<IconSwitchHorizontal size={14} />} disabled={!canDestroy} onClick={() => setManagementDialog("merge")}>
                    Merge into another person
                  </Menu.Item>
                  <Menu.Divider />
                  <Menu.Item color="red" leftSection={<IconArchive size={14} />} disabled={!canDestroy} onClick={() => setManagementDialog("archive")}>
                    Archive person
                  </Menu.Item>
                </>
              )}
              {archived && <Menu.Divider />}
              {personAllows(payload.person, "DELETE") && (
                <Menu.Item color="red" leftSection={<IconTrash size={14} />} disabled={!canDestroy} onClick={() => {
                  setProfileDeleteConfirmation("");
                  setManagementDialog("delete-profile");
                }}>
                  Delete entire profile
                </Menu.Item>
              )}
            </Menu.Dropdown>
          </Menu>
        </Group>
      </Group>

      <Group align="flex-start" wrap="nowrap" className="people-profile-hero">
        <ProfilePhoto path={selectedRecord?.thumbPath || payload.person.representative_image || selectedPath} name={payload.person.name} />
        <Box miw={0} className="people-profile-heading">
          <Group gap="xs" align="center">
            <Title order={2} size="h3">{payload.person.name}</Title>
            <ActionIcon
              variant="subtle"
              color={favorite ? "yellow" : "gray"}
              size="sm"
              onClick={() => onFavorite(payload.person.person_id, !favorite)}
              disabled={archived}
              aria-label={favorite ? "Remove favorite" : "Add favorite"}
            >
              <IconStar size={16} fill={favorite ? "currentColor" : "none"} />
            </ActionIcon>
          </Group>
          <Group gap="xs" mt={4}>
            <Text size="sm">{summaryProfile.rank || "Unknown role"}</Text>
            <Text size="sm" c="dimmed">•</Text>
            <Text size="sm">{summaryProfile.country || "Unknown country"}</Text>
            <Badge color={importanceColor(summaryProfile.importance)} variant="light">{summaryProfile.importance || "Regular"}</Badge>
            {archived && <Badge color="gray">{lifecycleStatusLabel(lifecycleStatus)}</Badge>}
          </Group>
          {(payload.person.tags || payload.person.metadata?.tags || []).length > 0 && (
            <Group gap={5} mt={7}>
              {(payload.person.tags || payload.person.metadata?.tags || []).map((tag) => (
                <Badge key={tag} size="sm" color="gray" variant="light">{tag}</Badge>
              ))}
            </Group>
          )}
          <Group gap="sm" mt="sm">
            <Badge variant="outline" leftSection={<IconImageInPicture size={13} />}>
              {imageRecords.length} {imageRecords.length === 1 ? "Photo" : "Photos"}
            </Badge>
            <Badge variant="outline">{latestSightingLabel}</Badge>
            {payload.person.is_placeholder && <Badge color="gray" variant="light">No ordinary recognition sample</Badge>}
          </Group>
          <Text size="xs" c="dimmed" mt="sm">ID: {payload.person.person_id}</Text>
        </Box>
        <Card withBorder radius="md" p="sm" className="people-profile-notes">
          <Text size="sm" fw={800} mb="xs">Notes</Text>
          <ProfileNoteSummary note={profileNote} onOpen={onOpen} />
        </Card>
      </Group>

      <Tabs value={activeTab} onChange={changeTab} className="people-profile-tabs" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="overview">Overview</Tabs.Tab>
          <Tabs.Tab value="photos">Photos ({imageRecords.length})</Tabs.Tab>
          <Tabs.Tab value="sightings">Sightings ({latestSightings.length})</Tabs.Tab>
          <Tabs.Tab value="events">Events</Tabs.Tab>
          <Tabs.Tab value="associations">Associations ({relationships.length})</Tabs.Tab>
          <Tabs.Tab value="changes">Activity ({activity.length})</Tabs.Tab>
        </Tabs.List>
        <Box ref={tabContentRef} className="people-profile-tab-content">
        <Tabs.Panel value="overview">
          <PeopleProfileOverview
            profile={summaryProfile}
            selectedPath={payload.person.representative_image || selectedPath}
            imageRecords={imageRecords}
            latestSightings={latestSightings}
            recentSightings={recentSightings}
            onSighting={selectSightingPhoto}
            onSightings={() => changeTab("sightings")}
          />
        </Tabs.Panel>
        <Tabs.Panel value="photos">
          <PeopleProfilePhotos
            payload={payload}
            canEdit={canEdit}
            canDestroy={canDestroy}
            records={imageRecords}
            selectedRecord={selectedRecord}
            selectedPath={selectedPath}
            selectedDetails={selectedDetails}
            profile={profile}
            onImage={selectPhoto}
            people={people}
            archived={archived}
            representativeEmbeddingId={payload.person.metadata?.representative_embedding_id}
            onSetRepresentative={() => selectedRecord && onSetRepresentative(payload.person.person_id, selectedRecord.embeddingId)}
            onMove={() => setManagementDialog("move-photo")}
            onDelete={() => setManagementDialog("delete-photo")}
          />
        </Tabs.Panel>
        <Tabs.Panel value="sightings">
          <PeopleProfileSightings details={latestSightings} imageRecords={imageRecords} onSighting={selectSightingPhoto} />
        </Tabs.Panel>
        <Tabs.Panel value="events">
          <Stack mt="md">
            <Text size="sm" c="dimmed">Occurrences where this Person was present, mentioned in an Event Note, or both.</Text>
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
              <TextInput label="Event or location" value={personEventFilters.search} onChange={(event) => setPersonEventFilters((current) => ({ ...current, search: event.currentTarget.value }))} />
              <TextInput type="date" label="From date" value={personEventFilters.date_from} onChange={(event) => setPersonEventFilters((current) => ({ ...current, date_from: event.currentTarget.value }))} />
              <TextInput type="date" label="To date" value={personEventFilters.date_to} onChange={(event) => setPersonEventFilters((current) => ({ ...current, date_to: event.currentTarget.value }))} />
              <TextInput label="Location" value={personEventFilters.location} onChange={(event) => setPersonEventFilters((current) => ({ ...current, location: event.currentTarget.value }))} />
              <Select clearable label="Context" data={[{ value: "ordinary", label: "Ordinary / small" }, { value: "public", label: "Public / group" }, { value: "unknown", label: "Unknown" }]} value={personEventFilters.context || null} onChange={(value) => setPersonEventFilters((current) => ({ ...current, context: value || "" }))} />
              <Select clearable label="Status" data={[{ value: "PRESENT", label: "Present" }, { value: "MENTIONED", label: "Mentioned" }, { value: "BOTH", label: "Present + Mentioned" }]} value={personEventFilters.person_status || null} onChange={(value) => setPersonEventFilters((current) => ({ ...current, person_status: value || "" }))} />
            </SimpleGrid>
            {(personEvents.events || []).map((event) => (
              <Paper key={event.observation_id} className="encounter-list-row" component="button" onClick={() => onOpenEncounter?.(event.observation_id)} style={{ textAlign: "left" }}>
                <Group justify="space-between"><Text fw={800}>{event.occasion || "Unnamed Event"}</Text><Badge>{event.person_status === "BOTH" ? "Present + Mentioned" : event.person_status === "PRESENT" ? "Present" : "Mentioned"}</Badge></Group>
                <Text size="sm">{eventDateTime(event)} · {event.location || "Location unknown"} · {event.context}</Text>
                {!!event.sighting_notes?.length && <Text size="sm">Sighting note: {event.sighting_notes.join(" · ")}</Text>}
                {event.person_status !== "PRESENT" && event.event_notes && <Text size="sm">Event Note: {event.event_notes}</Text>}
                <Text size="xs" c="dimmed">{event.person_media?.length || 0} observed media · {event.participant_ids?.length || 0} participants</Text>
              </Paper>
            ))}
            {!personEvents.events?.length && <Text c="dimmed">No matching Events.</Text>}
            <Group><Button variant="default" disabled={personEventPageCursors.length < 2} onClick={() => setPersonEventPageCursors((current) => current.slice(0, -1))}>Previous</Button><Button variant="default" disabled={!personEvents.next_cursor} onClick={() => setPersonEventPageCursors((current) => [...current, personEvents.next_cursor])}>Next</Button></Group>
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="associations">
          <PeopleProfileAssociations
            person={payload.person}
            people={people}
            canEdit={canEdit && !archived}
            onCreate={onCreateAssociation}
            onRetire={onRetireAssociation}
            associations={relationships}
            associationCount={payload.relationship_count}
            onOpen={onOpen}
            onOpenGraph={onOpenGraph}
          />
        </Tabs.Panel>
        <Tabs.Panel value="changes">
          <PeopleProfileChanges activity={activity} currentProfile={summaryProfile} />
        </Tabs.Panel>
        </Box>
      </Tabs>

      <Drawer opened={editOpen} onClose={() => setEditOpen(false)} position="right" size={380} title="Edit Person" className="people-edit-drawer">
        <form onSubmit={saveEdit}>
          <Stack>
            <PeopleEditableFields values={editValues} onChange={updateEditValue} />
            <Group justify="flex-end" mt="md">
              <Button variant="default" type="button" onClick={() => setEditOpen(false)}>Cancel</Button>
              <Button type="submit">Save Changes</Button>
            </Group>
          </Stack>
        </form>
      </Drawer>

      <Drawer opened={notesEditOpen} onClose={() => !notesBusy && cancelNotesEdit()} position="right" size={420} title="Edit Notes" className="people-edit-drawer">
        <Stack>
          <Textarea
            autoFocus
            autosize
            minRows={7}
            maxRows={16}
            label="Notes"
            description="Type @ and at least three characters to mention a person"
            value={notesDraft}
            disabled={notesBusy}
            placeholder="Add a short summary or detail about this person"
            onChange={(event) => setNotesDraft(event.currentTarget.value)}
          />
          {(noteMentionSuggestions.length > 0 || noteMentionCanCreate) && (
            <Stack gap={4} className="people-note-mention-suggestions">
              {noteMentionSuggestions.map((candidate) => (
                <Paper
                  key={candidate.person_id}
                  withBorder
                  radius="md"
                  p="xs"
                  component="button"
                  type="button"
                  className="mantine-click-card"
                  onClick={() => {
                    setNotesDraft((current) => replaceNoteMentionQuery(current, candidate.name));
                    setSelectedNoteMentionIds((current) => current.includes(candidate.person_id)
                      ? current
                      : [...current, candidate.person_id]);
                  }}
                >
                  <AssociationIdentity person={candidate} />
                </Paper>
              ))}
              {noteMentionCanCreate && (
                <Paper withBorder radius="md" p="xs">
                  <Group justify="space-between" gap="md" wrap="nowrap">
                    <Box>
                      <Text size="sm" fw={700}>No exact person named “{activeMentionQuery}”</Text>
                      <Text size="xs" c="dimmed">Create a profile without a photograph, then mention it here.</Text>
                    </Box>
                    <Button
                      type="button"
                      size="xs"
                      variant="light"
                      color="orange"
                      leftSection={<IconUserPlus size={14} />}
                      onClick={openNotePlaceholder}
                    >
                      Create profile
                    </Button>
                  </Group>
                </Paper>
              )}
            </Stack>
          )}
          <Group justify="flex-end" mt="md">
            <Button variant="default" disabled={notesBusy} onClick={cancelNotesEdit}>Cancel</Button>
            <Button loading={notesBusy} onClick={saveNotes}>Save notes</Button>
          </Group>
        </Stack>
      </Drawer>

      <Modal
        opened={notePlaceholderOpen}
        onClose={() => !notePlaceholderBusy && setNotePlaceholderOpen(false)}
        title={`Create “${notePlaceholderValues.name || activeMentionQuery}” without a photograph?`}
        size="xl"
        centered
      >
        <form onSubmit={async (event) => {
          event.preventDefault();
          if (notePlaceholderBusy || !notePlaceholderValues.name.trim()) return;
          setNotePlaceholderBusy(true);
          try {
            const createdPerson = await onCreateIdentifiedPerson(notePlaceholderValues);
            setNotesDraft((current) => replaceNoteMentionQuery(current, createdPerson.name));
            setSelectedNoteMentionIds((current) => current.includes(createdPerson.person_id)
              ? current
              : [...current, createdPerson.person_id]);
            setNotePlaceholderOpen(false);
          } finally {
            setNotePlaceholderBusy(false);
          }
        }}>
          <Stack>
            <Alert color="orange" title="This creates an unknown identity" icon={<IconUserPlus size={18} />}>
              This person will have no photograph or biometric data. Create the profile only when tracking their known details, habits, patterns, or relationships is useful. A face can be added later.
            </Alert>
            <PlaceholderPersonFields values={notePlaceholderValues} onChange={setNotePlaceholderValues} people={people} />
            <Group justify="flex-end">
              <Button type="button" variant="default" disabled={notePlaceholderBusy} onClick={() => setNotePlaceholderOpen(false)}>Cancel</Button>
              <Button type="submit" color="orange" loading={notePlaceholderBusy} disabled={!notePlaceholderValues.name.trim()}>
                Create profile without photo
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal
        opened={managementDialog === "archive"}
        onClose={() => !actionBusy && setManagementDialog(null)}
        title="Archive this person?"
        centered
      >
        <Stack>
          <Text size="sm">
            {payload.person.name} will stop appearing in recognition results. Their {imageRecords.length} photos, {latestSightings.length} sightings, and {relationships.length} relationships will be retained and can be restored later.
          </Text>
          <Text size="xs" c="dimmed">A named database backup is created and verified before archiving.</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setManagementDialog(null)} disabled={actionBusy}>Cancel</Button>
            <Button color="red" loading={actionBusy} leftSection={<IconArchive size={16} />} onClick={() => runManagement(() => onArchive(payload.person.person_id))}>
              Archive person
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal
        opened={managementDialog === "restore"}
        onClose={() => !actionBusy && setManagementDialog(null)}
        title="Restore this person?"
        centered
      >
        <Stack>
          <Text size="sm">
            {payload.person.name} and all retained photos will return to recognition and the active People library.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setManagementDialog(null)} disabled={actionBusy}>Cancel</Button>
            <Button loading={actionBusy} leftSection={<IconRestore size={16} />} onClick={() => runManagement(() => onRestore(payload.person.person_id))}>
              Restore person
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal
        opened={managementDialog === "delete-profile"}
        onClose={() => !actionBusy && setManagementDialog(null)}
        title="Delete entire profile permanently?"
        centered
      >
        <Stack>
          <Alert color="red" icon={<IconShield size={18} />} title="This tombstones the identity">
            <strong>{payload.person.name}</strong> will leave active use. Historical identity, sightings, relationships, and operation provenance remain represented. A verified safety backup is created first.
          </Alert>
          <TextInput
            label="Type DELETE to confirm"
            value={profileDeleteConfirmation}
            onChange={(event) => setProfileDeleteConfirmation(event.currentTarget.value)}
            autoComplete="off"
          />
          <Group justify="flex-end">
            <Button variant="default" disabled={actionBusy} onClick={() => setManagementDialog(null)}>Cancel</Button>
            <Button
              color="red"
              loading={actionBusy}
              disabled={profileDeleteConfirmation !== "DELETE"}
              leftSection={<IconTrash size={16} />}
              onClick={() => runManagement(() => onDelete(payload.person.person_id))}
            >
              Delete entire profile
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal
        opened={managementDialog === "merge"}
        onClose={() => !actionBusy && setManagementDialog(null)}
        title="Merge duplicate person"
        centered
      >
        <Stack>
          {managementConflict && <Box>
            <Text size="sm" c="red" role="alert">This merge would combine contradictory Encounter Relations. Correct the affected Encounter before retrying.</Text>
            <Button mt="xs" variant="light" onClick={() => { setManagementDialog(null); onOpenEncounter?.(managementConflict); }}>Open conflicting Encounter</Button>
          </Box>}
          <Text size="sm">
            <strong>{payload.person.name}</strong> will resolve to the selected person. Photos, sightings, notes, and other history keep their original provenance.
          </Text>
          <Select
            label="Keep this person"
            placeholder="Search for the correct identity"
            searchable
            data={targetOptions}
            value={targetPersonId}
            onChange={(value) => setTargetPersonId(value || "")}
            nothingFoundMessage="No other active people"
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setManagementDialog(null)} disabled={actionBusy}>Cancel</Button>
            <Button
              loading={actionBusy}
              disabled={!targetPersonId}
              leftSection={<IconSwitchHorizontal size={16} />}
              onClick={() => runManagement(() => onMerge(payload.person.person_id, targetPersonId))}
            >
              Merge people
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal
        opened={managementDialog === "move-photo"}
        onClose={() => !actionBusy && setManagementDialog(null)}
        title="Move photo to another person"
        centered
      >
        <Stack>
          <Text size="sm">
            Current face ownership will move to the selected identity. Original sightings and decisions remain in correction history; affected observation participants and graph evidence are recalculated.
          </Text>
          <Select
            label="Move to"
            placeholder="Select the correct identity"
            searchable
            data={targetOptions}
            value={targetPersonId}
            onChange={(value) => setTargetPersonId(value || "")}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setManagementDialog(null)} disabled={actionBusy}>Cancel</Button>
            <Button
              loading={actionBusy}
              disabled={!targetPersonId || !selectedRecord}
              leftSection={<IconSwitchHorizontal size={16} />}
              onClick={() => runManagement(() => onMovePhoto(payload.person.person_id, selectedRecord.embeddingId, targetPersonId))}
            >
              Move photo
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal
        opened={managementDialog === "delete-photo"}
        onClose={() => !actionBusy && setManagementDialog(null)}
        title="Move this face to Deleted Faces?"
        centered
      >
        <Stack>
          <Text size="sm">
            The face stops participating in recognition immediately. It and its {selectedDetails.length} linked sighting{selectedDetails.length === 1 ? "" : "s"} remain recoverable in Deleted Faces for 30 days.
          </Text>
          <Text size="xs" c="dimmed">
            A named database backup is created and verified first. The person remains in People.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setManagementDialog(null)} disabled={actionBusy}>Cancel</Button>
            <Button
              color="red"
              loading={actionBusy}
              disabled={!selectedRecord}
              leftSection={<IconTrash size={16} />}
              onClick={() => runManagement(() => onDeletePhoto(payload.person.person_id, selectedRecord.embeddingId))}
            >
              Move to Deleted Faces
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

function PeopleProfileOverview({ profile, selectedPath, imageRecords, latestSightings, recentSightings, onSighting, onSightings }) {
  const latest = latestSightings[0];
  return (
    <Grid mt="md" className="people-profile-content-grid">
      <Grid.Col span={{ base: 12, md: 4 }}>
        <Card withBorder radius="md" className="people-profile-panel">
          <Text fw={800} mb="md">Identity Information</Text>
          <ProfileInfoRows rows={[
            ["Rank", profile.rank || "-"],
            ["Country", profile.country || "-"],
            ["Tag", profile.importance || "-"],
            ["Created", compactChangeDate(profile.createdAt)],
            ["Added by", profile.addedBy || "-"],
          ]} />
        </Card>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 4 }}>
        <Card withBorder radius="md" className="people-profile-panel">
          <Text fw={800} mb="md">Latest Sighting</Text>
          {latest ? (
            <Paper withBorder radius="md" p="sm" component="button" className="mantine-click-card recent-sighting-row" onClick={() => onSighting(latest)}>
              <SightingSummary detail={latest} />
            </Paper>
          ) : <Text size="sm" c="dimmed">No sightings recorded.</Text>}
        </Card>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 4 }}>
        <Card withBorder radius="md" className="people-profile-panel">
          <Text fw={800} mb="md">Recent Sightings</Text>
          <Stack gap="xs">
            {recentSightings.length ? recentSightings.map((detail) => (
              <Group key={detail.detail_id} gap="sm" wrap="nowrap" component="button" className="mantine-click-card recent-sighting-row" onClick={() => onSighting(detail)}>
                <ThemeIcon variant="light" color="gray" size="sm"><IconMapPin size={13} /></ThemeIcon>
                <Box miw={0}>
                  <Text size="xs" truncate>{formatSeenDateTime(detail)}</Text>
                  <Text size="xs" c="dimmed" truncate>{detail.place_seen || detail.event_occasion || "-"}</Text>
                </Box>
                <SightingImage detail={detail} imageRecords={imageRecords} fallbackPath={selectedPath} size={40} />
              </Group>
            )) : <Text size="sm" c="dimmed">No recent sightings.</Text>}
          </Stack>
          <Button fullWidth mt="md" variant="default" rightSection={<IconArrowLeft size={14} style={{ transform: "rotate(180deg)" }} />} onClick={onSightings}>View All Sightings</Button>
        </Card>
      </Grid.Col>
    </Grid>
  );
}

function PeopleProfilePhotos({
  canEdit,
  canDestroy,
  payload,
  records,
  selectedRecord,
  selectedPath,
  selectedDetails,
  profile,
  onImage,
  archived,
  representativeEmbeddingId,
  onSetRepresentative,
  onMove,
  onDelete,
}) {
  const photoDetail = selectedDetails[0] || {};
  return (
    <Grid mt="md" className="people-profile-photos-grid">
      <Grid.Col span={{ base: 12, lg: 8 }}>
        <Group justify="space-between" mb="sm">
          <Box>
            <Text size="sm" fw={700}>Photos ({records.length})</Text>
            <Text size="xs" c="dimmed">Reference faces and Encounter photos where this Person was observed. Select a photo to inspect its origin; enrolled faces can be managed below.</Text>
          </Box>
        </Group>
        <Group gap="sm" mb="md" className="people-profile-thumb-row">
          {records.map((record) => (
            <Card
              key={record.path}
              withBorder
              p={0}
              component="button"
              className="mantine-click-card people-profile-thumb"
              data-selected={selectedRecord?.path === record.path}
              onClick={() => onImage(record.path)}
            >
              <Image src={mediaUrl(record.thumbPath || record.path)} alt={payload.person.name} fit="cover" radius="sm" />
            </Card>
          ))}
        </Group>
        <Paper withBorder radius="md" className="people-profile-selected-photo">
          {selectedPath
            ? <img src={mediaUrl(selectedPath)} alt={payload.person.name} className="people-profile-selected-photo-image" />
            : <Stack align="center" gap={4}><ThemeIcon size={54} radius="xl" variant="light" color="gray"><IconUser size={30} /></ThemeIcon><Text c="dimmed">No photograph</Text><Text size="xs" c="dimmed">No biometric data is stored for this person.</Text></Stack>}
        </Paper>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 4 }}>
        <Card withBorder radius="md" className="people-profile-panel">
          <Group justify="space-between" mb="md">
            <Text fw={800}>Photo Details</Text>
            {selectedRecord && selectedRecord.embeddingId === representativeEmbeddingId && <Badge color="teal">Profile photo</Badge>}
          </Group>
          <ProfileInfoRows rows={[
            ["Added", Object.keys(photoDetail).length ? formatSeenDateTime(photoDetail) : compactChangeDate(selectedRecord?.createdAt)],
            ["Source", photoDetail.event_occasion || "-"],
            ["Location", photoDetail.place_seen || "-"],
            ["Quality", selectedRecord?.qualityScore == null ? "-" : `${Math.round(selectedRecord.qualityScore * 100)}%`],
            ["Embedding", selectedRecord?.embeddingId ? "Indexed" : "-"],
            ["Face origin", [...new Set(selectedRecord?.faceOrigins?.map((origin) => ({ ENCOUNTER: "Added from Encounter", STANDALONE_ENROLLMENT: "Reference Only", UNKNOWN_LEGACY: "Legacy origin unknown" })[origin.face_origin] || "Legacy origin unknown") || [])].join(", ") || "Legacy origin unknown"],
            ["Face samples", selectedRecord?.embeddingIds?.length || "Historical media"],
            ["Rank", profile.rank || "-"],
          ]} />
          {photoDetail.notes && <Text size="sm" mt="md" style={{ whiteSpace: "pre-wrap" }}><Text span fw={700}>Notes: </Text>{photoDetail.notes}</Text>}
          {!archived && selectedRecord?.embeddingId && (
            <Stack gap="xs" mt="lg">
              <Button
                variant="light"
                leftSection={<IconPhotoStar size={16} />}
                disabled={!canEdit || selectedRecord.embeddingId === representativeEmbeddingId}
                onClick={onSetRepresentative}
              >
                {selectedRecord.embeddingId === representativeEmbeddingId ? "Current profile photo" : "Set as profile photo"}
              </Button>
              <Button variant="default" leftSection={<IconSwitchHorizontal size={16} />} disabled={!canDestroy || selectedRecord.faceOrigins?.some(o => o.face_origin === "STANDALONE_ENROLLMENT")} onClick={onMove}>
                Move to another person
              </Button>
              <Button color="red" variant="light" leftSection={<IconTrash size={16} />} disabled={!canDestroy || selectedRecord.faceOrigins?.some(o => o.face_origin === "STANDALONE_ENROLLMENT")} onClick={onDelete}>
                Move face to Deleted Faces
              </Button>
            </Stack>
          )}
        </Card>
      </Grid.Col>
    </Grid>
  );
}

function PeopleProfileSightings({ details, imageRecords, onSighting }) {
  return (
    <Stack mt="md" className="people-profile-list-panel">
      {details.length ? details.map((detail) => (
        <Paper key={detail.detail_id} withBorder radius="sm" p="sm" component="button" className="mantine-click-card people-sighting-card" onClick={() => onSighting(detail)}>
          <Group justify="space-between" align="center" wrap="nowrap">
            <SightingSummary detail={detail} />
            <SightingImage detail={detail} imageRecords={imageRecords} size={56} />
          </Group>
        </Paper>
      )) : <EmptyCard text="No sightings recorded yet." />}
    </Stack>
  );
}

function PeopleProfileAssociations({ person, people = [], canEdit, associations, associationCount = 0, onOpen, onOpenGraph, onCreate, onRetire }) {
  const [adding, setAdding] = useState(false);
  const [target, setTarget] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const operationRef = useRef({});
  const create = async () => {
    setBusy(true); setError("");
    const key = `create:${target}`;
    operationRef.current[key] ||= crypto.randomUUID();
    try { await onCreate(person.person_id, target, operationRef.current[key]); setAdding(false); setTarget(null); delete operationRef.current[key]; }
    catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  };
  const retire = async (evidenceId) => {
    setBusy(true); setError("");
    operationRef.current[evidenceId] ||= crypto.randomUUID();
    try { await onRetire(person.person_id, evidenceId, operationRef.current[evidenceId]); delete operationRef.current[evidenceId]; }
    catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  };
  return (
    <Stack mt="md" gap="md" className="people-associations-panel">
      <Box>
        {canEdit && <Button size="sm" mb="sm" onClick={() => setAdding(true)}>Add Association</Button>}
        {error && <Text role="alert" c="red">{error}</Text>}
        <Group justify="space-between" mb="md">
          <Text fw={800}>Associated people ({associationCount})</Text>
          <Button
            size="xs"
            variant="default"
            leftSection={<IconChartDots size={15} />}
            onClick={() => onOpenGraph(person.person_id)}
          >
            Open Person Graph
          </Button>
        </Group>
        <Text size="xs" c="dimmed" mb="sm">Removing a manual assertion preserves Encounter and note evidence. The relationship may remain visible.</Text>
        <Stack gap="xs">
          {associations.length ? associations.map((association) => {
            const associationHistorical = !personAllows(association.person, "OPEN");
            return (
            <Paper
              key={association.relationship_id}
              p="sm"
              component="div"
              role={associationHistorical ? undefined : "button"}
              tabIndex={associationHistorical ? undefined : 0}
              className={associationHistorical ? "association-person-row" : "mantine-click-card association-person-row"}
              onClick={() => {
                if (!associationHistorical) onOpen(association.person.person_id, { archived: false });
              }}
              onKeyDown={(event) => {
                if (!associationHistorical && (event.key === "Enter" || event.key === " ")) {
                  event.preventDefault();
                  onOpen(association.person.person_id, { archived: false });
                }
              }}
            >
              <Group justify="space-between" wrap="wrap">
                <AssociationIdentity person={association.person} />
                <Group gap="xs" wrap="wrap">
                  <Badge
                    variant="light"
                    color={association.evidence_type_counts?.NOTE_REFERENCE ? "violet" : "teal"}
                  >
                    {association.presentation_label}
                  </Badge>
                  <Badge variant="outline" color="gray">{association.evidence_count} evidence</Badge>
                  {canEdit && (association.manual_evidence || []).map((evidence) => <Button key={evidence.evidence_id} size="compact-xs" variant="subtle" color="red" disabled={busy} onClick={(event) => { event.stopPropagation(); retire(evidence.evidence_id); }}>Remove manual association</Button>)}
                </Group>
              </Group>
            </Paper>
            );
          }) : <EmptyCard text="No person associations recorded yet." />}
        </Stack>
      </Box>
      <Modal opened={adding} onClose={() => !busy && setAdding(false)} title="Add Association" centered>
        <Stack><Text size="sm" c="dimmed">Record an operator assertion. It creates Manual Association evidence independently of Encounters and selected note mentions.</Text>
          <Select searchable label="Person" value={target} onChange={setTarget} data={people.filter((p) => p.lifecycle_status === "ACTIVE" && p.person_id !== person.person_id).map((p) => ({ value: p.person_id, label: p.name }))} />
          {error && <Text c="red" role="alert">{error}</Text>}
          <Group justify="flex-end"><Button variant="default" disabled={busy} onClick={() => setAdding(false)}>Cancel</Button><Button loading={busy} disabled={!target} onClick={create}>Add Association</Button></Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

function AssociationIdentity({ person }) {
  const rank = person.metadata?.rank || "No role";
  const country = person.metadata?.country || "No country";
  return (
    <Group gap="sm" wrap="nowrap" miw={0}>
      {person.representative_image ? (
        <Image src={mediaUrl(person.representative_image)} alt={person.name} h={42} w={42} radius="xl" fit="cover" />
      ) : (
        <ThemeIcon size={42} radius="xl" variant="light" color="gray"><IconUser size={22} /></ThemeIcon>
      )}
      <Box miw={0}>
        <Group gap="xs" wrap="nowrap">
          <Text fw={800} truncate>{person.name}</Text>
          {person.is_placeholder && <Badge size="xs" color="gray" variant="light">No photo</Badge>}
          {requirePersonContract(person).lifecycle_status !== "ACTIVE" && (
            <Badge size="xs" color="gray">{lifecycleStatusLabel(person.lifecycle_status)}</Badge>
          )}
        </Group>
        <Text size="xs" c="dimmed" truncate>{rank} · {country} · ID {String(person.person_id || "").slice(0, 8)} · {person.embedding_count || 0} photos</Text>
      </Box>
    </Group>
  );
}

function PeopleProfileChanges({ activity, currentProfile }) {
  const historyCards = activity.map(normalizeManagementChange);
  const [historyFilter, setHistoryFilter] = useState("all");
  const [historyView, setHistoryView] = useState("cards");
  const [activeIndex, setActiveIndex] = useState(0);
  const filteredHistoryCards = historyCards.filter((change) => historyChangeMatchesFilter(change, historyFilter));
  const activeHistory = filteredHistoryCards[activeIndex] || null;
  useEffect(() => setActiveIndex(0), [historyFilter]);
  return (
    <Box mt="md" className="people-change-history-shell">
      <Card withBorder radius="md" className="people-profile-panel people-current-diff-card">
        <Group justify="space-between" mb="md">
          <Box>
            <Text fw={900} c="teal.3">Current Information</Text>
            <Text size="xs" c="dimmed">Authoritative profile values</Text>
          </Box>
        </Group>
        <Stack gap="xs">
          <CurrentInfoRow icon={IconUser} label="Name" value={currentProfile.name || "-"} />
          <CurrentInfoRow icon={IconShield} label="Rank" value={currentProfile.rank || "-"} />
          <CurrentInfoRow icon={IconGlobe} label="Country" value={currentProfile.country || "-"} />
          <CurrentInfoRow icon={IconFlag} label="Tag" value={currentProfile.importance || "-"} pill={importanceColor(currentProfile.importance)} />
          <Divider />
          <CurrentInfoRow icon={IconRefresh} label="Last Activity" value={activeHistory?.createdAt || "-"} subvalue={`By ${activeHistory?.editor || "System"}`} />
        </Stack>
      </Card>
      <Card withBorder radius="md" className="people-profile-panel people-change-history-panel">
        <Group justify="space-between" mb="sm" wrap="nowrap">
          <Group gap="sm" align="baseline">
            <Text fw={900}>Profile History</Text>
            <Text size="xs" c="dimmed">(Newest → Oldest)</Text>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <Group gap={0} className="people-change-view-toggle">
              <ActionIcon
                variant={historyView === "cards" ? "light" : "default"}
                aria-label="Card view"
                aria-pressed={historyView === "cards"}
                onClick={() => setHistoryView("cards")}
              >
                <IconGridDots size={16} />
              </ActionIcon>
              <ActionIcon
                variant={historyView === "list" ? "light" : "default"}
                aria-label="List view"
                aria-pressed={historyView === "list"}
                onClick={() => setHistoryView("list")}
              >
                <IconLayoutList size={16} />
              </ActionIcon>
            </Group>
            <Menu withinPortal position="bottom-end">
              <Menu.Target>
                <Button size="xs" variant="default" rightSection={<IconChevronDown size={14} />}>
                  {historyFilterLabel(historyFilter)}
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item onClick={() => setHistoryFilter("all")}>All Changes</Menu.Item>
                <Menu.Item onClick={() => setHistoryFilter("identity")}>Identity Changes</Menu.Item>
                <Menu.Item onClick={() => setHistoryFilter("metadata")}>Metadata Changes</Menu.Item>
                <Menu.Item onClick={() => setHistoryFilter("photos")}>Photo &amp; Favorite Changes</Menu.Item>
                <Menu.Item onClick={() => setHistoryFilter("management")}>Record Management</Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
        <Box className="people-change-timeline" data-view={historyView}>
          {filteredHistoryCards.length ? filteredHistoryCards.map((change, index) => (
            <Card
              key={change.id}
              withBorder
              radius="md"
              component="button"
              className="mantine-click-card people-change-card"
              data-active={index === activeIndex}
              onClick={() => setActiveIndex(index)}
              onFocus={() => setActiveIndex(index)}
            >
              <Group justify="space-between" align="flex-start" mb="sm" wrap="nowrap">
                <Box>
                  <Group gap="xs" wrap="nowrap">
                    <IconCalendarMini />
                    <Text size="xs">{compactChangeDate(change.createdAt)}</Text>
                  </Group>
                  <Text size="xs" c="dimmed" mt={2}>By {change.editor || "System"}</Text>
                </Box>
                {index === activeIndex && <Badge size="sm" variant="light">Active</Badge>}
              </Group>
              <Stack gap="sm" className="people-change-management-summary">
                <ThemeIcon size={42} radius="xl" variant="light"><IconRefresh size={21} /></ThemeIcon>
                <Text fw={800}>{change.title}</Text>
                <Text size="sm" c="dimmed">{change.detail}</Text>
              </Stack>
              {/* <Button mt="md" size="xs" variant="default" rightSection={<IconArrowLeft size={13} style={{ transform: "rotate(135deg)" }} />}>View Full Details</Button> */}
            </Card>
          )) : <EmptyCard text="No activity matches this filter." />}
        </Box>
        {historyView === "cards" && filteredHistoryCards.length > 1 && (
          <Group gap="xs" mt="sm" wrap="nowrap" className="people-change-scroll-hint">
            <Text c="dimmed">‹</Text>
            <Box className="people-change-scroll-track"><Box className="people-change-scroll-fill" style={{ width: `${Math.max(18, ((activeIndex + 1) / filteredHistoryCards.length) * 100)}%` }} /></Box>
            <Text c="dimmed">›</Text>
          </Group>
        )}
      </Card>
    </Box>
  );
}

function ProfilePhoto({ path, name }) {
  return (
    <Paper withBorder radius="md" className="people-profile-avatar">
      {path ? (
        <img src={mediaUrl(path)} alt={name} className="people-profile-avatar-image" />
      ) : (
        <ThemeIcon size={72} radius="xl" variant="light" color="gray"><IconUser size={44} /></ThemeIcon>
      )}
    </Paper>
  );
}

function ProfileNoteSummary({ note, onOpen }) {
  if (!note.content.trim()) return <Text size="sm" c="dimmed">No notes added.</Text>;
  return (
    <Stack gap="xs" className="people-profile-note-summary">
      <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{note.content}</Text>
      <Group gap="xs">
        {(note.mentions || []).map((mention) => (
          <Badge
            key={mention.occurrence_id}
            component="button"
            type="button"
            variant="light"
            color="violet"
            className="people-note-person-chip"
            disabled={!personAllows(mention.person, "OPEN")}
            onClick={() => {
              if (personAllows(mention.person, "OPEN")) {
                onOpen(mention.effective_person_id, { archived: false });
              }
            }}
          >@{mention.display_name}</Badge>
        ))}
      </Group>
    </Stack>
  );
}

function noteMentionQuery(notes) {
  const match = String(notes || "").match(/(?:^|\s)@([^@,\n]*)$/);
  return match ? match[1].trim() : "";
}

function replaceNoteMentionQuery(notes, personName) {
  return String(notes || "").replace(/(^|\s)@([^@,\n]*)$/, (_, prefix) => `${prefix}@${personName}, `);
}

function sameIds(left, right) {
  return [...left].sort().join("\u0000") === [...right].sort().join("\u0000");
}

function newPlaceholderValues(name = "") {
  const { date, time } = currentDateTimeParts();
  return {
    name,
    rank: "",
    country: "",
    importance: NEW_PERSON_IMPORTANCE_OPTIONS[1],
    date,
    time,
    placeSeen: "",
    individualCount: "",
    eventOccasion: "",
    addedBy: "",
    notes: "",
    tags: [],
    mentionedPersonIds: [],
  };
}

function PlaceholderPersonFields({ values, onChange, people }) {
  const mentionQuery = noteMentionQuery(values.notes);
  const suggestions = useMemo(() => {
    if (mentionQuery.length < 3) return [];
    const normalized = mentionQuery.toLocaleLowerCase();
    return people.filter((candidate) => (
      personAllows(candidate, "OPEN")
      && [candidate.name, candidate.person_id, candidate.metadata?.rank, candidate.metadata?.country]
        .filter(Boolean)
        .some((value) => String(value).toLocaleLowerCase().includes(normalized))
    )).slice(0, 6);
  }, [mentionQuery, people]);
  const update = (field, value) => onChange((current) => ({ ...current, [field]: value }));

  return (
    <Stack gap="md">
      <Text fw={800}>Add New Person Details</Text>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <TextInput required autoFocus label="Rank" value={values.rank} onChange={(event) => update("rank", event.currentTarget.value)} />
        <TextInput required label="Name" value={values.name} onChange={(event) => update("name", event.currentTarget.value)} />
        <CountrySelect value={values.country} onChange={(value) => update("country", value)} />
        <Select required label="Tag" data={NEW_PERSON_IMPORTANCE_OPTIONS} value={values.importance} onChange={(value) => update("importance", value)} />
        <TextInput required label="Date" type="date" leftSection={<IconCalendar size={18} />} value={values.date} onChange={(event) => update("date", event.currentTarget.value)} />
        <TextInput required label="Time" type="time" leftSection={<IconCalendar size={18} />} value={values.time} onChange={(event) => update("time", event.currentTarget.value)} />
        <TextInput required label="Place Seen" leftSection={<IconMapPin size={18} />} placeholder="e.g., Office, Gate A, Reception, Building C" value={values.placeSeen} onChange={(event) => update("placeSeen", event.currentTarget.value)} />
        <NumberInput required min={0} step={1} label="With how many individuals" leftSection={<IconUsers size={18} />} placeholder="Select count" value={values.individualCount} onChange={(value) => update("individualCount", value)} />
        <TextInput required label="Event/Occasion" leftSection={<IconCalendar size={18} />} placeholder="e.g., Meeting, Visit, Delivery, Staff Interaction, Security Check" value={values.eventOccasion} onChange={(event) => update("eventOccasion", event.currentTarget.value)} />
        <TextInput required label="Added by" placeholder="Your Name" value={values.addedBy} onChange={(event) => update("addedBy", event.currentTarget.value)} />
      </SimpleGrid>
      <Textarea
        autosize
        minRows={3}
        label="Person notes"
        description="Saved on the new person’s profile. Type @ and at least three characters to mention an existing person."
        value={values.notes || ""}
        onChange={(event) => update("notes", event.currentTarget.value)}
      />
      {suggestions.length > 0 && (
        <Stack gap={4} className="people-note-mention-suggestions">
          {suggestions.map((candidate) => (
            <Paper
              key={candidate.person_id}
              withBorder
              radius="md"
              p="xs"
              component="button"
              type="button"
              className="mantine-click-card"
              onClick={() => onChange((current) => ({
                ...current,
                notes: replaceNoteMentionQuery(current.notes, candidate.name),
                mentionedPersonIds: [...new Set([...(current.mentionedPersonIds || []), candidate.person_id])],
              }))}
            >
              <AssociationIdentity person={candidate} />
            </Paper>
          ))}
        </Stack>
      )}
    </Stack>
  );
}

function SightingImage({ detail, imageRecords, fallbackPath, size = 56 }) {
  const record = imageRecords.find((item) => item.embeddingId === detail.embedding_id);
  const path = detail.image_path || record?.thumbPath || record?.path || fallbackPath;
  if (!path) return null;
  return <Image src={mediaUrl(path)} alt={detail.place_seen || "sighting"} h={size} w={size} fit="cover" radius="sm" className="sighting-thumb" />;
}

function CurrentInfoRow({ icon: Icon, label, value, subvalue, active, pill, tags, multiline }) {
  return (
    <Paper withBorder radius="md" p="xs" className={active ? "current-info-row current-info-row--active" : "current-info-row"}>
      <Group gap="sm" align={multiline ? "flex-start" : "center"} wrap="nowrap">
        <ThemeIcon variant="subtle" color="gray" size="sm"><Icon size={16} /></ThemeIcon>
        <Text size="xs" fw={700} className="current-info-label">{label}</Text>
        <Box className="current-info-accent" />
        <Box miw={0} className="current-info-value">
          {Array.isArray(value) && tags ? (
            <Group gap="xs">{value.map((item) => <Badge key={item} variant="outline">{item}</Badge>)}</Group>
          ) : pill ? (
            <Badge color={pill} variant="light">{value}</Badge>
          ) : (
            <Text size="sm" fw={700} className={multiline ? "current-info-text-multiline" : ""}>{value}</Text>
          )}
          {subvalue && <Text size="xs" c="dimmed">{subvalue}</Text>}
        </Box>
      </Group>
    </Paper>
  );
}

function IconCalendarMini() {
  return <Text component="span" size="xs" c="dimmed">▣</Text>;
}

function ProfileInfoRows({ rows }) {
  return (
    <Stack gap="sm">
      {rows.map(([label, value]) => (
        <Group key={label} justify="space-between" wrap="nowrap">
          <Text size="xs" c="dimmed">{label}</Text>
          <Text size="xs" fw={700} ta="right">{value || "-"}</Text>
        </Group>
      ))}
    </Stack>
  );
}

function SightingSummary({ detail }) {
  return (
    <Stack gap="xs">
      <ProfileInfoRows rows={[
        ["Location", detail.place_seen || "-"],
        ["Date & Time", formatSeenDateTime(detail)],
        ["Source", detail.event_occasion || "-"],
        ["Added by", detail.added_by || "System"],
      ]} />
      {detail.notes && <Text size="xs" mt="xs" style={{ whiteSpace: "pre-wrap" }}>{detail.notes}</Text>}
    </Stack>
  );
}

function isSeenDetail(detail) {
  return Boolean(detail?.place_seen || detail?.date || detail?.time || detail?.event_occasion || detail?.added_by);
}

function sightingTimestamp(detail) {
  const date = detail?.seen_date || detail?.date || "";
  const time = detail?.seen_time || detail?.time || "00:00";
  const parsed = new Date(date ? `${date}T${time}` : detail?.created_at || 0);
  return Number.isNaN(parsed.getTime()) ? 0 : parsed.getTime();
}

function lastSeenLabel(detail) {
  if (!detail) return "No sightings";
  const timestamp = sightingTimestamp(detail);
  if (!timestamp) return "Sighting recorded";
  const seen = new Date(timestamp);
  const today = new Date();
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const startOfSeen = new Date(seen.getFullYear(), seen.getMonth(), seen.getDate()).getTime();
  const dayDifference = Math.round((startOfToday - startOfSeen) / 86_400_000);
  if (dayDifference === 0) return "Last seen today";
  if (dayDifference === 1) return "Last seen yesterday";
  return `Last seen ${seen.toLocaleDateString([], { day: "2-digit", month: "short", year: seen.getFullYear() === today.getFullYear() ? undefined : "numeric" })}`;
}

function importanceColor(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized.includes("suspicious") || normalized.includes("watch")) return "red";
  if (normalized.includes("vip") || normalized.includes("high")) return "yellow";
  return "teal";
}

function profileImageRecords(payload) {
  const byPath = new Map();
  for (const record of payload.embeddings || []) {
    const path = record.source_image || record.crop_path;
    if (!path) continue;
    const item = byPath.get(path);
    if (item) {
      item.embeddingIds.push(record.embedding_id);
      item.faceOrigins.push(...(record.face_origins || []));
    } else byPath.set(path, { embeddingId: record.embedding_id, embeddingIds: [record.embedding_id], path,
      thumbPath: record.crop_path || path, qualityScore: record.quality_score,
      faceOrigins: [...(record.face_origins || [])], createdAt: record.created_at });
  }
  for (const media of payload.encounter_media || []) {
    if (!byPath.has(media.media_path)) byPath.set(media.media_path, { path: media.media_path, thumbPath: media.media_path,
      embeddingId: null, embeddingIds: [], faceOrigins: [{ face_origin: "ENCOUNTER" }], observationIds: media.observation_ids });
  }
  return [...byPath.values()];
}

function managementEventLabel(event) {
  if (event.operation_type === "person-preferences" || event.operation_type === "identity.preferences.update") {
    const changed = event.result?.changed_preferences || [];
    if (changed.includes("representative_photo") && changed.includes("favorite")) return "Profile photo and favorite updated";
    if (changed.includes("representative_photo")) return "Profile photo updated";
    if (changed.includes("favorite")) return event.result?.favorite ? "Added to favorites" : "Removed from favorites";
    return "Favorite or profile photo changed";
  }
  return {
    "identity.archive": "Person archived",
    "identity.restore": "Person restored",
    "identity.merge": "People merged",
    "identity.merge.revert": "People merge undone",
    "identity.face.move": "Photo moved",
    "biometric.face.delete": "Photo removed",
    "identity.profile.update": "Profile updated",
    "identity.preferences.update": "Favorite or profile photo changed",
    "identity.observation.correct": "Recognition identity corrected",
    "create-person-association": "Person association added",
    "create-placeholder-association": "Placeholder created and associated",
    "remove-person-association": "Person association removed",
  }[event.operation_type] || "People record updated";
}

function managementEventDetail(event) {
  const result = event.result || {};
  if (event.operation_type === "identity.merge") {
    return `${result.moved_embeddings || 0} photos and ${result.moved_sightings || 0} sightings moved`;
  }
  if (event.operation_type === "identity.merge.revert") {
    return `${result.restored_embeddings || 0} photos and ${result.restored_sightings || 0} sightings restored`;
  }
  if (event.operation_type === "identity.face.move") {
    return `${result.moved_sightings || 0} linked sightings moved with the photo`;
  }
  if (event.operation_type === "biometric.face.delete") {
    return `${result.deleted_sightings || 0} linked sightings removed with the photo`;
  }
  if (event.operation_type === "person-preferences" || event.operation_type === "identity.preferences.update") {
    const changed = result.changed_preferences || [];
    if (changed.includes("representative_photo") && changed.includes("favorite")) return "The representative photo and favorite status were changed";
    if (changed.includes("representative_photo")) return "The representative photo shown for this person was changed";
    if (changed.includes("favorite")) return result.favorite ? "This person was added to Favorites" : "This person was removed from Favorites";
    return "An older audit record changed either the representative photo or favorite status";
  }
  if (event.operation_type === "create-person-association") {
    return "A human-entered association was added between these person records";
  }
  if (event.operation_type === "create-placeholder-association") {
    return "A placeholder person was created and linked from the Associations section";
  }
  if (event.operation_type === "remove-person-association") {
    return "Only the association was removed; both person records were preserved";
  }
  return "Completed successfully";
}

function normalizeManagementChange(event) {
  return {
    id: event.operation_id,
    kind: "management",
    operationType: event.operation_type,
    createdAt: event.created_at,
    editor: typeof event.actor === "string"
      ? event.actor
      : event.actor?.display_name || event.actor?.username || "System",
    title: managementEventLabel(event),
    detail: managementEventDetail(event),
    fields: [],
  };
}

function historyChangeMatchesFilter(change, filter) {
  if (filter === "all") return true;
  if (filter === "identity") return change.operationType?.startsWith("identity.");
  if (filter === "metadata") return ["identity.profile.update", "identity.note.update"].includes(change.operationType);
  if (filter === "photos") return ["identity.preferences.update", "identity.face.move", "biometric.face.delete"].includes(change.operationType);
  if (filter === "management") return ["identity.archive", "identity.restore", "identity.merge", "identity.delete"].includes(change.operationType);
  return true;
}

function historyFilterLabel(filter) {
  return {
    all: "All Changes",
    identity: "Identity Changes",
    metadata: "Metadata Changes",
    photos: "Photo & Favorite Changes",
    management: "Record Management",
  }[filter] || "All Changes";
}

function compactChangeDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value).split("T").join(", ").slice(0, 22);
  return parsed.toLocaleString([], {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function PeopleEditableFields({ values, onChange }) {
  return (
    <SimpleGrid cols={{ base: 1, sm: 2 }}>
      <TextInput required label="Rank" value={values.rank} onChange={(event) => onChange("rank", event.target.value)} />
      <TextInput required label="Name" value={values.name} onChange={(event) => onChange("name", event.target.value)} />
      <CountrySelect value={values.country} onChange={(value) => onChange("country", value)} />
      <Select required label="Tag" data={NEW_PERSON_IMPORTANCE_OPTIONS} value={values.importance} onChange={(value) => onChange("importance", value)} />
      <Box style={{ gridColumn: "1 / -1" }}>
        <TagsInput
          label="Tags"
          description="Use tags for roles, teams, access groups, or other searchable labels"
          placeholder="Type a tag and press Enter"
          value={values.tags || []}
          onChange={(value) => onChange("tags", value)}
          maxTags={20}
        />
      </Box>
      <TextInput required label="Edited by" placeholder="Your name" value={values.editorName || ""} onChange={(event) => onChange("editorName", event.target.value)} />
    </SimpleGrid>
  );
}

function lifecycleStatusLabel(status) {
  return {
    ACTIVE: "Active",
    ARCHIVED: "Archived",
    DELETED: "Deleted",
    MERGED: "Merged",
  }[status] || status;
}
