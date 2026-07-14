import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActionIcon,
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
  Paper,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  Textarea,
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
  IconFlag,
  IconGlobe,
  IconGridDots,
  IconImageInPicture,
  IconLayoutList,
  IconMapPin,
  IconNotes,
  IconPhoto,
  IconPhotoPlus,
  IconRefresh,
  IconSearch,
  IconSortDescending,
  IconStar,
  IconShield,
  IconTag,
  IconTrash,
  IconUser,
} from "@tabler/icons-react";

import { EmptyCard, ImageFrame } from "../components/Shared.jsx";
import { NEW_PERSON_IMPORTANCE_OPTIONS } from "../constants.js";
import {
  detailsForEmbedding,
  formatSeenDateTime,
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
  const imageRecords = profileImageRecords(payload);
  const tabContentRef = useRef(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [editOpen, setEditOpen] = useState(false);
  const selectedRecord = selectedImage
    ? imageRecords.find((record) => record.path === selectedImage || record.thumbPath === selectedImage) || imageRecords[0]
    : imageRecords[0] || null;
  const selectedPath = selectedRecord?.path || "";
  const selectedDetails = selectedRecord ? detailsForEmbedding(payload.details || [], selectedRecord.embeddingId) : [];
  const profile = personProfile(payload, selectedDetails, Boolean(selectedRecord));
  const summaryProfile = personProfile(payload);
  const latestSightings = (payload.details || []).filter(isSeenDetail);
  const recentSightings = latestSightings.slice(0, 3);
  const changes = payload.changes || [];
  const [editValues, setEditValues] = useState(summaryProfile);

  useEffect(() => {
    setEditValues(summaryProfile);
    setActiveTab("overview");
    setEditOpen(false);
  }, [payload.person.person_id, payload.person.name, payload.person.metadata]);

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
          <Button size="xs" onClick={() => setEditOpen(true)}>Edit</Button>
          <Menu withinPortal position="bottom-end">
            <Menu.Target>
              <Button size="xs" variant="default" rightSection={<IconChevronDown size={14} />}>More</Button>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconCopy size={14} />} onClick={() => navigator.clipboard?.writeText(payload.person.person_id)}>Copy ID</Menu.Item>
              <Menu.Item leftSection={<IconStar size={14} />}>Toggle favorite</Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </Group>

      <Group align="flex-start" wrap="nowrap" className="people-profile-hero">
        <ProfilePhoto path={payload.person.representative_image || selectedPath} name={payload.person.name} />
        <Box miw={0} className="people-profile-heading">
          <Group gap="xs" align="center">
            <Title order={2} size="h3">{payload.person.name}</Title>
            <ActionIcon variant="subtle" size="sm" aria-label="Favorite"><IconStar size={16} /></ActionIcon>
          </Group>
          <Group gap="xs" mt={4}>
            <Text size="sm">{summaryProfile.rank || "Unknown role"}</Text>
            <Text size="sm" c="dimmed">•</Text>
            <Text size="sm">{summaryProfile.country || "Unknown country"}</Text>
            <Badge color={importanceColor(summaryProfile.importance)} variant="light">{summaryProfile.importance || "Regular"}</Badge>
          </Group>
          <Group gap="sm" mt="sm">
            <Badge variant="outline" leftSection={<IconImageInPicture size={13} />}>{imageRecords.length} Photos</Badge>
            <Badge variant="outline">{latestSightings.length ? "Last seen today" : "Never seen"}</Badge>
          </Group>
          <Text size="xs" c="dimmed" mt="sm">ID: {payload.person.person_id}</Text>
        </Box>
      </Group>

      <Tabs value={activeTab} onChange={changeTab} className="people-profile-tabs" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="overview">Overview</Tabs.Tab>
          <Tabs.Tab value="photos">Photos ({imageRecords.length})</Tabs.Tab>
          <Tabs.Tab value="sightings">Sightings ({latestSightings.length})</Tabs.Tab>
          <Tabs.Tab value="changes">Changes ({changes.length})</Tabs.Tab>
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
            records={imageRecords}
            selectedRecord={selectedRecord}
            selectedPath={selectedPath}
            selectedDetails={selectedDetails}
            profile={profile}
            onImage={selectPhoto}
          />
        </Tabs.Panel>
        <Tabs.Panel value="sightings">
          <PeopleProfileSightings details={latestSightings} imageRecords={imageRecords} onSighting={selectSightingPhoto} />
        </Tabs.Panel>
        <Tabs.Panel value="changes">
          <PeopleProfileChanges changes={changes} currentProfile={summaryProfile} />
        </Tabs.Panel>
        </Box>
      </Tabs>

      <Drawer opened={editOpen} onClose={() => setEditOpen(false)} position="right" size={380} title="Edit Person" className="people-edit-drawer">
        <form onSubmit={saveEdit}>
          <Stack>
            <PeopleEditableFields values={editValues} onChange={updateEditValue} />
            <TextInput label="Tags" placeholder="Avenger, Red Room" />
            <Textarea label="Notes" minRows={5} placeholder="Add context, notes, or handling instructions" />
            <Group justify="flex-end" mt="md">
              <Button variant="default" type="button" onClick={() => setEditOpen(false)}>Cancel</Button>
              <Button type="submit">Save Changes</Button>
            </Group>
          </Stack>
        </form>
      </Drawer>
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
            ["Created", "-"],
            ["Added by", "System"],
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
      <Grid.Col span={12}>
        <Card withBorder radius="md" className="people-profile-panel">
          <Text fw={800} mb="xs">Notes</Text>
          <Text size="sm" c="dimmed">No notes saved for this person yet.</Text>
        </Card>
      </Grid.Col>
    </Grid>
  );
}

