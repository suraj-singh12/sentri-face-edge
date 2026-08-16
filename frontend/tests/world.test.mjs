import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  buildWorldClusterQuery,
  buildWorldEvidenceQuery,
  buildWorldEventQuery,
  buildWorldPersonQuery,
  buildWorldScopeQuery,
  filtersFromEffective,
  invalidateWorldSnapshot,
  isInvalidWorldClusterError,
  isInvalidWorldEventError,
  isInvalidWorldEvidenceError,
  isInvalidWorldPersonError,
  isStaleWorldError,
  requireWorldClusterContract,
  requireWorldEventContract,
  requireWorldEvidenceContract,
  requireWorldPersonContract,
  requireWorldScopeContract,
  worldEvidenceMediaRequestState,
  worldEntryMode,
  worldRetainedHierarchyIsCurrent,
} from "../src/utils/world.js";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

function page(collection, count) {
  return {
    collection,
    total_count: count,
    returned_count: count,
    has_more: false,
    next_cursor: null,
    truncated: false,
    truncation_reason: null,
  };
}

function unrequestedPage(collection, count = 0) {
  return {
    collection,
    total_count: count,
    returned_count: 0,
    has_more: count > 0,
    next_cursor: null,
    truncated: count > 0,
    truncation_reason: "collection_not_requested",
  };
}

function worldFilters(values = {}) {
  return {
    date_from: null,
    date_to: null,
    recent_activity: null,
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
    ...values,
  };
}

function worldLimits() {
  return {
    people: 25,
    clusters: 10,
    events: 25,
    evidence: 25,
    media: 25,
    relationships: 50,
    patterns: 10,
    provenance: 100,
    facets: 100,
  };
}

function explanation(values = {}) {
  return {
    summary: "Measured backend fact.",
    basis_type: "PERSON_RANKING",
    factual_factors: [],
    strongest_factors: [],
    limitations: [],
    method: "backend_method",
    ...values,
  };
}

function person(values = {}) {
  return {
    canonical_person_id: "person-a",
    historical_person_ids: [],
    display_name: "A",
    lifecycle_state: "ACTIVE",
    identity_state: "IDENTIFIED",
    biometric_state: "ENROLLED",
    display: { rank: "Analyst", country: "India" },
    intelligence_summary: { relationship_count: null, relationship_evidence_count: null, activity_bucket: null },
    activity_summary: { finalized_event_count: null, activity_bucket: null, state: "NOT_LOADED" },
    ranking: { applied: false, intent: "SALIENCE", rank_position: null, ranking_reason: "Selected by cluster membership.", metrics_state: "NOT_LOADED" },
    importance_indicators: [],
    analytics_state: "NOT_LOADED",
    allowed_actions: ["OPEN"],
    explanation: explanation(),
    cluster_memberships: [],
    ...values,
  };
}

function payload(values = {}) {
  return {
    contract: "sentriface.world-graph",
    contract_version: 2,
    filter_semantics_version: "world-filters-v1",
    ranking_version: "descriptive-salience-v1",
    clustering_version: "connected-evidence-components-v1",
    calculation_version: "world-descriptive-v1",
    requested_detail_level: "WORLD_SCOPE",
    returned_detail_level: "WORLD_SCOPE",
    graph_revision: "opaque-g7",
    as_of: "2026-08-11T12:00:00+00:00",
    generated_at: "2026-08-11T12:00:01+00:00",
    focus: null,
    requested_filters: worldFilters(),
    effective_filters: worldFilters(),
    ranking: "SALIENCE",
    limits: worldLimits(),
    scope_totals: { people: 1, clusters: 0, relationships: 0, finalized_events: 0 },
    available_facets: {
      filter_semantics_version: "world-filters-v1",
      ranking_version: "descriptive-salience-v1",
      clustering_version: "connected-evidence-components-v1",
      calculation_version: "world-descriptive-v1",
    },
    returned_counts: { people: 1, clusters: 0, events: 0, evidence: 0, relationships: 0, patterns: 0, media: 0 },
    pagination: {
      PEOPLE: page("PEOPLE", 1),
      CLUSTERS: unrequestedPage("CLUSTERS"),
      RELATIONSHIPS: unrequestedPage("RELATIONSHIPS"),
      PATTERNS: unrequestedPage("PATTERNS"),
      LOCATION_FACETS: unrequestedPage("LOCATION_FACETS"),
    },
    truncated: false,
    has_more: false,
    next_cursor: null,
    people: [person()],
    clusters: [],
    events: [],
    evidence: [],
    relationships: [],
    patterns: [],
    media: [],
    ...values,
  };
}

function emptyDatabaseWorldScopePayload(values = {}) {
  return payload({
    graph_revision: "0",
    scope_totals: { people: 0, clusters: 0, relationships: 0, finalized_events: 0 },
    returned_counts: { people: 0, clusters: 0, events: 0, evidence: 0, relationships: 0, patterns: 0, media: 0 },
    pagination: {
      PEOPLE: page("PEOPLE", 0),
      CLUSTERS: unrequestedPage("CLUSTERS"),
      RELATIONSHIPS: unrequestedPage("RELATIONSHIPS"),
      PATTERNS: unrequestedPage("PATTERNS"),
      LOCATION_FACETS: unrequestedPage("LOCATION_FACETS"),
    },
    people: [],
    clusters: [],
    events: [],
    evidence: [],
    relationships: [],
    patterns: [],
    media: [],
    ...values,
  });
}

function clusterSummary(values = {}) {
  return {
    cluster_id: "cluster:scope-a",
    graph_revision: "opaque-g7",
    member_ids: ["person-a"],
    member_count: 2,
    member_preview: [{ canonical_person_id: "person-a", display_name: "A" }],
    member_preview_state: { total_count: 2, returned_count: 1, has_more: true, truncated: true, truncation_reason: "backend_preview_limit:1" },
    grouping_algorithm: "EVIDENCE_CONNECTED_COMPONENT",
    algorithm_version: "connected-evidence-components-v1",
    parameters: { minimum_members: 2 },
    evidence_basis: { relationship_count: 1, evidence_count: 4, evidence_type_counts: { CO_OBSERVED: 4 }, strongest_relationships: [] },
    activity_summary: { member_event_contributions: 7, active_member_count: 2, measurement: "deduplicated_person_event_contributions" },
    ranking: { rank_position: 1, reason: "Ordered by member count and evidence count.", measurements: { member_count: 2, evidence_count: 4 } },
    explanation: explanation({
      summary: "2 people are connected by 4 scoped evidence records.",
      basis_type: "EVIDENCE_CONNECTED_COMPONENT",
      evidence_count: 4,
      factual_factors: [{ factor: "member_count", value: 2 }],
      limitations: ["A cluster is revision-bound."],
    }),
    ...values,
  };
}

function relationship(values = {}) {
  return {
    relationship_id: "relationship:person-a:person-b",
    source_person_id: "person-a",
    target_person_id: "person-b",
    directionality: "UNDIRECTED",
    relationship_types: ["CO_OBSERVED"],
    evidence_count: 4,
    evidence_type_counts: { CO_OBSERVED: 4 },
    first_occurrence_at: "2026-08-01T10:00:00Z",
    last_occurrence_at: "2026-08-05T10:00:00Z",
    strength_basis: "EVIDENCE_COUNT_IN_SCOPE",
    explanation: explanation({
      basis_type: "EVIDENCE_COUNT_IN_SCOPE",
      evidence_count: 4,
      factual_factors: [{ factor: "directionality", value: "UNDIRECTED" }],
      limitations: ["Strength is descriptive evidence count."],
    }),
    ...values,
  };
}

function clusterPayload(collection = "MEMBERS", values = {}) {
  const members = collection === "MEMBERS" ? [person({
    analytics_state: "LOADED",
    intelligence_summary: { relationship_count: 1, relationship_evidence_count: 4, activity_bucket: "MEDIUM" },
    activity_summary: { finalized_event_count: 3, activity_bucket: "MEDIUM", state: "LOADED" },
    ranking: { applied: false, intent: "SALIENCE", rank_position: null, ranking_reason: "Requested cluster member.", metrics_state: "LOADED" },
  })] : [];
  const relationships = collection === "RELATIONSHIPS" ? [relationship()] : [];
  return {
    contract: "sentriface.world-graph",
    contract_version: 2,
    requested_detail_level: "CLUSTER",
    returned_detail_level: "CLUSTER",
    graph_revision: "opaque-g7",
    as_of: "2026-08-11T12:00:00+00:00",
    focus: { type: "CLUSTER", id: "cluster:scope-a" },
    scope_totals: { people: 2, relationships: 1, clusters: 1, finalized_events: 5 },
    effective_filters: { recent_activity: "LAST_30_DAYS", missing_location: "INCLUDE" },
    limits: { people: 25, relationships: 50 },
    pagination: {
      MEMBERS: collection === "MEMBERS"
        ? { collection: "MEMBERS", total_count: 2, returned_count: 1, has_more: true, next_cursor: "members-next", truncated: true, truncation_reason: "backend_limit:1" }
        : { ...page("MEMBERS", 2), returned_count: 0, has_more: true, truncated: true, truncation_reason: "collection_not_requested" },
      RELATIONSHIPS: collection === "RELATIONSHIPS" ? page("RELATIONSHIPS", 1) : { ...page("RELATIONSHIPS", 1), returned_count: 0, has_more: true, truncated: true, truncation_reason: "collection_not_requested" },
    },
    people: members,
    clusters: [clusterSummary({ member_ids: collection === "MEMBERS" ? ["person-a"] : [] })],
    relationships,
    patterns: [], events: [], evidence: [], media: [],
    ...values,
  };
}

