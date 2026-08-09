import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { layoutRelationshipGraph } from "../src/utils/relationshipGraph.js";

const graph = {
  root_person_id: "A",
  nodes: [
    { person_id: "A", layout: { depth: 0 } },
    { person_id: "B", layout: { depth: 1 } },
    { person_id: "C", layout: { depth: 2 } },
  ],
  edges: [{ edge_id: "ignored", source_person_id: "A", target_person_id: "B" }],
};

test("relationship graph utility only converts backend depth bands to coordinates", () => {
  const positions = layoutRelationshipGraph(graph);
  assert.deepEqual(positions.A, { x: 50, y: 50 });
  assert.deepEqual(Object.keys(positions).sort(), ["A", "B", "C"]);
  assert.notDeepEqual(positions.B, positions.C);
});

test("edges do not determine frontend graph membership or depth", () => {
  const withoutEdges = layoutRelationshipGraph({ ...graph, edges: [] });
  const withDifferentEdges = layoutRelationshipGraph({
    ...graph,
    edges: [{ source_person_id: "C", target_person_id: "A" }],
  });
  assert.deepEqual(withoutEdges, withDifferentEdges);
});

test("frontend graph module contains no topology reconstruction", async () => {
  const source = await readFile(new URL("../src/utils/relationshipGraph.js", import.meta.url), "utf8");
  assert.doesNotMatch(source, /createRelationshipGraph|mergeRelationshipGraph|adjacency|source_person_id|target_person_id|edges\.map|edgeKey/);
  assert.match(source, /node\.layout\?\.depth/);
});
