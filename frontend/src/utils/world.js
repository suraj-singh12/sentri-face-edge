const WORLD_COLLECTIONS = new Set(["PEOPLE", "CLUSTERS", "RELATIONSHIPS", "PATTERNS"]);
const WORLD_CLUSTER_COLLECTIONS = new Set(["MEMBERS", "RELATIONSHIPS"]);
const WORLD_PERSON_COLLECTIONS = new Set(["RELATIONSHIPS", "EVENTS"]);
const WORLD_EVENT_COLLECTIONS = new Set(["PARTICIPANTS", "PROVENANCE", "EVIDENCE", "MEDIA"]);
const WORLD_EVIDENCE_COLLECTIONS = new Set(["EVIDENCE", "MEDIA"]);
const WORLD_EVIDENCE_TYPES = new Set(["CO_OBSERVED", "NOTE_REFERENCE", "MANUAL_ASSOCIATION"]);
const WORLD_EVIDENCE_DIRECTIONS = new Set(["DIRECTED", "UNDIRECTED"]);
const WORLD_LIFECYCLE_STATES = new Set(["ACTIVE", "ARCHIVED", "DELETED", "MERGED"]);
const WORLD_IDENTITY_STATES = new Set(["IDENTIFIED", "UNIDENTIFIED"]);
const WORLD_BIOMETRIC_STATES = new Set(["NO_FACE", "ENROLLED"]);
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

export function requireWorldPersonContract(payload, expected = {}) {
  requireWorldContractIdentity(payload);
  if (
    payload.requested_detail_level !== "PERSON"
    || payload.returned_detail_level !== "PERSON"
    || payload.focus?.type !== "PERSON"
    || !payload.focus.id
    || !payload.graph_revision
    || !payload.as_of
  ) throw new Error("Incomplete World Person focus or revision contract");
  if (expected.personId && payload.focus.id !== expected.personId) {
    throw staleWorldPersonContractError("World Person focus does not match the requested identity");
  }
  if (expected.revision && payload.graph_revision !== expected.revision) {
    throw staleWorldPersonContractError("World Person revision does not match the requested snapshot");
  }
  for (const field of ["scope_totals", "effective_filters", "pagination", "limits"]) {
    if (!payload[field] || typeof payload[field] !== "object" || Array.isArray(payload[field])) {
      throw new Error(`Incomplete World Person ${field} contract`);
    }
  }
  for (const field of ["people", "relationships", "events"]) {
    if (!Array.isArray(payload[field])) throw new Error(`Incomplete World Person ${field} collection`);
  }
  for (const collection of WORLD_PERSON_COLLECTIONS) {
    if (!payload.pagination[collection]) throw new Error(`Missing World Person ${collection} page state`);
  }
  requireWorldPagination(payload.pagination);
  if (!payload.people.length) throw new Error("World Person response must contain the focused person");
  payload.people.forEach(requireWorldPerson);
  payload.relationships.forEach(requireWorldRelationship);
  payload.events.forEach(requireWorldEvent);
  const root = payload.people[0];
  if (expected.personId && root.canonical_person_id !== expected.personId) {
    throw staleWorldPersonContractError("World Person canonical identity changed in the retained snapshot");
  }
  if (!Array.isArray(root.cluster_memberships)) {
    throw new Error("Invalid World Person cluster membership contract");
  }
  for (const membership of root.cluster_memberships) {
    if (
      !membership?.cluster_id
      || membership.graph_revision !== payload.graph_revision
      || !Number.isFinite(Number(membership.member_count))
      || !membership.grouping_algorithm
      || !membership.algorithm_version
    ) throw new Error("Invalid World Person cluster membership contract");
  }
  const requestedCollection = expected.collection || null;
  if (requestedCollection === "RELATIONSHIPS" && payload.relationships.length !== payload.pagination.RELATIONSHIPS.returned_count) {
    throw new Error("World Person relationship count does not match its page state");
  }
  if (requestedCollection === "EVENTS" && payload.events.length !== payload.pagination.EVENTS.returned_count) {
    throw new Error("World Person event count does not match its page state");
  }
  return payload;
}

