import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', ROOT / 'scripts/prepare_ci_installer.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

@pytest.fixture
def candidate(tmp_path, monkeypatch):
    (tmp_path / 'src/sentriface').mkdir(parents=True)
    (tmp_path / 'src/sentriface/_version.py').write_text('APP_VERSION = "2.0.0"')
    directory = tmp_path / 'dist/windows-x64/2.0.0'
    directory.mkdir(parents=True)
    name = 'SentriFaceEdge-2.0.0-x64-unsigned-pretag-rc.exe'
    (directory / name).write_bytes(b'controlled installer fixture')
    digest = hashlib.sha256((directory / name).read_bytes()).hexdigest()
    (directory / (name + '.sha256')).write_text(f'{digest}  {name}\n')
    (directory / 'artifact-inspection.json').write_text(json.dumps(dict(status='PASS', version='2.0.0', expected_architecture='AMD64', installer=dict(path=name, sha256=digest))))
    (directory / (name + '.provenance.json')).write_text(json.dumps(dict(commit='a'*40, version='2.0.0', development_build=True, authenticode_signed=False, artifacts=[dict(kind='installer', name=name, sha256=digest)])))
    monkeypatch.setattr(mod.subprocess, 'check_output', lambda *args, **kwargs: 'a'*40)
    return tmp_path, directory, name, digest


def test_validated_artifact_only(candidate):
    root, directory, name, digest = candidate
    (directory / 'private.onnx').write_bytes(b'secret')
    assert mod.prepare(root) == name
    out = root / 'qa-fixtures/installer-public'
    assert {p.name for p in out.iterdir()} == {name, name + '.sha256', 'manifest.json'}
    assert json.loads((out / 'manifest.json').read_text())['sha256'] == digest

@pytest.mark.parametrize('mutation', ['missing', 'checksum', 'ambiguous', 'inspection', 'revision'])
def test_invalid_artifact_refused(candidate, mutation):
    root, directory, name, _ = candidate
    if mutation == 'missing': (directory / name).unlink()
    elif mutation == 'checksum': (directory / (name + '.sha256')).write_text('0'*64 + '  ' + name)
    elif mutation == 'ambiguous': (directory / 'SentriFaceEdge-9.9.9-x64-unsigned-pretag-rc.exe').write_bytes(b'x')
    elif mutation == 'inspection': (directory / 'artifact-inspection.json').write_text('{"status":"FAIL"}')
    else:
        path = directory / (name + '.provenance.json')
        obj = json.loads(path.read_text()); obj['commit'] = 'b'*40; path.write_text(json.dumps(obj))
    with pytest.raises((ValueError, FileNotFoundError)):
        mod.prepare(root)
    assert not (root / 'qa-fixtures/installer-public').exists()


def test_workflow_gates_installer_but_not_failure_reports():
    workflow = (ROOT / '.github/workflows/ci.yml').read_text()
    assert "if: success() && steps.package.outcome == 'success' && steps.installer-evidence.outcome == 'success'" in workflow
    assert 'qa-fixtures/installer-public/*' not in workflow
    assert 'dist/windows-x64/2.0.0/*' not in workflow
    assert workflow.count('if: always()') == 6
    assert 'exit $LASTEXITCODE' in workflow
