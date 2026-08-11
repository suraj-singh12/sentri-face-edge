const WORLD_COLLECTIONS = new Set(["PEOPLE", "CLUSTERS", "RELATIONSHIPS", "PATTERNS"]);
const WORLD_LIFECYCLE_STATES = new Set(["ACTIVE", "ARCHIVED", "DELETED", "MERGED"]);
const WORLD_ANALYTICS_STATES = new Set(["LOADED", "NOT_LOADED"]);

export const EMPTY_WORLD_FILTERS = Object.freeze({
  date_from: "",
  date_to: "",
  recent_activity: "",
  locations: [],
  missing_location: "INCLUDE",
  lifecycle: [],
  identity_state: [],
  biometric_state: [],
  country: [],
  rank: [],
  priority: [],
  evidence_type: [],
  relationship_type: [],
  min_relationship_strength: null,
  activity: [],
  pattern_type: [],
});

export function requireWorldScopeContract(payload) {
  if (payload?.contract !== "sentriface.world-graph" || payload.contract_version !== 2) {
    throw new Error("Unsupported World contract");
  }
  if (
    payload.requested_detail_level !== "WORLD_SCOPE"
    || payload.returned_detail_level !== "WORLD_SCOPE"
    || !payload.graph_revision
    || !payload.as_of
  ) {
    throw new Error("Incomplete World scope or revision contract");
  }
  for (const field of ["scope_totals", "available_facets", "effective_filters", "pagination"]) {
    if (!payload[field] || typeof payload[field] !== "object" || Array.isArray(payload[field])) {
      throw new Error(`Incomplete World ${field} contract`);
    }
  }
  for (const field of ["people", "clusters", "relationships", "patterns"]) {
    if (!Array.isArray(payload[field])) throw new Error(`Incomplete World ${field} collection`);
  }
  for (const [name, page] of Object.entries(payload.pagination)) {
    if (
      page?.collection !== name
      || !Number.isFinite(Number(page.total_count))
      || !Number.isFinite(Number(page.returned_count))
      || typeof page.has_more !== "boolean"
      || typeof page.truncated !== "boolean"
    ) throw new Error(`Invalid World ${name} page state`);
  }
  for (const person of payload.people) {
    if (
      !person?.canonical_person_id
      || !person.display_name
      || !WORLD_LIFECYCLE_STATES.has(person.lifecycle_state)
      || !WORLD_ANALYTICS_STATES.has(person.analytics_state)
      || !Array.isArray(person.historical_person_ids)
      || !Array.isArray(person.allowed_actions)
      || !person.explanation
    ) throw new Error("Invalid World person contract");
  }
  for (const cluster of payload.clusters) {
    if (
      !cluster?.cluster_id
      || cluster.graph_revision !== payload.graph_revision
      || !Number.isFinite(Number(cluster.member_count))
      || !Array.isArray(cluster.member_preview)
      || !cluster.member_preview_state
      || !cluster.explanation
    ) throw new Error("Invalid World cluster contract");
  }
  for (const relationship of payload.relationships) {
    if (
      !relationship?.relationship_id
      || !relationship.source_person_id
      || !relationship.target_person_id
      || !Number.isFinite(Number(relationship.evidence_count))
      || !Array.isArray(relationship.relationship_types)
      || !relationship.explanation
    ) throw new Error("Invalid World relationship contract");
  }
  for (const pattern of payload.patterns) {
    if (
      !pattern?.pattern_id
      || !pattern.pattern_type
      || !pattern.status
      || !pattern.metrics
      || !pattern.explanation
    ) throw new Error("Invalid World pattern contract");
  }
  return payload;
}

export function buildWorldScopeQuery({
  collection = "PEOPLE",
  filters = EMPTY_WORLD_FILTERS,
  ranking = "SALIENCE",
  cursor = null,
  revision = null,
  asOf = null,
} = {}) {
  const normalizedCollection = String(collection || "PEOPLE").toUpperCase();
  if (!WORLD_COLLECTIONS.has(normalizedCollection)) throw new Error("Unsupported World collection");
  const query = new URLSearchParams({
    version: "2",
    level: "WORLD_SCOPE",
    collection: normalizedCollection,
    ranking,
    people_limit: "25",
    cluster_limit: "10",
    relationship_limit: "50",
    pattern_limit: "10",
    facet_limit: "100",
  });
  const scalar = {
    date_from: filters.date_from,
    date_to: filters.date_to,
    recent_activity: filters.recent_activity,
    missing_location: filters.missing_location || "INCLUDE",
    min_relationship_strength: filters.min_relationship_strength,
  };
  for (const [key, value] of Object.entries(scalar)) {
    if (value !== null && value !== undefined && value !== "") query.set(key, String(value));
  }
  const collections = {
    location: filters.locations,
    lifecycle: filters.lifecycle,
    identity_state: filters.identity_state,
    biometric_state: filters.biometric_state,
    country: filters.country,
    rank: filters.rank,
    priority: filters.priority,
    evidence_type: filters.evidence_type,
    relationship_type: filters.relationship_type,
    activity: filters.activity,
    pattern_type: filters.pattern_type,
  };
  for (const [key, values] of Object.entries(collections)) {
    for (const value of values || []) query.append(key, String(value));
  }
  if (cursor) query.set("cursor", cursor);
  if (revision) query.set("revision", revision);
  if (asOf) query.set("as_of", asOf);
  return `/api/world-graph?${query}`;
}

export function filtersFromEffective(filters = {}) {
  const list = (value) => Array.isArray(value) ? [...value] : [];
  const recent = filters.recent_activity || "";
  return {
    date_from: recent ? "" : String(filters.date_from || "").slice(0, 10),
    date_to: recent ? "" : String(filters.date_to || "").slice(0, 10),
    recent_activity: recent,
    locations: list(filters.locations),
    missing_location: filters.missing_location || "INCLUDE",
    lifecycle: list(filters.lifecycle),
    identity_state: list(filters.identity_state),
    biometric_state: list(filters.biometric_state),
    country: list(filters.country),
    rank: list(filters.rank),
    priority: list(filters.priority),
    evidence_type: list(filters.evidence_type),
    relationship_type: list(filters.relationship_type),
    min_relationship_strength: filters.min_relationship_strength ?? null,
    activity: list(filters.activity),
    pattern_type: list(filters.pattern_type),
  };
}

export function worldEntryMode(snapshot) {
  if (!snapshot?.data?.graph_revision || snapshot.invalidated) return "LOAD";
  return "VALIDATE";
}

export function invalidateWorldSnapshot(snapshot, mutation = null) {
  return {
    ...snapshot,
    invalidated: true,
    pendingRevision: mutation?.graph_revision || null,
    loading: false,
    error: null,
  };
}

export function isStaleWorldError(error) {
  return error?.status === 400 && /world (revision is stale|cursor does not match)/i.test(error.message || "");
}

export function worldPageFor(data, collection) {
  return data?.pagination?.[collection] || null;
}
