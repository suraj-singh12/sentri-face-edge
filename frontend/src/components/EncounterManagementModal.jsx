import { useState } from "react";
import { Button, Group, Modal, Select, Stack, Text } from "@mantine/core";

export function EncounterManagementModal({ detail, people, mode, onClose, onSave }) {
  const [action, setAction] = useState("REASSIGN");
  const [personId, setPersonId] = useState(null);
  const [targetId, setTargetId] = useState(null);
  const [decisions, setDecisions] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // This is an unsaved correction form. The server validates effective identities and pair completeness.
  const names = Object.fromEntries([...people, ...(detail.participants || [])].map((p) => [p.person_id, p.name]));
  const current = detail.participant_ids || [];
  const proposed = mode !== "participants" || !personId ? current : [...new Set(
    action === "ADD" ? [...current, personId] : action === "REMOVE" ? current.filter((id) => id !== personId)
      : current.map((id) => id === personId ? targetId || id : id),
  )].sort();
  const pairKey = (a, b) => [a, b].sort().join("|");
  const existing = Object.fromEntries((detail.relations || []).map((r) => {
    let pair = [r.first_person_id, r.second_person_id];
    if (mode === "participants" && action === "REASSIGN" && targetId) pair = pair.map((id) => id === personId ? targetId : id);
    return [pairKey(...pair), r.disposition];
  }));
  const pairs = proposed.flatMap((a, index) => proposed.slice(index + 1).map((b) => ({ a, b, key: pairKey(a, b) })));
  const valueFor = (pair) => decisions[pair.key] || existing[pair.key] || ((detail.relations || []).length === 0 && current.includes(pair.a) && current.includes(pair.b) ? "INCLUDE" : null);
  const save = async () => {
    setBusy(true); setError("");
    try {
      await onSave({
        ...(mode === "participants" ? { participant_correction: { action, person_id: personId, ...(action === "REASSIGN" ? { to_person_id: targetId } : {}) } } : {}),
        relations: pairs.map((pair) => ({ first_person_id: pair.a, second_person_id: pair.b, disposition: valueFor(pair) })),
      });
      onClose();
    } catch (failure) { setError(failure.message || "Correction failed"); }
    finally { setBusy(false); }
  };
  const activeOptions = people.filter((p) => p.lifecycle_status === "ACTIVE" && !current.includes(p.person_id)).map((p) => ({ value: p.person_id, label: p.name }));
  return <Modal opened onClose={() => !busy && onClose()} title={mode === "participants" ? "Correct Participants" : "Correct Relations"} size="lg" centered>
    <Stack gap="sm">
      <Text size="sm" c="dimmed">Current interpretation changes after Save. Original assignments and previous decisions remain in history.</Text>
      {mode === "participants" && <>
        <Select label="Correction" data={[{ value: "REASSIGN", label: "Wrong Person → correct Person" }, { value: "REMOVE", label: "Remove incorrect participant" }, { value: "ADD", label: "Add omitted participant" }]} value={action} onChange={(value) => { setAction(value); setPersonId(null); setTargetId(null); setDecisions({}); }} />
        <Select searchable label={action === "ADD" ? "Omitted Person" : "Current participant"} value={personId} onChange={(value) => { setPersonId(value); setDecisions({}); }} data={action === "ADD" ? activeOptions : current.map((id) => ({ value: id, label: names[id] || "Historical Person" }))} />
        {action === "REASSIGN" && <Select searchable label="Correct Person" value={targetId} onChange={(value) => { setTargetId(value); setDecisions({}); }} data={people.filter((p) => p.lifecycle_status === "ACTIVE" && p.person_id !== personId).map((p) => ({ value: p.person_id, label: p.name }))} />}
      </>}
      <Text fw={700}>Relations ({pairs.length})</Text>
      <Text size="xs" c="dimmed">Retained decisions are preselected. Every new pair needs an explicit choice.</Text>
      {pairs.map((pair) => <Group key={pair.key} justify="space-between" wrap="wrap">
        <Text size="sm">{names[pair.a]} · {names[pair.b]}</Text>
        <Select aria-label={`Relation ${names[pair.a]} and ${names[pair.b]}`} w={150} value={valueFor(pair)} placeholder="Choose" data={["INCLUDE", "EXCLUDE"]} onChange={(value) => setDecisions((old) => ({ ...old, [pair.key]: value }))} />
      </Group>)}
      {error && <Text c="red" role="alert">{error}</Text>}
      <Group justify="flex-end"><Button variant="default" disabled={busy} onClick={onClose}>Cancel</Button><Button loading={busy} disabled={pairs.some((pair) => !valueFor(pair)) || (mode === "participants" && (!personId || (action === "REASSIGN" && !targetId)))} onClick={save}>Save correction</Button></Group>
    </Stack>
  </Modal>;
}
