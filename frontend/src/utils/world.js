const WORLD_COLLECTIONS = new Set(["PEOPLE", "CLUSTERS", "RELATIONSHIPS", "PATTERNS"]);
const WORLD_CLUSTER_COLLECTIONS = new Set(["MEMBERS", "RELATIONSHIPS"]);
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
  requireWorldContractIdentity(payload);
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
  requireWorldPagination(payload.pagination);
  payload.people.forEach(requireWorldPerson);
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
  payload.relationships.forEach(requireWorldRelationship);
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

export function requireWorldClusterContract(payload, expected = {}) {
  requireWorldContractIdentity(payload);
  if (
    payload.requested_detail_level !== "CLUSTER"
    || payload.returned_detail_level !== "CLUSTER"
    || payload.focus?.type !== "CLUSTER"
    || !payload.focus.id
    || !payload.graph_revision
    || !payload.as_of
  ) throw new Error("Incomplete World Cluster focus or revision contract");
  if (expected.clusterId && payload.focus.id !== expected.clusterId) {
    throw new Error("World Cluster focus does not match the requested cluster");
  }
  if (expected.revision && payload.graph_revision !== expected.revision) {
    throw new Error("World Cluster revision does not match the requested snapshot");
  }
  for (const field of ["scope_totals", "effective_filters", "pagination", "limits"]) {
    if (!payload[field] || typeof payload[field] !== "object" || Array.isArray(payload[field])) {
      throw new Error(`Incomplete World Cluster ${field} contract`);
    }
  }
  for (const field of ["people", "clusters", "relationships"]) {
    if (!Array.isArray(payload[field])) throw new Error(`Incomplete World Cluster ${field} collection`);
  }
  if (payload.clusters.length !== 1) throw new Error("World Cluster response must contain exactly one cluster summary");
  for (const collection of WORLD_CLUSTER_COLLECTIONS) {
    if (!payload.pagination[collection]) throw new Error(`Missing World Cluster ${collection} page state`);
  }
  requireWorldPagination(payload.pagination);
  const cluster = payload.clusters[0];
  if (
    cluster.cluster_id !== payload.focus.id
    || cluster.graph_revision !== payload.graph_revision
    || !Number.isFinite(Number(cluster.member_count))
    || !Array.isArray(cluster.member_ids)
    || !Array.isArray(cluster.member_preview)
    || !cluster.member_preview_state
    || !cluster.evidence_basis
    || !Number.isFinite(Number(cluster.evidence_basis.evidence_count))
    || !Number.isFinite(Number(cluster.evidence_basis.relationship_count))
    || !Array.isArray(cluster.evidence_basis.strongest_relationships)
    || !cluster.activity_summary
    || !Number.isFinite(Number(cluster.activity_summary.member_event_contributions))
    || !Number.isFinite(Number(cluster.activity_summary.active_member_count))
    || !cluster.ranking
    || !Number.isFinite(Number(cluster.ranking.rank_position))
    || !cluster.ranking.reason
    || !cluster.ranking.measurements
    || !cluster.grouping_algorithm
    || !cluster.algorithm_version
    || !cluster.explanation
    || !Array.isArray(cluster.explanation.factual_factors)
    || !Array.isArray(cluster.explanation.limitations)
  ) throw new Error("Invalid World Cluster summary contract");
  payload.people.forEach(requireWorldPerson);
  payload.relationships.forEach(requireWorldRelationship);
  const requestedCollection = expected.collection || null;
  if (requestedCollection === "MEMBERS") {
    if (payload.people.length !== payload.pagination.MEMBERS.returned_count) {
      throw new Error("World Cluster member count does not match its page state");
    }
    if (cluster.member_ids.length !== payload.people.length) {
      throw new Error("World Cluster member IDs do not match the returned member page");
    }
    const returnedIds = new Set(payload.people.map((person) => person.canonical_person_id));
    if (cluster.member_ids.some((personId) => !returnedIds.has(personId))) {
      throw new Error("World Cluster member page contains inconsistent identities");
    }
  }
  if (requestedCollection === "RELATIONSHIPS" && payload.relationships.length !== payload.pagination.RELATIONSHIPS.returned_count) {
    throw new Error("World Cluster relationship count does not match its page state");
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

export function buildWorldClusterQuery({
  clusterId,
  collection = "MEMBERS",
  filters = EMPTY_WORLD_FILTERS,
  ranking = "SALIENCE",
  cursor = null,
  revision,
  asOf,
} = {}) {
  if (!clusterId || !revision || !asOf) throw new Error("World Cluster requests require cluster, revision, and as_of binding");
  const normalizedCollection = String(collection || "MEMBERS").toUpperCase();
  if (!WORLD_CLUSTER_COLLECTIONS.has(normalizedCollection)) throw new Error("Unsupported World Cluster collection");
  const query = new URLSearchParams({
    version: "2",
    level: "CLUSTER",
    focus_type: "CLUSTER",
    focus_id: clusterId,
    collection: normalizedCollection,
    ranking,
    people_limit: "25",
    cluster_limit: "10",
    relationship_limit: "50",
    pattern_limit: "10",
    facet_limit: "100",
    revision,
    as_of: asOf,
  });
  appendWorldFilters(query, filters);
  if (cursor) query.set("cursor", cursor);
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

export function isInvalidWorldClusterError(error) {
  return isStaleWorldError(error)
    || (
      [400, 404].includes(error?.status)
      && /world cluster (is unavailable|focus|revision)|cluster.*revision|cursor does not match/i.test(error.message || "")
    );
}

export function worldPageFor(data, collection) {
  return data?.pagination?.[collection] || null;
}

function requireWorldContractIdentity(payload) {
  if (payload?.contract !== "sentriface.world-graph" || payload.contract_version !== 2) {
    throw new Error("Unsupported World contract");
  }
}

function requireWorldPagination(pagination) {
  for (const [name, page] of Object.entries(pagination || {})) {
    if (
      page?.collection !== name
      || !Number.isFinite(Number(page.total_count))
      || !Number.isFinite(Number(page.returned_count))
      || typeof page.has_more !== "boolean"
      || typeof page.truncated !== "boolean"
      || (page.has_more && !page.next_cursor && page.truncation_reason !== "collection_not_requested")
    ) throw new Error(`Invalid World ${name} page state`);
  }
}

function requireWorldPerson(person) {
  if (
    !person?.canonical_person_id
    || !person.display_name
    || !WORLD_LIFECYCLE_STATES.has(person.lifecycle_state)
    || !WORLD_ANALYTICS_STATES.has(person.analytics_state)
    || !person.display
    || !person.intelligence_summary
    || !person.activity_summary
    || !person.ranking
    || !Array.isArray(person.historical_person_ids)
    || !Array.isArray(person.allowed_actions)
    || !person.explanation
  ) throw new Error("Invalid World person contract");
}

function requireWorldRelationship(relationship) {
  if (
    !relationship?.relationship_id
    || !relationship.source_person_id
    || !relationship.target_person_id
    || !relationship.directionality
    || !relationship.strength_basis
    || !relationship.first_occurrence_at
    || !relationship.last_occurrence_at
    || !Number.isFinite(Number(relationship.evidence_count))
    || !Array.isArray(relationship.relationship_types)
    || !relationship.evidence_type_counts
    || !relationship.explanation
    || !Array.isArray(relationship.explanation.factual_factors)
    || !Array.isArray(relationship.explanation.limitations)
  ) throw new Error("Invalid World relationship contract");
}

function appendWorldFilters(query, filters) {
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
}
