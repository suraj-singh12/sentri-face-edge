"""Select a validated unsigned installer and publish only minimal provenance."""
import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(root=ROOT):
    version = runpy.run_path(str(root / 'src/sentriface/_version.py'))['APP_VERSION']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid release version')
    directory = root / 'dist/windows-x64' / version
    name = f'SentriFaceEdge-{version}-x64-unsigned-pretag-rc.exe'
    candidates = list(directory.glob('SentriFaceEdge-*-x64-unsigned-pretag-rc.exe'))
    if len(candidates) != 1 or candidates[0].name != name:
        raise ValueError('Expected exactly one unsigned candidate installer')
    installer = directory / name
    checksum = directory / (name + '.sha256')
    inspection = json.loads((directory / 'artifact-inspection.json').read_text(encoding='utf8'))
    provenance = json.loads((directory / (name + '.provenance.json')).read_text(encoding='utf8'))
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()
    expected = checksum.read_text(encoding='ascii').strip()
    if expected != f'{digest}  {name}':
        raise ValueError('Installer checksum mismatch')
    item = inspection.get('installer') or {}
    artifacts = [a for a in provenance.get('artifacts', []) if a.get('kind') == 'installer']
    if (inspection.get('status') != 'PASS' or inspection.get('version') != version
        or inspection.get('expected_architecture') != 'AMD64' or item.get('path') != name
        or item.get('sha256') != digest or item.get('architecture') != 'AMD64'
        or item.get('size') != installer.stat().st_size):
        raise ValueError('Release inspection does not match the exact AMD64 installer')
    if provenance.get('commit') != sha or provenance.get('version') != version:
        raise ValueError('Release provenance commit or version does not match checkout')
    if provenance.get('working_tree_clean') is not True:
        raise ValueError('Release provenance records a dirty source tree')
    if provenance.get('development_build') is not True or provenance.get('authenticode_signed') is not False:
        raise ValueError('Release provenance is not an unsigned engineering candidate')
    if (len(artifacts) != 1 or artifacts[0].get('name') != name
        or artifacts[0].get('sha256') != digest or artifacts[0].get('size') != installer.stat().st_size):
        raise ValueError('Release provenance installer identity, size or hash mismatch')
    output = root / 'qa-fixtures/installer-public'
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(installer, output / name)
    shutil.copyfile(checksum, output / (name + '.sha256'))
    (output / 'manifest.json').write_text(json.dumps({'schema_version': 1, 'commit': sha,
        'installer': name, 'sha256': digest, 'classification': 'unsigned engineering candidate'}, indent=2) + '\n', encoding='utf8')
    return name


if __name__ == '__main__':
    name = prepare()
    manifest = json.loads((ROOT / 'qa-fixtures/installer-public/manifest.json').read_text(encoding='utf8'))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf8') as output:
            output.write(f'installer={name}\nchecksum={name}.sha256\n')
    print('Validated installer:', name)
    print('Installer SHA-256:', manifest['sha256'])
