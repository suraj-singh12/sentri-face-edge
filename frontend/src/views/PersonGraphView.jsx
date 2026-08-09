import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Divider,
  Group,
  Loader,
  Paper,
  Stack,
  Text,
  ThemeIcon,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconArrowLeft,
  IconFocusCentered,
  IconRefresh,
  IconUser,
  IconZoomIn,
  IconZoomOut,
} from "@tabler/icons-react";

import { SafeImage } from "../components/Shared.jsx";
import { mediaUrl } from "../utils.js";
import {
  graphNodeNavigation,
} from "../utils/personGraph.js";
import { fitGraphCamera, layoutPersonGraph } from "../utils/personGraphLayout.js";

const MIN_ZOOM = 0.35;
const MAX_ZOOM = 4;

export function PersonGraphView({ state, onBack, onRefresh, onOpenNode }) {
  const graph = state.data;
  const svgRef = useRef(null);
  const dragRef = useRef(null);
  const layout = useMemo(
    () => layoutPersonGraph(graph?.nodes || [], graph?.root_person_id),
    [graph?.nodes, graph?.root_person_id],
  );
  const [camera, setCamera] = useState(() => fitGraphCamera(layout));
  const [selected, setSelected] = useState(null);
  const [hovered, setHovered] = useState(null);

  useEffect(() => {
    setCamera(fitGraphCamera(layout));
    setSelected(null);
    setHovered(null);
  }, [graph?.graph_revision, graph?.root_person_id, layout.height, layout.width]);

  const zoom = layout.width / camera.width;
  const inspect = hovered || selected;
  const rootNode = graph?.nodes?.find((node) => node.person_id === graph.root_person_id);

  const zoomAt = (factor, clientX, clientY) => {
    const bounds = svgRef.current?.getBoundingClientRect();
    if (!bounds?.width || !bounds?.height) return;
    setCamera((current) => {
      const currentZoom = layout.width / current.width;
      const nextZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, currentZoom * factor));
      const nextWidth = layout.width / nextZoom;
      const nextHeight = nextWidth * (bounds.height / bounds.width);
      const ratioX = (clientX - bounds.left) / bounds.width;
      const ratioY = (clientY - bounds.top) / bounds.height;
      const anchorX = current.x + ratioX * current.width;
      const anchorY = current.y + ratioY * current.height;
      return {
        x: anchorX - ratioX * nextWidth,
        y: anchorY - ratioY * nextHeight,
        width: nextWidth,
        height: nextHeight,
      };
    });
  };

  const zoomFromCenter = (factor) => {
    const bounds = svgRef.current?.getBoundingClientRect();
    if (bounds) zoomAt(factor, bounds.left + bounds.width / 2, bounds.top + bounds.height / 2);
  };

  const beginPan = (event) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, camera };
  };

  const movePan = (event) => {
    const drag = dragRef.current;
    const bounds = svgRef.current?.getBoundingClientRect();
    if (!drag || drag.pointerId !== event.pointerId || !bounds?.width || !bounds?.height) return;
    setCamera({
      ...drag.camera,
      x: drag.camera.x - (event.clientX - drag.x) * (drag.camera.width / bounds.width),
      y: drag.camera.y - (event.clientY - drag.y) * (drag.camera.height / bounds.height),
    });
  };

  const endPan = (event) => {
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
  };

  if (!graph && state.loading) {
    return (
      <Stack align="center" justify="center" className="person-graph-loading">
        <Loader color="teal" />
        <Text size="sm" c="dimmed">Loading the authoritative relationship graph…</Text>
      </Stack>
    );
  }

  if (!graph) {
    return (
      <Stack className="person-graph-shell">
        <Group><Button variant="subtle" leftSection={<IconArrowLeft size={16} />} onClick={onBack}>Back to profile</Button></Group>
        <Alert color="red" title="Person Graph could not be loaded">
          {state.error?.message || "The graph contract is unavailable."}
        </Alert>
      </Stack>
    );
  }

  return (
    <Stack gap="sm" className="person-graph-shell" data-contract="sentriface.person-graph">
      <Group justify="space-between" align="flex-start" wrap="nowrap" className="person-graph-header">
        <Group gap="sm" wrap="nowrap" miw={0}>
          <ActionIcon variant="subtle" size={36} onClick={onBack} aria-label="Back to person profile">
            <IconArrowLeft size={19} />
          </ActionIcon>
          <Box miw={0}>
            <Group gap="xs" wrap="nowrap">
              <Title order={3} size="h4" truncate>{rootNode?.display_name || "Person Graph"}</Title>
              {rootNode ? <LifecycleBadge node={rootNode} /> : null}
            </Group>
            <Text size="xs" c="dimmed">
              {graph.node_count} people · {graph.edge_count} backend-provided relationships
            </Text>
          </Box>
        </Group>
        <Group gap="xs" wrap="nowrap">
          <Badge variant="outline" color="gray" tt="none">Revision {graph.graph_revision}</Badge>
          {state.loading ? <Loader size={18} /> : null}
          <Tooltip label="Refresh graph">
            <ActionIcon variant="default" size={36} onClick={onRefresh} disabled={state.loading} aria-label="Refresh Person Graph">
              <IconRefresh size={17} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label="Fit graph">
            <ActionIcon variant="default" size={36} onClick={() => setCamera(fitGraphCamera(layout))} aria-label="Fit graph">
              <IconFocusCentered size={17} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label="Zoom out">
            <ActionIcon variant="default" size={36} onClick={() => zoomFromCenter(0.82)} aria-label="Zoom out">
              <IconZoomOut size={17} />
            </ActionIcon>
          </Tooltip>
          <Text size="xs" c="dimmed" className="person-graph-zoom-label">{Math.round(zoom * 100)}%</Text>
          <Tooltip label="Zoom in">
            <ActionIcon variant="default" size={36} onClick={() => zoomFromCenter(1.22)} aria-label="Zoom in">
              <IconZoomIn size={17} />
            </ActionIcon>
          </Tooltip>
        </Group>
      </Group>

      {state.error ? (
        <Alert color="yellow" title="The last refresh failed">
          The existing graph remains visible. {state.error.message}
        </Alert>
      ) : null}

      <Box className="person-graph-workarea">
        <Box className="person-graph-stage">
          <svg
            ref={svgRef}
            className="person-graph-svg"
            viewBox={`${camera.x} ${camera.y} ${camera.width} ${camera.height}`}
            onPointerMove={movePan}
            onPointerUp={endPan}
            onPointerCancel={endPan}
            onWheel={(event) => {
              event.preventDefault();
              zoomAt(event.deltaY < 0 ? 1.12 : 0.89, event.clientX, event.clientY);
            }}
            aria-label={`Relationship graph for ${rootNode?.display_name || "selected person"}`}
          >
            <defs>
              <pattern id="person-graph-grid" width="32" height="32" patternUnits="userSpaceOnUse">
                <path d="M 32 0 L 0 0 0 32" className="person-graph-grid-line" fill="none" />
              </pattern>
            </defs>
            <rect
              x={camera.x - camera.width}
              y={camera.y - camera.height}
              width={camera.width * 3}
              height={camera.height * 3}
              fill="url(#person-graph-grid)"
              className="person-graph-pan-surface"
              onPointerDown={beginPan}
            />
            <g className="person-graph-edge-layer">
              {graph.edges.map((edge) => {
                const source = layout.positions[edge.source_person_id];
                const target = layout.positions[edge.target_person_id];
                if (!source || !target) return null;
                const strokeWidth = 1.5 + Math.min(8, Number(edge.relationship_strength)) * 0.35;
                return (
                  <g key={edge.edge_id}>
                    <line
                      x1={source.x}
                      y1={source.y}
                      x2={target.x}
                      y2={target.y}
                      className="person-graph-edge-hit"
                      onPointerEnter={() => setHovered({ type: "edge", value: edge })}
                      onPointerLeave={() => setHovered(null)}
                      onClick={() => setSelected({ type: "edge", value: edge })}
                    />
                    <line
                      x1={source.x}
                      y1={source.y}
                      x2={target.x}
                      y2={target.y}
                      strokeWidth={strokeWidth}
                      className="person-graph-edge-line"
                      data-directionality={edge.directionality}
                      data-selected={selected?.type === "edge" && selected.value.edge_id === edge.edge_id}
                      aria-hidden="true"
                    />
                  </g>
                );
              })}
            </g>
            <g className="person-graph-node-layer">
              {graph.nodes.map((node) => {
                const position = layout.positions[node.person_id];
                if (!position) return null;
                const isRoot = node.person_id === graph.root_person_id;
                const navigation = graphNodeNavigation(node);
                return (
                  <foreignObject
                    key={node.person_id}
                    x={position.x - 86}
                    y={position.y - 57}
                    width="172"
                    height="114"
                    className="person-graph-node-object"
                  >
                    <button
                      type="button"
                      className="person-graph-node"
                      data-lifecycle={node.lifecycle_status}
                      data-root={isRoot}
                      data-navigation-allowed={navigation.allowed}
                      onPointerEnter={() => setHovered({ type: "node", value: node })}
                      onPointerLeave={() => setHovered(null)}
                      onClick={() => {
                        setSelected({ type: "node", value: node });
                        if (!isRoot) onOpenNode(node);
                      }}
                      aria-label={navigation.allowed
                        ? `Open graph for ${node.display_name}`
                        : navigation.restriction}
                    >
                      <SafeImage
                        src={node.representative_media_reference ? mediaUrl(node.representative_media_reference) : ""}
                        alt=""
                        className="person-graph-node-image"
                        fallback={(
                          <ThemeIcon size={44} radius="xl" color="gray" variant="light">
                            <IconUser size={23} />
                          </ThemeIcon>
                        )}
                      />
                      <span className="person-graph-node-copy">
                        <Text component="span" size="xs" fw={800}>{node.display_name}</Text>
                        <Text component="span" size="10px" c="dimmed">{node.biometric_status}</Text>
                        <Text component="span" size="10px" c={node.lifecycle_status === "ACTIVE" ? "teal.4" : "orange.4"}>
                          {node.lifecycle_status} · {node.state_indicator}
                        </Text>
                      </span>
                    </button>
                  </foreignObject>
                );
              })}
            </g>
          </svg>
          {!graph.edge_count ? (
            <Paper withBorder p="sm" className="person-graph-empty-note">
              <Text fw={700} size="sm">No stored relationships</Text>
              <Text size="xs" c="dimmed">The selected identity is shown, but the backend returned no relationship edges.</Text>
            </Paper>
          ) : null}
          <Text size="10px" c="dimmed" className="person-graph-pan-hint">Drag to pan · Scroll to zoom · Select an edge for evidence</Text>
        </Box>
        <Paper withBorder radius="md" className="person-graph-inspector">
          <GraphInspector item={inspect} rootPersonId={graph.root_person_id} />
        </Paper>
      </Box>
    </Stack>
  );
}

