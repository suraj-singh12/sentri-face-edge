export const RELATIONSHIP_GRAPH_NODE_LIMIT = 60;
export const RELATIONSHIP_GRAPH_NEIGHBOR_LIMIT = 30;

export function createRelationshipGraph(centerPerson) {
  const center = normalizeGraphPerson(centerPerson);
  return {
    centerId: center?.person_id || "",
    nodes: center ? { [center.person_id]: center } : {},
    edges: {},
    limitReached: false,
  };
}

export function mergeRelationshipGraph(
  current,
  ownerPerson,
  associations,
  nodeLimit = RELATIONSHIP_GRAPH_NODE_LIMIT,
) {
  const graph = {
    centerId: current?.centerId || ownerPerson?.person_id || "",
    nodes: { ...(current?.nodes || {}) },
    edges: { ...(current?.edges || {}) },
    limitReached: Boolean(current?.limitReached),
  };
  const owner = normalizeGraphPerson(ownerPerson);
  if (owner) graph.nodes[owner.person_id] = { ...graph.nodes[owner.person_id], ...owner };

  for (const association of associations || []) {
    const person = normalizeGraphPerson(association?.person);
    if (!owner || !person || owner.person_id === person.person_id) continue;
    if (!graph.nodes[person.person_id] && Object.keys(graph.nodes).length >= nodeLimit) {
      graph.limitReached = true;
      continue;
    }
    graph.nodes[person.person_id] = { ...graph.nodes[person.person_id], ...person };
    const sourceId = String(association.source_person_id || owner.person_id);
    const targetId = String(association.target_person_id || person.person_id);
    const endpoints = [sourceId, targetId].sort();
    if (!graph.nodes[endpoints[0]] || !graph.nodes[endpoints[1]] || endpoints[0] === endpoints[1]) continue;
    const relationshipType = association.relationship_type || "ASSOCIATED_WITH";
    const edgeKey = `${endpoints[0]}::${endpoints[1]}::${relationshipType}`;
    if (!graph.edges[edgeKey]) {
      graph.edges[edgeKey] = {
        edgeKey,
        sourceId: endpoints[0],
        targetId: endpoints[1],
        relationshipType,
        associationId: association.association_id || edgeKey,
        associationOrigin: association.association_origin || "manual",
      };
    }
  }
  return graph;
}

export function relationshipGraphCollections(graph) {
  return {
    nodes: Object.values(graph?.nodes || {}),
    edges: Object.values(graph?.edges || {}),
  };
}

export function layoutRelationshipGraph(graph) {
  const { nodes, edges } = relationshipGraphCollections(graph);
  if (!nodes.length) return {};
  const adjacency = new Map(nodes.map((node) => [node.person_id, new Set()]));
  for (const edge of edges) {
    adjacency.get(edge.sourceId)?.add(edge.targetId);
    adjacency.get(edge.targetId)?.add(edge.sourceId);
  }
  const centerId = graph.centerId && adjacency.has(graph.centerId)
    ? graph.centerId
    : nodes[0].person_id;
  const depths = new Map([[centerId, 0]]);
  const queue = [centerId];
  while (queue.length) {
    const current = queue.shift();
    for (const neighbor of adjacency.get(current) || []) {
      if (depths.has(neighbor)) continue;
      depths.set(neighbor, depths.get(current) + 1);
      queue.push(neighbor);
    }
  }
  let disconnectedDepth = Math.max(0, ...depths.values()) + 1;
  for (const node of nodes) {
    if (!depths.has(node.person_id)) depths.set(node.person_id, disconnectedDepth);
  }
  const levels = new Map();
  for (const node of nodes) {
    const depth = depths.get(node.person_id);
    levels.set(depth, [...(levels.get(depth) || []), node.person_id]);
  }
  const positions = { [centerId]: { x: 50, y: 50, depth: 0 } };
  for (const [depth, ids] of levels.entries()) {
    if (depth === 0) continue;
    const radius = Math.min(43, 18 + (depth - 1) * 13);
    ids.sort();
    ids.forEach((personId, index) => {
      const angle = ((Math.PI * 2 * index) / ids.length) - Math.PI / 2 + (depth % 2 ? 0 : Math.PI / Math.max(2, ids.length));
      positions[personId] = {
        x: 50 + Math.cos(angle) * radius,
        y: 50 + Math.sin(angle) * radius,
        depth,
      };
    });
  }
  return positions;
}

function normalizeGraphPerson(person) {
  if (!person?.person_id || !person?.name) return null;
  return {
    ...person,
    person_id: String(person.person_id),
    name: String(person.name),
    is_placeholder: Boolean(person.is_placeholder || person.enrollment_status === "placeholder"),
    archived: Boolean(person.archived || person.deleted_at),
  };
}
