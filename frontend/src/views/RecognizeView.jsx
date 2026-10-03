import { resolvedRecognitionPerson } from "../reviewState.js";
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Grid,
  Group,
  Image,
  Modal,
  Paper,
  Progress,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  TextInput,
  ThemeIcon,
} from "@mantine/core";
import {
  IconAlertTriangle,
  IconCheck,
  IconChevronDown,
  IconChevronUp,
  IconFolder,
  IconAdjustmentsHorizontal,
  IconSearch,
  IconTrash,
  IconUserCheck,
  IconUserPlus,
  IconUsers,
} from "@tabler/icons-react";

import { RecognitionFollowupForm } from "../components/RecognitionFollowupForm.jsx";
import { EncounterDetailsModal } from "../components/EncounterDetailsModal.jsx";
import { useIntentionalFormScroll } from "../hooks/useIntentionalFormScroll.js";
import { GalleryPanel, LoadImagePanel, Surface } from "../components/Shared.jsx";
import { isNewPersonSuggestion, matchDisplay, mediaUrl, qualityColor } from "../utils.js";
import { browsePeopleCandidates, PROFILE_BROWSE_MODES } from "../utils/profileBrowse.js";

const FACE_COLORS = ["#35d6d0", "#bd83ff", "#f5a623", "#59a7ff", "#f472b6", "#a3e635"];