function worldEvent(values = {}) {
  return {
    event_id: "event-a",
    finalized_at: "2026-08-05T10:05:00Z",
    occurred_at: "2026-08-05T10:00:00Z",
    location: null,
    context_summary: { available: true, event_type: "arrival" },
    source: "camera-1",
    participants: [],
    participant_provenance: [],
    participant_summary: {
      total_count: 2,
      returned_count: 0,
      has_more: true,
      provenance_total_count: 2,
      provenance_returned_count: 0,
      participants_state: "NOT_REQUESTED",
      provenance_state: "NOT_REQUESTED",
    },
    evidence_summary: { total_count: 4, evidence_type_counts: { CO_OBSERVED: 4 } },
    media_summary: { total_count: 1, retrieval: "EVENT_MEDIA_COLLECTION" },
    explanation: explanation({
      basis_type: "FINALIZED_OBSERVATION",
      factual_factors: [{ factor: "participant_count", value: 2 }],
      limitations: ["Media and evidence details use separate collections."],
    }),
    ...values,
  };
}

function personPayload(collection = "RELATIONSHIPS", values = {}) {
  const root = person({
    display_name: "Ananya Rao",
    analytics_state: "LOADED",
    intelligence_summary: { relationship_count: 1, relationship_evidence_count: 4, activity_bucket: "MEDIUM" },
    activity_summary: { finalized_event_count: 3, activity_bucket: "MEDIUM", state: "LOADED" },
    ranking: { applied: false, intent: "SALIENCE", rank_position: null, ranking_reason: "Requested person focus; global ranking was not used.", metrics_state: "LOADED" },
    cluster_memberships: [{
      cluster_id: "cluster:scope-a",
      graph_revision: "opaque-g7",
      member_count: 2,
      grouping_algorithm: "EVIDENCE_CONNECTED_COMPONENT",
      algorithm_version: "connected-evidence-components-v1",
    }],
  });
  const neighbor = person({ canonical_person_id: "person-b", display_name: "B", analytics_state: "NOT_LOADED" });
  const relationships = collection === "RELATIONSHIPS" ? [relationship()] : [];
  const events = collection === "EVENTS" ? [worldEvent()] : [];
  return {
    contract: "sentriface.world-graph",
    contract_version: 2,
    requested_detail_level: "PERSON",
    returned_detail_level: "PERSON",
    graph_revision: "opaque-g7",
    as_of: "2026-08-11T12:00:00+00:00",
    focus: { type: "PERSON", id: "person-a" },
    scope_totals: { people: 1, relationships: 1, clusters: 0, finalized_events: 3 },
    effective_filters: { recent_activity: "LAST_30_DAYS", missing_location: "INCLUDE" },
    limits: { people: 25, relationships: 50, events: 25 },
    pagination: {
      RELATIONSHIPS: collection === "RELATIONSHIPS"
        ? page("RELATIONSHIPS", 1)
        : { ...page("RELATIONSHIPS", 1), returned_count: 0, has_more: true, truncated: true, truncation_reason: "collection_not_requested" },
      EVENTS: collection === "EVENTS"
        ? { collection: "EVENTS", total_count: 3, returned_count: 1, has_more: true, next_cursor: "events-next", truncated: true, truncation_reason: "backend_limit:1" }
        : { ...page("EVENTS", 3), returned_count: 0, has_more: true, truncated: true, truncation_reason: "collection_not_requested" },
    },
    people: collection === "RELATIONSHIPS" ? [root, neighbor] : [root],
    relationships,
    events,
    clusters: [], patterns: [], evidence: [], media: [],
    ...values,
  };
}

function worldEvidence(values = {}) {
  return {
    evidence_id: "evidence-a",
    provenance: { created_operation_id: "operation-a", source: "event-finalization", canonical_endpoints: ["person-a", "person-b"], raw_endpoints: ["person-raw", "person-b"] },
    evidence_type: "CO_OBSERVED",
    supporting_references: [{ source_entity_type: "OBSERVATION", source_entity_id: "event-a", evidence_revision_id: "revision-a" }],
    occurred_at: "2026-08-05T10:00:00Z",
    explanation_links: ["relationship:person-a:person-b"],
    active: true,
    directionality: "UNDIRECTED",
    effective_endpoints: ["person-a", "person-b"],
    raw_endpoints: ["person-raw", "person-b"],
    occurrence_bounds: { first: "2026-08-05T10:00:00Z", last: "2026-08-05T10:00:00Z" },
    explanation: explanation({
      basis_type: "AUTHORITATIVE_EVIDENCE_PROVENANCE",
      factual_factors: [{ factor: "raw_endpoints", value: ["person-raw", "person-b"] }],
      limitations: ["This evidence is descriptive provenance."],
    }),
    media_summary: { total_count: 1, availability: "AVAILABLE", retrieval: "EVIDENCE_MEDIA_COLLECTION", reason: null },
    ...values,
  };
}

function worldMedia(values = {}) {
  return {
    media_id: "media-a",
    media_reference: "events/event-a/photo.jpg",
    source: "camera-1",
    occurred_at: "2026-08-05T10:00:00Z",
    supporting_event_id: "event-a",
    supporting_evidence_id: null,
    ...values,
  };
}

function eventPayload(collection = "PARTICIPANTS", values = {}) {
  const participants = collection === "PARTICIPANTS" ? [{ person_id: "person-a" }, { person_id: "person-b" }] : [];
  const provenance = collection === "PROVENANCE" ? [{
    raw_person_id: "person-raw",
    effective_person_id: "person-a",
    relationship_to_effective_identity: "CORRECTED_PARTICIPANT",
    correction_operation_ids: ["correction-a"],
  }] : [];
  const event = worldEvent({
    participants,
    participant_provenance: provenance,
    participant_summary: {
      total_count: 2,
      returned_count: participants.length,
      has_more: false,
      provenance_total_count: 1,
      provenance_returned_count: provenance.length,
      participants_state: collection === "PARTICIPANTS" ? "LOADED" : "NOT_REQUESTED",
      provenance_state: collection === "PROVENANCE" ? "LOADED" : "NOT_REQUESTED",
    },
  });
  const unrequested = (name, total) => ({ ...page(name, total), returned_count: 0, has_more: total > 0, truncated: total > 0, truncation_reason: "collection_not_requested" });
  return {
    contract: "sentriface.world-graph",
    contract_version: 2,
    requested_detail_level: "EVENT",
    returned_detail_level: "EVENT",
    graph_revision: "opaque-g7",
    as_of: "2026-08-11T12:00:00+00:00",
    focus: { type: "EVENT", id: "event-a" },
    scope_totals: { people: 2, relationships: 0, clusters: 0, finalized_events: 1, evidence: 1, media: 1 },
    effective_filters: { recent_activity: "LAST_30_DAYS", missing_location: "INCLUDE" },
    limits: { people: 25, provenance: 100, evidence: 25, media: 25 },
    pagination: {
      PARTICIPANTS: collection === "PARTICIPANTS" ? page("PARTICIPANTS", 2) : unrequested("PARTICIPANTS", 2),
      PROVENANCE: collection === "PROVENANCE" ? page("PROVENANCE", 1) : unrequested("PROVENANCE", 1),
      EVIDENCE: collection === "EVIDENCE" ? page("EVIDENCE", 1) : unrequested("EVIDENCE", 1),
      MEDIA: collection === "MEDIA" ? page("MEDIA", 1) : unrequested("MEDIA", 1),
    },
    people: [], clusters: [], relationships: [], patterns: [],
    events: [event],
    evidence: collection === "EVIDENCE" ? [worldEvidence()] : [],
    media: collection === "MEDIA" ? [worldMedia()] : [],
    ...values,
  };
}

function evidencePayload(collection = "EVIDENCE", values = {}) {
  const detail = values.detail || worldEvidence();
  const media = collection === "MEDIA"
    ? (values.media || [worldMedia({ supporting_evidence_id: detail.evidence_id })])
    : [];
  const mediaTotal = collection === "MEDIA" ? (values.mediaTotal ?? detail.media_summary.total_count) : 0;
  const evidencePage = page("EVIDENCE", 1);
  const mediaPage = collection === "MEDIA"
    ? { ...page("MEDIA", mediaTotal), returned_count: media.length, has_more: media.length < mediaTotal, next_cursor: media.length < mediaTotal ? "media-next" : null, truncated: media.length < mediaTotal, truncation_reason: media.length < mediaTotal ? `backend_limit:${media.length}` : null }
    : unrequestedPage("MEDIA", detail.media_summary.total_count);
  return {
    contract: "sentriface.world-graph",
    contract_version: 2,
    requested_detail_level: "EVIDENCE",
    returned_detail_level: "EVIDENCE",
    graph_revision: "opaque-g7",
    as_of: "2026-08-11T12:00:00+00:00",
    focus: { type: "EVIDENCE", id: detail.evidence_id },
    scope_totals: { evidence: 1, media: mediaTotal },
    effective_filters: { recent_activity: "LAST_30_DAYS", missing_location: "INCLUDE" },
    limits: { evidence: 25, media: 25 },
    pagination: { EVIDENCE: evidencePage, MEDIA: mediaPage },
    people: [], clusters: [], relationships: [], patterns: [], events: [],
    evidence: [detail],
    media,
    ...values,
  };
}

