"""Offline regression tests for the Commons actor-photo fetcher."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import hashlib

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_marvel_photos.py"
spec = importlib.util.spec_from_file_location("qa_marvel", SCRIPT)
marvel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(marvel)

def test_actor_and_license_filters():
    assert marvel.actor_match("Robert Downey Jr", "File:Robert Downey, Jr. SDCC.jpg")
    assert not marvel.actor_match("Robert Downey Jr", "File:Someone Else.jpg")
    assert marvel.license_ok("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/")
    assert not marvel.license_ok("CC BY-NC 4.0", "https://creativecommons.org/licenses/by-nc/4.0/")

def test_candidate_rejects_poster():
    p = {"title": "File:Scarlett Johansson red carpet.jpg", "imageinfo": [{
        "mime": "image/jpeg", "width": 1600, "height": 900,
        "thumburl": "https://upload.wikimedia.org/test.jpg",
        "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}}}]}
    assert marvel.candidate("Scarlett Johansson", p)
    p["title"] = "File:Scarlett Johansson poster.jpg"
    assert marvel.candidate("Scarlett Johansson", p) is None

def test_download_pins_sha_and_rejects_tampering(tmp_path):
    import cv2
    import numpy as np
    blob = cv2.imencode(".jpg", np.full((120, 120, 3), 180, dtype=np.uint8))[1].tobytes()
    row = {"file": "chris-evans/example.jpg", "url": "https://upload.wikimedia.org/example.jpg", "sha256": ""}
    with patch.object(marvel, "request", return_value=blob):
        sha = marvel.download(row, tmp_path, 2)
    assert sha == hashlib.sha256(blob).hexdigest()
    assert marvel.download(row, tmp_path, 2) == sha
    (tmp_path / row["file"]).write_bytes(bytes([255, 216, 255]) + b"b" * 6000)
    import pytest
    with pytest.raises(ValueError, match="hash differs"):
        marvel.download(row, tmp_path, 2)

def test_verify_requires_existing_fixture(tmp_path):
    assert marvel.main(["--verify", "--out", str(tmp_path)]) == 1


def test_restore_rejects_changed_source_before_writing(tmp_path):
    import cv2
    import numpy as np
    import pytest
    blob = cv2.imencode(".jpg", np.zeros((120, 120, 3), dtype=np.uint8))[1].tobytes()
    row = {"file": "actor/photo.jpg", "url": "https://upload.wikimedia.org/a.jpg", "sha256": "0" * 64}
    with patch.object(marvel, "request", return_value=blob), pytest.raises(ValueError, match="Restored photo hash"):
        marvel.download(row, tmp_path, 2)
    assert not (tmp_path / row["file"]).exists()
    assert row["sha256"] == "0" * 64


def test_rejects_fake_image_and_escaped_path(tmp_path):
    import pytest
    assert not marvel.image_valid(b"\xff\xd8\xff" + b"x" * 6000, ".jpg")
    with pytest.raises(ValueError, match="Unsafe"):
        marvel.photo_path(tmp_path, "../outside.jpg")