export function requireWorldEventContract(payload, expected = {}) {
  requireWorldContractIdentity(payload);
  if (
    payload.requested_detail_level !== "EVENT"
    || payload.returned_detail_level !== "EVENT"
    || payload.focus?.type !== "EVENT"
    || !payload.focus.id
    || !payload.graph_revision
    || !payload.as_of
  ) throw new Error("Incomplete World Event focus or revision contract");
  if (expected.eventId && payload.focus.id !== expected.eventId) {
    throw staleWorldEventContractError("World Event focus does not match the requested observation");
  }
  if (expected.revision && payload.graph_revision !== expected.revision) {
    throw staleWorldEventContractError("World Event revision does not match the requested snapshot");
  }
  for (const field of ["scope_totals", "effective_filters", "pagination", "limits"]) {
    if (!payload[field] || typeof payload[field] !== "object" || Array.isArray(payload[field])) {
      throw new Error(`Incomplete World Event ${field} contract`);
    }
  }
  for (const field of ["events", "evidence", "media"]) {
    if (!Array.isArray(payload[field])) throw new Error(`Incomplete World Event ${field} collection`);
  }
  for (const collection of WORLD_EVENT_COLLECTIONS) {
    if (!payload.pagination[collection]) throw new Error(`Missing World Event ${collection} page state`);
  }
  requireWorldPagination(payload.pagination);
  if (payload.events.length !== 1) throw new Error("World Event response must contain exactly one finalized observation");
  const event = payload.events[0];
  requireWorldEvent(event);
  if (event.event_id !== payload.focus.id) {
    throw staleWorldEventContractError("World Event identity changed in the retained snapshot");
  }
  event.participants.forEach(requireWorldParticipant);
  event.participant_provenance.forEach(requireWorldParticipantProvenance);
  payload.evidence.forEach(requireWorldEvidence);
  payload.media.forEach(requireWorldMediaReference);
  const requestedCollection = expected.collection || null;
  if (requestedCollection === "PARTICIPANTS" && (
    event.participants.length !== payload.pagination.PARTICIPANTS.returned_count
    || event.participant_summary.total_count !== payload.pagination.PARTICIPANTS.total_count
  )) throw new Error("World Event participant page does not match its page state");
  if (requestedCollection === "PROVENANCE" && (
    event.participant_provenance.length !== payload.pagination.PROVENANCE.returned_count
    || event.participant_summary.provenance_total_count !== payload.pagination.PROVENANCE.total_count
  )) throw new Error("World Event provenance page does not match its page state");
  if (requestedCollection === "EVIDENCE" && payload.evidence.length !== payload.pagination.EVIDENCE.returned_count) {
    throw new Error("World Event evidence page does not match its page state");
  }
  if (requestedCollection === "MEDIA" && (
    payload.media.length !== payload.pagination.MEDIA.returned_count
    || event.media_summary.total_count !== payload.pagination.MEDIA.total_count
  )) throw new Error("World Event media page does not match its page state");
  return payload;
}

