import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Card,
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
  IconArchive,
  IconChevronDown,
  IconCopy,
  IconDots,
  IconEdit,
  IconFilter,
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
  IconTag,
  IconUser,
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
  onImage,
  onBack,
  onSave,
  onFavorite,
  onSetRepresentative,
  onArchive,
  onRestore,
  onMerge,
  onMovePhoto,
  onDeletePhoto,
  onRestoreDeletedFace,
  onPermanentlyDeleteFace,
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("recent");
  const [viewMode, setViewMode] = useState("grid");
  const [pageSize, setPageSize] = useState("12");
  const [page, setPage] = useState(1);
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
        if (sort === "name") return String(left.name || "").localeCompare(String(right.name || ""));
        if (sort === "photos") return Number(right.embedding_count || 0) - Number(left.embedding_count || 0);
        return new Date(right.created_at || 0).getTime() - new Date(left.created_at || 0).getTime();
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
  }, [filter, normalizedQuery, pageSize, sort, viewMode]);

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
          onFavorite={onFavorite}
          onSetRepresentative={onSetRepresentative}
          onArchive={onArchive}
          onRestore={onRestore}
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
                  <PeopleToolbar
                    query={query}
                    filter={filter}
                    sort={sort}
                    viewMode={viewMode}
                    onQuery={setQuery}
                    onFilter={setFilter}
                    onSort={setSort}
                    onViewMode={setViewMode}
                  />
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
                      <Box className={viewMode === "list" ? "people-card-list" : "people-card-grid"}>
                        {pagePeople.map((person) => (
                          <PersonCard
                            key={person.person_id}
                            person={person}
                            favorite={Boolean(person.favorite)}
                            archived={Boolean(person.archived)}
                            viewMode={viewMode}
                            onOpen={() => onOpen(person.person_id, { archived: Boolean(person.archived) })}
                            onFavorite={() => toggleFavorite(person)}
                          />
                        ))}
                      </Box>
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
    </Paper>
  );
}

function PeopleToolbar({ query, filter, sort, viewMode, onQuery, onFilter, onSort, onViewMode }) {
  const filterLabel = {
    all: "Filter",
    favorites: "Favorites",
    withPhotos: "With Photos",
    withoutPhotos: "No Photos",
    archived: "Archived",
  }[filter];
  const sortLabel = {
    recent: "Newest Added",
    name: "Name",
    photos: "Photo Count",
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
          <Button variant="default" leftSection={<IconSortDescending size={16} />} rightSection={<IconChevronDown size={15} />}>Sort: {sortLabel}</Button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item onClick={() => onSort("recent")}>Newest Added</Menu.Item>
          <Menu.Item onClick={() => onSort("name")}>Name</Menu.Item>
          <Menu.Item onClick={() => onSort("photos")}>Photo Count</Menu.Item>
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
    { label: "Total Photos", value: totalPhotos.toLocaleString(), icon: IconImageInPicture, color: "violet" },
    { label: "Favorites", value: favoriteCount, icon: IconStar, color: "yellow" },
    { label: "Added Today", value: addedToday, icon: IconRefresh, color: "blue" },
  ];
  return (
    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="sm" className="people-stats-strip">
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

function PersonCard({ person, favorite, archived, viewMode, onOpen, onFavorite }) {
  const cardClass = viewMode === "list" ? "people-person-card people-person-card--list" : "people-person-card";
  const openPerson = () => onOpen(person.person_id);
  const toggleFavorite = (event) => {
    event.stopPropagation();
    onFavorite();
  };
  const photoCount = Number(person.embedding_count || 0);
  const photoFallback = <ThemeIcon size={72} radius="xl" variant="light" color="gray"><IconUser size={44} /></ThemeIcon>;
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
            <Group justify="space-between" align="flex-start" wrap="nowrap">
              <Text fw={800} lineClamp={1}>{person.name}</Text>
              <Badge color={archived ? "gray" : "teal"} variant="light">
                {archived ? person.metadata?.merged_into ? "Merged" : "Archived" : photoCount}
              </Badge>
            </Group>
            <Group gap={5} mt={5}>
              <IconImageInPicture size={13} />
              <Text size="xs" c="dimmed">{photoCount} {photoCount === 1 ? "photo" : "photos"}</Text>
            </Group>
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
        <Group justify="space-between" className="people-card-actions">
          <Button size="compact-xs" variant="subtle" onClick={(event) => { event.stopPropagation(); openPerson(); }}>
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
  onFavorite,
  onSetRepresentative,
  onArchive,
  onRestore,
  onMerge,
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
  const [editValues, setEditValues] = useState(summaryProfile);

  useEffect(() => {
    setActiveTab("overview");
    setEditOpen(false);
    setManagementDialog(null);
    setTargetPersonId("");
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
            <Button
              size="xs"
              leftSection={<IconSwitchHorizontal size={14} />}
              onClick={() => onOpen(mergedInto, { archived: true })}
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
          </Group>
          <Text size="xs" c="dimmed" mt="sm">ID: {payload.person.person_id}</Text>
        </Box>
      </Group>

      <Tabs value={activeTab} onChange={changeTab} className="people-profile-tabs" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="overview">Overview</Tabs.Tab>
          <Tabs.Tab value="photos">Photos ({imageRecords.length})</Tabs.Tab>
          <Tabs.Tab value="sightings">Sightings ({latestSightings.length})</Tabs.Tab>
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
            {payload.person.name} will stop appearing in recognition results. Their {imageRecords.length} photos and {latestSightings.length} sightings will be retained and can be restored later.
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
            : <Text c="dimmed">No photo selected</Text>}
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
    "move-embedding": "Photo moved",
    "delete-embedding": "Photo removed",
    "update-profile": "Profile updated",
  }[event.operation_type] || "People record updated";
}

function managementEventDetail(event) {
  const result = event.result || {};
  if (event.operation_type === "merge-persons") {
    return `${result.moved_embeddings || 0} photos and ${result.moved_sightings || 0} sightings moved`;
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
  return "Completed successfully";
}

function normalizeChange(change) {
  const fields = [
    ["name", "Name", change.previous_name, change.new_name],
    ["rank", "Rank", change.previous_rank, change.new_rank],
    ["country", "Country", change.previous_country, change.new_country],
    ["importance", "Importance", change.previous_importance, change.new_importance],
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
  if (filter === "identity") return change.kind === "profile" && change.fields.some((field) => field.key === "name");
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
