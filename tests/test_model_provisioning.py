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


def test_research_payload_creates_bundle_and_activation_request(monkeypatch, tmp_path):
    import hashlib
    import json
    from sentriface.model_bundle import ModelBundleAuthority

    detector = b"fixture-detector"
    recognizer = b"fixture-recognizer"
    monkeypatch.setitem(model_provisioning.RESEARCH_MODELS, "detector", {
        "filename": "det_500m.onnx",
        "size": len(detector),
        "sha256": hashlib.sha256(detector).hexdigest(),
    })
    monkeypatch.setitem(model_provisioning.RESEARCH_MODELS, "recognizer", {
        "filename": "w600k_r50.onnx",
        "size": len(recognizer),
        "sha256": hashlib.sha256(recognizer).hexdigest(),
    })
    payload = tmp_path / "bundled-models"
    payload.mkdir()
    (payload / "det_500m.onnx").write_bytes(detector)
    (payload / "w600k_r50.onnx").write_bytes(recognizer)
    (payload / "THIRD-PARTY-MODEL-NOTICE.txt").write_text("notice")
    (payload / "research-model-provenance.json").write_text(
        json.dumps({"contract": "sentriface.research-model-provenance"})
    )
    monkeypatch.setattr(model_provisioning, "bundled_research_payload_dir", lambda: payload)

    class Activation:
        def __init__(self):
            self.executed = []
        def active_state(self):
            return None
        def prepare_model_activation(self, bundle_id):
            return {"token": f"token:{bundle_id}"}
        def execute(self, token, operation_id, *, actor, reason):
            self.executed.append((token, operation_id, actor, reason))

    class Server:
        runtime = "onnx"
        def __init__(self):
            self.model_bundles = ModelBundleAuthority(tmp_path / "models")
            self.model_activation = Activation()
            self.events = []
        def sync_model_runtime_state(self):
            pass
        def log_event(self, event, **details):
            self.events.append((event, details))

    server = Server()
    assert model_provisioning.provision_bundled_research_models(server) is True
    bundles = server.model_bundles.list_bundles()
    assert len(bundles) == 1
    assert server.model_activation.executed[0][0] == f"token:{bundles[0].bundle_id}"
    declaration = json.loads((bundles[0].directory / "model-usage.json").read_text())
    assert "approved Research installer supplied" in declaration["operator_declaration"]
    assert declaration["usage_basis"] == "noncommercial-research"
    assert server.events[0][0] == "bundled-research-models-provisioned"