export function RecognizeView({
  people = [],
  canAdd = false,
  recognizeFileRef,
  recognition,
  selectedFaceIndex,
  recognitionGallery,
  recognitionGalleryImage,
  recognitionAcceptedFaces,
  recognitionFaceDecisions = {},
  recognitionReviewReady = false,
  recognitionFollowup,
  recognitionFollowupDone,
  proofOnlyDuplicateCandidates = [],
  targetPerson,
  qualityOnly = true,
  onQualityOnlyChange,
  eventDraft,
  onEventChange,
  onEventConfirm,
  onRecognizeFile,
  onLoadAnother,
  onSelectFace,
  onAccept,
  onEnrollTarget,
  onNew,
  onSelectExisting,
  onSkip,
  onDiscard,
  onComplete,
  onClear,
  onGallery,
  onGalleryImage,
  onGalleryBack,
  onLoadPeopleCandidates,
  onFollowupChange,
  onFollowupSubmit,
  onUseProofOnlyDuplicate,
  onCreateAfterProofOnlyCheck,
  onFollowupClear,
  onCancelTarget,
}) {
  const faces = recognition?.faces || [];
  const selectedFace = faces.find((face) => face.index === selectedFaceIndex) || faces[0] || null;
  const [manualMatches, setManualMatches] = useState({});
  const [peoplePickerFace, setPeoplePickerFace] = useState(null);
  const [peopleLoading, setPeopleLoading] = useState(false);
  const [peopleQuery, setPeopleQuery] = useState("");
  const [peoplePickerMode, setPeoplePickerMode] = useState("biometric");
  const [peopleCandidates, setPeopleCandidates] = useState({});
  const selectedManualMatch = manualMatches[selectedFace?.index] || null;
  const selectedMatch = resolvedRecognitionPerson(recognition?.faceResolutions?.[selectedFace?.index], selectedFace?.matches)
    || selectedManualMatch || selectedFace?.matches?.[0] || null;
  const selectedAccepted = recognitionAcceptedFaces.includes(selectedFace?.index);
  const selectedIsKnown = Boolean(selectedManualMatch || (selectedFace?.decision !== "unknown" && selectedMatch?.is_known));
  const selectedIsBad = selectedFace?.quality?.status === "bad";
  const imageSrc = recognition?.inputPath ? mediaUrl(recognition.inputPath) : null;
  const imageSize = useImageSize(imageSrc);
  const [sort, setSort] = useState("index");
  const [qualityOverride, setQualityOverride] = useState(null);
  const [targetConflict, setTargetConflict] = useState(null);
  const [followupRef, scrollToFollowup] = useIntentionalFormScroll(recognitionFollowup?.identityOperationId);
  const sortedFaces = useMemo(() => [...faces].sort((left, right) => {
    if (sort === "quality") return (right.quality?.score || 0) - (left.quality?.score || 0) || left.index - right.index;
    if (sort === "confidence") return (right.box?.confidence || 0) - (left.box?.confidence || 0) || left.index - right.index;
    return left.index - right.index;
  }), [faces, sort]);
  useEffect(() => {
    setQualityOverride(null);
    setManualMatches({});
    setPeoplePickerFace(null);
    setPeopleQuery("");
    setPeopleCandidates({});
  }, [recognition?.inputPath]);

  const conflictingMatch = (face) => {
    const match = face?.matches?.[0];
    return face?.decision !== "unknown" && match?.person_id && match.person_id !== targetPerson?.person_id
      ? match
      : null;
  };
  const continueTargetEnrollment = (face, forceBadQuality = false) => {
    const conflict = conflictingMatch(face);
    if (conflict) {
      setTargetConflict({ face, conflict, forceBadQuality });
      return;
    }
    onEnrollTarget(face.index, forceBadQuality);
  };
  const requestFaceAction = (action, faceIndex) => {
    if (!canAdd) return;
    const face = faces.find((item) => item.index === faceIndex);
    if (!face) return;
    onSelectFace(faceIndex);
    if (targetPerson) {
      if (face.quality?.status === "bad") {
        setQualityOverride({ action: "target", face, selectedPerson: targetPerson });
        return;
      }
      scrollToFollowup();
      continueTargetEnrollment(face);
      return;
    }
    if (face.quality?.status === "bad") {
      setQualityOverride({ action, face, selectedPerson: manualMatches[faceIndex] || null });
      return;
    }
    scrollToFollowup();
    if (action === "accept") onAccept(faceIndex, false, manualMatches[faceIndex] || null);
    else onNew(faceIndex);
  };

  const confirmQualityOverride = (acceptForRecognition = true) => {
    if (!qualityOverride) return;
    const { action, face, selectedPerson } = qualityOverride;
    setQualityOverride(null);
    scrollToFollowup();
    if (action === "target") continueTargetEnrollment(face, acceptForRecognition);
    else if (action === "accept") onAccept(face.index, acceptForRecognition, selectedPerson || null);
    else onNew(face.index, acceptForRecognition);
  };

  const openPeoplePicker = async (faceIndex) => {
    setPeoplePickerFace(faceIndex);
    setPeopleQuery("");
    setPeoplePickerMode("biometric");
    if (peopleCandidates[faceIndex]) return;
    setPeopleLoading(true);
    try {
      const payload = await onLoadPeopleCandidates(faceIndex);
      setPeopleCandidates((current) => ({ ...current, [faceIndex]: payload.candidates || [] }));
    } finally {
      setPeopleLoading(false);
    }
  };

  const choosePerson = (person) => {
    onSelectExisting();
    setManualMatches((current) => ({
      ...current,
      [peoplePickerFace]: {
        ...person,
        classification: "manual",
        is_known: true,
        manual_selection: true,
      },
    }));
    setPeoplePickerFace(null);
    setPeopleQuery("");
    onGalleryBack();
  };

  const chooseNewPerson = () => {
    const faceIndex = peoplePickerFace;
    setManualMatches((current) => {
      const next = { ...current };
      delete next[faceIndex];
      return next;
    });
    setPeoplePickerFace(null);
    setPeopleQuery("");
    onGalleryBack();
    requestFaceAction("new", faceIndex);
  };

  return (
    <>
      <EncounterDetailsModal opened={Boolean(recognition?.faces?.length && !recognition?.encounterMetadata && !targetPerson)} values={eventDraft} people={people} onChange={onEventChange} onConfirm={onEventConfirm} />
      <input ref={recognizeFileRef} className="hidden-file" type="file" accept="image/*" onChange={onRecognizeFile} />
      {targetPerson && (
        <Alert color="blue" title={`Adding a photograph to ${targetPerson.name}`} icon={<IconUserCheck size={18} />} mb="md">
          The selected face will be added only to this existing person (ID {String(targetPerson.person_id).slice(0, 8)}). No new person will be created.
        </Alert>
      )}
      <Paper withBorder radius="md" p="md" className="recognize-workspace">
        <Stack gap="md">
          <Switch checked={qualityOnly} onChange={(event) => onQualityOnlyChange?.(event.currentTarget.checked)} label="Prefer quality photos for recognition" />
          {!qualityOnly && <Alert color="orange">Low-quality face samples may reduce recognition accuracy and may produce poorer or less reliable matches. Re-run recognition to apply this choice.</Alert>}
          <Grid align="stretch" className="recognize-grid recognize-grid--multi">
            <Grid.Col span={{ base: 12, md: 7 }}>
              <Surface
                step="1"
                title="Input Image"
                subtitle={recognition?.inputPath || "Upload or select a photo to recognize"}
                action={(
                  <Group gap="sm" wrap="nowrap">
                    {recognition && <Button variant="default" leftSection={<IconFolder size={18} />} onClick={onLoadAnother}>Load Another</Button>}
                    {recognition && <Badge size="lg" variant="outline" color={faces.length ? "gray" : "red"}>{faceCountLabel(faces.length)}</Badge>}
                  </Group>
                )}
              >
                <Box className="multi-face-image-frame">
                  {imageSrc
                    ? <AnnotatedImage src={imageSrc} faces={faces} imageSize={imageSize} selectedFaceIndex={selectedFace?.index} onSelectFace={onSelectFace} />
                    : <LoadImagePanel onClick={onLoadAnother} />}
                </Box>
                <Box className="face-quality-section">
                  <Group justify="space-between" gap="sm" wrap="nowrap">
                    <Group gap="sm">
                      <Text fw={600}>Face Quality</Text>
                      <Badge variant="light" color="gray">{faces.length} {faces.length === 1 ? "face" : "faces"}</Badge>
                    </Group>
                    {faces.length > 1 && (
                      <Select
                        size="xs"
                        w={150}
                        value={sort}
                        onChange={(value) => setSort(value || "index")}
                        data={[
                          { value: "index", label: "Face order" },
                          { value: "quality", label: "Quality" },
                          { value: "confidence", label: "Detection" },
                        ]}
                        leftSection={<IconAdjustmentsHorizontal size={14} />}
                        allowDeselect={false}
                        aria-label="Sort detected faces"
                      />
                    )}
                  </Group>
                  {faces.length ? (
                    <Box className="face-quality-scroll" role="list" aria-label="Detected face quality">
                      {sortedFaces.map((face) => (
                        <FaceQualityCard
                          key={face.index}
                          face={face}
                          src={imageSrc}
                          imageSize={imageSize}
                          selected={face.index === selectedFace?.index}
                          onClick={() => onSelectFace(face.index)}
                        />
                      ))}
                    </Box>
                  ) : recognition ? (
                    <Paper withBorder p="md" className="recognize-empty-inline">
                      <Text size="sm" c="dimmed">No faces were detected. Try a clearer, front-facing photo.</Text>
                    </Paper>
                  ) : null}
                </Box>
              </Surface>
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 5 }}>
              <Surface
                step="2"
                title="Recognition Results"
                subtitle="Best matches from your people database"
                action={recognition && <Badge size="lg" variant="light" color={faces.length ? "green" : "gray"}>{faces.length} detected</Badge>}
              >
                {recognitionGallery
                  ? <GalleryPanel payload={recognitionGallery} selectedImage={recognitionGalleryImage} onImage={onGalleryImage} onBack={onGalleryBack} />
                  : (
                    <RecognitionResults
                      faces={faces}
                      inputSrc={imageSrc}
                      imageSize={imageSize}
                      selectedFaceIndex={selectedFace?.index}
                      acceptedFaces={recognitionAcceptedFaces}
                      faceDecisions={recognitionFaceDecisions}
                      faceResolutions={recognition?.faceResolutions || {}}
                      canAdd={canAdd && !targetPerson}
                      manualMatches={manualMatches}
                      onSelectFace={onSelectFace}
                      onAccept={(faceIndex) => requestFaceAction("accept", faceIndex)}
                      onNew={(faceIndex) => requestFaceAction("new", faceIndex)}
                      onBrowse={openPeoplePicker}
                      onGallery={onGallery}
                    />
                  )}
              </Surface>
            </Grid.Col>
          </Grid>
          {targetPerson ? (
            <Group grow className="action-slot">
              <Button
                className="recognize-action recognize-action--accept"
                leftSection={<IconUserCheck size={20} />}
                onClick={() => requestFaceAction("target", selectedFace?.index)}
                disabled={!canAdd || !selectedFace || selectedAccepted}
              >
                Add Face {selectedFace ? faceNumber(selectedFace.index) : ""} to {targetPerson.name}
                <Text component="span" size="xs" fw={400}>Keep the existing person ID, notes, metadata, associations, and history</Text>
              </Button>
              <Button className="recognize-action recognize-action--clear" color="red" variant="light" leftSection={<IconTrash size={20} />} onClick={onCancelTarget}>
                Cancel
                <Text component="span" size="xs" fw={400}>Leave the placeholder unchanged</Text>
              </Button>
            </Group>
          ) : <Group grow className="action-slot">
            <Button
              className="recognize-action recognize-action--accept"
              leftSection={<IconUserCheck size={20} />}
              onClick={() => requestFaceAction("accept", selectedFace?.index)}
              disabled={!canAdd || !selectedFace || !selectedMatch || !selectedIsKnown || selectedAccepted}
            >
              {selectedMatch && selectedIsKnown ? `Accept Face ${faceNumber(selectedFace.index)}${selectedIsBad ? " Anyway" : ""}` : "Accept"}
              <Text component="span" size="xs" fw={400}>{selectedMatch && selectedIsKnown ? (selectedIsBad ? "Review the quality warning first" : `Add this photo to ${selectedMatch.name}`) : "Select a confident match"}</Text>
            </Button>
            <Button
              className="recognize-action recognize-action--new"
              variant="light"
              leftSection={<IconUserPlus size={20} />}
              onClick={() => requestFaceAction("new", selectedFace?.index)}
              disabled={!canAdd || !selectedFace || selectedAccepted}
            >
              {selectedIsBad ? "New Person Anyway" : "New Person"}
              <Text component="span" size="xs" fw={400}>{selectedFace ? (selectedIsBad ? "Review the quality warning first" : `Create a person from Face ${faceNumber(selectedFace.index)}`) : "Select a face first"}</Text>
            </Button>
            <Button
              className="recognize-action"
              variant="light"
              onClick={() => onSkip(selectedFace?.index)}
              disabled={!canAdd || !selectedFace || selectedAccepted}
            >
              Skip Face
              <Text component="span" size="xs" fw={400}>Defer this face for later review</Text>
            </Button>
            <Button className="recognize-action recognize-action--clear" color="red" variant="light" leftSection={<IconTrash size={20} />} onClick={onClear} disabled={!recognition}>
              Clear
              <Text component="span" size="xs" fw={400}>Reset and try another photo</Text>
            </Button>
          </Group>}
          {recognition && (!targetPerson || recognitionAcceptedFaces.length > 0) ? (
            <>
            {!targetPerson && <Button variant="light" color="red" disabled={!canAdd || !selectedFace || selectedAccepted}
              onClick={() => onDiscard(selectedFace.index)}>Discard Face</Button>}
            <Button
              className="recognize-complete-button"
              leftSection={<IconCheck size={20} />}
              onClick={onComplete}
              disabled={!canAdd || !recognitionReviewReady}
            >
              {targetPerson ? "Finish enrollment" : "Complete Review"}
            </Button>
            </>
          ) : null}
        </Stack>
      </Paper>
      <Modal
        opened={Boolean(qualityOverride)}
        onClose={() => setQualityOverride(null)}
        title={`Use Face ${faceNumber(qualityOverride?.face?.index)} despite quality warning?`}
        centered
      >
        <Stack gap="md">
          <Text size="sm">
            This face was marked poor quality{qualityOverride?.face?.quality?.reasons?.length
              ? ` (${qualityOverride.face.quality.reasons.map(qualityReasonLabel).join(", ")})`
              : ""}. You can continue, but future recognition may be less reliable.
          </Text>
          <Paper withBorder p="sm" className="quality-override-summary">
            <Group gap="sm" wrap="nowrap">
              <FaceCrop src={imageSrc} face={qualityOverride?.face} imageSize={imageSize} className="quality-override-thumb" />
              <Box>
                <Text fw={700}>Face {faceNumber(qualityOverride?.face?.index)}</Text>
                <Text size="xs" c="dimmed">Quality score {Math.round((qualityOverride?.face?.quality?.score || 0) * 100)}%</Text>
              </Box>
            </Group>
          </Paper>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => confirmQualityOverride(false)}>No, keep as proof only</Button>
            <Button color="orange" onClick={() => confirmQualityOverride(true)}>Yes, accept low-quality face</Button>
          </Group>
        </Stack>
      </Modal>
      <RecognitionPeoplePicker
        opened={Boolean(peoplePickerFace)}
        people={peopleCandidates[peoplePickerFace] || []}
        allPeople={people}
        mode={peoplePickerMode}
        onMode={setPeoplePickerMode}
        loading={peopleLoading}
        query={peopleQuery}
        onQuery={setPeopleQuery}
        onClose={() => setPeoplePickerFace(null)}
        onNewPerson={chooseNewPerson}
        onSelect={choosePerson}
      />
      <Modal opened={proofOnlyDuplicateCandidates.length > 0} onClose={() => {}} title="Possible existing profile" centered>
        <Stack gap="md">
          <Text size="sm">A proof-only face may match an existing Person. It was not used in normal recognition.</Text>
          {proofOnlyDuplicateCandidates.map((candidate) => (
            <Button key={candidate.person_id} variant="light" onClick={() => onUseProofOnlyDuplicate(candidate)}>Use existing {candidate.name}</Button>
          ))}
          <Button variant="default" onClick={onCreateAfterProofOnlyCheck}>Create new Person anyway</Button>
        </Stack>
      </Modal>
      <Modal
        opened={Boolean(targetConflict)}
        onClose={() => setTargetConflict(null)}
        title="This face resembles another person"
        centered
      >
        <Stack gap="md">
          <Alert color="orange" title="Review before adding">
            Recognition suggests {targetConflict?.conflict?.name || "another existing person"}, but you selected {targetPerson?.name}. SentriFace will not merge either profile.
          </Alert>
          <Text size="sm">Continue only if you are certain this photograph belongs to {targetPerson?.name}.</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setTargetConflict(null)}>Cancel</Button>
            <Button color="orange" onClick={() => {
              const pending = targetConflict;
              setTargetConflict(null);
              if (pending?.face) {
                scrollToFollowup();
                onEnrollTarget(pending.face.index, pending.forceBadQuality, true);
              }
            }}>Add to {targetPerson?.name}</Button>
          </Group>
        </Stack>
      </Modal>
      {recognitionFollowup && <Box ref={followupRef} className="followup-scroll-target recognize-followup-anchor">
        <RecognitionFollowupForm
          people={people}
          values={recognitionFollowup}
          confirmed={recognitionFollowupDone}
          onChange={onFollowupChange}
          onSubmit={onFollowupSubmit}
          onClear={onFollowupClear}
          addFaceOnly={Boolean(targetPerson)}
        />
      </Box>}
      {/* Developer metrics are retained for later diagnostics, but hidden from the operator UI. */}
    </>
  );
}

