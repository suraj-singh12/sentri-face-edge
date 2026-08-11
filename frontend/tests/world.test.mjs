import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildWorldClusterQuery,
  buildWorldScopeQuery,
  filtersFromEffective,
  invalidateWorldSnapshot,
  isInvalidWorldClusterError,
  isStaleWorldError,
  requireWorldClusterContract,
  requireWorldScopeContract,
  worldEntryMode,
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

function explanation(values = {}) {
  return {
    summary: "Measured backend fact.",
    basis_type: "PERSON_RANKING",
    factual_factors: [],
    strongest_factors: [],
    limitations: [],
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
    analytics_state: "NOT_LOADED",
    allowed_actions: ["OPEN"],
    explanation: explanation(),
    ...values,
  };
}

function payload(values = {}) {
  return {
    contract: "sentriface.world-graph",
    contract_version: 2,
    requested_detail_level: "WORLD_SCOPE",
    returned_detail_level: "WORLD_SCOPE",
    graph_revision: "opaque-g7",
    as_of: "2026-08-11T12:00:00+00:00",
    scope_totals: { people: 1, clusters: 0, relationships: 0, finalized_events: 0 },
    available_facets: {},
    effective_filters: { missing_location: "INCLUDE" },
    pagination: { PEOPLE: page("PEOPLE", 1) },
    people: [person()],
    clusters: [],
    relationships: [],
    patterns: [],
    ...values,
  };
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
  assert.match(view, /No profile API or person drilldown is opened/);
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
