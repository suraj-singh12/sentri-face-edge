import { useEffect, useState } from "react";
import { Alert, Badge, Button, Checkbox, Group, Image, Modal, Select, Stack, Text, Title } from "@mantine/core";
import { mediaUrl } from "../utils.js";
import { usePersistentState } from "../hooks/usePersistentState.js";

export function RecognitionReferences({ opened, onClose, person, data = {}, actions, canMutate, startAdding = false }) {
  const [adding, setAdding] = useState(startAdding);
  const [acknowledged, setAcknowledged] = useState(false);
  const [draft, setDraft] = useState(null);
  const [quality, setQuality] = useState("PROOF_ONLY");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [commands, setCommands] = usePersistentState("sentriface.reference.commands", {});
  useEffect(() => {
    if (opened) {
      setAdding(startAdding || Boolean(data.drafts?.length));
      setDraft(data.drafts?.[0] || null);
      setAcknowledged(false);
      setError("");
    }
  }, [opened, person.person_id]);
  const run = async (action) => {
    setBusy(true); setError("");
    try { await action(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const references = data.references || [];
  return <Modal opened={opened} onClose={() => { if (!busy) onClose(); }} title="Recognition References" size="lg" closeButtonProps={{"aria-label":"Close Recognition References"}}>
    <Stack>
      <Text>Reference Only · {data.active_count || 0} / 4 active sources</Text>
      <Text size="sm">Ordinary photographs with known date, place or occurrence belong in an Encounter. Reference Only is for a known Person when no reliable Encounter context is available. It creates no Encounter, sighting, recurrence, relationship or Event history.</Text>
      {data.has_encounter_coverage && <Text size="sm" c="dimmed">This Person already has usable recognition coverage from Encounter photos. Add a Reference Only image only when no reliable Encounter context is available and it adds useful biometric value.</Text>}
      {error && <Alert color="red">{error}</Alert>}
      {references.filter(r => r.active).length > data.active_count && <Text size="sm" c="dimmed">Legacy history contains multiple assignments for an exact image. It counts as one active source; retire each active historical assignment to free that source's slot.</Text>}
      {!adding && <Button variant="light" disabled={!canMutate || busy || data.active_count >= 4} onClick={() => { setAdding(true); setAcknowledged(false); }}>Add Reference Only</Button>}
      {adding && <Stack>
        <Text>Upload a cropped image containing only this person's face. Do not upload group or scene photographs. If this photograph represents a known occurrence, use an Encounter instead.</Text>
        <Checkbox label="No reliable Encounter context is available" checked={acknowledged} onChange={e => setAcknowledged(e.currentTarget.checked)} disabled={busy} />
        {!draft && <Button component="label" disabled={!canMutate || !acknowledged || busy || data.active_count >= 4}>
          Select cropped Reference image
          <input type="file" accept="image/*" hidden disabled={!acknowledged || busy || data.active_count >= 4}
            onChange={e => { const file=e.target.files?.[0]; e.target.value=""; if (file) run(async () => {
              const result=await actions.prepare(person.person_id,file); setDraft(result);
              setCommands(c => ({...c, [result.review_id]: crypto.randomUUID()}));
            }); }} />
        </Button>}
        {draft && <>
          <Image src={mediaUrl(draft.image_path)} h={160} fit="contain" alt="Staged Reference Only image" />
          <Text>Detected one face · quality {draft.quality}</Text>
          {String(draft.quality).toLowerCase()==="bad" && <Select label="Poor-quality Reference decision" value={quality} onChange={setQuality}
            data={[{value:"POOR_ACCEPTED",label:"Accept poor quality for recognition"},{value:"PROOF_ONLY",label:"Proof Only — excluded from recognition"}]} />}
          <Group><Button disabled={!canMutate || !acknowledged || busy} onClick={() => run(async () => {
            const id=commands[draft.review_id] || crypto.randomUUID();
            setCommands(c => ({...c, [draft.review_id]: id}));
            let result;
            try {
              result=await actions.confirm(person.person_id,draft,String(draft.quality).toLowerCase()==="bad" ? quality : "GOOD",acknowledged,id);
            } catch (e) {
              // A definitive rejected command needs a new ID after correction.
              // Keep the ID for a lost/network response so retry is exact.
              if (e.status >= 400 && e.status < 500) setCommands(c => ({...c, [draft.review_id]: crypto.randomUUID()}));
              throw e;
            }
            setDraft(null); setAdding(false);
            if (!result.created_reference_ids?.length) setError("Already present, or no new biometric value. No additional Reference slot was used.");
          })}>Confirm Reference Only</Button>
          <Button variant="default" disabled={busy} onClick={() => run(async () => {await actions.cancel(person.person_id,draft.review_id);setDraft(null);setAdding(false);})}>Cancel Reference upload</Button></Group>
        </>}
        {!draft && <Button variant="subtle" disabled={busy} onClick={() => setAdding(false)}>Back to References</Button>}
      </Stack>}
      {data.active_count >= 4 && <Alert color="yellow">Retire an existing Reference before activating another. Four active sources keep Reference Only an exceptional biometric aid, rather than a contextless photo library.</Alert>}
      {['Active References','Retired References'].map((heading,index)=><Stack key={heading}>
        <Title order={4}>{heading}</Title>
        {references.filter(r=>r.active===(index===0)).map(r=><Stack key={r.reference_id} gap="xs">
          <Group><Image src={mediaUrl(r.crop_path || r.source_image)} w={72} h={72} fit="contain" alt="Reference Only" />
            <Badge>Reference Only</Badge><Text size="sm">{r.recognition_state}</Text>
            <Button size="xs" variant="default" disabled={!canMutate || busy || (!r.active && data.active_count>=4)}
              onClick={()=>run(()=>actions.lifecycle(person.person_id,r.reference_id,!r.active,crypto.randomUUID()))}>{r.active ? 'Retire' : 'Restore Reference'}</Button></Group>
          {r.recognition_conflict && <Alert color="yellow">This Reference shares a biometric sample with another source assigned to a different Person. It remains assigned to {person.name} and occupies its slot, but the shared sample is excluded from recognition until the conflict is resolved.</Alert>}
        </Stack>)}
      </Stack>)}
    </Stack>
  </Modal>;
}
