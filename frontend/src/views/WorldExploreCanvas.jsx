import { useEffect, useMemo, useRef, useState } from "react";
import { ActionIcon, Box, Group, Text, Tooltip } from "@mantine/core";
import { IconFocusCentered, IconZoomIn, IconZoomOut } from "@tabler/icons-react";
import { fitGraphCamera, layoutPersonGraph } from "../utils/personGraphLayout.js";

export function WorldExploreCanvas({ graph, selected, onSelect, weaker }) {
  const canvasRef = useRef(null);
  const [aspect, setAspect] = useState(1.5);
  useEffect(() => { const observer = new ResizeObserver(([entry]) => { if (entry.contentRect.height > 0) setAspect(entry.contentRect.width / entry.contentRect.height); }); observer.observe(canvasRef.current); return () => observer.disconnect(); }, []);
  const root = selected?.type === "person" ? selected.value.canonical_person_id : null;
  const nodes = useMemo(() => graph.people.map((p) => ({ ...p, person_id: p.canonical_person_id })), [graph.people]);
  const layout = useMemo(() => {
    const base = layoutPersonGraph(nodes, root);
    if (nodes.length === 3) {
      const centerId = root && base.positions[root] ? root : nodes[0].person_id;
      for (const node of nodes) if (node.person_id !== centerId) base.positions[node.person_id].x += 100;
    }
    if (aspect > 1.5) {
      base.positions = Object.fromEntries(Object.entries(base.positions).map(([id, point]) => [id, { x: base.width / 2 + point.y - base.height / 2, y: base.height / 2 + point.x - base.width / 2 }]));
    }
    return base;
  }, [nodes, root, aspect > 1.5]);
  const fitted = useMemo(() => {
    const positions = Object.values(layout.positions);
    if (!positions.length) return fitGraphCamera(layout);
    const left = Math.min(...positions.map((p) => p.x)) - 85, top = Math.min(...positions.map((p) => p.y)) - 75;
    const width = Math.max(...positions.map((p) => p.x)) + 85 - left, height = Math.max(...positions.map((p) => p.y)) + 90 - top;
    const cameraWidth = Math.max(width, height * aspect), cameraHeight = cameraWidth / aspect;
    return { x: left - (cameraWidth - width) / 2, y: top - (cameraHeight - height) / 2, width: cameraWidth, height: cameraHeight };
  }, [layout, aspect]);
  const [camera, setCamera] = useState(() => fitted);
  const drag = useRef(null);
  useEffect(() => setCamera(fitted), [fitted]);
  const zoom = (factor) => setCamera((value) => {
    const width = Math.max(fitted.width / 4, Math.min(fitted.width * 2, value.width * factor));
    const height = width * value.height / value.width;
    return { x: value.x + (value.width - width) / 2, y: value.y + (value.height - height) / 2, width, height };
  });
  return <Box ref={canvasRef} className="explore-canvas">
    <Group className="explore-camera" gap="xs"><Tooltip label="Zoom in"><ActionIcon variant="default" aria-label="Zoom in" onClick={() => zoom(.8)}><IconZoomIn size={17} /></ActionIcon></Tooltip><Tooltip label="Zoom out"><ActionIcon variant="default" aria-label="Zoom out" onClick={() => zoom(1.25)}><IconZoomOut size={17} /></ActionIcon></Tooltip><Tooltip label="Fit to view"><ActionIcon variant="default" aria-label="Fit to view" onClick={() => setCamera(fitted)}><IconFocusCentered size={17} /></ActionIcon></Tooltip></Group>
    {!nodes.length ? <Text className="explore-canvas-empty" size="sm" c="dimmed">Select a discovery or cluster to explore its relationships.</Text> : <svg aria-label="World relationship canvas" role="group" viewBox={`${camera.x} ${camera.y} ${camera.width} ${camera.height}`} onWheel={(event) => zoom(event.deltaY > 0 ? 1.1 : .9)} onPointerDown={(event) => { if (event.button !== 0 || event.target.closest('[role="button"]')) return; event.currentTarget.setPointerCapture(event.pointerId); drag.current = { x: event.clientX, y: event.clientY, camera }; }} onPointerMove={(event) => { if (!drag.current) return; const bounds = event.currentTarget.getBoundingClientRect(); setCamera({ ...drag.current.camera, x: drag.current.camera.x - (event.clientX - drag.current.x) * camera.width / bounds.width, y: drag.current.camera.y - (event.clientY - drag.current.y) * camera.height / bounds.height }); }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
      {graph.relationships.filter((edge) => weaker || edge.qualifies_for_cluster).map((edge) => {
        const a = layout.positions[edge.source_person_id], b = layout.positions[edge.target_person_id];
        if (!a || !b) return null;
        const active = selected?.value?.relationship_id === edge.relationship_id;
        const choose = () => onSelect({ type: "relationship", value: edge });
        return <g key={edge.relationship_id} role="button" tabIndex={0} aria-label={`Inspect relationship, strength ${edge.selected_evidence_strength}`} onClick={choose} onKeyDown={(event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); choose(); } }} className="explore-edge" data-weak={!edge.qualifies_for_cluster} data-selected={active}><rect className="explore-edge-bounds" x={Math.min(a.x, b.x) - 8} y={Math.min(a.y, b.y) - 8} width={Math.max(16, Math.abs(b.x - a.x) + 16)} height={Math.max(16, Math.abs(b.y - a.y) + 16)} /><title>{edge.selected_evidence_strength} selected evidence records</title><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} strokeWidth={active ? 6 : Math.min(5, 1.5 + Math.log2(1 + edge.selected_evidence_strength))} /><line className="explore-edge-hit" x1={a.x} y1={a.y} x2={b.x} y2={b.y} /></g>;
      })}
      {nodes.map((person) => {
        const position = layout.positions[person.person_id];
        const choose = () => onSelect({ type: "person", value: person });
        return <g key={person.person_id} transform={`translate(${position.x},${position.y})`} role="button" tabIndex={0} aria-label={`Inspect ${person.display_name}`} onClick={choose} onKeyDown={(event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); choose(); } }} className="explore-node" data-selected={selected?.value?.canonical_person_id === person.person_id}><circle r={32} /><text textAnchor="middle" dy="5">{person.display_name.slice(0, 2).toUpperCase()}</text><text className="explore-node-label" textAnchor="middle" dy="54">{person.display_name.length > 23 ? `${person.display_name.slice(0, 22)}…` : person.display_name}</text><title>{person.display_name} · {person.lifecycle_state}</title></g>;
      })}
    </svg>}
  </Box>;
}
