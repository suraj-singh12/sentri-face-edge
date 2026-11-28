import hashlib
import json
import zipfile

from scripts.acquire_research_models import _ensure_archive, _extract_verified, acquire


def test_extract_verified_requires_exact_member_identity(tmp_path, monkeypatch):
    content = b"approved model bytes"
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("model.onnx", content)
    spec = {
        "archive": archive.name,
        "archive_url": "https://example.test/bundle.zip",
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "description": "fixture",
    }
    output = tmp_path / "out"
    output.mkdir()
    record = _extract_verified(archive, "model.onnx", spec, output)
    assert (output / "model.onnx").read_bytes() == content
    assert record["sha256"] == spec["sha256"]
    spec["sha256"] = "0" * 64
    try:
        _extract_verified(archive, "model.onnx", spec, output)
    except RuntimeError as exc:
        assert "integrity mismatch" in str(exc)
    else:
        raise AssertionError("corrupt identity accepted")


def test_acquire_writes_provenance_and_notice(tmp_path, monkeypatch):
    import scripts.acquire_research_models as acquisition

    content = b"x"
    archive = tmp_path / "buffalo_s.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("det_500m.onnx", content)
    other = tmp_path / "buffalo_l.zip"
    with zipfile.ZipFile(other, "w") as zf:
        zf.writestr("w600k_r50.onnx", content)
    sha = hashlib.sha256(content).hexdigest()
    monkeypatch.setitem(acquisition.MODELS, "det_500m.onnx", {
        "archive_url": "x", "archive": "buffalo_s.zip", "size": 1, "sha256": sha, "description": "d"
    })
    monkeypatch.setitem(acquisition.MODELS, "w600k_r50.onnx", {
        "archive_url": "x", "archive": "buffalo_l.zip", "size": 1, "sha256": sha, "description": "r"
    })
    output = tmp_path / "payload"
    provenance = acquire(tmp_path, output)
    assert len(provenance["models"]) == 2
    assert json.loads((output / "research-model-provenance.json").read_text())["contract"] == "sentriface.research-model-provenance"
    assert "non-commercial research" in (output / "THIRD-PARTY-MODEL-NOTICE.txt").read_text()


def test_acquire_replaces_cached_archive_that_fails_identity(monkeypatch, tmp_path):
    import scripts.acquire_research_models as acquisition

    content = b"approved"
    good_archive = tmp_path / "good.zip"
    with zipfile.ZipFile(good_archive, "w") as zf:
        zf.writestr("det_500m.onnx", content)
    cache = tmp_path / "cache"
    cache.mkdir()
    bad_archive = cache / "buffalo_s.zip"
    with zipfile.ZipFile(bad_archive, "w") as zf:
        zf.writestr("det_500m.onnx", b"corrupt")
    sha = hashlib.sha256(content).hexdigest()
    monkeypatch.setitem(acquisition.MODELS, "det_500m.onnx", {
        "archive_url": "redownload", "archive": "buffalo_s.zip", "size": len(content), "sha256": sha, "description": "d"
    })
    monkeypatch.setitem(acquisition.MODELS, "w600k_r50.onnx", {
        "archive_url": "unused", "archive": "buffalo_l.zip", "size": len(content), "sha256": sha, "description": "r"
    })
    with zipfile.ZipFile(cache / "buffalo_l.zip", "w") as zf:
        zf.writestr("w600k_r50.onnx", content)

    downloads = []
    def download(url, destination, member):
        downloads.append((url, member))
        destination.write_bytes(good_archive.read_bytes())
    monkeypatch.setattr(acquisition, "_download", download)

    acquire(cache, tmp_path / "payload")
    assert downloads == [("redownload", "det_500m.onnx")]
    assert (tmp_path / "payload" / "det_500m.onnx").read_bytes() == content


def test_acquire_replaces_cached_archive_that_fails_zip_integrity(monkeypatch, tmp_path):
    import scripts.acquire_research_models as acquisition

    content = b"approved"
    good_archive = tmp_path / "good.zip"
    with zipfile.ZipFile(good_archive, "w") as zf:
        zf.writestr("det_500m.onnx", content)
    cache = tmp_path / "cache"
    cache.mkdir()
    with zipfile.ZipFile(cache / "buffalo_s.zip", "w") as zf:
        zf.writestr("det_500m.onnx", b"cached")
    sha = hashlib.sha256(content).hexdigest()
    monkeypatch.setitem(acquisition.MODELS, "det_500m.onnx", {
        "archive_url": "redownload", "archive": "buffalo_s.zip", "size": len(content), "sha256": sha, "description": "d"
    })
    monkeypatch.setitem(acquisition.MODELS, "w600k_r50.onnx", {
        "archive_url": "unused", "archive": "buffalo_l.zip", "size": len(content), "sha256": sha, "description": "r"
    })
    with zipfile.ZipFile(cache / "buffalo_l.zip", "w") as zf:
        zf.writestr("w600k_r50.onnx", content)
    monkeypatch.setattr(acquisition, "_download", lambda url, destination, member: destination.write_bytes(good_archive.read_bytes()))
    real_extract = acquisition._extract_verified
    failures = []
    def fail_first_archive(archive, member, spec, output):
        if member == "det_500m.onnx" and not failures:
            failures.append(member)
            raise zipfile.BadZipFile("Bad CRC-32")
        return real_extract(archive, member, spec, output)
    monkeypatch.setattr(acquisition, "_extract_verified", fail_first_archive)

    acquire(cache, tmp_path / "payload")
    assert (tmp_path / "payload" / "det_500m.onnx").read_bytes() == content
