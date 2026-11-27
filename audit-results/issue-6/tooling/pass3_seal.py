"""Pass 3 seal on Linux: verify registered public images and links, then refresh the manifest file list.
seal_library.py needs macOS `sips` and the private Pass 1/2 accessibility snapshots, so Pass 3 uses
this narrower check and leaves earlier derived registers (overlays, surfaces) unchanged.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, re, struct
R = Path.cwd(); A = R / 'audit-results/issue-6'
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
reg = json.loads((A / 'capture-register.json').read_text())
public = [r for r in reg if r.get('public_file')]
for r in public:
    p = A / r['public_file']; assert p.exists() and digest(p) == r['public_sha256'], p
    raw = p.read_bytes()
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        assert dict(zip(('width', 'height'), struct.unpack('>II', raw[16:24]))) == r['raster_pixels'], p
    else: assert raw.startswith(b'\xff\xd8'), p
assert {str(p.relative_to(A)) for p in (A / 'screenshots').rglob('*') if p.is_file()} == {r['public_file'] for r in public}
broken = []
for p in [*A.rglob('*.md'), R / 'docs/UI_UX_DESIGN.md']:
    for t in re.findall(r'\]\(([^)]+)\)', p.read_text()):
        if t.startswith(('https:', 'http:', '#', 'mailto:')): continue
        d = t.split('#')[0].strip('<>')
        if d and not (p.parent / d).exists(): broken.append((str(p), t))
assert not broken, broken
m = json.loads((A / 'manifest.json').read_text())
files = []
for p in sorted([*A.rglob('*'), R / 'docs/UI_UX_DESIGN.md']):
    if not p.is_file() or '__pycache__' in p.parts or p.suffix == '.pyc' or p.name in ('manifest.json', 'manifest.sha256'): continue
    assert p.suffix not in ('.sqlite', '.db', '.onnx', '.enc'), p
    if p.suffix in ('.md', '.json', '.csv'):
        assert not re.search(r'/home/ubuntu/|/Users/user/|/private/var/', p.read_text()), p
    files.append(dict(path=str(p.relative_to(R)), bytes=p.stat().st_size, sha256=digest(p)))
m.update(files=files, sealed_at=datetime.now(timezone.utc).isoformat())
m['pass3'] = dict(source_sha='677bb61e8e9d659db95123871bb2e011cf663a79', branch='v2-hardening-followups',
    environment='Linux (Ubuntu VM), headless Chromium via Playwright, 1440x900 CSS, DPR 1, light theme, dev synthetic source authority; audit-only multi-face seam for J42-J44',
    journeys=[f'J{n}' for n in range(42, 53)], public_images=sum(r.get('pass_id') == 'Pass 3' for r in public),
    private_only=sum(r.get('pass_id') == 'Pass 3' and not r.get('public_file') for r in reg))
m['counts']['public_images'] = len(public); m['counts']['registered_capture_attempts'] = len(reg)
m['counts']['runtime_journey_records'] = len(list((A / 'journeys').glob('J*.md')))
(A / 'manifest.json').write_text(json.dumps(m, indent=2) + '\n')
(A / 'manifest.sha256').write_text(digest(A / 'manifest.json') + '  manifest.json\n')
print('sealed', len(public), 'public;', len(files), 'files')
