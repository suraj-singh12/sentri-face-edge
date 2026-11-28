from pathlib import Path

import pytest

from sentriface.errors import ModelSetupError
from sentriface import model_provisioning


class _Activation:
    def __init__(self, active=True):
        self._active = object() if active else None
    def active_state(self):
        return self._active


class _Server:
    runtime = "onnx"
    def __init__(self, active=True):
        self.model_activation = _Activation(active)


def test_existing_active_model_is_never_replaced(monkeypatch, tmp_path):
    payload = tmp_path / "bundled-models"
    payload.mkdir()
    monkeypatch.setattr(model_provisioning, "bundled_research_payload_dir", lambda: payload)
    server = _Server(active=True)
    assert model_provisioning.provision_bundled_research_models(server) is False
    assert not list(payload.iterdir())


def test_corrupt_payload_fails_closed_before_upload(monkeypatch, tmp_path):
    payload = tmp_path / "bundled-models"
    payload.mkdir()
    (payload / "THIRD-PARTY-MODEL-NOTICE.txt").write_text("notice")
    (payload / "research-model-provenance.json").write_text('{"contract":"sentriface.research-model-provenance"}')
    (payload / "det_500m.onnx").write_bytes(b"wrong")
    (payload / "w600k_r50.onnx").write_bytes(b"wrong")
    monkeypatch.setattr(model_provisioning, "bundled_research_payload_dir", lambda: payload)
    server = _Server(active=False)
    with pytest.raises(ModelSetupError, match="size does not match"):
        model_provisioning.provision_bundled_research_models(server)


def test_payload_path_is_present_beside_executable(monkeypatch, tmp_path):
    executable = tmp_path / "install" / "SentriFaceEdge.exe"
    payload = executable.parent / "bundled-models"
    payload.mkdir(parents=True)
    monkeypatch.setattr(model_provisioning.sys, "executable", str(executable))
    assert model_provisioning.bundled_research_payload_dir() == payload
    payload.rmdir()
    assert model_provisioning.bundled_research_payload_dir() is None
