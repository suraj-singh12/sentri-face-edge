import { Box, Button, Grid, Group, Image, Paper, Stack } from "@mantine/core";
import { IconTrash, IconUserCheck, IconUserPlus } from "@tabler/icons-react";

import { RecognitionFollowupForm } from "../components/RecognitionFollowupForm.jsx";
import {
  BestMatchPanel,
  GalleryPanel,
  ImageFrame,
  InputImageQuality,
  LoadImagePanel,
  Metrics,
  Surface,
} from "../components/Shared.jsx";
import { MATCH_TEXT_THRESHOLDS } from "../constants.js";
import { hasCertainMatch, mediaUrl } from "../utils.js";

export function RecognizeView({
  recognizeFileRef,
  recognition,
  recognitionGallery,
  recognitionGalleryImage,
  recognitionAccepted,
  recognitionFollowup,
  recognitionFollowupDone,
  onRecognizeFile,
  onLoadAnother,
  onAccept,
  onNew,
  onClear,
  onGallery,
  onGalleryImage,
  onGalleryBack,
  onFollowupChange,
  onFollowupSubmit,
  onFollowupClear,
}) {
  const topMostMatch = recognition?.face?.matches?.[0] || null;
  const isExistingPerson = topMostMatch?.score > MATCH_TEXT_THRESHOLDS.newPerson;
  const shouldFadeNewPerson = hasCertainMatch(topMostMatch);

  return (
    <>
      <input ref={recognizeFileRef} className="hidden-file" type="file" accept="image/*" onChange={onRecognizeFile} />
      <Paper withBorder radius="md" p="md">
        <Stack gap="md">
          <Grid align="stretch" className="recognize-grid">
            <Grid.Col span={{ base: 12, md: 7 }}>
              <Surface title="Input Image" subtitle={recognition?.inputPath || "Load one photo to recognize."} action={recognition?.inputPath ? (
                <Button variant="light" onClick={onLoadAnother}>Load Another</Button>
              ) : null}>
                <ImageFrame>
                  {recognition?.inputPath
                    ? <Image src={mediaUrl(recognition.inputPath)} alt="input" fit="contain" h="100%" />
                    : <LoadImagePanel onClick={onLoadAnother} />}
                </ImageFrame>
                <Box className="quality-slot">
                  {recognition?.face?.quality && <InputImageQuality quality={recognition.face.quality} />}
                </Box>
              </Surface>
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 5 }}>
              <Surface title="Best Match" subtitle={recognition?.face ? `Face ${recognition.face.index}` : "No result yet."}>
                {recognitionGallery
                  ? <GalleryPanel payload={recognitionGallery} selectedImage={recognitionGalleryImage} onImage={onGalleryImage} onBack={onGalleryBack} />
                  : <BestMatchPanel best={topMostMatch} face={recognition?.face} onGallery={onGallery} />}
              </Surface>
            </Grid.Col>
          </Grid>
          <Group grow className="action-slot">
            <Button leftSection={<IconUserCheck size={17} />} onClick={onAccept} disabled={!topMostMatch || !isExistingPerson || recognitionAccepted}>
              {topMostMatch && isExistingPerson ? `Accept as ${topMostMatch.name}` : "Accept"}
            </Button>
            <Button variant="light" leftSection={<IconUserPlus size={17} />} onClick={onNew} disabled={!recognition || recognitionAccepted || shouldFadeNewPerson}>New Person</Button>
            <Button color="red" variant="light" leftSection={<IconTrash size={17} />} onClick={onClear}>Clear</Button>
          </Group>
        </Stack>
      </Paper>
      {recognitionFollowup && (
        <RecognitionFollowupForm
          values={recognitionFollowup}
          confirmed={recognitionFollowupDone}
          onChange={onFollowupChange}
          onSubmit={onFollowupSubmit}
          onClear={onFollowupClear}
        />
      )}
      {recognition?.metrics && <Metrics metrics={recognition.metrics} />}
    </>
  );
}
