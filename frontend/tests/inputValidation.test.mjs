import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_IMAGE_FILE_BYTES,
  partitionImageFiles,
  skippedInputMessage,
} from "../src/inputValidation.js";

function browserFile(name, type, bytes) {
  const file = new Blob([Uint8Array.from(bytes)], { type });
  Object.defineProperty(file, "name", { value: name });
  return file;
}

test("mixed selections preserve valid images and aggregate invalid reasons", async () => {
  const validJpeg = browserFile("valid.jpg", "image/jpeg", [0xff, 0xd8, 0xff, 0xe0]);
  const fakeJpeg = browserFile("fake.jpg", "image/jpeg", [0x6e, 0x6f, 0x70, 0x65]);
  const wrongExtension = browserFile(
    "mismatch.jpg",
    "image/jpeg",
    [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a],
  );

  const result = await partitionImageFiles([validJpeg, fakeJpeg, wrongExtension]);

  assert.deepEqual(result.validFiles, [validJpeg]);
  assert.equal(result.rejected.length, 2);
  assert.deepEqual(result.reasons, {
    invalid_image_content: 1,
    content_type_mismatch: 1,
  });
});

test("invalid metadata, empty files, unsupported types, and unsafe sizes are rejected", async () => {
  const oversized = {
    name: "large.png",
    type: "image/png",
    size: MAX_IMAGE_FILE_BYTES + 1,
    slice() {
      throw new Error("oversized files must be rejected before being read");
    },
  };
  const result = await partitionImageFiles([
    null,
    browserFile("", "image/jpeg", [0xff, 0xd8, 0xff]),
    browserFile("empty.jpg", "image/jpeg", []),
    browserFile("notes.txt", "text/plain", [0x6e, 0x6f]),
    browserFile("wrong.png", "image/jpeg", [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    oversized,
  ]);

  assert.equal(result.validFiles.length, 0);
  assert.equal(result.rejected.length, 6);
  assert.deepEqual(result.reasons, {
    invalid_file: 1,
    invalid_name: 1,
    empty_file: 1,
    unsupported_extension: 1,
    media_type_mismatch: 1,
    file_too_large: 1,
  });
});

test("skip notifications use one clear singular or aggregate message", () => {
  assert.equal(
    skippedInputMessage(1, 0),
    "1 invalid file was skipped. No usable images were found.",
  );
  assert.equal(
    skippedInputMessage(3, 2),
    "3 invalid files were skipped. 2 valid images will continue.",
  );
});

test("an unreadable file object cannot abort validation of valid siblings", async () => {
  const hostileFile = {
    get name() {
      throw new Error("unreadable metadata");
    },
  };
  const validPng = browserFile(
    "valid.png",
    "image/png",
    [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a],
  );

  const result = await partitionImageFiles([hostileFile, validPng]);

  assert.deepEqual(result.validFiles, [validPng]);
  assert.equal(result.rejected.length, 1);
  assert.deepEqual(result.reasons, { unreadable_file: 1 });
});