export function requireWorldEvidenceContract(payload, expected = {}) {
  requireWorldContractIdentity(payload);
  if (
    payload.requested_detail_level !== "EVIDENCE"
    || payload.returned_detail_level !== "EVIDENCE"
    || payload.focus?.type !== "EVIDENCE"
    || !payload.focus.id
    || !payload.graph_revision
    || !payload.as_of
  ) throw new Error("Incomplete World Evidence focus or revision contract");
  if (expected.evidenceId && payload.focus.id !== expected.evidenceId) {
    throw staleWorldEvidenceContractError("World Evidence focus does not match the requested evidence");
  }
  if (expected.revision && payload.graph_revision !== expected.revision) {
    throw staleWorldEvidenceContractError("World Evidence revision does not match the requested snapshot");
  }
  for (const field of ["scope_totals", "effective_filters", "pagination", "limits"]) {
    if (!payload[field] || typeof payload[field] !== "object" || Array.isArray(payload[field])) {
      throw new Error(`Incomplete World Evidence ${field} contract`);
    }
  }
  for (const field of ["evidence", "media"]) {
    if (!Array.isArray(payload[field])) throw new Error(`Incomplete World Evidence ${field} collection`);
  }
  for (const collection of WORLD_EVIDENCE_COLLECTIONS) {
    if (!payload.pagination[collection]) throw new Error(`Missing World Evidence ${collection} page state`);
  }
  requireWorldPagination(payload.pagination);
  if (payload.evidence.length !== 1) throw new Error("World Evidence response must contain exactly one evidence record");
  const evidence = payload.evidence[0];
  requireWorldEvidence(evidence, "Evidence");
  if (evidence.evidence_id !== payload.focus.id) {
    throw staleWorldEvidenceContractError("World Evidence identity changed in the retained snapshot");
  }
  payload.media.forEach((item) => requireWorldMediaReference(item, "Evidence"));
  const requestedCollection = expected.collection || null;
  if (requestedCollection === "EVIDENCE" && payload.pagination.EVIDENCE.returned_count !== 1) {
    throw new Error("World Evidence detail does not match its page state");
  }
  if (requestedCollection === "MEDIA") {
    if (payload.media.length !== payload.pagination.MEDIA.returned_count) {
      throw new Error("World Evidence media page does not match its page state");
    }
    if (evidence.media_summary.total_count !== payload.pagination.MEDIA.total_count) {
      throw new Error("World Evidence media availability does not match its page state");
    }
    if (payload.media.some((item) => item.supporting_evidence_id !== evidence.evidence_id)) {
      throw new Error("World Evidence media reference does not match its supporting evidence");
    }
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

export function buildWorldPersonQuery({
  personId,
  collection = "RELATIONSHIPS",
  filters = EMPTY_WORLD_FILTERS,
  ranking = "SALIENCE",
  cursor = null,
  revision,
  asOf,
} = {}) {
  if (!personId || !revision || !asOf) throw new Error("World Person requests require person, revision, and as_of binding");
  const normalizedCollection = String(collection || "RELATIONSHIPS").toUpperCase();
  if (!WORLD_PERSON_COLLECTIONS.has(normalizedCollection)) throw new Error("Unsupported World Person collection");
  const query = new URLSearchParams({
    version: "2",
    level: "PERSON",
    focus_type: "PERSON",
    focus_id: personId,
    collection: normalizedCollection,
    ranking,
    people_limit: "25",
    event_limit: "25",
    relationship_limit: "50",
    cluster_limit: "10",
    facet_limit: "100",
    revision,
    as_of: asOf,
  });
  appendWorldFilters(query, filters);
  if (cursor) query.set("cursor", cursor);
  return `/api/world-graph?${query}`;
}

export function buildWorldEventQuery({
  eventId,
  collection = "PARTICIPANTS",
  filters = EMPTY_WORLD_FILTERS,
  cursor = null,
  revision,
  asOf,
} = {}) {
  if (!eventId || !revision || !asOf) throw new Error("World Event requests require event, revision, and as_of binding");
  const normalizedCollection = String(collection || "PARTICIPANTS").toUpperCase();
  if (!WORLD_EVENT_COLLECTIONS.has(normalizedCollection)) throw new Error("Unsupported World Event collection");
  const query = new URLSearchParams({
    version: "2",
    level: "EVENT",
    focus_type: "EVENT",
    focus_id: eventId,
    collection: normalizedCollection,
    people_limit: "25",
    provenance_limit: "100",
    evidence_limit: "25",
    media_limit: "25",
    facet_limit: "100",
    revision,
    as_of: asOf,
  });
  appendWorldFilters(query, filters);
  if (cursor) query.set("cursor", cursor);
  return `/api/world-graph?${query}`;
}

export function buildWorldEvidenceQuery({
  evidenceId,
  collection = "EVIDENCE",
  filters = EMPTY_WORLD_FILTERS,
  cursor = null,
  revision,
  asOf,
} = {}) {
  if (!evidenceId || !revision || !asOf) throw new Error("World Evidence requests require evidence, revision, and as_of binding");
  const normalizedCollection = String(collection || "EVIDENCE").toUpperCase();
  if (!WORLD_EVIDENCE_COLLECTIONS.has(normalizedCollection)) throw new Error("Unsupported World Evidence collection");
  const query = new URLSearchParams({
    version: "2",
    level: "EVIDENCE",
    focus_type: "EVIDENCE",
    focus_id: evidenceId,
    collection: normalizedCollection,
    evidence_limit: "25",
    media_limit: "25",
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

export function isInvalidWorldPersonError(error) {
  return error?.code === "WORLD_PERSON_STALE"
    || isStaleWorldError(error)
    || (
      [400, 404].includes(error?.status)
      && /world person (is unavailable|focus|revision)|person.*revision|cursor does not match/i.test(error.message || "")
    );
}

export function isInvalidWorldEventError(error) {
  return error?.code === "WORLD_EVENT_STALE"
    || isStaleWorldError(error)
    || (
      [400, 404].includes(error?.status)
      && /world event (is unavailable|focus|revision)|event.*revision|cursor does not match/i.test(error.message || "")
    );
}

export function isInvalidWorldEvidenceError(error) {
  return error?.code === "WORLD_EVIDENCE_STALE"
    || isStaleWorldError(error)
    || (
      [400, 404].includes(error?.status)
      && /world evidence (is unavailable|focus|revision)|evidence.*(revision|retired|deactivated|unavailable)|cursor does not match/i.test(error.message || "")
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
    || !WORLD_IDENTITY_STATES.has(person.identity_state)
    || !WORLD_BIOMETRIC_STATES.has(person.biometric_state)
    || !WORLD_ANALYTICS_STATES.has(person.analytics_state)
    || !person.display
    || !person.intelligence_summary
    || !person.activity_summary
    || !person.ranking
    || !Array.isArray(person.historical_person_ids)
    || !Array.isArray(person.importance_indicators)
    || !Array.isArray(person.allowed_actions)
    || !person.explanation
    || !Array.isArray(person.explanation.factual_factors)
    || !Array.isArray(person.explanation.limitations)
  ) throw new Error("Invalid World person contract");
  if (person.analytics_state === "LOADED" && (
    !Number.isFinite(Number(person.activity_summary.finalized_event_count))
    || !Number.isFinite(Number(person.intelligence_summary.relationship_count))
    || !Number.isFinite(Number(person.intelligence_summary.relationship_evidence_count))
  )) throw new Error("Invalid loaded World person analytics contract");
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

function requireWorldEvent(event) {
  if (
    !event?.event_id
    || !event.finalized_at
    || !event.occurred_at
    || (event.location !== null && typeof event.location !== "string")
    || !event.context_summary
    || typeof event.context_summary.available !== "boolean"
    || (event.source !== null && typeof event.source !== "string")
    || !Array.isArray(event.participants)
    || !Array.isArray(event.participant_provenance)
    || !event.participant_summary
    || !Number.isFinite(Number(event.participant_summary.total_count))
    || !Number.isFinite(Number(event.participant_summary.returned_count))
    || typeof event.participant_summary.has_more !== "boolean"
    || !Number.isFinite(Number(event.participant_summary.provenance_total_count))
    || !Number.isFinite(Number(event.participant_summary.provenance_returned_count))
    || !event.participant_summary.participants_state
    || !event.participant_summary.provenance_state
    || !event.evidence_summary
    || !Number.isFinite(Number(event.evidence_summary.total_count))
    || !event.evidence_summary.evidence_type_counts
    || !event.media_summary
    || !Number.isFinite(Number(event.media_summary.total_count))
    || !event.media_summary.retrieval
    || !event.explanation
    || !Array.isArray(event.explanation.factual_factors)
    || !Array.isArray(event.explanation.limitations)
  ) throw new Error("Invalid World event summary contract");
}

function requireWorldParticipant(participant) {
  if (!participant?.person_id) throw new Error("Invalid World Event participant contract");
}

function requireWorldParticipantProvenance(item) {
  if (
    !item?.raw_person_id
    || !item.effective_person_id
    || !item.relationship_to_effective_identity
    || !Array.isArray(item.correction_operation_ids)
  ) throw new Error("Invalid World Event provenance contract");
}

function requireWorldEvidence(evidence, level = "Event") {
  if (
    !evidence?.evidence_id
    || !WORLD_EVIDENCE_TYPES.has(evidence.evidence_type)
    || !WORLD_EVIDENCE_DIRECTIONS.has(evidence.directionality)
    || typeof evidence.active !== "boolean"
    || !evidence.occurred_at
    || !Array.isArray(evidence.effective_endpoints)
    || evidence.effective_endpoints.length !== 2
    || evidence.effective_endpoints.some((item) => !item)
    || !Array.isArray(evidence.raw_endpoints)
    || evidence.raw_endpoints.length !== 2
    || evidence.raw_endpoints.some((item) => !item)
    || !Array.isArray(evidence.supporting_references)
    || !evidence.supporting_references.length
    || evidence.supporting_references.some((item) => !item?.source_entity_type || !item.source_entity_id || !item.evidence_revision_id)
    || !evidence.provenance
    || !evidence.provenance.created_operation_id
    || !Array.isArray(evidence.provenance.canonical_endpoints)
    || evidence.provenance.canonical_endpoints.length !== 2
    || !Array.isArray(evidence.provenance.raw_endpoints)
    || evidence.provenance.raw_endpoints.length !== 2
    || !evidence.occurrence_bounds
    || !evidence.occurrence_bounds.first
    || !evidence.occurrence_bounds.last
    || !evidence.explanation
    || !evidence.explanation.summary
    || !evidence.explanation.method
    || !Array.isArray(evidence.explanation.factual_factors)
    || !Array.isArray(evidence.explanation.limitations)
    || !evidence.media_summary
    || !Number.isFinite(Number(evidence.media_summary.total_count))
    || !["AVAILABLE", "UNAVAILABLE"].includes(evidence.media_summary.availability)
    || evidence.media_summary.retrieval !== "EVIDENCE_MEDIA_COLLECTION"
    || (evidence.media_summary.availability === "UNAVAILABLE" && !evidence.media_summary.reason)
    || evidence.provenance.canonical_endpoints.some((item, index) => item !== evidence.effective_endpoints[index])
    || evidence.provenance.raw_endpoints.some((item, index) => item !== evidence.raw_endpoints[index])
  ) throw new Error(`Invalid World ${level} evidence contract`);
}

function requireWorldMediaReference(media, level = "Event") {
  if (
    !media?.media_id
    || (media.media_reference !== null && typeof media.media_reference !== "string")
    || !media.occurred_at
    || !media.supporting_event_id
  ) throw new Error(`Invalid World ${level} media reference contract`);
}

function staleWorldPersonContractError(message) {
  const error = new Error(message);
  error.code = "WORLD_PERSON_STALE";
  return error;
}

function staleWorldEventContractError(message) {
  const error = new Error(message);
  error.code = "WORLD_EVENT_STALE";
  return error;
}

function staleWorldEvidenceContractError(message) {
  const error = new Error(message);
  error.code = "WORLD_EVIDENCE_STALE";
  return error;
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
