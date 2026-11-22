import { useEffect, useRef, useState } from "react";
import { Autocomplete, Badge, Button, Stack, Text } from "@mantine/core";
import { useApiClient } from "../hooks/useApiClient.js";
import { buildWorldScopeQuery, requireWorldDiscoveryContract } from "../utils/world.js";

const MIN_QUERY = 3;

export function normalizeLocation(value) {
  return String(value || "").trim().replace(/\s+/gu, " ");
}

// Saved matches come first; only when nothing matches is the typed text offered as a new location.
export function locationOptions(query, saved, { loading = false, loaded = false } = {}) {
  if (Array.from(query).length < MIN_QUERY || loading || !loaded) return saved;
  return saved.length ? saved : [query];
}

// Suggestions are reads of successfully saved Encounters. This input never registers a value.
export function SavedLocationInput({ value, onChange, required, label = "Location", placeholder, leftSection, error }) {
  const { apiGet } = useApiClient();
  const [state, setState] = useState({ values: [], data: null });
  const request = useRef(null);
  const query = normalizeLocation(value);
  const load = async (cursor = null, previous = null) => {
    request.current?.abort(); const abort = new AbortController(); request.current = abort;
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const data = requireWorldDiscoveryContract(await apiGet(buildWorldScopeQuery({ collection: "LOCATION_SUGGESTIONS", locationQuery: query, cursor, revision: previous?.graph_revision, asOf: previous?.as_of }), { signal: abort.signal, dedupe: false, silent: true }), { collection: "LOCATION_SUGGESTIONS", revision: previous?.graph_revision });
      if (!abort.signal.aborted) setState({ values: data.available_facets.locations.map((item) => item.value), data, loading: false });
    } catch (error) { if (!abort.signal.aborted) setState({ values: [], loading: false, error }); }
  };
  useEffect(() => {
    request.current?.abort(); setState({ values: [], data: null });
    if (Array.from(query).length < MIN_QUERY) return;
    const timer = setTimeout(() => load(), 200);
    return () => { clearTimeout(timer); request.current?.abort(); };
  }, [query, apiGet]);
  const isNew = (option) => !state.values.includes(option);
  const options = locationOptions(query, state.values, { loading: state.loading, loaded: Boolean(state.data) });
  const saved = state.values.some((item) => item.toLocaleLowerCase() === query.toLocaleLowerCase());
  return (
    <Stack gap={4}>
      <Autocomplete
        required={required}
        label={label}
        placeholder={placeholder}
        leftSection={leftSection}
        error={error}
        value={value}
        onChange={onChange}
        data={options}
        limit={100}
        filter={({ options: all }) => all}
        renderOption={({ option }) => isNew(option.value) ? <Text size="sm">Create “{option.value}”</Text> : <Text size="sm">{option.value}</Text>}
        description={state.loading ? "Loading saved locations…" : "Type 3 letters to see saved locations. Pick one to reuse it, or create a new one."}
      />
      {saved && <Badge size="xs" variant="light">Saved location</Badge>}
      {state.error && <Text size="xs" c="red">Saved locations unavailable. You can still enter a location.</Text>}
      {state.data?.has_more && <Button size="compact-xs" variant="subtle" onClick={() => load(state.data.next_cursor, state.data)}>Next saved locations</Button>}
    </Stack>
  );
}