function AnnotatedImage({ src, faces, imageSize, selectedFaceIndex, onSelectFace }) {
  const width = imageSize.width || 1;
  const height = imageSize.height || 1;
  return (
    <svg className="annotated-face-image" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Input image with ${faceCountLabel(faces.length)}`}>
      <image href={src} width={width} height={height} preserveAspectRatio="xMidYMid meet" />
      {faces.map((face) => {
        const color = faceColor(face.index);
        const selected = face.index === selectedFaceIndex;
        const labelHeight = Math.max(18, height * 0.035);
        const fontSize = Math.max(12, height * 0.022);
        return (
          <g key={face.index} className="face-overlay" data-selected={selected} onClick={() => onSelectFace(face.index)}>
            <rect x={face.box.x} y={face.box.y} width={face.box.width} height={face.box.height} fill="transparent" stroke={color} strokeWidth={selected ? 4 : 2.5} rx="2" vectorEffect="non-scaling-stroke" />
            <rect x={face.box.x} y={Math.max(0, face.box.y - labelHeight)} width={Math.max(68, face.box.width * 0.58)} height={labelHeight} fill={color} rx="2" />
            <text x={face.box.x + 6} y={Math.max(labelHeight * 0.72, face.box.y - labelHeight * 0.25)} fill="#071018" fontSize={fontSize} fontWeight="700">Face {faceNumber(face.index)}</text>
          </g>
        );
      })}
    </svg>
  );
}

function FaceCrop({ src, face, imageSize, className = "" }) {
  if (!src || !face) return null;
  const width = imageSize.width || 1;
  const height = imageSize.height || 1;
  const padX = face.box.width * 0.22;
  const padY = face.box.height * 0.18;
  const x = Math.max(0, face.box.x - padX);
  const y = Math.max(0, face.box.y - padY);
  const cropWidth = Math.min(width - x, face.box.width + padX * 2);
  const cropHeight = Math.min(height - y, face.box.height + padY * 2);
  return (
    <svg className={`face-crop ${className}`} viewBox={`${x} ${y} ${Math.max(1, cropWidth)} ${Math.max(1, cropHeight)}`} role="img" aria-label={`Face ${faceNumber(face.index)}`}>
      <image href={src} width={width} height={height} preserveAspectRatio="none" />
    </svg>
  );
}

function FaceQualityCard({ face, src, imageSize, selected, onClick }) {
  const quality = face.quality || {};
  const color = qualityColor(quality.status);
  const status = quality.status === "warn" ? "Fair" : quality.status === "bad" ? "Poor" : "Good";
  const reason = qualityReasonLabel(quality.reasons?.[0]);
  return (
    <Card component="button" withBorder p="xs" className="face-quality-card" data-selected={selected} data-face-index={face.index} data-face-color={color} onClick={onClick} role="listitem">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <FaceCrop src={src} face={face} imageSize={imageSize} className="face-quality-thumb" />
        <Stack gap={4} miw={0} className="face-quality-copy">
          <Text fw={700} size="sm" style={{ color: faceColor(face.index) }}>Face {faceNumber(face.index)}</Text>
          <Group gap={6} wrap="nowrap">
            <ThemeIcon size="sm" radius="xl" color={color}>{quality.status === "bad" ? <IconAlertTriangle size={13} /> : <IconCheck size={13} />}</ThemeIcon>
            <Text size="sm" fw={600}>{status}</Text>
            <Text size="xs" c="dimmed">{Math.round((quality.score || 0) * 100)}</Text>
          </Group>
          {reason && <Badge size="xs" color={color} variant="light" className="quality-reason-badge">{reason}</Badge>}
        </Stack>
      </Group>
      <Group grow gap="xs" mt="xs">
        <QualityMeter label="Quality" value={(quality.score || 0) * 100} color={color} />
        <QualityMeter label="Detection" value={(face.box?.confidence || 0) * 100} color={(face.box?.confidence || 0) > 0.75 ? "green" : "yellow"} />
      </Group>
    </Card>
  );
}

function QualityMeter({ label, value, color }) {
  return (
    <Box>
      <Text size="10px" c="dimmed" mb={4}>{label}</Text>
      <Progress value={value} color={color} size={5} />
    </Box>
  );
}

function RecognitionResults({ faces, inputSrc, imageSize, selectedFaceIndex, acceptedFaces, faceDecisions = {}, faceResolutions = {}, canAdd, manualMatches, onSelectFace, onAccept, onNew, onBrowse, onGallery }) {
  if (!faces.length) {
    return (
      <Paper withBorder className="recognition-results-empty">
        <Text fw={700}>{inputSrc ? "No faces detected" : "No result yet"}</Text>
        <Text size="sm" c="dimmed">{inputSrc ? "Try another photo with visible faces." : "Load an image to start recognition."}</Text>
      </Paper>
    );
  }
  return (
    <Stack className="recognition-results-shell" gap={6}>
      <ScrollArea type="auto" scrollbars="y" className="recognition-results-scroll">
        <Stack gap="xs" pr="xs">
          {faces.map((face) => (
            <RecognitionFaceCard
              key={face.index}
              face={face}
              inputSrc={inputSrc}
              imageSize={imageSize}
              selected={face.index === selectedFaceIndex}
              accepted={acceptedFaces.includes(face.index)}
              reviewDecision={faceDecisions[face.index]}
              resolution={faceResolutions[face.index]}
              canAdd={canAdd}
              manualMatch={manualMatches[face.index] || null}
              onSelect={() => onSelectFace(face.index)}
              onAccept={() => onAccept(face.index)}
              onNew={() => onNew(face.index)}
              onBrowse={() => onBrowse(face.index)}
              onGallery={onGallery}
            />
          ))}
        </Stack>
      </ScrollArea>
      <Text size="xs" c="dimmed">Showing {faces.length} of {faces.length} {faces.length === 1 ? "face" : "faces"}</Text>
    </Stack>
  );
}

function RecognitionFaceCard({ face, inputSrc, imageSize, selected, accepted, reviewDecision, resolution, canAdd, manualMatch, onSelect, onAccept, onNew, onBrowse, onGallery }) {
  const automaticBest = face.matches?.[0] || null;
  const automaticKnown = face.decision !== "unknown" && automaticBest && !isNewPersonSuggestion(automaticBest);
  const resolved = resolvedRecognitionPerson(resolution, face.matches);
  const best = accepted ? resolved : manualMatch || (automaticKnown ? automaticBest : null);
  const unknown = !best;
  const display = matchDisplay(best);
  const faceLabel = `Face ${faceNumber(face.index)}`;
  const matchImage = best?.representative_image;
  return (
    <Card withBorder p="xs" className="recognition-face-card" data-selected={selected} data-face-index={face.index} style={{ "--face-color": faceColor(face.index) }}>
      <button type="button" className="recognition-face-summary" onClick={onSelect} aria-expanded={selected}>
        <Box className="recognition-face-photo">
          {matchImage && !unknown
            ? <Image src={mediaUrl(matchImage)} alt={best.name} fit="cover" h="100%" />
            : <FaceCrop src={inputSrc} face={face} imageSize={imageSize} />}
        </Box>
        <Box miw={0} className="recognition-face-identity">
          <Text size="sm" fw={700} className="recognition-face-label">{faceLabel}</Text>
          <Text fw={800} truncate>{accepted && !resolved ? "Accepted identity loading" : unknown ? "No match found" : best.name}</Text>
          <Badge size="xs" color={unknown ? "orange" : display.color} variant="light">
            {reviewDecision === "SKIP" ? "Deferred" : reviewDecision === "EXCLUDE" ? "Discarded" : accepted ? "Accepted" : unknown ? "Human review" : manualMatch ? "Selected" : display.badge}
          </Badge>
        </Box>
        {selected ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
      </button>
      {selected && (
        <Box className="recognition-face-details">
          <Group justify="space-between" align="center" gap="xs" wrap="nowrap">
            <Text size="xs" c="dimmed">{best?.staged_new ? "New Person · pending completion" : accepted && !resolved ? "Reloading saved decision" : unknown ? "No person met the recognition threshold." : `ID ${best.person_id}`}</Text>
            <Button size="compact-xs" variant="subtle" leftSection={<IconUsers size={14} />} disabled={!canAdd || accepted} onClick={onBrowse}>Browse People</Button>
          </Group>
          <Group grow mt="xs">
            {unknown ? (
              <Button size="xs" variant="light" leftSection={<IconUserPlus size={14} />} disabled={!canAdd || accepted} onClick={onNew}>Create new person</Button>
            ) : (
              <>
                <Button size="xs" variant="default" disabled={!best?.person_id} onClick={() => onGallery(best.person_id)}>View profile</Button>
                <Button size="xs" color={face.quality?.status === "bad" ? "orange" : "green"} leftSection={<IconCheck size={14} />} disabled={!canAdd || accepted} onClick={onAccept}>
                  {accepted ? "Accepted" : face.quality?.status === "bad" ? "Accept Anyway" : "Accept"}
                </Button>
              </>
            )}
          </Group>
        </Box>
      )}
    </Card>
  );
}

function RecognitionPeoplePicker({ opened, people, allPeople, mode, onMode, loading, query, onQuery, onClose, onNewPerson, onSelect }) {
  const normalizedQuery = query.trim().toLowerCase();
  const visiblePeople = browsePeopleCandidates(people, allPeople, mode).filter((person) => (
    !normalizedQuery
    || person.name?.toLowerCase().includes(normalizedQuery)
    || person.person_id?.toLowerCase().includes(normalizedQuery)
  ));
  return (
    <Modal opened={opened} onClose={onClose} title="Browse People" size="xl" centered>
      <Text size="sm" c="dimmed" mb="md">{mode === "biometric" ? "People are ordered from the closest visual match to the least similar." : "Active people without an enrolled face, ordered by name."}</Text>
      <Group align="end" mb="md">
      <TextInput
        value={query}
        onChange={(event) => onQuery(event.currentTarget.value)}
        leftSection={<IconSearch size={16} />}
        placeholder="Search people by name or ID"
        style={{ flex: 1 }}
      />
      <Select data={PROFILE_BROWSE_MODES} value={mode} onChange={(value) => onMode(value || "biometric")} aria-label="Profile type" w={250} />
      </Group>
      <ScrollArea.Autosize mah="60dvh" type="auto" offsetScrollbars>
        <SimpleGrid cols={{ base: 2, sm: 3, md: 4 }} className="queue-people-picker-grid">
          <Card component="button" withBorder radius="md" className="queue-person-picker-card queue-person-picker-new" onClick={onNewPerson}>
            <ThemeIcon size={58} radius="xl" variant="light" color="teal"><IconUserPlus size={28} /></ThemeIcon>
            <Text fw={800}>New person</Text>
            <Text size="xs" c="dimmed">Create a profile from this face</Text>
          </Card>
          {visiblePeople.map((person) => {
            const candidateDisplay = person.match?.classification === "unknown"
              ? { badge: "Weak match", color: "orange" }
              : matchDisplay(person.match);
            return (
              <Card key={person.person_id} component="button" withBorder radius="md" className="queue-person-picker-card" onClick={() => onSelect(person)}>
                <Box className="queue-person-picker-photo">
                  {person.representative_image ? (
                    <Image src={mediaUrl(person.representative_image)} alt={person.name} fit="contain" />
                  ) : (
                    <ThemeIcon size={54} radius="xl" variant="light" color="gray"><IconUsers size={27} /></ThemeIcon>
                  )}
                  {person.match && <Badge className="queue-person-picker-rank" color={candidateDisplay.color}>#{person.match.rank}</Badge>}
                </Box>
                <Group justify="space-between" wrap="nowrap" gap={6}>
                  <Text fw={800} truncate>{person.name}</Text>
                  <Badge size="xs" variant="light" color={person.match ? candidateDisplay.color : "gray"}>
                    {mode === "no_face" ? "No face enrolled" : person.match ? candidateDisplay.badge : "No references"}
                  </Badge>
                </Group>
                <Text size="xs" c="dimmed">{person.embedding_count || 0} reference photo{Number(person.embedding_count || 0) === 1 ? "" : "s"}</Text>
              </Card>
            );
          })}
        </SimpleGrid>
        {!loading && !visiblePeople.length && <Text ta="center" c="dimmed" py="xl">No existing people match this search.</Text>}
        {loading && <Text ta="center" c="dimmed" py="xl">Ranking People…</Text>}
      </ScrollArea.Autosize>
    </Modal>
  );
}

function useImageSize(src) {
  const [size, setSize] = useState({ width: 1, height: 1 });
  useEffect(() => {
    if (!src) {
      setSize({ width: 1, height: 1 });
      return undefined;
    }
    const image = new window.Image();
    image.onload = () => setSize({ width: image.naturalWidth || 1, height: image.naturalHeight || 1 });
    image.src = src;
    return () => { image.onload = null; };
  }, [src]);
  return size;
}

function faceColor(index) {
  return FACE_COLORS[(Math.max(1, index) - 1) % FACE_COLORS.length];
}

function faceNumber(index) {
  return String(index || 0).padStart(2, "0");
}

function faceCountLabel(count) {
  return `${count} ${count === 1 ? "face" : "faces"} detected`;
}

function qualityReasonLabel(reason) {
  return {
    low_detector_confidence: "Low confidence",
    face_too_small: "Too small",
    face_box_outside_image: "Partly outside",
    invalid_face_crop: "Invalid crop",
    too_blurry: "Too blurry",
    too_dark: "Too dark",
    too_bright: "Too bright",
    missing_landmarks: "Missing landmarks",
  }[reason] || String(reason || "").replaceAll("_", " ");
}
