import { Badge, Box, Button, Grid, Group, Image, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconBulb, IconFolder, IconTrash, IconUserCheck, IconUserPlus } from "@tabler/icons-react";

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
  const quality = recognition?.face?.quality;

  return (
    <>
      <input ref={recognizeFileRef} className="hidden-file" type="file" accept="image/*" onChange={onRecognizeFile} />
      <Paper withBorder radius="md" p="md" className="recognize-workspace">
        <Stack gap="md">
          <Grid align="stretch" className="recognize-grid">
            <Grid.Col span={{ base: 12, md: 7 }}>
              <Surface step="1" title="Input Image" subtitle={recognition?.inputPath || "Upload or select a photo to recognize"} action={(
                <Button variant="default" leftSection={<IconFolder size={18} />} onClick={onLoadAnother}>Load Another</Button>
              )}>
                <ImageFrame>
                  {recognition?.inputPath
                    ? <Image src={mediaUrl(recognition.inputPath)} alt="input" fit="contain" h="100%" />
                    : <LoadImagePanel onClick={onLoadAnother} />}
                </ImageFrame>
                {quality && (
                  <Box className="quality-slot">                
                    <InputImageQuality quality={quality} />
                  </Box>
                )}
              </Surface>
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 5 }}>
              <Surface step="2" title="Recognition Result" subtitle="Best match from your people database">
                {recognitionGallery
                  ? <GalleryPanel payload={recognitionGallery} selectedImage={recognitionGalleryImage} onImage={onGalleryImage} onBack={onGalleryBack} />
                  : <BestMatchPanel best={topMostMatch} face={recognition?.face} selectedImage={recognitionGalleryImage} onGallery={onGallery} />}
              </Surface>
            </Grid.Col>
          </Grid>
          <Group grow className="action-slot">
            <Button className="recognize-action recognize-action--accept" leftSection={<IconUserCheck size={20} />} onClick={onAccept} disabled={!topMostMatch || !isExistingPerson || recognitionAccepted}>
              {topMostMatch && isExistingPerson ? `Accept as ${topMostMatch.name}` : "Accept"}
              <Text component="span" size="xs" fw={400}>Add this photo to this person</Text>
            </Button>
            <Button className="recognize-action recognize-action--new" variant="light" leftSection={<IconUserPlus size={20} />} onClick={onNew} disabled={!recognition || recognitionAccepted || shouldFadeNewPerson}>
              New Person
              <Text component="span" size="xs" fw={400}>Create a new person from this photo</Text>
            </Button>
            <Button className="recognize-action recognize-action--clear" color="red" variant="light" leftSection={<IconTrash size={20} />} onClick={onClear}>
              Clear
              <Text component="span" size="xs" fw={400}>Reset and try another photo</Text>
            </Button>
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
      <Group justify="center" mt="xs" className="recognize-tip">
        <ThemeIcon size="sm" variant="subtle" color="gray"><IconBulb size={15} /></ThemeIcon>
        <Text size="xs" c="dimmed">Tip: Use high quality, front-facing photos for best recognition results.</Text>
      </Group>
    </>
  );
}
