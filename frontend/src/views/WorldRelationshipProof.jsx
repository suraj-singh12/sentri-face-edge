import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Loader, Stack, Text } from "@mantine/core";
import { buildWorldRelationshipProofQuery, requireWorldRelationshipProofContract } from "../utils/world.js";
import { useWorldEvidenceController } from "../hooks/useWorldEvidenceController.js";
import { WorldEvidenceDrilldownView } from "./WorldEvidenceDrilldownView.jsx";

export function WorldRelationshipProof({ relationship, binding, apiGet, onStale, validateMedia, onOpenSource }) {
  const [page, setPage] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const getOrigin = useCallback(() => ({ binding, origin: { level: "RELATIONSHIP", relationshipId: relationship.relationship_id } }), [binding, relationship.relationship_id]);
  const evidence = useWorldEvidenceController({ apiGet, getOrigin, onStale });
  const load = useCallback(async (cursor = null, signal) => {
    setLoading(true); setError(null);
    try {
      const result = requireWorldRelationshipProofContract(await apiGet(buildWorldRelationshipProofQuery({ ...binding, relationshipId: relationship.relationship_id, cursor }), { signal, silent: true, dedupe: false, timeoutMs: 120_000 }), { relationshipId: relationship.relationship_id, revision: binding.revision });
      if (!signal?.aborted) { setPage(result); setLoading(false); }
    } catch (failure) { if (!signal?.aborted) { setError(failure); setLoading(false); } }
  }, [apiGet, binding, relationship.relationship_id]);
  useEffect(() => { const abort = new AbortController(); load(null, abort.signal); return () => abort.abort(); }, [load]);
  const run = (fn) => (...args) => Promise.resolve(fn(...args)).catch(setError);
  if (evidence.state.active) return <Stack h="100%" gap="xs">{evidence.state.detail?.supporting_references?.filter((reference) => ["OBSERVATION", "EVENT", "ENCOUNTER"].includes(reference.source_entity_type)).map((reference) => <Button key={reference.source_entity_id} size="xs" variant="light" onClick={run(() => onOpenSource(reference.source_entity_id))}>Open source Encounter</Button>)}<WorldEvidenceDrilldownView evidence={evidence.state} onBack={evidence.actions.closeWorldEvidence} onRefresh={run(evidence.actions.refreshWorldEvidence)} onCollection={run(evidence.actions.selectWorldEvidenceCollection)} onNextPage={run(evidence.actions.nextWorldEvidencePage)} onValidateMediaOrigin={validateMedia} /></Stack>;
  return <Stack gap="sm">{loading && <Loader size="sm" />}{error && <Alert color="red">{error.message}<Button size="xs" onClick={run(onStale)}>Reload World</Button></Alert>}<Text size="sm">Direct relationship · {relationship.selected_evidence_strength} selected evidence records</Text>{page?.evidence.map((item) => <Button variant="light" key={item.evidence_id} onClick={run(() => evidence.actions.openWorldEvidence(item))}>{item.evidence_type.replaceAll("_", " ")} · {item.occurred_at.slice(0, 10)}</Button>)}{page && !page.evidence.length && <Text size="sm" c="dimmed">No supporting evidence available in this snapshot.</Text>}<Button size="xs" disabled={!page?.pagination.EVIDENCE.next_cursor || loading} onClick={() => load(page.pagination.EVIDENCE.next_cursor)}>Next proof page</Button></Stack>;
}
