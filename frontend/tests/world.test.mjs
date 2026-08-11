import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildWorldScopeQuery,
  filtersFromEffective,
  invalidateWorldSnapshot,
  isStaleWorldError,
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
    people: [{
      canonical_person_id: "person-a",
      historical_person_ids: [],
      display_name: "A",
      lifecycle_state: "ACTIVE",
      analytics_state: "NOT_LOADED",
      allowed_actions: ["OPEN"],
      explanation: explanation(),
    }],
    clusters: [],
    relationships: [],
    patterns: [],
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
