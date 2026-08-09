import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  graphNodeNavigation,
  graphRevisionChanged,
  invalidatePersonGraphSnapshot,
  personGraphEntryMode,
  requirePersonGraphContract,
} from "../src/utils/personGraph.js";
import { layoutPersonGraph } from "../src/utils/personGraphLayout.js";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

const node = (personId, values = {}) => ({
  person_id: personId,
  canonical_person_id: personId,
  display_name: `Person ${personId}`,
  lifecycle_status: "ACTIVE",
  biometric_status: "NO_FACE",
  allowed_actions: ["OPEN"],
  ...values,
});

const edge = {
  edge_id: "edge-a-b",
  source_person_id: "A",
  target_person_id: "B",
  relationship_strength: 3,
  evidence_count: 3,
  evidence_types: ["CO_OBSERVED", "NOTE_REFERENCE"],
};

test("Person Graph accepts the versioned backend contract without rebuilding it", () => {
  const payload = requirePersonGraphContract({
    contract: "sentriface.person-graph",
    contract_version: 1,
    graph_revision: "g17",
    root_person_id: "A",
    nodes: [node("A"), node("B")],
    edges: [edge],
  });
  assert.equal(payload.graph_revision, "g17");
  assert.equal(payload.edges[0], edge);
  assert.throws(() => requirePersonGraphContract({ ...payload, graph_revision: "" }));
});

test("layout uses backend nodes and root only", () => {
  const nodes = [node("A"), node("B"), node("C")];
  const first = layoutPersonGraph(nodes, "A");
  const second = layoutPersonGraph(nodes, "A");
  assert.deepEqual(first, second);
  assert.deepEqual(Object.keys(first.positions).sort(), ["A", "B", "C"]);
  assert.deepEqual(first.positions.A, { x: first.width / 2, y: first.height / 2 });
});

test("large graphs receive finite multi-ring coordinates", () => {
  const nodes = Array.from({ length: 251 }, (_, index) => node(`P${index}`));
  const layout = layoutPersonGraph(nodes, "P0");
  const points = Object.values(layout.positions);
  assert.equal(points.length, nodes.length);
  assert.ok(layout.width > 960);
  assert.ok(layout.height > 640);
  assert.ok(points.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y)));
  assert.equal(new Set(points.map((point) => `${point.x.toFixed(4)}:${point.y.toFixed(4)}`)).size, nodes.length);
});

test("node navigation follows backend allowed_actions", () => {
  assert.deepEqual(graphNodeNavigation(node("A")), {
    allowed: true,
    personId: "A",
    restriction: null,
  });
  const restricted = graphNodeNavigation(node("B", {
    lifecycle_status: "ARCHIVED",
    allowed_actions: ["VIEW_HISTORY"],
  }));
  assert.equal(restricted.allowed, false);
  assert.match(restricted.restriction, /restricted by the backend/i);
});

test("revision comparison treats tokens as opaque", () => {
  assert.equal(graphRevisionChanged("g17", "g18"), true);
  assert.equal(graphRevisionChanged("g17", "g17"), false);
  assert.equal(graphRevisionChanged(null, "g18"), false);
});

test("opening loads a graph revision and returning validates a reusable snapshot", () => {
  const cached = {
    personId: "A",
    data: { graph_revision: "opaque-one", nodes: [node("A")], edges: [] },
    active: false,
    invalidated: false,
  };
  assert.equal(personGraphEntryMode(null, "A"), "LOAD");
  assert.equal(personGraphEntryMode(cached, "A"), "VALIDATE");
  assert.equal(personGraphEntryMode(cached, "B"), "LOAD");
  assert.equal(personGraphEntryMode({ ...cached, invalidated: true }, "A"), "LOAD");
});

test("successful mutations invalidate without patching the cached graph", () => {
  const data = { graph_revision: "opaque-one", nodes: [node("A")], edges: [edge] };
  const invalidated = invalidatePersonGraphSnapshot(
    { personId: "A", data, active: false, loading: true, error: new Error("old") },
    { operation_id: "operation-1", graph_revision: "opaque-two" },
  );
  assert.equal(invalidated.invalidated, true);
  assert.equal(invalidated.pendingRevision, "opaque-two");
  assert.equal(invalidated.data, data);
  assert.equal(invalidated.loading, false);
  assert.equal(invalidated.error, null);
});

test("controller validates only at lifecycle boundaries and fully reloads changed revisions", async () => {
  const controller = await read("../src/hooks/usePeopleController.js");
  assert.match(controller, /\/api\/person-graph\?person_id=/);
  assert.match(controller, /requirePersonGraphContract/);
  assert.match(controller, /\/api\/graph-revision\?current_revision=/);
  assert.match(controller, /personGraphEntryMode\(cached, personId\)/);
  assert.match(controller, /activeView !== "people"[\s\S]*openPersonGraph\(cached\.personId\)/);
  assert.match(controller, /revision\.stale[\s\S]*loadPersonGraph\(personId\)/);
  assert.match(controller, /active: false, loading: false/);
  assert.doesNotMatch(controller, /setInterval|clearInterval|addEventListener\(["']focus|visibilitychange/);
  assert.doesNotMatch(controller, /setPersonGraph\([^;]*(\.edges|\.nodes)\s*=|patchPersonGraph|mergeGraphEdges/s);
});

test("graph-affecting operations share explicit invalidation", async () => {
  const [people, recognize, queue, root] = await Promise.all([
    read("../src/hooks/usePeopleController.js"),
    read("../src/hooks/useRecognizeController.js"),
    read("../src/hooks/useQueueController.js"),
    read("../src/hooks/useSentriFaceController.js"),
  ]);
  for (const endpoint of [
    "person-notes",
    "person-archive",
    "person-restore",
    "person-purge",
    "person-merge",
    "person-photo-move",
  ]) {
    assert.match(people, new RegExp(`${endpoint}[\\s\\S]{0,500}invalidatePersonGraph\\(`));
  }
  assert.match(recognize, /photo-review-complete[\s\S]{0,500}onGraphMutation\?\.\(result\)/);
  assert.match(queue, /queue-confirm-existing/);
  assert.match(queue, /onGraphMutation\?\.\(payload\)/);
  assert.equal((root.match(/onGraphMutation: people\.actions\.invalidatePersonGraph/g) || []).length, 2);
});

test("view renders backend edges and lifecycle without constructing topology", async () => {
  const [view, layout] = await Promise.all([
    read("../src/views/PersonGraphView.jsx"),
    read("../src/utils/personGraphLayout.js"),
  ]);
  assert.match(view, /graph\.edges\.map/);
  assert.match(view, /edge\.source_person_id/);
  assert.match(view, /edge\.target_person_id/);
  assert.match(view, /edge\.relationship_strength/);
  assert.match(view, /edge\.provenance_summary/);
  assert.match(view, /data-lifecycle=\{node\.lifecycle_status\}/);
  assert.match(view, /No stored relationships/);
  assert.doesNotMatch(layout, /\.edges|adjacency|relationship_strength|evidence_count|source_person_id|target_person_id/);
  assert.doesNotMatch(view, /createEdge|inferRelationship|calculateRelationship|person_associations/);
});
