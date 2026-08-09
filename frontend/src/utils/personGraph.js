const GRAPH_LIFECYCLE_STATES = new Set(["ACTIVE", "ARCHIVED", "DELETED", "MERGED"]);

export function requirePersonGraphContract(payload) {
  if (payload?.contract !== "sentriface.person-graph" || payload.contract_version !== 1) {
    throw new Error("Unsupported Person Graph contract");
  }
  if (!payload.graph_revision || !payload.root_person_id) {
    throw new Error("Incomplete Person Graph revision contract");
  }
  if (!Array.isArray(payload.nodes) || !Array.isArray(payload.edges)) {
    throw new Error("Incomplete Person Graph collection contract");
  }
  for (const node of payload.nodes) {
    if (
      !node?.person_id
      || !node.canonical_person_id
      || !node.display_name
      || !GRAPH_LIFECYCLE_STATES.has(node.lifecycle_status)
      || !Array.isArray(node.allowed_actions)
    ) {
      throw new Error("Invalid Person Graph node contract");
    }
  }
  for (const edge of payload.edges) {
    if (
      !edge?.edge_id
      || !edge.source_person_id
      || !edge.target_person_id
      || !Number.isFinite(Number(edge.relationship_strength))
      || !Number.isFinite(Number(edge.evidence_count))
      || !Array.isArray(edge.evidence_types)
    ) {
      throw new Error("Invalid Person Graph edge contract");
    }
  }
  return payload;
}

export function graphNodeNavigation(node) {
  const actions = Array.isArray(node?.allowed_actions) ? node.allowed_actions : [];
  const allowed = actions.includes("OPEN") || actions.includes("OPEN_CANONICAL");
  return {
    allowed,
    personId: node?.person_id || null,
    restriction: allowed
      ? null
      : `${node?.display_name || "This identity"} is restricted by the backend (${node?.lifecycle_status || "historical"}).`,
  };
}

export function graphRevisionChanged(currentRevision, serverRevision) {
  return Boolean(currentRevision && serverRevision && currentRevision !== serverRevision);
}

export function personGraphEntryMode(snapshot, personId) {
  if (
    !personId
    || snapshot?.personId !== personId
    || !snapshot?.data?.graph_revision
    || snapshot?.invalidated
  ) return "LOAD";
  return "VALIDATE";
}

export function invalidatePersonGraphSnapshot(snapshot, mutation = null) {
  return {
    ...snapshot,
    invalidated: true,
    pendingRevision: mutation?.graph_revision || null,
    loading: false,
    error: null,
  };
}