test("World scope validates the frozen v2 authority and availability states", () => {
  const result = requireWorldScopeContract(payload());
  assert.equal(result.people[0].analytics_state, "NOT_LOADED");
  assert.throws(() => requireWorldScopeContract({ ...payload(), contract_version: 1 }));
  assert.throws(() => requireWorldScopeContract({ ...payload(), people: [{ ...payload().people[0], analytics_state: "ZERO" }] }));
});

test("World request builder sends intent and does not calculate filter semantics", () => {
  const request = new URL(buildWorldScopeQuery({
    collection: "RELATIONSHIPS",
    ranking: "EVIDENCE_COUNT",
    filters: {
      locations: ["Dock", "MISSING"],
      lifecycle: ["ACTIVE"],
      evidence_type: ["CO_OBSERVED"],
      missing_location: "ONLY",
      min_relationship_strength: 3,
    },
    cursor: "cursor-1",
    revision: "opaque-g7",
    asOf: "2026-08-11T12:00:00+00:00",
  }), "http://localhost");
  assert.equal(request.searchParams.get("version"), "2");
  assert.equal(request.searchParams.get("level"), "WORLD_SCOPE");
  assert.equal(request.searchParams.get("collection"), "RELATIONSHIPS");
  assert.deepEqual(request.searchParams.getAll("location"), ["Dock", "MISSING"]);
  assert.equal(request.searchParams.get("revision"), "opaque-g7");
  assert.equal(request.searchParams.get("cursor"), "cursor-1");
});

