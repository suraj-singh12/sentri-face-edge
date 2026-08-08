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
  Menu,
  Modal,
  Paper,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Tabs,
  TagsInput,
  Text,
  TextInput,
  ThemeIcon,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconAt,
  IconArchive,
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
  IconLink,
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
  IconTag,
  IconUser,
  IconUserPlus,
  IconUnlink,
} from "@tabler/icons-react";

import { EmptyCard, ImageFrame, SafeImage } from "../components/Shared.jsx";
import { NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import {
  detailsForEmbedding,
  formatSeenDateTime,
  mediaUrl,
  personProfile,
} from "../utils.js";

export function PeopleView({
  canEdit = false,
  canDestroy = false,
  people,
  archivedPeople,
  deletedFaces = [],
  peopleGallery,
  peopleGalleryImage,
  onRefresh,
  onOpen,
  onCreatePlaceholder,
  onCreateAssociation,
  onCreatePlaceholderAssociation,
  onRemoveAssociation,
  onImage,
  onBack,
  onSave,
  onFavorite,
  onSetRepresentative,
  onArchive,
  onRestore,
  onDelete,
  onMerge,
  onUndoMerge,
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
  const [placeholderValues, setPlaceholderValues] = useState({
    name: "", rank: "", country: "", importance: "", tags: [],
  });
  const resultsRef = useRef(null);
  const normalizedQuery = query.trim().toLowerCase();
  const statsCollection = filter === "archived" ? archivedPeople : people;
  const peopleStats = useMemo(() => {
    const totalPhotos = statsCollection.reduce((sum, person) => sum + Number(person.embedding_count || 0), 0);
    const addedToday = statsCollection.filter((person) => isTodayLike(person.created_at)).length;
    return { totalPhotos, addedToday };
  }, [statsCollection]);
  const visiblePeople = useMemo(() => {
    const collection = filter === "archived" ? archivedPeople : people;
    return collection
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
      })
      .sort((left, right) => {
        if (sort === "name") return compareText(left.name, right.name);
        if (sort === "country") return compareText(profileValue(left, "country"), profileValue(right, "country")) || compareText(left.name, right.name);
        if (sort === "rank") return compareText(profileValue(left, "rank"), profileValue(right, "rank")) || compareText(left.name, right.name);
        if (sort === "priority") return priorityScore(right) - priorityScore(left) || compareText(left.name, right.name);
        if (sort === "sightings") return sightingCount(right) - sightingCount(left) || compareText(left.name, right.name);
        if (sort === "frequency") return sightingFrequencyScore(right) - sightingFrequencyScore(left) || compareText(left.name, right.name);
        if (sort === "seen") return dateValue(right.last_seen_at) - dateValue(left.last_seen_at) || compareText(left.name, right.name);
        if (sort === "frequent") return frequentlySeenScore(right) - frequentlySeenScore(left) || compareText(left.name, right.name);
        return dateValue(right.created_at) - dateValue(left.created_at);
      });
  }, [archivedPeople, filter, normalizedQuery, people, sort]);
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
      {peopleGallery ? (
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
          onCreateAssociation={onCreateAssociation}
          onCreatePlaceholderAssociation={onCreatePlaceholderAssociation}
          onRemoveAssociation={onRemoveAssociation}
          onFavorite={onFavorite}
          onSetRepresentative={onSetRepresentative}
          onArchive={onArchive}
          onRestore={onRestore}
          onDelete={onDelete}
          onMerge={onMerge}
          onUndoMerge={onUndoMerge}
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
                      <Button leftSection={<IconUserPlus size={16} />} onClick={() => setPlaceholderOpen(true)}>
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
                    people={statsCollection}
                    totalPhotos={peopleStats.totalPhotos}
                    favoriteCount={statsCollection.filter((person) => person.favorite).length}
                    addedToday={peopleStats.addedToday}
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
        centered
      >
        <form onSubmit={async (event) => {
          event.preventDefault();
          if (placeholderBusy || !placeholderValues.name.trim()) return;
          setPlaceholderBusy(true);
          try {
            await onCreatePlaceholder(placeholderValues);
            setPlaceholderValues({ name: "", rank: "", country: "", importance: "", tags: [] });
            setPlaceholderOpen(false);
          } finally {
            setPlaceholderBusy(false);
          }
        }}>
          <Stack>
            <Text size="sm" c="dimmed">Create an identity-only profile now. A photograph and biometric data can be added later.</Text>
            <TextInput required autoFocus label="Name" value={placeholderValues.name} onChange={(event) => setPlaceholderValues((current) => ({ ...current, name: event.currentTarget.value }))} />
            <TextInput label="Rank or role" value={placeholderValues.rank} onChange={(event) => setPlaceholderValues((current) => ({ ...current, rank: event.currentTarget.value }))} />
            <TextInput label="Country" value={placeholderValues.country} onChange={(event) => setPlaceholderValues((current) => ({ ...current, country: event.currentTarget.value }))} />
            <Select clearable label="Importance" data={NEW_PERSON_IMPORTANCE_OPTIONS} value={placeholderValues.importance || null} onChange={(value) => setPlaceholderValues((current) => ({ ...current, importance: value || "" }))} />
            <TagsInput label="Tags" value={placeholderValues.tags} onChange={(tags) => setPlaceholderValues((current) => ({ ...current, tags }))} />
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
          <Alert color="red" icon={<IconShield size={18} />} title="This removes the live profile">
            {deleteTarget?.name} and all linked photos, deleted faces, sightings, associations, and profile history will be removed from the live library. Associated people themselves are not deleted. A verified safety backup is created first.
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
                  {face.person_archived && (
                    <Text size="xs" c="yellow.4" mt="sm">
                      Restore the archived person before restoring this face.
                    </Text>
                  )}
                  <Group grow mt="md">
                    <Button
                      variant="default"
                      size="xs"
                      onClick={() => onOpenPerson(face.person_id, { archived: face.person_archived })}
                    >
                      View person
                    </Button>
                    <Button
                      variant="light"
                      size="xs"
                      leftSection={<IconRestore size={15} />}
                      disabled={face.person_archived}
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

function PeopleStatsStrip({ people, totalPhotos, favoriteCount, addedToday, archived }) {
  const stats = archived ? [
    { label: "Archived Records", value: people.length, icon: IconArchive, color: "gray" },
    { label: "Retained Photos", value: totalPhotos.toLocaleString(), icon: IconImageInPicture, color: "violet" },
    { label: "Merged Records", value: people.filter((person) => person.metadata?.merged_into).length, icon: IconSwitchHorizontal, color: "blue" },
    { label: "Archived Today", value: people.filter((person) => isTodayLike(person.deleted_at)).length, icon: IconRefresh, color: "green" },
  ] : [
    { label: "Total People", value: people.length, icon: IconUser, color: "teal" },
    { label: "With Photos", value: people.filter((person) => Number(person.embedding_count || 0)).length, icon: IconImageInPicture, color: "violet" },
    { label: "No Photos", value: people.filter((person) => !Number(person.embedding_count || 0)).length, icon: IconUser, color: "indigo" },
    { label: "Favorites", value: favoriteCount, icon: IconStar, color: "yellow" },
    { label: "Seen in last 7 days", value: people.filter((person) => daysSince(person.last_seen_at) <= 7).length, icon: IconEye, color: "blue" },
    { label: "Added Today", value: addedToday, icon: IconRefresh, color: "blue" },
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
        const isArchived = archived || Boolean(person.archived || person.deleted_at);
        return (
          <PersonCard
            key={person.person_id}
            person={person}
            favorite={Boolean(person.favorite)}
            archived={isArchived}
            viewMode={viewMode}
            canDestroy={canDestroy}
            onOpen={() => onOpen(person.person_id, { archived: isArchived })}
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
  const openPerson = () => onOpen(person.person_id);
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
        <Box component="button" type="button" className="people-card-main" onClick={openPerson} aria-label={`Open ${person.name}`}>
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
              {archived && <Badge color="gray" variant="light">{person.metadata?.merged_into ? "Merged" : "Archived"}</Badge>}
            </Group>
            <Group gap="xs" mt={4} wrap="nowrap">
              <Text size="xs" c="dimmed" fw={700}>{rank}</Text>
              <Badge color={priority.color} variant="light" size="xs">{priority.label}</Badge>
            </Group>
            <Text size="xs" c="dimmed" mt={5}>
              {person.is_placeholder ? "No photograph · No biometric data" : <>{photoCount} {photoCount === 1 ? "photo" : "photos"} <Text span mx={5}>·</Text> {sightings} {sightings === 1 ? "sighting" : "sightings"}</>}
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
          disabled={archived}
          aria-label={archived ? "Archived person" : favorite ? "Remove favorite" : "Add favorite"}
        >
          {favorite ? <IconStar size={15} fill="currentColor" /> : <IconStar size={15} />}
        </ActionIcon>
        <Group justify="space-between" wrap="nowrap" className="people-card-actions">
          <Button fullWidth size="compact-xs" variant="subtle" onClick={(event) => { event.stopPropagation(); openPerson(); }}>
            {archived ? "Review archived" : "Open profile"}
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
  if (groupBy === "country") return profileValue(person, "country") || "Unknown Country";
  if (groupBy === "rank") return profileValue(person, "rank") || "Unspecified Rank";
  if (groupBy === "priority") return `${priorityDetails(person).longLabel} Priority`;
  if (groupBy === "frequency") return sightingFrequencyLabel(person);
  if (groupBy === "frequent") {
    if (!sightingCount(person)) return "Not Seen Yet";
    return sightingFrequencyScore(person) >= 3 && daysSince(person.last_seen_at) <= 30
      ? "Frequently Seen"
      : "Seen Occasionally";
  }
  return "All People";
}

function profileValue(person, key) {
  return String(person?.metadata?.[key] || "").trim();
}

function compareText(left, right) {
  return String(left || "").localeCompare(String(right || ""), undefined, { sensitivity: "base" });
}

function dateValue(value) {
  const parsed = new Date(value || 0).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

function daysSince(value) {
  const timestamp = dateValue(value);
  if (!timestamp) return Number.POSITIVE_INFINITY;
  return Math.max(0, (Date.now() - timestamp) / 86_400_000);
}

function sightingCount(person) {
  return Number(person?.sighting_count || 0);
}

function sightingFrequencyScore(person) {
  const activeMonths = Math.max(1, daysSince(person?.created_at) / 30);
  return sightingCount(person) / activeMonths;
}

function frequentlySeenScore(person) {
  const recencyWeight = Math.max(0.1, 1 - (daysSince(person?.last_seen_at) / 365));
  return sightingFrequencyScore(person) * recencyWeight;
}

function sightingFrequencyLabel(person) {
  const score = sightingFrequencyScore(person);
  if (score >= 8) return "Very Frequent";
  if (score >= 3) return "Frequent";
  if (score >= 1) return "Occasional";
  if (sightingCount(person)) return "Rare";
  return "Never Seen";
}

function priorityScore(person) {
  const value = profileValue(person, "importance").toLowerCase();
  if (value === "important" || value === "high") return 3;
  if (value === "suspicious" || value === "watch") return 2;
  if (value === "regular" || value === "medium") return 1;
  return 0;
}

function priorityDetails(person) {
  const score = priorityScore(person);
  if (score === 3) return { label: "HIGH", longLabel: "High", color: "red" };
  if (score === 2) return { label: "WATCH", longLabel: "Watch", color: "orange" };
  if (score === 1) return { label: "REGULAR", longLabel: "Regular", color: "yellow" };
  return { label: "UNSPECIFIED", longLabel: "Unspecified", color: "gray" };
}

function lastSeenLabelForCard(value) {
  const days = daysSince(value);
  if (!Number.isFinite(days)) return "Never seen";
  if (days < 1) return "Seen today";
  const rounded = Math.floor(days);
  return `Seen ${rounded} day${rounded === 1 ? "" : "s"} ago`;
}

function isTodayLike(value) {
  if (!value) return false;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return false;
  return parsed.toDateString() === new Date().toDateString();
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
  onCreateAssociation,
  onCreatePlaceholderAssociation,
  onRemoveAssociation,
  onFavorite,
  onSetRepresentative,
  onArchive,
  onRestore,
  onDelete,
  onMerge,
  onUndoMerge,
  onMovePhoto,
  onDeletePhoto,
}) {
  const imageRecords = profileImageRecords(payload);
  const tabContentRef = useRef(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [editOpen, setEditOpen] = useState(false);
  const [managementDialog, setManagementDialog] = useState(null);
  const [targetPersonId, setTargetPersonId] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const [profileDeleteConfirmation, setProfileDeleteConfirmation] = useState("");
  const archived = Boolean(payload.person.archived);
  const mergedInto = payload.person.metadata?.merged_into || "";
  const favorite = Boolean(payload.person.favorite || payload.person.metadata?.favorite);
  const selectedRecord = selectedImage
    ? imageRecords.find((record) => record.path === selectedImage || record.thumbPath === selectedImage) || imageRecords[0]
    : imageRecords[0] || null;
  const selectedPath = selectedRecord?.path || "";
  const selectedDetails = selectedRecord ? detailsForEmbedding(payload.details || [], selectedRecord.embeddingId) : [];
  const profile = personProfile(payload, selectedDetails, Boolean(selectedRecord));
  const summaryProfile = personProfile(payload);
  const latestSightings = [...(payload.details || [])].filter(isSeenDetail).sort(compareSightingsNewestFirst);
  const recentSightings = latestSightings.slice(0, 3);
  const latestSightingLabel = lastSeenLabel(latestSightings[0]);
  const changes = payload.changes || [];
  const managementEvents = payload.management_events || [];
  const associations = payload.associations || [];
  const mergeEvent = managementEvents.find((event) => (
    event.operation_type === "merge-persons"
    && event.result?.source_person_id === payload.person.person_id
    && event.result?.target_person_id === mergedInto
  ));
  const mergeWasUndone = managementEvents.some((event) => (
    event.operation_type === "undo-merge-persons"
    && event.result?.merge_operation_id === mergeEvent?.operation_id
  ));
  const canUndoMerge = Boolean(mergeEvent?.result?.undo_supported && !mergeWasUndone);
  const [editValues, setEditValues] = useState(summaryProfile);

  useEffect(() => {
    setActiveTab("overview");
    setEditOpen(false);
    setManagementDialog(null);
    setTargetPersonId("");
    setProfileDeleteConfirmation("");
  }, [payload.person.person_id]);

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
    .filter((person) => person.person_id !== payload.person.person_id)
    .map((person) => ({
      value: person.person_id,
      label: `${person.name} · ${person.embedding_count || 0} photos`,
    }));
  const runManagement = async (action) => {
    if (actionBusy) return;
    setActionBusy(true);
    try {
      await action();
      setManagementDialog(null);
      setTargetPersonId("");
    } catch (error) {
      console.error(error);
    } finally {
      setActionBusy(false);
    }
  };

  return (
    <Stack className="people-profile-shell">
      <Group justify="space-between" align="flex-start" wrap="nowrap" className="people-profile-topbar">
        <Group gap="xs">
          <ActionIcon variant="subtle" onClick={onBack} aria-label="Back to people"><IconArrowLeft size={18} /></ActionIcon>
          <Text size="xs" c="dimmed">All People</Text>
          <Text size="xs" c="dimmed">/</Text>
          <Text size="xs">{payload.person.name}</Text>
        </Group>
        <Group gap="xs">
          {!archived && (
            <>
              <Button size="xs" variant="default" leftSection={<IconPhoto size={14} />} disabled={!canEdit && !canDestroy} onClick={() => changeTab("photos")}>
                Manage faces
              </Button>
              <Button size="xs" disabled={!canEdit} onClick={() => setEditOpen(true)}>Edit profile</Button>
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
          {archived && !mergedInto && (
            <Button size="xs" leftSection={<IconRestore size={14} />} disabled={!canDestroy} onClick={() => setManagementDialog("restore")}>
              Restore
            </Button>
          )}
          {archived && mergedInto && (
            <>
              {canUndoMerge && (
                <Button
                  size="xs"
                  color="orange"
                  variant="light"
                  leftSection={<IconRestore size={14} />}
                  disabled={!canDestroy}
                  onClick={() => setManagementDialog("undo-merge")}
                >
                  Undo merge
                </Button>
              )}
              <Button
                size="xs"
                variant="default"
                leftSection={<IconSwitchHorizontal size={14} />}
                onClick={() => onOpen(mergedInto)}
              >
                View merged person
              </Button>
            </>
          )}
          <Menu withinPortal position="bottom-end">
            <Menu.Target>
              <Button size="xs" variant="default" rightSection={<IconChevronDown size={14} />}>More</Button>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconCopy size={14} />} onClick={() => navigator.clipboard?.writeText(payload.person.person_id)}>Copy ID</Menu.Item>
              {!archived && (
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
              <Menu.Item color="red" leftSection={<IconTrash size={14} />} disabled={!canDestroy} onClick={() => {
                setProfileDeleteConfirmation("");
                setManagementDialog("delete-profile");
              }}>
                Delete entire profile
              </Menu.Item>
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
            {archived && <Badge color="gray">{mergedInto ? "Merged record" : "Archived"}</Badge>}
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
            {payload.person.is_placeholder && <Badge color="gray" variant="light">No biometric data</Badge>}
          </Group>
          <Text size="xs" c="dimmed" mt="sm">ID: {payload.person.person_id}</Text>
        </Box>
      </Group>

      <Tabs value={activeTab} onChange={changeTab} className="people-profile-tabs" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="overview">Overview</Tabs.Tab>
          <Tabs.Tab value="photos">Photos ({imageRecords.length})</Tabs.Tab>
          <Tabs.Tab value="sightings">Sightings ({latestSightings.length})</Tabs.Tab>
          <Tabs.Tab value="associations">Associations ({associations.length})</Tabs.Tab>
          <Tabs.Tab value="changes">Activity ({changes.length + managementEvents.length})</Tabs.Tab>
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
        <Tabs.Panel value="associations">
          <PeopleProfileAssociations
            person={payload.person}
            people={people}
            associations={associations}
            canEdit={canEdit && !archived}
            onOpen={onOpen}
            onCreate={onCreateAssociation}
            onCreatePlaceholder={onCreatePlaceholderAssociation}
            onRemove={onRemoveAssociation}
          />
        </Tabs.Panel>
        <Tabs.Panel value="changes">
          <PeopleProfileChanges changes={changes} managementEvents={managementEvents} currentProfile={summaryProfile} />
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

      <Modal
        opened={managementDialog === "archive"}
        onClose={() => !actionBusy && setManagementDialog(null)}
        title="Archive this person?"
        centered
      >
        <Stack>
          <Text size="sm">
            {payload.person.name} will stop appearing in recognition results. Their {imageRecords.length} photos, {latestSightings.length} sightings, and {associations.length} associations will be retained and can be restored later.
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
          <Alert color="red" icon={<IconShield size={18} />} title="This cannot be undone in the live library">
            <strong>{payload.person.name}</strong>, {imageRecords.length} photo record{imageRecords.length === 1 ? "" : "s"}, {latestSightings.length} sighting{latestSightings.length === 1 ? "" : "s"}, {associations.length} association{associations.length === 1 ? "" : "s"}, deleted faces, and profile history will be removed. Associated people themselves are preserved. A verified safety backup is created first.
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
          <Text size="sm">
            All photos and sightings from <strong>{payload.person.name}</strong> will move to the selected person. This profile will then be archived as a merge record.
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
        opened={managementDialog === "undo-merge"}
        onClose={() => !actionBusy && setManagementDialog(null)}
        title="Undo this merge?"
        centered
      >
        <Stack>
          <Text size="sm">
            SentriFace will restore <strong>{payload.person.name}</strong> as a separate active person and return exactly the photos and sightings recorded by the merge.
          </Text>
          <Alert color="orange" title="Protected undo">
            Undo stops without changing anything if either profile or any merged photo changed after the merge. A safety backup is created first.
          </Alert>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setManagementDialog(null)} disabled={actionBusy}>Cancel</Button>
            <Button
              color="orange"
              loading={actionBusy}
              leftSection={<IconRestore size={16} />}
              onClick={() => runManagement(() => onUndoMerge(mergeEvent.operation_id))}
            >
              Undo merge
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
            The selected photo and its {selectedDetails.length} linked sighting{selectedDetails.length === 1 ? "" : "s"} will move together.
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
            ["Importance", profile.importance || "-"],
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
            <Text size="sm" fw={700}>All Faces ({records.length})</Text>
            <Text size="xs" c="dimmed">Select a face to set it as the profile photo, move it, or delete it.</Text>
          </Box>
        </Group>
        <Group gap="sm" mb="md" className="people-profile-thumb-row">
          {records.map((record) => (
            <Card
              key={record.embeddingId}
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
            ["Rank", profile.rank || "-"],
          ]} />
          {!archived && selectedRecord && (
            <Stack gap="xs" mt="lg">
              <Button
                variant="light"
                leftSection={<IconPhotoStar size={16} />}
                disabled={!canEdit || selectedRecord.embeddingId === representativeEmbeddingId}
                onClick={onSetRepresentative}
              >
                {selectedRecord.embeddingId === representativeEmbeddingId ? "Current profile photo" : "Set as profile photo"}
              </Button>
              <Button variant="default" leftSection={<IconSwitchHorizontal size={16} />} disabled={!canDestroy} onClick={onMove}>
                Move to another person
              </Button>
              <Button color="red" variant="light" leftSection={<IconTrash size={16} />} disabled={!canDestroy} onClick={onDelete}>
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
        <Card key={detail.detail_id} withBorder radius="md" component="button" className="mantine-click-card people-sighting-card" onClick={() => onSighting(detail)}>
          <Group justify="space-between" align="center" wrap="nowrap">
            <SightingSummary detail={detail} />
            <SightingImage detail={detail} imageRecords={imageRecords} size={92} />
          </Group>
        </Card>
      )) : <EmptyCard text="No sightings recorded yet." />}
    </Stack>
  );
}

function PeopleProfileAssociations({
  person,
  people,
  associations,
  canEdit,
  onOpen,
  onCreate,
  onCreatePlaceholder,
  onRemove,
}) {
  const [query, setQuery] = useState("@");
  const [selectedPersonId, setSelectedPersonId] = useState("");
  const [busy, setBusy] = useState(false);
  const [removeTarget, setRemoveTarget] = useState(null);
  const searchText = query.replace(/^@/, "").trim();
  const normalizedSearch = searchText.toLowerCase();
  const associatedIds = new Set(associations.map((item) => item.person?.person_id));
  const allMatches = normalizedSearch ? people.filter((candidate) => [
    candidate.name,
    candidate.person_id,
    candidate.metadata?.rank,
    candidate.metadata?.country,
  ].filter(Boolean).some((value) => String(value).toLowerCase().includes(normalizedSearch))) : [];
  const availableMatches = allMatches
    .filter((candidate) => candidate.person_id !== person.person_id && !associatedIds.has(candidate.person_id))
    .slice(0, 8);
  const selectedPerson = people.find((candidate) => candidate.person_id === selectedPersonId) || null;
  const clearSearch = () => {
    setQuery("@");
    setSelectedPersonId("");
  };
  const run = async (action) => {
    if (busy) return;
    setBusy(true);
    try {
      await action();
      clearSearch();
    } finally {
      setBusy(false);
    }
  };
  return (
    <Stack mt="md" gap="md" className="people-associations-panel">
      <Card withBorder radius="md" className="people-profile-panel">
        <Group gap="sm" mb="xs">
          <ThemeIcon variant="light"><IconAt size={18} /></ThemeIcon>
          <Box>
            <Text fw={800}>Link another person</Text>
            <Text size="xs" c="dimmed">Type @ followed by a name, role, country, or person ID. A link is created only after you confirm it.</Text>
          </Box>
        </Group>
        <TextInput
          disabled={!canEdit || busy}
          value={query}
          onChange={(event) => {
            const value = event.currentTarget.value;
            setQuery(value.startsWith("@") ? value : `@${value}`);
            setSelectedPersonId("");
          }}
          leftSection={<IconAt size={16} />}
          placeholder="@Name"
          aria-label="Search people to associate"
        />
        {selectedPerson ? (
          <Group justify="space-between" mt="sm">
            <AssociationIdentity person={selectedPerson} />
            <Button
              loading={busy}
              leftSection={<IconLink size={16} />}
              onClick={() => run(() => onCreate(person.person_id, selectedPerson.person_id))}
            >
              Link person
            </Button>
          </Group>
        ) : normalizedSearch ? (
          <Stack gap="xs" mt="sm">
            {availableMatches.map((candidate) => (
              <Paper
                key={candidate.person_id}
                withBorder
                radius="md"
                p="sm"
                component="button"
                type="button"
                className="mantine-click-card association-search-result"
                onClick={() => {
                  setSelectedPersonId(candidate.person_id);
                  setQuery(`@${candidate.name}`);
                }}
              >
                <AssociationIdentity person={candidate} />
              </Paper>
            ))}
            {!availableMatches.length && allMatches.length > 0 && (
              <Text size="sm" c="dimmed">Matching people are already linked or refer to this profile.</Text>
            )}
            {!allMatches.length && (
              <Paper withBorder radius="md" p="sm">
                <Group justify="space-between" gap="md">
                  <Box>
                    <Text fw={700}>No existing person matches “{searchText}”</Text>
                    <Text size="xs" c="dimmed">Create an identity-only profile, then link it to {person.name}.</Text>
                  </Box>
                  <Button
                    variant="light"
                    loading={busy}
                    leftSection={<IconUserPlus size={16} />}
                    onClick={() => run(() => onCreatePlaceholder(person.person_id, searchText))}
                  >
                    Create placeholder “{searchText}”
                  </Button>
                </Group>
              </Paper>
            )}
          </Stack>
        ) : null}
      </Card>

      <Card withBorder radius="md" className="people-profile-panel">
        <Text fw={800} mb="md">Associated people ({associations.length})</Text>
        <Stack gap="xs">
          {associations.length ? associations.map((association) => (
            <Paper
              key={association.association_id}
              withBorder
              radius="md"
              p="sm"
              component="div"
              role="button"
              tabIndex={0}
              className="mantine-click-card association-person-row"
              onClick={() => onOpen(association.person.person_id, { archived: Boolean(association.person.archived) })}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onOpen(association.person.person_id, { archived: Boolean(association.person.archived) });
                }
              }}
            >
              <Group justify="space-between" wrap="nowrap">
                <AssociationIdentity person={association.person} />
                <Group gap="xs" wrap="nowrap">
                  <Badge variant="light" color="gray">Associated with</Badge>
                  {canEdit && (
                    <Tooltip label="Remove association">
                      <ActionIcon
                        color="red"
                        variant="subtle"
                        aria-label={`Remove association with ${association.person.name}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          setRemoveTarget(association);
                        }}
                      >
                        <IconUnlink size={17} />
                      </ActionIcon>
                    </Tooltip>
                  )}
                </Group>
              </Group>
            </Paper>
          )) : <EmptyCard text="No person associations recorded yet." />}
        </Stack>
      </Card>

      <Modal
        opened={Boolean(removeTarget)}
        onClose={() => !busy && setRemoveTarget(null)}
        title="Remove this association?"
        centered
      >
        <Stack>
          <Text size="sm">
            Remove the association between <strong>{person.name}</strong> and <strong>{removeTarget?.person?.name}</strong>?
          </Text>
          <Alert color="blue" title="Profiles are preserved">
            This removes only the association. Neither person nor their photos, biometric data, or history will be deleted.
          </Alert>
          <Group justify="flex-end">
            <Button variant="default" disabled={busy} onClick={() => setRemoveTarget(null)}>Cancel</Button>
            <Button
              color="red"
              loading={busy}
              leftSection={<IconUnlink size={16} />}
              onClick={async () => {
                if (!removeTarget) return;
                await run(() => onRemove(person.person_id, removeTarget.association_id));
                setRemoveTarget(null);
              }}
            >
              Remove association
            </Button>
          </Group>
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
      <ThemeIcon size={42} radius="xl" variant="light" color="gray"><IconUser size={22} /></ThemeIcon>
      <Box miw={0}>
        <Group gap="xs" wrap="nowrap">
          <Text fw={800} truncate>{person.name}</Text>
          {person.is_placeholder && <Badge size="xs" color="gray" variant="light">No photo</Badge>}
          {person.archived && <Badge size="xs" color="gray">Archived</Badge>}
        </Group>
        <Text size="xs" c="dimmed" truncate>{rank} · {country} · ID {String(person.person_id || "").slice(0, 8)} · {person.embedding_count || 0} photos</Text>
      </Box>
    </Group>
  );
}

function PeopleProfileChanges({ changes, managementEvents, currentProfile }) {
  const changeCards = changes.map(normalizeChange).filter((change) => change.fields.length);
  const historyCards = [
    ...changeCards,
    ...managementEvents.map(normalizeManagementChange),
  ].sort((left, right) => new Date(right.createdAt || 0).getTime() - new Date(left.createdAt || 0).getTime());
  const [historyFilter, setHistoryFilter] = useState("all");
  const [historyView, setHistoryView] = useState("cards");
  const [activeIndex, setActiveIndex] = useState(0);
  const filteredHistoryCards = historyCards.filter((change) => historyChangeMatchesFilter(change, historyFilter));
  const activeHistory = filteredHistoryCards[activeIndex] || null;
  const activeChange = activeHistory?.kind === "profile" ? activeHistory : null;
  const changedFields = new Set(activeChange?.fields.map((field) => field.key) || []);
  useEffect(() => setActiveIndex(0), [historyFilter]);
  return (
    <Box mt="md" className="people-change-history-shell">
      <Card withBorder radius="md" className="people-profile-panel people-current-diff-card">
        <Group justify="space-between" mb="md">
          <Box>
            <Text fw={900} c="teal.3">Current Information (Latest)</Text>
            <Text size="xs" c="dimmed">Compared with selected change on the right</Text>
          </Box>
          {activeChange && <Badge variant="light" className="current-updated-badge">Up to date</Badge>}
        </Group>
        <Stack gap="xs">
          <CurrentInfoRow icon={IconUser} label="Name" value={currentProfile.name || "-"} active={changedFields.has("name")} />
          <CurrentInfoRow icon={IconShield} label="Rank" value={currentProfile.rank || "-"} active={changedFields.has("rank")} />
          <CurrentInfoRow icon={IconGlobe} label="Country" value={currentProfile.country || "-"} active={changedFields.has("country")} />
          <CurrentInfoRow icon={IconFlag} label="Importance" value={currentProfile.importance || "-"} active={changedFields.has("importance")} pill={importanceColor(currentProfile.importance)} />
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
              {change.kind === "profile" ? (
                <Stack gap={0} className="people-change-field-list">
                  {change.fields.map((field) => <ChangeFieldRow key={field.key} field={field} />)}
                </Stack>
              ) : (
                <Stack gap="sm" className="people-change-management-summary">
                  <ThemeIcon size={42} radius="xl" variant="light"><IconRefresh size={21} /></ThemeIcon>
                  <Text fw={800}>{change.title}</Text>
                  <Text size="sm" c="dimmed">{change.detail}</Text>
                </Stack>
              )}
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

function SightingImage({ detail, imageRecords, fallbackPath, size = 56 }) {
  const record = imageRecords.find((item) => item.embeddingId === detail.embedding_id);
  const path = record?.thumbPath || record?.path || fallbackPath;
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

function DiffRow({ label, value, tone }) {
  return (
    <Paper withBorder radius="md" p="sm" className={tone === "new" ? "diff-row diff-row--new" : "diff-row"}>
      <Text size="xs" c="dimmed">{label}</Text>
      <Text fw={800}>{value}</Text>
    </Paper>
  );
}

function ChangeFieldRow({ field }) {
  const Icon = iconForChangeField(field.key);
  return (
    <Group gap="sm" wrap="nowrap" className="change-field-row">
      <ThemeIcon variant="subtle" color="gray" size="sm"><Icon size={15} /></ThemeIcon>
      <Text size="xs" className="change-field-label">{field.label}</Text>
      <Text size="xs" className="diff-old">{field.from || "—"}</Text>
      <Text size="xs" c="dimmed">→</Text>
      <Text size="xs" className="diff-new">{field.to || "—"}</Text>
    </Group>
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
    </Stack>
  );
}

function isSeenDetail(detail) {
  return Boolean(detail?.place_seen || detail?.date || detail?.time || detail?.event_occasion || detail?.added_by);
}

function compareSightingsNewestFirst(left, right) {
  return sightingTimestamp(right) - sightingTimestamp(left);
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
  return (payload.embeddings || [])
    .map((record) => ({
      embeddingId: record.embedding_id,
      path: record.source_image || record.crop_path,
      thumbPath: record.crop_path || record.source_image,
      qualityScore: record.quality_score,
      createdAt: record.created_at,
    }))
    .filter((record) => record.path);
}

function managementEventLabel(event) {
  if (event.operation_type === "person-preferences") {
    const changed = event.result?.changed_preferences || [];
    if (changed.includes("representative_photo") && changed.includes("favorite")) return "Profile photo and favorite updated";
    if (changed.includes("representative_photo")) return "Profile photo updated";
    if (changed.includes("favorite")) return event.result?.favorite ? "Added to favorites" : "Removed from favorites";
    return "Favorite or profile photo changed";
  }
  return {
    "archive-person": "Person archived",
    "restore-person": "Person restored",
    "merge-persons": "People merged",
    "undo-merge-persons": "People merge undone",
    "move-embedding": "Photo moved",
    "delete-embedding": "Photo removed",
    "update-profile": "Profile updated",
    "create-person-association": "Person association added",
    "create-placeholder-association": "Placeholder created and associated",
    "remove-person-association": "Person association removed",
  }[event.operation_type] || "People record updated";
}

function managementEventDetail(event) {
  const result = event.result || {};
  if (event.operation_type === "merge-persons") {
    return `${result.moved_embeddings || 0} photos and ${result.moved_sightings || 0} sightings moved`;
  }
  if (event.operation_type === "undo-merge-persons") {
    return `${result.restored_embeddings || 0} photos and ${result.restored_sightings || 0} sightings restored`;
  }
  if (event.operation_type === "move-embedding") {
    return `${result.moved_sightings || 0} linked sightings moved with the photo`;
  }
  if (event.operation_type === "delete-embedding") {
    return `${result.deleted_sightings || 0} linked sightings removed with the photo`;
  }
  if (event.operation_type === "person-preferences") {
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

function normalizeChange(change) {
  const fields = [
    ["name", "Name", change.previous_name, change.new_name],
    ["rank", "Rank", change.previous_rank, change.new_rank],
    ["country", "Country", change.previous_country, change.new_country],
    ["importance", "Importance", change.previous_importance, change.new_importance],
    ["status", "Biometric status", change.previous_status, change.new_status],
    ["tags", "Tags", change.previous_tags, change.new_tags],
    ["notes", "Notes", change.previous_notes, change.new_notes],
  ]
    .filter(([, , from, to]) => (from || "") !== (to || ""))
    .map(([key, label, from, to]) => ({ key, label, from, to }));
  return {
    id: change.change_id,
    kind: "profile",
    createdAt: change.created_at,
    editor: change.editor_name,
    fields,
  };
}

function normalizeManagementChange(event) {
  return {
    id: event.operation_id,
    kind: "management",
    operationType: event.operation_type,
    createdAt: event.created_at,
    editor: "System",
    title: managementEventLabel(event),
    detail: managementEventDetail(event),
    fields: [],
  };
}

function historyChangeMatchesFilter(change, filter) {
  if (filter === "all") return true;
  if (filter === "identity") return change.kind === "profile" && change.fields.some((field) => ["name", "status"].includes(field.key));
  if (filter === "metadata") return change.kind === "profile" && change.fields.some((field) => field.key !== "name");
  if (filter === "photos") return ["person-preferences", "move-embedding", "delete-embedding"].includes(change.operationType);
  if (filter === "management") return change.kind === "management"
    && !["person-preferences", "move-embedding", "delete-embedding"].includes(change.operationType);
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

function iconForChangeField(key) {
  return {
    name: IconUser,
    rank: IconShield,
    country: IconGlobe,
    importance: IconFlag,
    tags: IconTag,
    notes: IconNotes,
    status: IconPhoto,
  }[key] || IconEdit;
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
      <TextInput required label="Country" value={values.country} onChange={(event) => onChange("country", event.target.value)} />
      <Select required label="Importance" data={NEW_PERSON_IMPORTANCE_OPTIONS} value={values.importance} onChange={(value) => onChange("importance", value)} />
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

function PeopleInfoFields({ profile, details }) {
  return (
    <Stack>
      <Badge size="lg" variant="light">{profile.scopeLabel}</Badge>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <InfoLine label="Rank" value={profile.rank} />
        <InfoLine label="Name" value={profile.name} />
        <InfoLine label="Country" value={profile.country} />
        <InfoLine label="Importance" value={profile.importance} />
      </SimpleGrid>
      <Card withBorder radius="md">
        <Text fw={700} mb="sm">Seen At</Text>
        <SeenAtList details={details} />
      </Card>
    </Stack>
  );
}

function PeopleChangesPanel({ payload, profile, onBack }) {
  const changes = payload.changes || [];
  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <Box>
          <Text fw={700}>Changes</Text>
          <Text size="xs" c="dimmed">Latest changes first</Text>
        </Box>
        <Button size="xs" variant="light" leftSection={<IconArrowLeft size={14} />} onClick={onBack}>Back</Button>
      </Group>
      <PeopleInfoFields profile={profile} details={payload.details || []} />
      {changes.length ? changes.map((change) => (
        <Card key={change.change_id} withBorder radius="md">
          <Text size="xs" c="dimmed" mb="xs">{change.created_at}</Text>
          <Stack gap={6}>
            <ChangeLine label="Rank" from={change.previous_rank} to={change.new_rank} editor={change.editor_name} />
            <ChangeLine label="Name" from={change.previous_name} to={change.new_name} editor={change.editor_name} />
            <ChangeLine label="Country" from={change.previous_country} to={change.new_country} editor={change.editor_name} />
            <ChangeLine label="Importance" from={change.previous_importance} to={change.new_importance} editor={change.editor_name} />
          </Stack>
        </Card>
      )) : <EmptyCard text="No changes recorded yet." />}
    </Stack>
  );
}

function InfoLine({ label, value }) {
  return (
    <Paper withBorder radius="md" p="sm">
      <Text size="xs" c="dimmed" fw={700}>{label}</Text>
      <Text fw={700}>{value || "-"}</Text>
    </Paper>
  );
}

function ChangeLine({ label, from, to, editor }) {
  if ((from || "") === (to || "")) return null;
  return (
    <Text size="sm">
      <Text span fw={700}>{label}: </Text>{from || "-"} -&gt; {to || "-"} <Text span c="dimmed">(By {editor || "-"})</Text>
    </Text>
  );
}

function SeenAtList({ details }) {
  const items = (details || []).filter((detail) => detail.place_seen || detail.date || detail.time || detail.event_occasion || detail.added_by);
  if (!items.length) return <Text size="sm" c="dimmed">No seen-at details saved.</Text>;
  return (
    <Stack gap="xs">
      {items.map((detail) => (
        <Paper key={detail.detail_id} withBorder radius="md" p="sm" className="detail-history-card">
          <Text fw={700}>{detail.place_seen || "-"}</Text>
          <Text size="xs" c="dimmed">
            [AT] {formatSeenDateTime(detail)} | [Event] {detail.event_occasion || "-"} | [Added by] - {detail.added_by || "-"}
          </Text>
        </Paper>
      ))}
    </Stack>
  );
}
