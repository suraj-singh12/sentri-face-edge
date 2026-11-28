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
