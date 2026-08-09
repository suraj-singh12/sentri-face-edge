// Layout only: node membership and the root identity arrive from the backend.
// Relationship records are deliberately not accepted, inspected, or used here.
export function layoutPersonGraph(nodes, rootPersonId) {
  const orderedNodes = Array.isArray(nodes) ? nodes : [];
  if (!orderedNodes.length) return { width: 960, height: 640, positions: {} };

  const root = orderedNodes.find((node) => node.person_id === rootPersonId) || orderedNodes[0];
  const surrounding = orderedNodes.filter((node) => node.person_id !== root.person_id);
  const rings = [];
  let cursor = 0;
  let ringIndex = 0;
  while (cursor < surrounding.length) {
    const capacity = 10 + ringIndex * 6;
    rings.push(surrounding.slice(cursor, cursor + capacity));
    cursor += capacity;
    ringIndex += 1;
  }

  const outerRadius = rings.length ? 210 + (rings.length - 1) * 170 : 0;
  const width = Math.max(960, outerRadius * 2 + 360);
  const height = Math.max(640, outerRadius * 2 + 300);
  const center = { x: width / 2, y: height / 2 };
  const positions = { [root.person_id]: center };

  rings.forEach((ring, index) => {
    const radius = 210 + index * 170;
    const offset = index % 2 ? Math.PI / Math.max(1, ring.length) : 0;
    ring.forEach((node, nodeIndex) => {
      const angle = -Math.PI / 2 + offset + (Math.PI * 2 * nodeIndex) / ring.length;
      positions[node.person_id] = {
        x: center.x + Math.cos(angle) * radius,
        y: center.y + Math.sin(angle) * radius,
      };
    });
  });

  return { width, height, positions };
}

export function fitGraphCamera(layout) {
  return { x: 0, y: 0, width: layout.width, height: layout.height };
}