function PeopleProfilePhotos({ payload, records, selectedRecord, selectedPath, selectedDetails, profile, onImage }) {
  const photoDetail = selectedDetails[0] || {};
  return (
    <Grid mt="md" className="people-profile-photos-grid">
      <Grid.Col span={{ base: 12, lg: 8 }}>
        <Group justify="space-between" mb="sm">
          <Text size="sm">All Photos ({records.length})</Text>
          <Button size="xs" leftSection={<IconPhotoPlus size={14} />}>Add Photo</Button>
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
          {selectedPath ? <Image src={mediaUrl(selectedPath)} alt={payload.person.name} fit="contain" h="100%" /> : <Text c="dimmed">No photo selected</Text>}
        </Paper>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 4 }}>
        <Card withBorder radius="md" className="people-profile-panel">
          <Text fw={800} mb="md">Photo Details</Text>
          <ProfileInfoRows rows={[
            ["Added", formatSeenDateTime(photoDetail)],
            ["Source", photoDetail.event_occasion || "-"],
            ["Location", photoDetail.place_seen || "-"],
            ["Quality", "Good"],
            ["Embedding", selectedRecord?.embeddingId ? "Indexed" : "-"],
            ["Rank", profile.rank || "-"],
          ]} />
          <Button fullWidth mt="md" variant="outline">Set as Profile Photo</Button>
          <Button fullWidth mt="sm" variant="outline" color="red" leftSection={<IconTrash size={14} />}>Delete Photo</Button>
        </Card>
      </Grid.Col>
    </Grid>
  );
}

function PeopleProfileSightings({ details, imageRecords, onSighting }) {
  return (
    <Stack mt="md" className="people-profile-list-panel">
      {details.length ? details.map((detail) => (
        <Card key={detail.detail_id} withBorder radius="md" component="button" className="mantine-click-card people-profile-panel people-sighting-card" onClick={() => onSighting(detail)}>
          <Group justify="space-between" align="center" wrap="nowrap">
            <SightingSummary detail={detail} />
            <SightingImage detail={detail} imageRecords={imageRecords} size={92} />
          </Group>
        </Card>
      )) : <EmptyCard text="No sightings recorded yet." />}
    </Stack>
  );
}

function PeopleProfileChanges({ changes, currentProfile }) {
  const changeCards = changes.map(normalizeChange).filter((change) => change.fields.length);
  const [activeIndex, setActiveIndex] = useState(0);
  const activeChange = changeCards[activeIndex] || null;
  const changedFields = new Set(activeChange?.fields.map((field) => field.key) || []);
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
          <CurrentInfoRow icon={IconTag} label="Tags" value={["Avenger", "Red Room"]} active={changedFields.has("tags")} tags />
          <CurrentInfoRow icon={IconNotes} label="Notes" value="Former spy. Highly skilled in close combat and espionage." active={changedFields.has("notes")} multiline />
          <Divider />
          <CurrentInfoRow icon={IconRefresh} label="Last Updated" value={activeChange?.createdAt || "-"} subvalue={`By ${activeChange?.editor || "System"}`} />
        </Stack>
      </Card>
      <Card withBorder radius="md" className="people-profile-panel people-change-history-panel">
        <Group justify="space-between" mb="sm" wrap="nowrap">
          <Group gap="sm" align="baseline">
            <Text fw={900}>Change History</Text>
            <Text size="xs" c="dimmed">(Newest → Oldest)</Text>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <Group gap={0} className="people-change-view-toggle">
              <ActionIcon variant="light" aria-label="Card view"><IconGridDots size={16} /></ActionIcon>
              <ActionIcon variant="default" aria-label="List view"><IconLayoutList size={16} /></ActionIcon>
            </Group>
            <Menu withinPortal position="bottom-end">
              <Menu.Target>
                <Button size="xs" variant="default" rightSection={<IconChevronDown size={14} />}>All Changes</Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item>All Changes</Menu.Item>
                <Menu.Item>Identity Changes</Menu.Item>
                <Menu.Item>Metadata Changes</Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
        <Box className="people-change-timeline">
          {changeCards.length ? changeCards.map((change, index) => (
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
              <Stack gap={0} className="people-change-field-list">
                {change.fields.map((field) => <ChangeFieldRow key={field.key} field={field} />)}
              </Stack>
              {/* <Button mt="md" size="xs" variant="default" rightSection={<IconArrowLeft size={13} style={{ transform: "rotate(135deg)" }} />}>View Full Details</Button> */}
            </Card>
          )) : <EmptyCard text="No changes recorded yet." />}
        </Box>
        {changeCards.length > 1 && (
          <Group gap="xs" mt="sm" wrap="nowrap" className="people-change-scroll-hint">
            <Text c="dimmed">‹</Text>
            <Box className="people-change-scroll-track"><Box className="people-change-scroll-fill" style={{ width: `${Math.max(18, ((activeIndex + 1) / changeCards.length) * 100)}%` }} /></Box>
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
        <Image src={mediaUrl(path)} alt={name} fit="cover" h="100%" />
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
    }))
    .filter((record) => record.path);
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
    createdAt: change.created_at,
    editor: change.editor_name,
    fields,
  };
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
