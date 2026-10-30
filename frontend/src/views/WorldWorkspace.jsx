import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Box, SegmentedControl } from "@mantine/core";
import { WorldView } from "./WorldView.jsx";
import { WorldExploreView } from "./WorldExploreView.jsx";

export function WorldWorkspace({ apiGet, active, ...current }) {
  const [mode, setMode] = useState("current");
  const [visited, setVisited] = useState(false);
  const root = useRef(null);
  const [height, setHeight] = useState(null);
  useLayoutEffect(() => {
    if (mode !== "explore") return;
    const measure = () => setHeight(Math.max(200, window.innerHeight - root.current.getBoundingClientRect().top - 12));
    measure(); window.addEventListener("resize", measure);
    const observer = new ResizeObserver(measure); observer.observe(document.querySelector(".mantine-AppShell-main"));
    return () => { window.removeEventListener("resize", measure); observer.disconnect(); };
  }, [mode]);
  useEffect(() => {
    const revision = current.state.data?.graph_revision;
    if (mode !== "current" || !active || !visited || !revision) return;
    const abort = new AbortController();
    apiGet(`/api/graph-revision?current_revision=${encodeURIComponent(revision)}`, { signal: abort.signal, dedupe: false, silent: true }).then((result) => {
      if (!abort.signal.aborted && (result.stale || result.graph_revision !== revision)) current.onRefresh();
    }).catch((error) => { if (error.name !== "AbortError") current.onRefresh(); });
    return () => abort.abort();
  }, [mode, active, visited, apiGet, current.state.data?.graph_revision]);
  return <Box ref={root} className="world-workspace" style={mode === "explore" && height ? { height } : undefined}>
    <SegmentedControl size="xs" value={mode} data={[{ value: "current", label: "Current" }, { value: "explore", label: "Explore" }]} aria-label="World experience" onChange={(value) => { setVisited(true); setMode(value); }} />
    <Box className="world-mode" hidden={mode !== "current"}><WorldView {...current} /></Box>
    {visited && <Box className="world-mode" hidden={mode !== "explore"}><WorldExploreView apiGet={apiGet} active={active && mode === "explore"} mutationRevision={current.state.pendingRevision} /></Box>}
  </Box>;
}
