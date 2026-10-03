// Display/progress projections of existing durable face decisions, never authority.
export const acceptedDecision = (decision) => ["ACCEPT_EXISTING_PERSON", "ACCEPT_NEW_PERSON"].includes(decision);
export const finalDecision = (decision) => acceptedDecision(decision) || decision === "EXCLUDE";
export function recognitionReviewReady(faces, decisions) {
  return faces.length > 0 && faces.every((face) => finalDecision(decisions[face.index]))
    && faces.some((face) => acceptedDecision(decisions[face.index]));
}
export function actionableQueueGroups(groups, media, planned) {
  if (planned || !media.length) return groups;
  const usable = new Set(media.filter((item) => !item.excluded && !item.finalized_encounter).map((item) => item.media_path));
  return groups.map((group) => ({ ...group, faces: group.faces.filter((face) => usable.has(face.source_image || face.image_path)) }))
    .filter((group) => group.faces.length);
}
// Completion snapshots may finish after navigation. Reconcile against the live
// selection, not the selected ID captured when the request began.
export function reconcileQueueSelection(groups, selectedId, selectedFaces) {
  const group = groups.find((item) => item.group_id === selectedId) || null;
  const live = new Set((group?.faces || []).map((face) => face.init_face_id));
  return { group, faces: selectedFaces.filter((id) => live.has(id)) };
}

// Retain the server's full staged decisions so acceptance and identity are read
// from the same review snapshot on mutation, refresh and restart/resume.
export function recognitionReviewState(review) {
  const records = Object.fromEntries((review.faces || []).map((face) => [Number(face.face_id.replace("face-", "")), face]));
  return { faceDecisions: Object.fromEntries(Object.entries(records).map(([id, face]) => [id, face.decision])), faceResolutions: records };
}
export function resolvedRecognitionPerson(record, proposals = []) {
  if (!acceptedDecision(record?.decision)) return null;
  if (record.decision === "ACCEPT_NEW_PERSON") {
    return { person_id: null, name: record.new_person_name, is_known: true, staged_new: true };
  }
  const proposal = proposals.find((item) => item.person_id === record.person_id);
  return { person_id: record.person_id, name: record.recognition_detail?.name || proposal?.name || record.person_id,
    representative_image: proposal?.representative_image, is_known: true };
}