function GraphInspector({ item, rootPersonId }) {
  if (!item) {
    return (
      <Stack gap="xs">
        <Text fw={800}>Graph details</Text>
        <Text size="sm" c="dimmed">Hover over a person or relationship. Select an edge to keep its evidence summary here.</Text>
      </Stack>
    );
  }
  if (item.type === "node") {
    const node = item.value;
    const intelligence = node.summary_intelligence || {};
    return (
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap">
          <Text fw={800} truncate>{node.display_name}</Text>
          <LifecycleBadge node={node} />
        </Group>
        <Text size="xs" c="dimmed">{node.person_id === rootPersonId ? "Selected identity" : "Connected identity"}</Text>
        <Divider />
        <InspectorRow label="Biometric state" value={node.biometric_status} />
        <InspectorRow label="Record state" value={node.state_indicator} />
        <InspectorRow label="Sightings" value={intelligence.observation_count ?? "—"} />
        <InspectorRow label="Frequency" value={intelligence.frequency_label || "—"} />
        <InspectorRow label="Last seen" value={formatGraphDate(intelligence.last_seen_at)} />
        <Text size="xs" c="dimmed">Available actions are supplied by the backend: {node.allowed_actions.join(", ") || "none"}.</Text>
      </Stack>
    );
  }
  const edge = item.value;
  const provenance = edge.provenance_summary || {};
  return (
    <Stack gap="sm">
      <Box>
        <Text fw={800}>Relationship evidence</Text>
        <Text size="xs" c="dimmed">{edge.relationship_type_summary}</Text>
      </Box>
      <Divider />
      <InspectorRow label="Strength" value={`${edge.relationship_strength} · ${edge.strength_basis}`} />
      <InspectorRow label="Evidence count" value={edge.evidence_count} />
      <InspectorRow label="Evidence types" value={edge.evidence_types.map(humanizeToken).join(", ") || "—"} />
      <InspectorRow label="Direction" value={humanizeToken(edge.directionality)} />
      <InspectorRow label="First occurrence" value={formatGraphDate(edge.first_occurrence)} />
      <InspectorRow label="Last occurrence" value={formatGraphDate(edge.last_occurrence)} />
      <Divider />
      <Text size="xs" fw={700}>Provenance summary</Text>
      {Object.entries(provenance.evidence_type_counts || {}).map(([type, count]) => (
        <InspectorRow key={type} label={humanizeToken(type)} value={count} />
      ))}
      <InspectorRow label="Source records" value={provenance.source_record_count ?? "—"} />
    </Stack>
  );
}

function LifecycleBadge({ node }) {
  const color = {
    ACTIVE: "teal",
    ARCHIVED: "yellow",
    DELETED: "red",
    MERGED: "violet",
  }[node.lifecycle_status] || "gray";
  return <Badge size="xs" variant="light" color={color}>{node.lifecycle_status}</Badge>;
}

function InspectorRow({ label, value }) {
  return (
    <Group justify="space-between" gap="sm" wrap="nowrap">
      <Text size="xs" c="dimmed">{label}</Text>
      <Text size="xs" fw={700} ta="right">{value}</Text>
    </Group>
  );
}

function humanizeToken(value) {
  return String(value || "—").toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function formatGraphDate(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
}