test("effective filters replace form intent with backend-normalized values", () => {
  assert.deepEqual(filtersFromEffective({
    recent_activity: "LAST_30_DAYS",
    date_from: "2026-07-12T12:00:00+00:00",
    date_to: "2026-08-11T12:00:00+00:00",
    locations: ["Dock"],
    lifecycle: ["ACTIVE"],
    missing_location: "EXCLUDE",
  }), {
    date_from: "",
    date_to: "",
    recent_activity: "LAST_30_DAYS",
    locations: ["Dock"],
    missing_location: "EXCLUDE",
    lifecycle: ["ACTIVE"],
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
});

test("World lifecycle invalidates snapshots and treats revisions as opaque", () => {
  const snapshot = { data: payload(), invalidated: false, loading: true };
  assert.equal(worldEntryMode(snapshot), "VALIDATE");
  const invalidated = invalidateWorldSnapshot(snapshot, { graph_revision: "opaque-g8" });
  assert.equal(invalidated.invalidated, true);
  assert.equal(invalidated.pendingRevision, "opaque-g8");
  assert.equal(invalidated.data, snapshot.data);
  assert.equal(worldEntryMode(invalidated), "LOAD");
  assert.equal(isStaleWorldError({ status: 400, message: "World revision is stale; request a new snapshot" }), true);
});

test("FR-01 stale re-entry and Back paths discard retained semantic hierarchy before rendering a parent", async () => {
  const [controller, evidenceController] = await Promise.all([
    read("../src/hooks/useWorldController.js"),
    read("../src/hooks/useWorldEvidenceController.js"),
  ]);
  assert.match(controller, /discardRetainedWorldHierarchy/);
  assert.match(controller, /revision\.stale[\s\S]*discardRetainedWorldHierarchy\([\s\S]*loadWorld/);
  assert.match(controller, /closeWorldCluster[\s\S]*validateRetainedWorldRevision/);
  assert.match(controller, /closeWorldPerson[\s\S]*validateRetainedWorldRevision/);
  assert.match(controller, /closeWorldEvent[\s\S]*validateRetainedWorldRevision/);
  assert.match(controller, /closeWorldEvidence[\s\S]*validateRetainedWorldRevision/);
  assert.match(controller, /validateWorldMediaOrigin/);
  assert.match(controller, /const next = \{ \.\.\.current, active: false, notice: null \}/);
  assert.match(evidenceController, /resetWorldEvidence[\s\S]*generation \+ 1/);
});

test("FR-01 retained hierarchy is renderable only for the current authoritative scope revision", () => {
  const hierarchy = {
    cluster: { active: true, binding: { revision: "opaque-g6" } },
    person: { active: true, binding: { revision: "opaque-g6" } },
    event: { active: true, binding: { revision: "opaque-g6" } },
    evidence: { active: true, binding: { revision: "opaque-g6" } },
  };
  assert.equal(worldRetainedHierarchyIsCurrent(hierarchy, { graph_revision: "opaque-g6" }), true);
  assert.equal(worldRetainedHierarchyIsCurrent(hierarchy, { graph_revision: "opaque-g7" }), false);
  assert.equal(worldRetainedHierarchyIsCurrent(hierarchy, null), false);
  assert.equal(worldRetainedHierarchyIsCurrent({ evidence: { active: false } }, { graph_revision: "opaque-g7" }), true);
});

test("FR-01 World rendering suppresses stale g6 Evidence under g7 and preserves same-revision Evidence", async (t) => {
  const { createServer } = await import("vite");
  const React = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { MantineProvider } = await import("@mantine/core");
  const server = await createServer({
    root: fileURLToPath(new URL("../", import.meta.url)),
    appType: "custom",
    logLevel: "silent",
    server: { middlewareMode: true },
  });
  t.after(() => server.close());
  const { WorldView } = await server.ssrLoadModule("/src/views/WorldView.jsx");
  const detail = worldEvidence();
  const evidenceData = evidencePayload("EVIDENCE", { graph_revision: "opaque-g7", detail });
  const evidenceState = (revision) => ({
    active: true,
    evidenceId: detail.evidence_id,
    collection: "EVIDENCE",
    detail,
    binding: { revision, asOf: evidenceData.as_of, filters: worldFilters() },
    collections: {
      EVIDENCE: { data: evidenceData, loading: false, error: null, pageNumber: 1 },
      MEDIA: { data: null, loading: false, error: null, pageNumber: 1 },
    },
  });
  const render = (revision) => renderToStaticMarkup(React.createElement(
    MantineProvider,
    null,
    React.createElement(WorldView, {
      state: {
        data: payload(), collection: "PEOPLE", filters: worldFilters(), ranking: "SALIENCE",
        loading: false, error: null, pageNumber: 1,
        cluster: { active: true, binding: { revision } },
        person: { active: true, binding: { revision } },
        event: { active: true, binding: { revision } },
        evidence: evidenceState(revision),
      },
      onValidateMediaOrigin: async () => true,
    }),
  ));
  const staleMarkup = render("opaque-g6");
  assert.doesNotMatch(staleMarkup, /data-world-level="EVIDENCE"/);
  assert.match(staleMarkup, /data-contract="sentriface\.world-graph-v2"/);
  const currentMarkup = render("opaque-g7");
  assert.match(currentMarkup, /data-world-level="EVIDENCE"/);
});

test("FR-02 WORLD_SCOPE rejects every required frozen envelope and nullable page property when absent", () => {
  for (const field of [
    "filter_semantics_version", "ranking_version", "clustering_version", "calculation_version",
    "generated_at", "focus", "requested_filters", "effective_filters", "ranking", "limits",
    "scope_totals", "available_facets", "returned_counts", "pagination", "truncated", "has_more",
    "next_cursor", "events", "evidence", "media",
  ]) {
    const malformed = payload();
    delete malformed[field];
    assert.throws(() => requireWorldScopeContract(malformed), undefined, `missing ${field}`);
  }
  for (const collection of ["PEOPLE", "CLUSTERS", "RELATIONSHIPS", "PATTERNS", "LOCATION_FACETS"]) {
    const malformed = payload();
    delete malformed.pagination[collection];
    assert.throws(() => requireWorldScopeContract(malformed), undefined, `missing ${collection} page`);
  }
  for (const field of ["next_cursor", "truncation_reason"]) {
    const malformed = payload();
    delete malformed.pagination.PEOPLE[field];
    assert.throws(() => requireWorldScopeContract(malformed), undefined, `missing nullable page property ${field}`);
  }
  for (const field of ["people", "clusters", "relationships", "finalized_events"]) {
    const malformed = payload();
    delete malformed.scope_totals[field];
    assert.throws(() => requireWorldScopeContract(malformed), undefined, `missing scope total ${field}`);
  }
  for (const field of ["people", "clusters", "events", "evidence", "relationships", "patterns", "media"]) {
    const malformed = payload();
    delete malformed.returned_counts[field];
    assert.throws(() => requireWorldScopeContract(malformed), undefined, `missing returned count ${field}`);
  }
  assert.throws(() => requireWorldScopeContract(payload({ ranking: "UNSPECIFIED" })), /scope or revision contract/);
});

test("FR-02 accepts the frozen requested and collection-not-requested page-state matrix", () => {
  assert.doesNotThrow(() => requireWorldScopeContract(emptyDatabaseWorldScopePayload(), { collection: "PEOPLE" }));

  const populatedComplete = payload();
  assert.doesNotThrow(() => requireWorldScopeContract(populatedComplete, { collection: "PEOPLE" }));

  const requestedPaginated = payload({
    scope_totals: { people: 2, clusters: 0, relationships: 0, finalized_events: 0 },
    pagination: {
      ...payload().pagination,
      PEOPLE: {
        collection: "PEOPLE", total_count: 2, returned_count: 1,
        has_more: true, next_cursor: "opaque-next", truncated: true,
        truncation_reason: "backend_limit:25",
      },
    },
    truncated: true,
    has_more: true,
    next_cursor: "opaque-next",
  });
  assert.doesNotThrow(() => requireWorldScopeContract(requestedPaginated, { collection: "PEOPLE" }));

  const unrequestedPopulatedCollection = payload({
    scope_totals: { people: 1, clusters: 0, relationships: 2, finalized_events: 0 },
    pagination: {
      ...payload().pagination,
      RELATIONSHIPS: unrequestedPage("RELATIONSHIPS", 2),
    },
    truncated: true,
  });
  assert.doesNotThrow(() => requireWorldScopeContract(unrequestedPopulatedCollection, { collection: "PEOPLE" }));

  const malformedPages = [
    { ...page("CLUSTERS", 0), truncation_reason: "arbitrary_reason" },
    { ...unrequestedPage("CLUSTERS"), returned_count: 1 },
    { ...unrequestedPage("CLUSTERS", 1), next_cursor: "forbidden-cursor" },
    { ...page("CLUSTERS", 1), has_more: true, truncated: true, truncation_reason: "backend_limit:10" },
    { ...page("CLUSTERS", 1), has_more: true, next_cursor: "opaque-next", truncation_reason: "backend_limit:10" },
  ];
  for (const malformedPage of malformedPages) {
    const malformed = payload({
      pagination: { ...payload().pagination, CLUSTERS: malformedPage },
      truncated: Boolean(malformedPage.truncated),
    });
    assert.throws(() => requireWorldScopeContract(malformed, { collection: "PEOPLE" }), /Invalid World CLUSTERS page state/);
  }

  for (const field of ["next_cursor", "truncation_reason"]) {
    const malformed = emptyDatabaseWorldScopePayload();
    delete malformed.pagination.CLUSTERS[field];
    assert.throws(() => requireWorldScopeContract(malformed, { collection: "PEOPLE" }), /Invalid World CLUSTERS page state/);
  }
});

test("FR-02 World rendering does not fabricate required totals or ranking", async () => {
  const view = await read("../src/views/WorldView.jsx");
  assert.doesNotMatch(view, /totals\.(people|finalized_events|relationships|clusters) \?\? 0/);
  assert.doesNotMatch(view, /setRanking\(state\.ranking \|\| "SALIENCE"\)/);
  assert.match(view, /value: totals\.people/);
  assert.match(view, /setRanking\(state\.ranking\)/);
});

test("FR-03 PERSON relationship pages require backend neighbor projections and preserve analytics distinctions", () => {
  const valid = requireWorldPersonContract(personPayload("RELATIONSHIPS"), {
    personId: "person-a", collection: "RELATIONSHIPS", revision: "opaque-g7",
  });
  assert.equal(valid.people[1].analytics_state, "NOT_LOADED");
  assert.throws(() => requireWorldPersonContract(personPayload("RELATIONSHIPS", {
    people: [personPayload("RELATIONSHIPS").people[0]],
  }), { personId: "person-a", collection: "RELATIONSHIPS", revision: "opaque-g7" }), /neighbor projection/);

  const loadedZeroNeighbor = person({
    canonical_person_id: "person-b",
    display_name: "B",
    analytics_state: "LOADED",
    intelligence_summary: { relationship_count: 0, relationship_evidence_count: 0, activity_bucket: "NONE" },
    activity_summary: { finalized_event_count: 0, activity_bucket: "NONE", state: "LOADED" },
  });
  const loadedZero = requireWorldPersonContract(personPayload("RELATIONSHIPS", {
    people: [personPayload("RELATIONSHIPS").people[0], loadedZeroNeighbor],
  }), { personId: "person-a", collection: "RELATIONSHIPS", revision: "opaque-g7" });
  assert.equal(loadedZero.people[1].analytics_state, "LOADED");
  assert.equal(loadedZero.people[1].activity_summary.finalized_event_count, 0);
  assert.equal(loadedZero.people[1].intelligence_summary.relationship_count, 0);
});

test("FR-03 Person relationship rendering consumes explicit neighbor state without synthesizing authority", async () => {
  const view = await read("../src/views/WorldPersonDrilldownView.jsx");
  assert.match(view, /neighbor\.display_name/);
  assert.match(view, /neighbor\.analytics_state/);
  assert.doesNotMatch(view, /neighbor\?\.analytics_state \|\| "NOT_LOADED"|neighbor\?\.display_name \|\|/);
});

test("FR-04 Evidence media request failure is not rendered as requested-empty", async () => {
  const view = await read("../src/views/WorldEvidenceDrilldownView.jsx");
  assert.match(view, /EVIDENCE_MEDIA_REQUEST_FAILED/);
  assert.match(view, /Supporting media request failed/);
  assert.doesNotMatch(view, /const media = data\?\.media \|\| \[\]/);
  assert.match(view, /EVIDENCE_MEDIA_EMPTY[\s\S]*No supporting media returned/);
});

test("FR-04 Evidence media state machine keeps all request outcomes mutually exclusive", () => {
  const state = (values = {}) => worldEvidenceMediaRequestState({
    availability: "AVAILABLE", data: null, loading: false, error: null, ...values,
  });
  assert.equal(state(), "EVIDENCE_MEDIA_NOT_REQUESTED");
  assert.equal(state({ loading: true }), "EVIDENCE_MEDIA_LOADING");
  assert.equal(state({ error: new Error("offline") }), "EVIDENCE_MEDIA_REQUEST_FAILED");
  assert.equal(state({ data: { media: [] } }), "EVIDENCE_MEDIA_EMPTY");
  assert.equal(state({ data: { media: [worldMedia({ supporting_evidence_id: "evidence-a" })] } }), "EVIDENCE_MEDIA_POPULATED");
  for (const evidenceType of ["NOTE_REFERENCE", "MANUAL_ASSOCIATION"]) {
    const detail = worldEvidence({ evidence_type: evidenceType, media_summary: { total_count: 0, availability: "UNAVAILABLE", retrieval: "EVIDENCE_MEDIA_COLLECTION", reason: "evidence_source_has_no_authoritative_media" } });
    assert.equal(state({ availability: detail.media_summary.availability }), "EVIDENCE_MEDIA_UNAVAILABLE");
  }
  assert.equal(state({ data: { media: [worldMedia({ supporting_evidence_id: "evidence-a" })] } }), "EVIDENCE_MEDIA_POPULATED");
  assert.equal(state({ error: new Error("first request failed") }), "EVIDENCE_MEDIA_REQUEST_FAILED");
  assert.equal(state({ data: { media: [] }, error: null }), "EVIDENCE_MEDIA_EMPTY");
});

test("World controller uses bounded replacement, lifecycle validation, and no polling", async () => {
  const controller = await read("../src/hooks/useWorldController.js");
  assert.match(controller, /version: "2"|buildWorldScopeQuery/);
  assert.match(controller, new RegExp("/api/graph-revision\\?current_revision="));
  assert.match(controller, /revision: current\.data\.graph_revision/);
  assert.match(controller, /asOf: current\.data\.as_of/);
  assert.match(controller, /isStaleWorldError\(error\)[\s\S]*loadWorld/);
  assert.match(controller, /data: payload/);
  assert.doesNotMatch(controller, /\.concat\(|setInterval|visibilitychange|addEventListener\(["']focus/);
});

test("World view renders backend collections and never creates intelligence", async () => {
  const [view, root, constants] = await Promise.all([
    read("../src/views/WorldView.jsx"),
    read("../src/SentriFaceApp.jsx"),
    read("../src/constants.js"),
  ]);
  assert.match(constants, /"world"/);
  assert.match(root, /Tabs\.Panel value="world"/);
  assert.match(view, /data\.people/);
  assert.match(view, /data\.clusters/);
  assert.match(view, /data\.relationships/);
  assert.match(view, /data\.patterns/);
  assert.match(view, /person\.analytics_state === "LOADED"/);
  assert.match(view, /Analytics not loaded/);
  assert.match(view, /explanation\.factual_factors/);
  assert.match(view, /Next authoritative page/);
  assert.doesNotMatch(view, /inferRelationship|calculateRank|calculateCluster|createRelationship|risk score|threat score|affiliation score|prediction score/i);
});

test("known graph mutations also invalidate retained World state", async () => {
  const [root, people] = await Promise.all([
    read("../src/hooks/useSentriFaceController.js"),
    read("../src/hooks/usePeopleController.js"),
  ]);
  assert.match(root, /onWorldMutation: world\.actions\.invalidateWorld/);
  assert.match(people, /invalidatePersonGraph[\s\S]*onWorldMutation\?\.\(mutation\)/);
});

test("Cluster requests bind focus, revision, as_of, effective scope, and child collection", () => {
  const request = new URL(buildWorldClusterQuery({
    clusterId: "cluster:scope-a",
    collection: "RELATIONSHIPS",
    revision: "opaque-g7",
    asOf: "2026-08-11T12:00:00+00:00",
    ranking: "SALIENCE",
    filters: { recent_activity: "LAST_30_DAYS", locations: ["Dock"], missing_location: "EXCLUDE" },
    cursor: "relationships-next",
  }), "http://localhost");
  assert.equal(request.searchParams.get("level"), "CLUSTER");
  assert.equal(request.searchParams.get("focus_type"), "CLUSTER");
  assert.equal(request.searchParams.get("focus_id"), "cluster:scope-a");
  assert.equal(request.searchParams.get("collection"), "RELATIONSHIPS");
  assert.equal(request.searchParams.get("revision"), "opaque-g7");
  assert.equal(request.searchParams.get("as_of"), "2026-08-11T12:00:00+00:00");
  assert.equal(request.searchParams.get("recent_activity"), "LAST_30_DAYS");
  assert.equal(request.searchParams.get("cursor"), "relationships-next");
});

test("Cluster contract validates members and relationships independently", () => {
  const members = requireWorldClusterContract(clusterPayload("MEMBERS"), {
    clusterId: "cluster:scope-a", collection: "MEMBERS", revision: "opaque-g7",
  });
  assert.equal(members.people.length, 1);
  assert.equal(members.relationships.length, 0);
  assert.equal(members.pagination.MEMBERS.has_more, true);
  const relationships = requireWorldClusterContract(clusterPayload("RELATIONSHIPS"), {
    clusterId: "cluster:scope-a", collection: "RELATIONSHIPS", revision: "opaque-g7",
  });
  assert.equal(relationships.people.length, 0);
  assert.equal(relationships.relationships.length, 1);
});

test("Cluster contract fails explicitly when required semantics are missing", () => {
  const missingRanking = clusterPayload("MEMBERS", {
    clusters: [clusterSummary({ ranking: undefined })],
  });
  assert.throws(() => requireWorldClusterContract(missingRanking, {
    clusterId: "cluster:scope-a", collection: "MEMBERS", revision: "opaque-g7",
  }), /Invalid World Cluster summary contract/);
  const missingLifecycle = clusterPayload("MEMBERS", {
    people: [person({ lifecycle_state: undefined })],
  });
  assert.throws(() => requireWorldClusterContract(missingLifecycle, {
    clusterId: "cluster:scope-a", collection: "MEMBERS", revision: "opaque-g7",
  }), /Invalid World person contract/);
});

test("Cluster view renders header, explanation, member states, relationships, and selection intent", async () => {
  const view = await read("../src/views/ClusterDrilldownView.jsx");
  assert.match(view, /Evidence-connected cluster/);
  assert.match(view, /Why this cluster exists/);
  assert.match(view, /summary\.evidence_basis\.evidence_count/);
  assert.match(view, /summary\.activity_summary\.member_event_contributions/);
  assert.match(view, /person\.analytics_state === "LOADED"/);
  assert.match(view, /Analytics not loaded/);
  assert.match(view, /data-lifecycle=\{person\.lifecycle_state\}/);
  assert.match(view, /ARCHIVED/);
  assert.match(view, /DELETED/);
  assert.match(view, /relationship\.directionality/);
  assert.match(view, /relationship\.evidence_type_counts/);
  assert.match(view, /relationship\.strength_basis/);
  assert.match(view, /Member navigation intent/);
  assert.match(view, /fresh World PERSON request/);
  assert.match(view, /Next authoritative page/);
  assert.doesNotMatch(view, /inferCluster|deriveMembers|dedupeRelationships|combineRelationships|person-associations|\/api\/person/);
});

test("WORLD_SCOPE cluster selection navigates through the controller rather than the preview", async () => {
  const [scopeView, controller, app] = await Promise.all([
    read("../src/views/WorldView.jsx"),
    read("../src/hooks/useWorldController.js"),
    read("../src/SentriFaceApp.jsx"),
  ]);
  assert.match(scopeView, /onClick=\{\(\) => onOpenCluster\(cluster\)\}/);
  assert.match(scopeView, /state\.cluster\?\.active[\s\S]*ClusterDrilldownView/);
  assert.match(controller, /buildWorldClusterQuery/);
  assert.match(controller, /summary: current\.summary \|\| payload\.clusters\[0\]/);
  assert.match(app, /onOpenCluster=\{guarded\(actions\.openWorldCluster\)\}/);
});

test("Cluster collections retain independent loading, errors, and replacement pagination", async () => {
  const controller = await read("../src/hooks/useWorldController.js");
  assert.match(controller, /MEMBERS: emptyClusterCollection\(\)/);
  assert.match(controller, /RELATIONSHIPS: emptyClusterCollection\(\)/);
  assert.match(controller, /\[nextCollection\]: \{ data: payload, loading: false, error: null, pageNumber \}/);
  assert.match(controller, /page = state\?\.data\?\.pagination\?\.\[cluster\.collection\]/);
  assert.match(controller, /cursor: page\.next_cursor/);
  assert.doesNotMatch(controller, /\.concat\(|push\(\.\.\.payload|mergeClusterPages/);
});

test("Cluster stale revision and invalid ID close drilldown and reload WORLD_SCOPE", async () => {
  const controller = await read("../src/hooks/useWorldController.js");
  assert.equal(isInvalidWorldClusterError({ status: 404, message: "World cluster is unavailable in this revision and scope" }), true);
  assert.match(controller, /isInvalidWorldClusterError\(error\)[\s\S]*recoverStaleCluster/);
  assert.match(controller, /setWorldCluster\(emptyWorldCluster\(\{ notice: message \}\)\)/);
  assert.match(controller, /recoverStaleCluster[\s\S]*loadWorld\(\{/);
  assert.match(controller, /refreshWorldCluster[\s\S]*preserve: true/);
  assert.doesNotMatch(controller, /setInterval|visibilitychange|addEventListener\(["']focus/);
});

test("World Person requests bind canonical focus, revision, as_of, effective scope, and collection", () => {
  const request = new URL(buildWorldPersonQuery({
    personId: "person-a",
    collection: "EVENTS",
    revision: "opaque-g7",
    asOf: "2026-08-11T12:00:00+00:00",
    ranking: "RECENT_ACTIVITY",
    filters: { recent_activity: "LAST_30_DAYS", locations: ["Dock"], lifecycle: ["ACTIVE"], missing_location: "EXCLUDE" },
    cursor: "events-next",
  }), "http://localhost");
  assert.equal(request.searchParams.get("level"), "PERSON");
  assert.equal(request.searchParams.get("focus_type"), "PERSON");
  assert.equal(request.searchParams.get("focus_id"), "person-a");
  assert.equal(request.searchParams.get("collection"), "EVENTS");
  assert.equal(request.searchParams.get("revision"), "opaque-g7");
  assert.equal(request.searchParams.get("as_of"), "2026-08-11T12:00:00+00:00");
  assert.equal(request.searchParams.get("recent_activity"), "LAST_30_DAYS");
  assert.deepEqual(request.searchParams.getAll("location"), ["Dock"]);
  assert.equal(request.searchParams.get("cursor"), "events-next");
});

test("World Person contract validates focused intelligence and independent relationship and event pages", () => {
  const relationships = requireWorldPersonContract(personPayload("RELATIONSHIPS"), {
    personId: "person-a", collection: "RELATIONSHIPS", revision: "opaque-g7",
  });
  assert.equal(relationships.people[0].activity_summary.finalized_event_count, 3);
  assert.equal(relationships.people[0].cluster_memberships[0].cluster_id, "cluster:scope-a");
  assert.equal(relationships.people[1].analytics_state, "NOT_LOADED");
  assert.equal(relationships.relationships[0].directionality, "UNDIRECTED");

  const events = requireWorldPersonContract(personPayload("EVENTS"), {
    personId: "person-a", collection: "EVENTS", revision: "opaque-g7",
  });
  assert.equal(events.events[0].location, null);
  assert.equal(events.events[0].participant_summary.participants_state, "NOT_REQUESTED");
  assert.equal(events.pagination.EVENTS.truncated, true);
  assert.equal(events.pagination.EVENTS.next_cursor, "events-next");
});

test("World Person contract fails closed for missing semantics and changed canonical identity", () => {
  assert.throws(() => requireWorldPersonContract(personPayload("EVENTS", {
    people: [person({ importance_indicators: undefined })],
  }), { personId: "person-a", collection: "EVENTS", revision: "opaque-g7" }), /Invalid World person contract/);
  assert.throws(() => requireWorldPersonContract(personPayload("EVENTS", {
    people: [person({
      analytics_state: "LOADED",
      intelligence_summary: { relationship_count: undefined, relationship_evidence_count: 4 },
      activity_summary: { finalized_event_count: 3, state: "LOADED" },
    })],
  }), { personId: "person-a", collection: "EVENTS", revision: "opaque-g7" }), /Invalid loaded World person analytics contract/);
  assert.throws(() => requireWorldPersonContract(personPayload("EVENTS", {
    events: [worldEvent({ media_summary: undefined })],
  }), { personId: "person-a", collection: "EVENTS", revision: "opaque-g7" }), /Invalid World event summary contract/);
  assert.equal(isInvalidWorldPersonError({ status: 404, message: "World person is unavailable in the effective scope" }), true);
  assert.throws(() => requireWorldPersonContract(personPayload("RELATIONSHIPS", {
    people: [person({ canonical_person_id: "person-survivor", cluster_memberships: [] })],
  }), { personId: "person-a", collection: "RELATIONSHIPS", revision: "opaque-g7" }), /canonical identity changed/);
});

test("WORLD_SCOPE and CLUSTER person intents issue fresh World PERSON reads with retained origins", async () => {
  const [scopeView, clusterView, controller, app] = await Promise.all([
    read("../src/views/WorldView.jsx"),
    read("../src/views/ClusterDrilldownView.jsx"),
    read("../src/hooks/useWorldController.js"),
    read("../src/SentriFaceApp.jsx"),
  ]);
  assert.match(scopeView, /Open scoped person/);
  assert.match(scopeView, /onOpenPerson\(value\)/);
  assert.match(clusterView, /onOpenPerson\(person\)/);
  assert.match(controller, /buildWorldPersonQuery/);
  assert.match(controller, /origin: cluster\.active[\s\S]*level: "CLUSTER"[\s\S]*level: "WORLD_SCOPE"/);
  assert.match(controller, /return loadWorldPersonCollection\(\{ collection: "RELATIONSHIPS" \}\)/);
  assert.match(app, /onOpenPerson=\{guarded\(actions\.openWorldPerson\)\}/);
  assert.doesNotMatch(controller, /personSummary[\s\S]{0,220}root:/);
});

test("World Person view renders scoped header, authoritative memberships, relationships, and event intent", async () => {
  const view = await read("../src/views/WorldPersonDrilldownView.jsx");
  assert.match(view, /data-world-level="PERSON"/);
  assert.match(view, /person\.lifecycle_state/);
  assert.match(view, /person\.identity_state/);
  assert.match(view, /person\.biometric_state/);
  assert.match(view, /person\.allowed_actions/);
  assert.match(view, /person\.analytics_state === "LOADED"/);
  assert.match(view, /Scoped analytics not loaded/);
  assert.match(view, /root\.cluster_memberships/);
  assert.match(view, /revision-bound memberships/);
  assert.match(view, /not organizations or affiliations/);
  assert.match(view, /relationship\.directionality/);
  assert.match(view, /relationship\.strength_basis/);
  assert.match(view, /relationship\.evidence_type_counts/);
  assert.match(view, /Neighbor analytics/);
  assert.match(view, /event\.participant_summary\.total_count/);
  assert.match(view, /event\.evidence_summary\.total_count/);
  assert.match(view, /event\.media_summary\.total_count/);
  assert.match(view, /Location not recorded/);
  assert.match(view, /Event navigation intent/);
  assert.match(view, /fresh World EVENT request/);
  assert.match(view, /Next authoritative page/);
  assert.doesNotMatch(view, /inferCluster|deriveMembership|calculateSightings|calculateRank|dedupeRelationships|combineRelationships|\/api\/person|\/api\/observations/);
});

test("World Person collections keep independent lifecycle, replacement pagination, refresh, and stale recovery", async () => {
  const controller = await read("../src/hooks/useWorldController.js");
  assert.match(controller, /RELATIONSHIPS: emptyPersonCollection\(\)/);
  assert.match(controller, /EVENTS: emptyPersonCollection\(\)/);
  assert.match(controller, /\[nextCollection\]: \{ data: payload, loading: false, error: null, pageNumber \}/);
  assert.match(controller, /page = state\?\.data\?\.pagination\?\.\[person\.collection\]/);
  assert.match(controller, /cursor: page\.next_cursor/);
  assert.match(controller, /refreshWorldPerson[\s\S]*preserve: true/);
  assert.match(controller, /isInvalidWorldPersonError\(error\)[\s\S]*recoverStalePerson/);
  assert.match(controller, /recoverStalePerson[\s\S]*setWorldCluster\(emptyWorldCluster\(\)\)[\s\S]*loadWorld\(\{/);
  assert.match(controller, /closeWorldPerson[\s\S]*active: false/);
  assert.doesNotMatch(controller, /mergePersonPages|\.concat\(|push\(\.\.\.payload|setInterval|visibilitychange|addEventListener\(["']focus/);
});

test("World Person empty collections and totals remain backend-owned", async () => {
  const emptyRelationships = personPayload("RELATIONSHIPS", {
    relationships: [],
    people: [personPayload("RELATIONSHIPS").people[0]],
    pagination: {
      RELATIONSHIPS: page("RELATIONSHIPS", 0),
      EVENTS: { ...page("EVENTS", 3), returned_count: 0, has_more: true, truncated: true, truncation_reason: "collection_not_requested" },
    },
  });
  assert.equal(requireWorldPersonContract(emptyRelationships, {
    personId: "person-a", collection: "RELATIONSHIPS", revision: "opaque-g7",
  }).pagination.RELATIONSHIPS.total_count, 0);
  const emptyEvents = personPayload("EVENTS", {
    events: [],
    pagination: {
      RELATIONSHIPS: { ...page("RELATIONSHIPS", 1), returned_count: 0, has_more: true, truncated: true, truncation_reason: "collection_not_requested" },
      EVENTS: page("EVENTS", 0),
    },
  });
  assert.equal(requireWorldPersonContract(emptyEvents, {
    personId: "person-a", collection: "EVENTS", revision: "opaque-g7",
  }).pagination.EVENTS.total_count, 0);
  const view = await read("../src/views/WorldPersonDrilldownView.jsx");
  assert.doesNotMatch(view, /relationships\.length[^\n]*relationship_count|events\.length[^\n]*finalized_event_count|cluster_memberships\s*=|reduce\([^\n]*(events|relationships)/);
});

test("World Event requests bind event focus, revision, as_of, effective scope, and one child collection", () => {
  const request = new URL(buildWorldEventQuery({
    eventId: "event-a",
    collection: "PROVENANCE",
    revision: "opaque-g7",
    asOf: "2026-08-11T12:00:00+00:00",
    filters: { recent_activity: "LAST_30_DAYS", locations: ["Dock"], missing_location: "EXCLUDE" },
    cursor: "provenance-next",
  }), "http://localhost");
  assert.equal(request.searchParams.get("level"), "EVENT");
  assert.equal(request.searchParams.get("focus_type"), "EVENT");
  assert.equal(request.searchParams.get("focus_id"), "event-a");
  assert.equal(request.searchParams.get("collection"), "PROVENANCE");
  assert.equal(request.searchParams.get("revision"), "opaque-g7");
  assert.equal(request.searchParams.get("as_of"), "2026-08-11T12:00:00+00:00");
  assert.equal(request.searchParams.get("recent_activity"), "LAST_30_DAYS");
  assert.equal(request.searchParams.get("cursor"), "provenance-next");
});

test("World Event contract validates participants, provenance, evidence, and media independently", () => {
  const participants = requireWorldEventContract(eventPayload("PARTICIPANTS"), { eventId: "event-a", collection: "PARTICIPANTS", revision: "opaque-g7" });
  assert.deepEqual(participants.events[0].participants.map((item) => item.person_id), ["person-a", "person-b"]);
  assert.equal(participants.events[0].participant_provenance.length, 0);
  assert.equal(participants.pagination.PROVENANCE.truncation_reason, "collection_not_requested");

  const provenance = requireWorldEventContract(eventPayload("PROVENANCE"), { eventId: "event-a", collection: "PROVENANCE", revision: "opaque-g7" });
  assert.equal(provenance.events[0].participant_provenance[0].relationship_to_effective_identity, "CORRECTED_PARTICIPANT");
  assert.equal(provenance.events[0].participants.length, 0);

  const evidence = requireWorldEventContract(eventPayload("EVIDENCE"), { eventId: "event-a", collection: "EVIDENCE", revision: "opaque-g7" });
  assert.deepEqual(evidence.evidence[0].effective_endpoints, ["person-a", "person-b"]);
  assert.equal(evidence.evidence[0].media_summary.availability, "AVAILABLE");

  const media = requireWorldEventContract(eventPayload("MEDIA"), { eventId: "event-a", collection: "MEDIA", revision: "opaque-g7" });
  assert.equal(media.media[0].media_reference, "events/event-a/photo.jpg");
  assert.equal(media.evidence.length, 0);
});

test("World Event contract fails closed for missing child semantics and stale identity", () => {
  assert.throws(() => requireWorldEventContract(eventPayload("PARTICIPANTS", {
    events: [worldEvent({ participants: [{ person_id: undefined }] })],
  }), { eventId: "event-a", collection: "PARTICIPANTS", revision: "opaque-g7" }), /participant contract/);
  assert.throws(() => requireWorldEventContract(eventPayload("PROVENANCE", {
    events: [worldEvent({ participant_provenance: [{ raw_person_id: "raw", effective_person_id: "effective", correction_operation_ids: [] }] })],
  }), { eventId: "event-a", collection: "PROVENANCE", revision: "opaque-g7" }), /provenance contract/);
  assert.throws(() => requireWorldEventContract(eventPayload("EVIDENCE", {
    evidence: [worldEvidence({ effective_endpoints: undefined })],
  }), { eventId: "event-a", collection: "EVIDENCE", revision: "opaque-g7" }), /evidence contract/);
  assert.throws(() => requireWorldEventContract(eventPayload("MEDIA", {
    media: [worldMedia({ supporting_event_id: undefined })],
  }), { eventId: "event-a", collection: "MEDIA", revision: "opaque-g7" }), /media reference contract/);
  assert.equal(isInvalidWorldEventError({ status: 404, message: "World event is unavailable in the effective scope" }), true);
  assert.throws(() => requireWorldEventContract(eventPayload("PARTICIPANTS", {
    events: [worldEvent({ event_id: "event-replaced", participants: [{ person_id: "person-a" }, { person_id: "person-b" }] })],
  }), { eventId: "event-a", collection: "PARTICIPANTS", revision: "opaque-g7" }), /identity changed/);
});

test("PERSON event selection opens a fresh EVENT request and retains the PERSON origin", async () => {
  const [personView, worldView, controller, app] = await Promise.all([
    read("../src/views/WorldPersonDrilldownView.jsx"),
    read("../src/views/WorldView.jsx"),
    read("../src/hooks/useWorldController.js"),
    read("../src/SentriFaceApp.jsx"),
  ]);
  assert.match(personView, /onOpenEvent\(event\)/);
  assert.match(personView, /PERSON event summary is not reused as event detail/);
  assert.match(worldView, /state\.event\?\.active[\s\S]*WorldEventDrilldownView/);
  assert.match(controller, /buildWorldEventQuery/);
  assert.match(controller, /origin: \{[\s\S]*level: "PERSON"[\s\S]*personId: person\.personId[\s\S]*collection: person\.collection/);
  assert.match(controller, /return loadWorldEventCollection\(\{ collection: "PARTICIPANTS" \}\)/);
  assert.match(app, /onOpenEvent=\{guarded\(actions\.openWorldEvent\)\}/);
  assert.doesNotMatch(controller, /eventSummary[\s\S]{0,220}summary:/);
});

test("World Event workspace renders authoritative overview and four bounded child collections", async () => {
  const view = await read("../src/views/WorldEventDrilldownView.jsx");
  assert.match(view, /data-world-level="EVENT"/);
  assert.match(view, /Finalized observation/);
  assert.match(view, /summary\.event_id/);
  assert.match(view, /summary\.occurred_at/);
  assert.match(view, /Location not recorded/);
  assert.match(view, /summary\.participant_summary\.total_count/);
  assert.match(view, /summary\.participant_summary\.provenance_total_count/);
  assert.match(view, /summary\.evidence_summary\.total_count/);
  assert.match(view, /summary\.media_summary\.total_count/);
  assert.match(view, /Participants.*PARTICIPANTS/);
  assert.match(view, /Provenance.*PROVENANCE/);
  assert.match(view, /Evidence.*EVIDENCE/);
  assert.match(view, /Media.*MEDIA/);
  assert.match(view, /Backend-returned effective canonical participant/);
  assert.match(view, /Raw → effective/);
  assert.match(view, /relationship_to_effective_identity/);
  assert.match(view, /item\.effective_endpoints/);
  assert.match(view, /value\.raw_endpoints/);
  assert.match(view, /item\.media_summary\.availability/);
  assert.match(view, /mediaUrl\(item\.media_reference\)/);
  assert.match(view, /Open authoritative evidence/);
  assert.match(view, /Inspect event media/);
  assert.match(view, /WorldMediaPreview/);
  assert.match(view, /Next authoritative page/);
  assert.doesNotMatch(view, /deriveParticipants|inferEvidence|profile.*photo|reconstructChain|function reconstruct|\/api\/observations|\/api\/person/);
});

test("World Event child state is independent, page-replacing, refreshable, and stale-safe", async () => {
  const controller = await read("../src/hooks/useWorldController.js");
  for (const collection of ["PARTICIPANTS", "PROVENANCE", "EVIDENCE", "MEDIA"]) {
    assert.match(controller, new RegExp(`${collection}: emptyEventCollection\\(\\)`));
  }
  assert.match(controller, /\[nextCollection\]: \{ data: payload, loading: false, error: null, pageNumber \}/);
  assert.match(controller, /page = state\?\.data\?\.pagination\?\.\[event\.collection\]/);
  assert.match(controller, /cursor: page\.next_cursor/);
  assert.match(controller, /refreshWorldEvent[\s\S]*preserve: true/);
  assert.match(controller, /isInvalidWorldEventError\(error\)[\s\S]*recoverStaleEvent/);
  assert.match(controller, /recoverStaleEvent[\s\S]*setWorldPerson\(emptyWorldPerson\(\)\)[\s\S]*setWorldCluster\(emptyWorldCluster\(\)\)[\s\S]*loadWorld\(\{/);
  assert.match(controller, /closeWorldEvent[\s\S]*active: false/);
  assert.doesNotMatch(controller, /mergeEventPages|\.concat\(|push\(\.\.\.payload|setInterval|visibilitychange|addEventListener\(["']focus/);
});

test("World Event never derives totals or treats provenance as the participant page", async () => {
  const view = await read("../src/views/WorldEventDrilldownView.jsx");
  assert.doesNotMatch(view, /participants\.length[^\n]*(total|count)|evidence\.length[^\n]*(total|count)|media\.length[^\n]*(total|count)|participant_provenance\s*=.*participants|reduce\([^\n]*(participants|evidence|media)/);
  assert.match(view, /event\?\.participants \|\| \[\]/);
  assert.match(view, /event\?\.participant_provenance \|\| \[\]/);
  assert.match(view, /participant entry supplies a canonical ID but no allowed actions/);
  assert.match(view, /PERSON navigation is therefore not enabled/);
});

test("World Evidence requests bind evidence focus, revision, as_of, effective scope, collection, and cursor", () => {
  const request = new URL(buildWorldEvidenceQuery({
    evidenceId: "evidence-a",
    collection: "MEDIA",
    revision: "opaque-g7",
    asOf: "2026-08-11T12:00:00+00:00",
    filters: { recent_activity: "LAST_30_DAYS", locations: ["Dock"], evidence_type: ["CO_OBSERVED"], missing_location: "EXCLUDE" },
    cursor: "media-next",
  }), "http://localhost");
  assert.equal(request.searchParams.get("level"), "EVIDENCE");
  assert.equal(request.searchParams.get("focus_type"), "EVIDENCE");
  assert.equal(request.searchParams.get("focus_id"), "evidence-a");
  assert.equal(request.searchParams.get("collection"), "MEDIA");
  assert.equal(request.searchParams.get("revision"), "opaque-g7");
  assert.equal(request.searchParams.get("as_of"), "2026-08-11T12:00:00+00:00");
  assert.equal(request.searchParams.get("recent_activity"), "LAST_30_DAYS");
  assert.equal(request.searchParams.get("location"), "Dock");
  assert.equal(request.searchParams.get("cursor"), "media-next");
});

test("World Evidence validates exact type, direction, raw/effective endpoints, provenance, explanation, and media", () => {
  const detail = requireWorldEvidenceContract(evidencePayload("EVIDENCE"), { evidenceId: "evidence-a", collection: "EVIDENCE", revision: "opaque-g7" });
  assert.equal(detail.evidence[0].evidence_type, "CO_OBSERVED");
  assert.equal(detail.evidence[0].directionality, "UNDIRECTED");
  assert.deepEqual(detail.evidence[0].raw_endpoints, ["person-raw", "person-b"]);
  assert.deepEqual(detail.evidence[0].effective_endpoints, ["person-a", "person-b"]);
  assert.equal(detail.evidence[0].supporting_references[0].source_entity_type, "OBSERVATION");

  const media = requireWorldEvidenceContract(evidencePayload("MEDIA"), { evidenceId: "evidence-a", collection: "MEDIA", revision: "opaque-g7" });
  assert.equal(media.media[0].supporting_evidence_id, "evidence-a");
  assert.equal(media.media[0].supporting_event_id, "event-a");

  const directed = requireWorldEvidenceContract(evidencePayload("EVIDENCE", { detail: worldEvidence({ evidence_type: "NOTE_REFERENCE", directionality: "DIRECTED", media_summary: { total_count: 0, availability: "UNAVAILABLE", retrieval: "EVIDENCE_MEDIA_COLLECTION", reason: "evidence_source_has_no_authoritative_media" } }) }), { evidenceId: "evidence-a", collection: "EVIDENCE", revision: "opaque-g7" });
  assert.equal(directed.evidence[0].directionality, "DIRECTED");
  assert.equal(directed.evidence[0].media_summary.availability, "UNAVAILABLE");
  const historical = requireWorldEvidenceContract(evidencePayload("EVIDENCE", { detail: worldEvidence({
    raw_endpoints: ["deleted-historical-person", "archived-person"],
    effective_endpoints: ["surviving-canonical-person", "archived-person"],
    provenance: { created_operation_id: "operation-a", source: "event-finalization", canonical_endpoints: ["surviving-canonical-person", "archived-person"], raw_endpoints: ["deleted-historical-person", "archived-person"] },
  }) }), { evidenceId: "evidence-a", collection: "EVIDENCE", revision: "opaque-g7" });
  assert.deepEqual(historical.evidence[0].raw_endpoints, ["deleted-historical-person", "archived-person"]);
  assert.deepEqual(historical.evidence[0].effective_endpoints, ["surviving-canonical-person", "archived-person"]);
});

test("Evidence media preserves unavailable, requested-empty, multiple, truncated, and page-replacement truth", () => {
  for (const evidenceType of ["NOTE_REFERENCE", "MANUAL_ASSOCIATION"]) {
    const detail = worldEvidence({ evidence_type: evidenceType, directionality: "DIRECTED", media_summary: { total_count: 0, availability: "UNAVAILABLE", retrieval: "EVIDENCE_MEDIA_COLLECTION", reason: "evidence_source_has_no_authoritative_media" } });
    const response = requireWorldEvidenceContract(evidencePayload("MEDIA", { detail, media: [], mediaTotal: 0 }), { evidenceId: "evidence-a", collection: "MEDIA", revision: "opaque-g7" });
    assert.equal(response.evidence[0].media_summary.availability, "UNAVAILABLE");
    assert.equal(response.pagination.MEDIA.total_count, 0);
  }
  const empty = requireWorldEvidenceContract(evidencePayload("MEDIA", { detail: worldEvidence({ media_summary: { total_count: 0, availability: "AVAILABLE", retrieval: "EVIDENCE_MEDIA_COLLECTION", reason: null } }), media: [], mediaTotal: 0 }), { evidenceId: "evidence-a", collection: "MEDIA", revision: "opaque-g7" });
  assert.equal(empty.evidence[0].media_summary.availability, "AVAILABLE");
  assert.equal(empty.media.length, 0);
  const truncated = requireWorldEvidenceContract(evidencePayload("MEDIA", { detail: worldEvidence({ media_summary: { total_count: 2, availability: "AVAILABLE", retrieval: "EVIDENCE_MEDIA_COLLECTION", reason: null } }), media: [worldMedia({ supporting_evidence_id: "evidence-a" })], mediaTotal: 2 }), { evidenceId: "evidence-a", collection: "MEDIA", revision: "opaque-g7" });
  assert.equal(truncated.pagination.MEDIA.has_more, true);
  assert.equal(truncated.pagination.MEDIA.next_cursor, "media-next");
});

test("World Evidence contract fails explicitly for missing authority, stale identity, and inconsistent media provenance", () => {
  assert.throws(() => requireWorldEvidenceContract(evidencePayload("EVIDENCE", { detail: worldEvidence({ directionality: undefined }) }), { evidenceId: "evidence-a", collection: "EVIDENCE", revision: "opaque-g7" }), /Evidence evidence contract/);
  assert.throws(() => requireWorldEvidenceContract(evidencePayload("EVIDENCE", { detail: worldEvidence({ raw_endpoints: undefined }) }), { evidenceId: "evidence-a", collection: "EVIDENCE", revision: "opaque-g7" }), /Evidence evidence contract/);
  assert.throws(() => requireWorldEvidenceContract(evidencePayload("EVIDENCE", { detail: worldEvidence({ evidence_type: "GENERIC_CONNECTION" }) }), { evidenceId: "evidence-a", collection: "EVIDENCE", revision: "opaque-g7" }), /Evidence evidence contract/);
  assert.throws(() => requireWorldEvidenceContract(evidencePayload("MEDIA", { media: [worldMedia({ supporting_evidence_id: "different-evidence" })] }), { evidenceId: "evidence-a", collection: "MEDIA", revision: "opaque-g7" }), /supporting evidence/);
  assert.throws(() => requireWorldEvidenceContract(evidencePayload("EVIDENCE", { graph_revision: "opaque-g8" }), { evidenceId: "evidence-a", collection: "EVIDENCE", revision: "opaque-g7" }), /revision does not match/);
  assert.equal(isInvalidWorldEvidenceError({ code: "WORLD_EVIDENCE_STALE" }), true);
  assert.equal(isInvalidWorldEvidenceError({ status: 404, message: "World evidence is unavailable in the effective scope" }), true);
  assert.equal(isInvalidWorldEvidenceError({ status: 400, message: "World cursor does not match the requested revision" }), true);
});

test("EVENT Evidence selection opens a fresh authoritative EVIDENCE request and retains EVENT origin", async () => {
  const [eventView, worldView, controller, evidenceController, app] = await Promise.all([
    read("../src/views/WorldEventDrilldownView.jsx"),
    read("../src/views/WorldView.jsx"),
    read("../src/hooks/useWorldController.js"),
    read("../src/hooks/useWorldEvidenceController.js"),
    read("../src/SentriFaceApp.jsx"),
  ]);
  assert.match(eventView, /onOpenEvidence\(value\)/);
  assert.match(worldView, /state\.evidence\?\.active[\s\S]*WorldEvidenceDrilldownView/);
  assert.match(evidenceController, /buildWorldEvidenceQuery/);
  assert.match(evidenceController, /origin: \{[\s\S]*level: "EVENT"[\s\S]*eventId: event\.eventId[\s\S]*collection: event\.collection/);
  assert.match(evidenceController, /return loadWorldEvidenceCollection\(\{ collection: "EVIDENCE" \}\)/);
  assert.match(app, /onOpenEvidence=\{guarded\(actions\.openWorldEvidence\)\}/);
  assert.doesNotMatch(evidenceController, /evidenceSummary[\s\S]{0,220}detail:/);
  assert.match(controller, /evidence: worldEvidence/);
});

test("World Evidence workspace renders factual type, direction, endpoints, provenance, explanation, and state distinctions", async () => {
  const view = await read("../src/views/WorldEvidenceDrilldownView.jsx");
  assert.match(view, /data-world-level="EVIDENCE"/);
  assert.match(view, /evidence\.evidence_type/);
  assert.match(view, /evidence\.directionality/);
  assert.match(view, /Raw endpoints/);
  assert.match(view, /Current effective endpoints/);
  assert.match(view, /evidence\.raw_endpoints/);
  assert.match(view, /evidence\.effective_endpoints/);
  assert.match(view, /evidence\.provenance\.created_operation_id/);
  assert.match(view, /supporting_references\.map/);
  assert.match(view, /explanation\.factual_factors/);
  assert.match(view, /explanation\.limitations/);
  assert.match(view, /No supporting media for this evidence type/);
  assert.match(view, /The collection is not requested until opened/);
  assert.match(view, /No supporting media returned/);
  assert.match(view, /The media collection was requested and is empty/);
  assert.doesNotMatch(view, /likely close|suspicious|risk|affiliation|inferEndpoint|resolveCanonical|reconstructChain|deriveEvidence/);
});

test("Evidence and Event media share inspection infrastructure while keeping origins explicit", async () => {
  const [eventView, evidenceView, preview] = await Promise.all([
    read("../src/views/WorldEventDrilldownView.jsx"),
    read("../src/views/WorldEvidenceDrilldownView.jsx"),
    read("../src/components/WorldMediaPreview.jsx"),
  ]);
  assert.match(eventView, /origin=\{\{ type: "EVENT", eventId: summary\.event_id \}\}/);
  assert.match(evidenceView, /origin=\{\{ type: "EVIDENCE", evidenceId: detail\.evidence_id/);
  assert.match(preview, /Opened from Event/);
  assert.match(preview, /Opened as supporting media for Evidence/);
  assert.match(preview, /mediaUrl\(item\.media_reference\)/);
  assert.match(preview, /Media preview unavailable/);
  assert.match(preview, /does not run recognition or create World identity, evidence, participant, or relationship state/);
  assert.doesNotMatch(preview, /recognize\(|apiPost|apiPut|apiDelete|new WebSocket|EventSource/);
});

test("World Evidence collections replace pages independently, refresh manually, recover stale state, and never poll", async () => {
  const hook = await read("../src/hooks/useWorldEvidenceController.js");
  assert.match(hook, /EVIDENCE: emptyEvidenceCollection\(\)/);
  assert.match(hook, /MEDIA: emptyEvidenceCollection\(\)/);
  assert.match(hook, /\[nextCollection\]: \{ data: payload, loading: false, error: null, pageNumber \}/);
  assert.match(hook, /page = collectionState\?\.data\?\.pagination\?\.\[current\.collection\]/);
  assert.match(hook, /cursor: page\.next_cursor/);
  assert.match(hook, /refreshWorldEvidence[\s\S]*preserve: true/);
  assert.match(hook, /isInvalidWorldEvidenceError\(error\)[\s\S]*resetWorldEvidence[\s\S]*onStale/);
  assert.match(hook, /apiGet\(buildWorldEvidenceQuery/);
  assert.doesNotMatch(hook, /\.concat\(|push\(\.\.\.payload|setInterval|setTimeout|visibilitychange|addEventListener\(["']focus|WebSocket|EventSource/);
});

test("World Evidence UI never calculates endpoints, provenance, evidence, or media totals from loaded pages", async () => {
  const [view, hook] = await Promise.all([
    read("../src/views/WorldEvidenceDrilldownView.jsx"),
    read("../src/hooks/useWorldEvidenceController.js"),
  ]);
  assert.doesNotMatch(view, /media\.length\s*[+*/-]|(total|count)\s*[:=]\s*media\.length|reduce\([^\n]*(endpoint|evidence|media)|raw_endpoints\s*=|effective_endpoints\s*=|canonical_(person|endpoint)\s*=/);
  assert.doesNotMatch(hook, /media\.length[^\n]*(total|count)|mergeEvidencePages|derive|infer|resolveAlias/);
  assert.match(view, /page\.returned_count/);
  assert.match(view, /page\.total_count/);
  assert.match(view, /evidence\.media_summary\.availability/);
});
