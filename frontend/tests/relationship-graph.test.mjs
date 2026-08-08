import assert from "node:assert/strict";
import test from "node:test";

import {
  createRelationshipGraph,
  layoutRelationshipGraph,
  mergeRelationshipGraph,
  relationshipGraphCollections,
} from "../src/utils/relationshipGraph.js";

const person = (id, extras = {}) => ({ person_id: id, name: `Person ${id}`, ...extras });
const association = (id, source, target, other, extras = {}) => ({
  association_id: id,
  source_person_id: source,
  target_person_id: target,
  relationship_type: "ASSOCIATED_WITH",
  person: other,
  ...extras,
});

test("relationship graph handles cycles and collapses duplicate undirected edges", () => {
  let graph = createRelationshipGraph(person("A"));
  graph = mergeRelationshipGraph(graph, person("A"), [
    association("ab-1", "A", "B", person("B")),
    association("ab-2", "B", "A", person("B")),
  ]);
  graph = mergeRelationshipGraph(graph, person("B"), [
    association("bc", "B", "C", person("C")),
  ]);
  graph = mergeRelationshipGraph(graph, person("C"), [
    association("ca", "C", "A", person("A")),
  ]);

  const { nodes, edges } = relationshipGraphCollections(graph);
  assert.equal(nodes.length, 3);
  assert.equal(edges.length, 3);
  assert.deepEqual(Object.keys(layoutRelationshipGraph(graph)).sort(), ["A", "B", "C"]);
});

test("relationship graph preserves placeholder state and skips missing or deleted references", () => {
  let graph = createRelationshipGraph(person("A"));
  graph = mergeRelationshipGraph(graph, person("A"), [
    association("placeholder", "A", "P", person("P", { is_placeholder: true, representative_image: "" })),
    association("missing", "A", "M", null),
    association("deleted", "A", "D", { person_id: "D" }),
  ]);

  const { nodes, edges } = relationshipGraphCollections(graph);
  assert.equal(nodes.length, 2);
  assert.equal(edges.length, 1);
  assert.equal(graph.nodes.P.is_placeholder, true);
});

test("relationship graph enforces the node limit without creating dangling edges", () => {
  const root = person("A");
  const graph = mergeRelationshipGraph(
    createRelationshipGraph(root),
    root,
    ["B", "C", "D"].map((id) => association(`a${id}`, "A", id, person(id))),
    3,
  );

  const { nodes, edges } = relationshipGraphCollections(graph);
  assert.equal(nodes.length, 3);
  assert.equal(edges.length, 2);
  assert.equal(graph.limitReached, true);
  assert.ok(edges.every((edge) => graph.nodes[edge.sourceId] && graph.nodes[edge.targetId]));
});
