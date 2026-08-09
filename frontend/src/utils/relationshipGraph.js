export const RELATIONSHIP_GRAPH_NODE_LIMIT = 60;

// The backend owns graph membership, topology, canonical endpoints, depth, and counts.
// This helper converts backend-provided layout bands into screen coordinates only.
export function layoutRelationshipGraph(graphReadModel) {
  const nodes = graphReadModel?.nodes || [];
  if (!nodes.length) return {};
  const rootId = graphReadModel.root_person_id;
  const levels = new Map();
  for (const node of nodes) {
    const depth = Number(node.layout?.depth || 0);
    levels.set(depth, [...(levels.get(depth) || []), node.person_id]);
  }
  const positions = {};
  for (const [depth, ids] of levels.entries()) {
    ids.forEach((personId, index) => {
      if (personId === rootId) {
        positions[personId] = { x: 50, y: 50 };
        return;
      }
      const radius = Math.min(43, 18 + Math.max(0, depth - 1) * 13);
      const angle = ((Math.PI * 2 * index) / ids.length)
        - Math.PI / 2
        + (depth % 2 ? 0 : Math.PI / Math.max(2, ids.length));
      positions[personId] = {
        x: 50 + Math.cos(angle) * radius,
        y: 50 + Math.sin(angle) * radius,
      };
    });
  }
  return positions;
}
