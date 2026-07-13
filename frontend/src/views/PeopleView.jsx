import { useEffect, useMemo, useState } from "react";
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Grid,
  Group,
  Image,
  Menu,
  Paper,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  ThemeIcon,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconChevronDown,
  IconCopy,
  IconDots,
  IconEdit,
  IconFilter,
  IconGridDots,
  IconImageInPicture,
  IconLayoutList,
  IconPhoto,
  IconRefresh,
  IconSearch,
  IconSortDescending,
  IconStar,
  IconUser,
} from "@tabler/icons-react";

import { EmptyCard, ImageFrame } from "../components/Shared.jsx";
import { NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import {
  detailsForEmbedding,
  formatSeenDateTime,
  galleryImageRecords,
  mediaUrl,
  personProfile,
} from "../utils.js";

export function PeopleView({
  people,
  peopleGallery,
  peopleGalleryImage,
  onRefresh,
  onOpen,
  onImage,
  onBack,
  onSave,
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("recent");
  const [viewMode, setViewMode] = useState("grid");
  const [favorites, setFavorites] = useState(() => new Set());
  const [pageSize, setPageSize] = useState("12");
  const normalizedQuery = query.trim().toLowerCase();
  const peopleStats = useMemo(() => {
    const totalPhotos = people.reduce((sum, person) => sum + Number(person.embedding_count || 0), 0);
    const updatedToday = people.filter((person) => isTodayLike(person.created_at)).length;
    return { totalPhotos, updatedToday };
  }, [people]);
  const visiblePeople = useMemo(() => {
    return people
      .filter((person) => {
        if (filter === "favorites" && !favorites.has(person.person_id)) return false;
        if (filter === "withPhotos" && !Number(person.embedding_count || 0)) return false;
        if (filter === "withoutPhotos" && Number(person.embedding_count || 0)) return false;
        if (!normalizedQuery) return true;
        return [person.name, person.person_id, person.created_at]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(normalizedQuery));
      })
      .sort((left, right) => {
        if (sort === "name") return String(left.name || "").localeCompare(String(right.name || ""));
        if (sort === "photos") return Number(right.embedding_count || 0) - Number(left.embedding_count || 0);
        return new Date(right.created_at || 0).getTime() - new Date(left.created_at || 0).getTime();
      });
  }, [favorites, filter, normalizedQuery, people, sort]);
  const pageCount = Number(pageSize);
  const pagePeople = visiblePeople.slice(0, pageCount);
  const toggleFavorite = (personId) => {
    setFavorites((current) => {
      const next = new Set(current);
      if (next.has(personId)) next.delete(personId);
      else next.add(personId);
      return next;
    });
  };

  return (
    <Paper withBorder radius="md" p="md" className="people-workspace">
      {peopleGallery ? (
        <PeopleGalleryView
          payload={peopleGallery}
          selectedImage={peopleGalleryImage}
          onImage={onImage}
          onBack={onBack}
          onSave={onSave}
        />
      ) : (
        <Grid gutter="lg" className="people-library-shell">
          <Grid.Col span={{ base: 12, md: "content" }} className="people-library-sidebar-col">
            <PeopleLibrarySidebar
              people={people}
              favorites={favorites}
              activeFilter={filter}
              onFilter={setFilter}
              onRefresh={onRefresh}
            />
          </Grid.Col>
          <Grid.Col span="auto" className="people-library-main-col">
            <Stack gap="md" className="people-library-main">
              <Group justify="space-between" align="flex-start" gap="md" className="people-library-header">
                <Box>
                  <Group gap="xs" align="baseline">
                    <Title order={3} size="h4">People</Title>
                    <Text size="xs" c="dimmed">({people.length})</Text>
                  </Group>
                  <Text size="sm" c="dimmed">Manage and browse all known identities</Text>
                </Box>
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
              </Group>
              <PeopleStatsStrip people={people} totalPhotos={peopleStats.totalPhotos} favoriteCount={favorites.size} updatedToday={peopleStats.updatedToday} />
              <Box className="people-results-scroll">
                {pagePeople.length ? (
                  <Box className={viewMode === "list" ? "people-card-list" : "people-card-grid"}>
                    {pagePeople.map((person) => (
                      <PersonCard
                        key={person.person_id}
                        person={person}
                        favorite={favorites.has(person.person_id)}
                        viewMode={viewMode}
                        onOpen={onOpen}
                        onFavorite={toggleFavorite}
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
                pageSize={pageSize}
                onPageSize={setPageSize}
              />
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
  }[filter];
  const sortLabel = {
    recent: "Recently Updated",
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
          <Menu.Item onClick={() => onSort("recent")}>Recently Updated</Menu.Item>
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

function PeopleLibrarySidebar({ people, favorites, activeFilter, onFilter, onRefresh }) {
  const totalPhotos = people.reduce((sum, person) => sum + Number(person.embedding_count || 0), 0);
  const collectionItems = [
    { key: "all", label: "All People", icon: IconImageInPicture, count: people.length },
    { key: "favorites", label: "Favorites", icon: IconStar, count: favorites.size },
    { key: "withPhotos", label: "With Photos", icon: IconPhoto, count: people.filter((person) => Number(person.embedding_count || 0)).length },
    { key: "withoutPhotos", label: "No Photos", icon: IconUser, count: people.filter((person) => !Number(person.embedding_count || 0)).length },
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
      <Box>
        <Text size="xs" c="dimmed" fw={800} tt="uppercase" mb="sm">Groups</Text>
        <Paper withBorder radius="md" p="sm" className="people-groups-empty">
          <Text size="sm" c="dimmed">No groups yet.</Text>
        </Paper>
      </Box>
      <Paper withBorder radius="md" p="md" className="people-overview-card">
        <Text size="xs" c="dimmed" fw={800} tt="uppercase" mb="md">Database Overview</Text>
        <InfoMetric label="Total People" value={people.length} />
        <InfoMetric label="Total Photos" value={totalPhotos.toLocaleString()} />
        <InfoMetric label="Favorites" value={favorites.size} />
      </Paper>
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

function PeopleStatsStrip({ people, totalPhotos, favoriteCount, updatedToday }) {
  const stats = [
    { label: "Total People", value: people.length, icon: IconUser, color: "teal" },
    { label: "Total Photos", value: totalPhotos.toLocaleString(), icon: IconImageInPicture, color: "violet" },
    { label: "Favorites", value: favoriteCount, icon: IconStar, color: "yellow" },
    { label: "Updated Today", value: updatedToday, icon: IconRefresh, color: "blue" },
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

function PersonCard({ person, favorite, viewMode, onOpen, onFavorite }) {
  const hasImage = Boolean(person.representative_image);
  const cardClass = viewMode === "list" ? "people-person-card people-person-card--list" : "people-person-card";
  const openPerson = () => onOpen(person.person_id);
  const toggleFavorite = (event) => {
    event.stopPropagation();
    onFavorite(person.person_id);
  };
  const photoCount = Number(person.embedding_count || 0);
  const openWithKeyboard = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openPerson();
    }
  };
  return (
    <Card withBorder radius="md" p="sm" role="button" tabIndex={0} className={`mantine-click-card ${cardClass}`} onClick={openPerson} onKeyDown={openWithKeyboard}>
      <Stack gap="sm" align="stretch" className="people-person-card-inner">
        <Box className="people-card-image-wrap">
          <ImageFrame variant="peopleCard">
            {hasImage
              ? <Image src={mediaUrl(person.representative_image)} alt={person.name} fit="cover" h="100%" />
              : <ThemeIcon size={72} radius="xl" variant="light" color="gray"><IconUser size={44} /></ThemeIcon>}
          </ImageFrame>
          <ActionIcon
            size="sm"
            radius="xl"
            color={favorite ? "yellow" : "teal"}
            variant="filled"
            className="people-card-star"
            onClick={toggleFavorite}
            aria-label={favorite ? "Remove favorite" : "Add favorite"}
          >
            {favorite ? <IconStar size={15} fill="currentColor" /> : <IconStar size={15} />}
          </ActionIcon>
        </Box>
        <Box miw={0} className="people-card-copy">
          <Group justify="space-between" align="flex-start" wrap="nowrap">
            <Text fw={800} lineClamp={1}>{person.name}</Text>
            <Badge variant="light">{photoCount}</Badge>
          </Group>
          <Group gap={5} mt={5}>
            <IconImageInPicture size={13} />
            <Text size="xs" c="dimmed">{photoCount} {photoCount === 1 ? "photo" : "photos"}</Text>
          </Group>
          <Group gap={6} mt={8} wrap="nowrap">
            <Box className={photoCount ? "people-seen-dot people-seen-dot--active" : "people-seen-dot"} />
            <Text size="xs" c={photoCount ? "teal.3" : "dimmed"} truncate>{photoCount ? "Seen today" : "Never seen"}</Text>
          </Group>
        </Box>
        <Group justify="space-between" className="people-card-actions">
          <Tooltip label="Edit details">
            <ActionIcon variant="subtle" onClick={(event) => { event.stopPropagation(); openPerson(); }} aria-label="Edit details"><IconEdit size={16} /></ActionIcon>
          </Tooltip>
          <Tooltip label="Open photos">
            <ActionIcon variant="subtle" onClick={(event) => { event.stopPropagation(); openPerson(); }} aria-label="Open photos"><IconImageInPicture size={16} /></ActionIcon>
          </Tooltip>
          <Menu withinPortal position="bottom-end">
            <Menu.Target>
              <ActionIcon variant="subtle" onClick={(event) => event.stopPropagation()} aria-label="More actions"><IconDots size={16} /></ActionIcon>
            </Menu.Target>
            <Menu.Dropdown onClick={(event) => event.stopPropagation()}>
              <Menu.Item leftSection={<IconStar size={14} />} onClick={() => onFavorite(person.person_id)}>
                {favorite ? "Remove favorite" : "Add favorite"}
              </Menu.Item>
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

function PeoplePagination({ total, shown, pageSize, onPageSize }) {
  const size = Number(pageSize) || 12;
  const totalPages = Math.max(1, Math.ceil(total / size));
  const visiblePages = Array.from({ length: Math.min(totalPages, 3) }, (_, index) => index + 1);
  return (
    <Paper withBorder radius="md" p="sm" className="people-pagination">
      <Group justify="space-between">
        <Group gap="sm">
          <Text size="sm" c="dimmed">Show</Text>
          <Select value={pageSize} onChange={(value) => onPageSize(value || "12")} data={["8", "12", "24"]} w={80} />
          <Text size="sm" c="dimmed">Showing {shown ? `1 to ${shown}` : "0"} of {total} people</Text>
        </Group>
        <Group gap="xs">
          <ActionIcon variant="default" disabled aria-label="Previous page"><IconArrowLeft size={16} /></ActionIcon>
          {visiblePages.map((page) => (
            <Badge key={page} size="lg" variant={page === 1 ? "filled" : "light"}>{page}</Badge>
          ))}
          {totalPages > 3 && <Text c="dimmed">...</Text>}
          <ActionIcon variant="default" disabled={totalPages <= 1} aria-label="Next page"><IconChevronDown size={16} style={{ transform: "rotate(-90deg)" }} /></ActionIcon>
        </Group>
      </Group>
    </Paper>
  );
}

function InfoMetric({ label, value }) {
  return (
    <Group justify="space-between" mb="xs">
      <Text size="xs" c="dimmed">{label}</Text>
      <Text size="xs" fw={800}>{value}</Text>
    </Group>
  );
}

function isTodayLike(value) {
  if (!value) return false;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return false;
  return parsed.toDateString() === new Date().toDateString();
}

function PeopleGalleryView({ payload, selectedImage, onImage, onBack, onSave }) {
  const imageRecords = galleryImageRecords(payload);
  const [mode, setMode] = useState("info");
  const selectedRecord = selectedImage ? imageRecords.find((record) => record.path === selectedImage) : null;
  const selectedDetails = selectedRecord ? detailsForEmbedding(payload.details || [], selectedRecord.embeddingId) : payload.details || [];
  const profile = personProfile(payload, selectedDetails, Boolean(selectedRecord));
  const [editValues, setEditValues] = useState(profile);

  useEffect(() => {
    setEditValues(profile);
    setMode("info");
  }, [payload.person.person_id, payload.person.name, payload.person.metadata]);

  const updateEditValue = (field, value) => setEditValues((current) => ({ ...current, [field]: value }));
  const saveEdit = async (event) => {
    event.preventDefault();
    try {
      if (await onSave(editValues)) setMode("info");
    } catch (error) {
      console.error(error);
    }
  };

  return (
    <Stack className="people-gallery-shell">
      <Group justify="space-between" align="flex-start">
        <Box>
          <Title order={3} size="h4">{payload.person.name}</Title>
          <Text size="xs" c="dimmed">{imageRecords.length} image(s) | {payload.person.person_id}</Text>
        </Box>
        <Button variant="light" leftSection={<IconArrowLeft size={16} />} onClick={onBack}>Back</Button>
      </Group>
      <Grid className="people-gallery-grid">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Stack className="library-image-stack">
            <Box className="library-selected-slot">
              {selectedImage ? (
                <ImageFrame variant="librarySelected">
                  <Image src={mediaUrl(selectedImage)} alt={payload.person.name} fit="contain" h="100%" />
                </ImageFrame>
              ) : (
                <Paper withBorder radius="md" className="library-empty-selected">
                  <Text size="sm" c="dimmed">Select a photo</Text>
                </Paper>
              )}
            </Box>
            {imageRecords.length ? (
              <ScrollArea type="auto" offsetScrollbars className="library-thumb-strip">
                <Group wrap="nowrap" gap="sm" pb="xs">
                  {imageRecords.map((record) => (
                    <Card key={record.embeddingId} withBorder p={4} miw={128} w={128} component="button" className="mantine-click-card" data-selected={selectedImage === record.path} onClick={() => onImage(record.path)}>
                      <Image src={mediaUrl(record.path)} alt={payload.person.name} fit="cover" h={96} radius="sm" />
                    </Card>
                  ))}
                </Group>
              </ScrollArea>
            ) : <EmptyCard text="No images saved for this person." />}
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card withBorder radius="md">
            {mode === "changes" ? (
              <PeopleChangesPanel payload={payload} profile={profile} onBack={() => setMode("info")} />
            ) : mode === "edit" ? (
              <form onSubmit={saveEdit}>
                <Stack>
                  <Group justify="space-between" align="flex-start">
                    <Box>
                      <Text fw={700}>Edit Details</Text>
                      <Text size="xs" c="dimmed">Editor name is asked before saving.</Text>
                    </Box>
                    <Group gap="xs">
                      <Button size="xs" type="submit">Save</Button>
                      <Button size="xs" variant="light" type="button" onClick={() => setMode("info")}>Cancel</Button>
                    </Group>
                  </Group>
                  <PeopleEditableFields values={editValues} onChange={updateEditValue} />
                </Stack>
              </form>
            ) : (
              <Stack>
                <Group justify="space-between" align="flex-start">
                  <Box>
                    <Text fw={700}>Info</Text>
                    <Text size="xs" c="dimmed">{selectedRecord ? selectedRecord.embeddingId : payload.person.person_id}</Text>
                  </Box>
                  <Group gap="xs">
                    <Button size="xs" variant="light" onClick={() => setMode("changes")}>Changes</Button>
                    <Button size="xs" onClick={() => setMode("edit")}>Edit</Button>
                  </Group>
                </Group>
                <PeopleInfoFields profile={profile} details={selectedDetails} />
              </Stack>
            )}
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}

function PeopleEditableFields({ values, onChange }) {
  return (
    <SimpleGrid cols={{ base: 1, sm: 2 }}>
      <TextInput required label="Rank" value={values.rank} onChange={(event) => onChange("rank", event.target.value)} />
      <TextInput required label="Name" value={values.name} onChange={(event) => onChange("name", event.target.value)} />
      <TextInput required label="Country" value={values.country} onChange={(event) => onChange("country", event.target.value)} />
      <Select required label="Importance (Strat pt of view)" data={NEW_PERSON_IMPORTANCE_OPTIONS} value={values.importance} onChange={(value) => onChange("importance", value)} />
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
            <ChangeLine label="Importance (Strat pt of view)" from={change.previous_importance} to={change.new_importance} editor={change.editor_name} />
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
