import { useEffect, useRef, useState } from "react";
import { Autocomplete, Badge, Button, Stack, Text } from "@mantine/core";
import { useApiClient } from "../hooks/useApiClient.js";
import { buildWorldScopeQuery, requireWorldDiscoveryContract } from "../utils/world.js";

// Suggestions are reads of successfully saved Encounters. This input never registers a value.
export function SavedLocationInput({ value, onChange, required }) {
  const { apiGet } = useApiClient();
  const [state, setState] = useState({ values: [], data: null });
  const request = useRef(null);
  const query = value.trim().replace(/\s+/gu, " ");
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
    if (Array.from(query).length < 3) return;
    const timer = setTimeout(() => load(), 200);
    return () => { clearTimeout(timer); request.current?.abort(); };
  }, [query, apiGet]);
  return <Stack gap={4}><Autocomplete required={required} label="Location" value={value} onChange={onChange} data={state.values} limit={100} filter={({ options }) => options} description={state.loading ? "Loading saved locations…" : "Type 3 characters to find saved locations, or enter a new value."} />{state.values.includes(value) && <Badge size="xs" variant="light">Saved location</Badge>}{state.error && <Text size="xs" c="red">Saved locations unavailable. You can still enter a location.</Text>}{state.data?.has_more && <Button size="compact-xs" variant="subtle" onClick={() => load(state.data.next_cursor, state.data)}>Next saved locations</Button>}</Stack>;
}
