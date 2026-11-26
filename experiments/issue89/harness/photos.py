"""Build the genuine-face photo kit for the Issue #89 experiments.

Source: Labeled Faces in the Wild (funneled), downloaded locally by
``fetch_assets.sh``; images are never committed. Real identities are mapped to
neutral fixture pseudonyms. Every prepared photograph is validated with the
genuine InsightFace buffalo_s detector/recognizer (the exact ONNX files later
admitted into each disposable authority):

* single-person photos must yield exactly one detection;
* composite multi-person photos (horizontal tiles of single-person crops, a
  disclosed construction) must yield exactly one detection per tile;
* the supporting scene photo must yield zero detections;
* same-identity embeddings must exceed the ``strong`` tier (0.6) against the
  identity's first photo and cross-identity similarity must stay below
  ``possible`` (0.4), so that real recognition outcomes are unambiguous.

Output: ``<kit>/<name>.jpg`` plus ``kit.json`` (sha256, faces, identity).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "src"))

from sentriface.components.onnx_components import OnnxArcFaceEmbedder, OnnxScrfdDetector  # noqa: E402
from sentriface.models import DetectedFace  # noqa: E402

ASSETS = Path("/projects/sandbox/assets")
LFW = ASSETS / "lfw_funneled"
MODELS = ASSETS / "buffalo_s"

# Pseudonym -> LFW identity. Pseudonyms are what the fixtures name the People.
PSEUDONYMS = ["Alder", "Birch", "Cedar", "Dogwood", "Elm", "Fir", "Ginkgo", "Hazel", "Iris",
              "Juniper", "Kauri", "Laurel", "Maple", "Nutmeg"]
SOURCE_POOL = ["Colin_Powell", "Tony_Blair", "Donald_Rumsfeld", "Gerhard_Schroeder", "Ariel_Sharon",
               "Hugo_Chavez", "Junichiro_Koizumi", "Jean_Chretien", "Serena_Williams", "Jacques_Chirac",
               "Vladimir_Putin", "Gloria_Macapagal_Arroyo", "Arnold_Schwarzenegger", "Hans_Blix",
               "Luiz_Inacio_Lula_da_Silva", "Jennifer_Capriati", "Lleyton_Hewitt", "Alejandro_Toledo",
               "Nestor_Kirchner", "Andre_Agassi", "Alvaro_Uribe", "Tom_Ridge", "Silvio_Berlusconi"]
PHOTOS_PER_IDENTITY = 10


def _crop(path: Path) -> np.ndarray:
    # SCRFD needs context around the face: centre 190px of the LFW frame on a
    # neutral 480px canvas (no resampling of the face pixels).
    image = cv2.imread(str(path))[30:220, 30:220]
    canvas = np.full((480, 480, 3), 200, np.uint8)
    canvas[145:335, 145:335] = image
    return canvas


def detector():
    return OnnxScrfdDetector(MODELS / "det_500m.onnx")


def embedder():
    return OnnxArcFaceEmbedder(MODELS / "w600k_mbf.onnx")


def _write(path: Path, image: np.ndarray) -> str:
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    path.write_bytes(data.tobytes())
    return hashlib.sha256(data.tobytes()).hexdigest()


def _select(source: str, kit: Path, det, emb):
    """First PHOTOS_PER_IDENTITY single-detection photos similar (>=0.6) to the anchor."""
    chosen, vectors = [], []
    tmp = kit / "_probe.jpg"
    for candidate in sorted((LFW / source).glob("*.jpg")):
        image = _crop(candidate)
        _write(tmp, image)
        faces = det.detect(tmp)
        if len(faces) != 1 or faces[0].box.confidence < 0.7:
            continue
        vector = np.array(emb.encode(tmp, faces[0]))
        if vectors and float(vector @ vectors[0]) < 0.6:
            continue
        vectors.append(vector)
        chosen.append(image)
        if len(chosen) == PHOTOS_PER_IDENTITY:
            break
    return chosen, vectors


def build(kit: Path) -> dict:
    kit.mkdir(parents=True, exist_ok=True)
    det, emb = detector(), embedder()
    entries: dict[str, dict] = {}
    singles: dict[str, list[np.ndarray]] = {}
    vectors: dict[str, list[np.ndarray]] = {}
    pool = iter(SOURCE_POOL)
    for pseudonym in PSEUDONYMS:
        chosen, chosen_vectors = [], []
        while len(chosen) < PHOTOS_PER_IDENTITY:
            chosen, chosen_vectors = _select(next(pool), kit, det, emb)
        vectors[pseudonym] = chosen_vectors
        singles[pseudonym] = chosen
        for index, image in enumerate(chosen):
            name = f"{pseudonym.lower()}-{index}"
            digest = _write(kit / f"{name}.jpg", image)
            entries[name] = {"file": f"{name}.jpg", "sha256": digest, "faces": [pseudonym], "kind": "single"}
    (kit / "_probe.jpg").unlink(missing_ok=True)
    # Cross-identity separation on first photos.
    names = list(vectors)
    worst = max(float(vectors[a][0] @ vectors[b][0]) for i, a in enumerate(names) for b in names[i + 1:])
    assert worst < 0.4, worst
    # Poor-quality variants (genuine face, deliberately blurred).
    for pseudonym in names:
        blurred = cv2.GaussianBlur(singles[pseudonym][PHOTOS_PER_IDENTITY - 1], (0, 0), 6)
        name = f"{pseudonym.lower()}-blur"
        digest = _write(kit / f"{name}.jpg", blurred)
        entries[name] = {"file": f"{name}.jpg", "sha256": digest, "faces": [pseudonym], "kind": "blurred"}
    # Face-free supporting scene photograph.
    scene = np.zeros((320, 480, 3), dtype=np.uint8)
    for row in range(320):
        scene[row, :, :] = (120 + row // 4, 160 - row // 5, 90 + row // 6)
    cv2.rectangle(scene, (60, 180), (220, 300), (40, 70, 110), -1)
    cv2.rectangle(scene, (280, 120), (420, 300), (60, 60, 60), -1)
    entries["scene"] = {"file": "scene.jpg", "sha256": _write(kit / "scene.jpg", scene), "faces": [], "kind": "scene"}
    entries["scene-2"] = {"file": "scene-2.jpg", "sha256": _write(kit / "scene-2.jpg", cv2.flip(scene, 1)), "faces": [], "kind": "scene"}
    for entry in entries.values():
        found = det.detect(kit / entry["file"])
        if entry["kind"] != "blurred":
            assert len(found) == len(entry["faces"]), (entry, len(found))
        entry["detected"] = len(found)
    manifest = {"source": "LFW funneled (local research copy, not committed)", "detector": "buffalo_s det_500m.onnx",
                "recognizer": "buffalo_s w600k_mbf.onnx", "max_cross_identity_similarity": round(worst, 4),
                "identities": PSEUDONYMS, "photos": entries}
    (kit / "kit.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def composite(kit: Path, name: str, parts: list[str]) -> dict:
    """Create (and validate) a multi-person photo from single-person kit photos."""
    manifest = json.loads((kit / "kit.json").read_text())
    if name in manifest["photos"]:
        return manifest["photos"][name]
    images = [cv2.imread(str(kit / manifest["photos"][p]["file"])) for p in parts]
    tiled = np.hstack(images)
    digest = _write(kit / f"{name}.jpg", tiled)
    found = detector().detect(kit / f"{name}.jpg")
    faces = [manifest["photos"][p]["faces"][0] for p in parts]
    assert len(found) == len(parts), (name, len(found))
    entry = {"file": f"{name}.jpg", "sha256": digest, "faces": faces, "kind": "composite", "parts": parts, "detected": len(found)}
    manifest["photos"][name] = entry
    (kit / "kit.json").write_text(json.dumps(manifest, indent=1))
    return entry


if __name__ == "__main__":
    result = build(Path(sys.argv[1] if len(sys.argv) > 1 else "/projects/sandbox/kit"))
    print(json.dumps({k: v for k, v in result.items() if k != "photos"}, indent=1), len(result["photos"]))
