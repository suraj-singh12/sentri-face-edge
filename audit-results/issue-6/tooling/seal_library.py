"""Recompute audit counts, links and file integrity after reviewed capture promotion.
Run from repository root. Never imports raw accessibility text into public output.
The manifest excludes itself and its checksum to avoid circular hashes.
"""
from pathlib import Path
from datetime import datetime, timezone
import collections, csv, hashlib, json, re, struct
import subprocess

R = Path.cwd()
A = R / 'audit-results/issue-6'
P = R / 'qa-fixtures/runs/issue-6-audit'
SHA = 'b457f0a723e845dd1a92a07a577072c85146c89a'
def read(name): return json.loads((A / name).read_text())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def csvread(name): return list(csv.DictReader((A/name).open()))
def csvwrite(name, rows):
    with (A/name).open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0]),lineterminator='\n'); w.writeheader(); w.writerows(rows)

records=read('capture-register.json')
accepted=[r for r in records if not r.get('capture_acceptance','').startswith('REJECTED') and r.get('capture_status')!='REJECTED']
public=[r for r in records if r.get('public_file')]
semantic=read('semantic-summary.json'); candidates=read('coverage-summary.json')
overlays={}
for r in accepted:
    f=P/'captures'/(r['file']+'.txt')
    if not f.exists(): continue
    for kind,title in re.findall(r'^\s*- (dialog|menu|listbox|tooltip) "([^"\n]+)"', f.read_text(), re.M):
        key=(kind,title)
        overlays.setdefault(key,[]).append(r)
overlayrows=[]
for i,((kind,title),rr) in enumerate(sorted(overlays.items()),1):
    overlayrows.append(dict(overlay_id=f'OV-{i:03d}',accessible_role=kind,observed_title=title,journeys=' | '.join(sorted({r['journey'] for r in rr})),evidence=' | '.join(sorted({r.get('public_file', 'journeys/'+r['journey']+'.md') for r in rr})),qualification='Observed accessible titled instance; unnamed and dynamic source definitions remain in source oracle'))
csvwrite('captured-overlays.csv',overlayrows)
surfaces=[
('UX-00','First-owner setup','J01'),('UX-00','Sign-in','J40'),('UX-00','Model setup gate','J32'),('UX-00','Backup readiness gate','J01'),
('UX-02','Check a photo workspace','J06'),('UX-03','Import and grouping workspace','J08'),('UX-04','Queue face review workspace','J08'),
('UX-05','People collections','J09'),('UX-05','Archived collection','J13'),('UX-05','Deleted Faces collection','J11'),
('UX-06','Person Overview','J04'),('UX-06','Person Photos','J05'),('UX-06','Person Sightings','J10'),('UX-06','Person Events','J10'),('UX-06','Person Associations','J12'),('UX-06','Person Activity','J10'),('UX-06','Person Graph','J12'),
('UX-09','Events collection','J07'),('UX-09','Event detail','J15'),
('UX-11','Explore Discover and canvas','J18'),('UX-11','Explore inspector','J18'),('UX-11','Explore compact panes','J26'),
('UX-12','Connections Overview','J19'),('UX-12','Connections Clusters','J19'),('UX-12','Connections Relationships','J19'),('UX-12','Connections Patterns','J19'),('UX-12','Connections Person drilldown','J19'),('UX-12','Connections Cluster drilldown','J19'),('UX-12','Connections Event drilldown','J19'),('UX-12','Connections Evidence drilldown','J19'),
('UX-13','Settings License','J20'),('UX-13','Settings Backups and restore','J22'),('UX-13','Settings User accounts','J20'),('UX-13','Settings Integrity and recovery','J21'),('UX-13','Settings System details','J23'),('UX-13','Settings Activity log','J23'),('UX-13','Settings About and support','J23')]
csvwrite('surface-register.csv',[dict(surface_id=f'VIEW-{i:03d}',ux_id=u,surface_family=n,journey=j,evidence=f'journeys/{j}.md',result='PARTIAL',definition='Semantic page, collection, profile pane or drilldown; excludes overlays, roles, themes and transient states') for i,(u,n,j) in enumerate(surfaces,1)])
keys={(r['ux'],r['state'],r['role'],r['kind'],r.get('theme'),json.dumps(r.get('viewport'),sort_keys=True)) for r in accepted}
summary=dict(source_sha=SHA,status='PARTIAL — completeness/design Gate 1 remains open',registered_capture_attempts=len(records),accepted_capture_records=len(accepted),rejected_attempts=len(records)-len(accepted),distinct_sampled_visual_state_keys=len(keys),public_images=len(public),public_originals=sum(not r.get('sanitized_file') for r in public),public_sanitized_derivatives=sum(bool(r.get('sanitized_file')) for r in public),private_only_accepted=sum(not r.get('public_file') for r in accepted),private_genuine_images=len(read('private-evidence-register.json')),runtime_journey_records=len(list((A/'journeys').glob('J*.md'))),semantic_surface_families=len(surfaces),observed_titled_overlays=len(overlayrows),observed_dialog_title_count=sum(x['accessible_role']=='dialog' for x in overlayrows),source_task_contracts=60,source_task_status=semantic['task_counts'],source_branch_contracts=509,source_branch_status=semantic['branch_counts'],roles_sampled=5,source_definition_sites=832,control_overlay_transition_definition_sites=598,candidate_presence=candidates['result_counts'],counting_definitions='Surfaces: explicit semantic families in surface-register.csv, not all state variants. Journeys: ordered J records, not source contracts. Branches:509 source contracts. Visual key:UX/state/role/kind/theme/viewport, excludes rejected attempts. Titled overlay count excludes unnamed popovers and tooltip definitions; see source oracle. Native and CSS captures are distinct evidence classes.')
(A/'execution-summary.json').write_text(json.dumps(summary,indent=2)+'\n')

for r in public:
    p=A/r['public_file']; assert p.exists() and digest(p)==r['public_sha256'],p
    raw=p.read_bytes();assert raw.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8')),p
    info=subprocess.check_output(['sips','-g','pixelWidth','-g','pixelHeight',str(p)],text=True)
    dimensions=tuple(int(next(x.split(':')[1] for x in info.splitlines() if label in x)) for label in ('pixelWidth','pixelHeight'))
    assert dimensions==tuple(r['raster_pixels'][k] for k in ('width','height')),p
assert {str(p.relative_to(A)) for p in (A/'screenshots').rglob('*') if p.is_file()}=={r['public_file'] for r in public},'Unregistered public screenshot'
assert len(csvread('source-inventory.csv'))==832
assert len(csvread('coverage.csv'))==598
assert len(csvread('task-coverage.csv'))==60
assert len(csvread('branch-coverage.csv'))==509
assert sum(semantic['branch_counts'].values())==509
broken=[]
for p in [*A.rglob('*.md'),R/'docs/UI_UX_DESIGN.md']:
    for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
        if target.startswith(('https:','http:','#','mailto:')):continue
        dest=target.split('#')[0].strip('<>')
        if dest and not (p.parent/dest).exists():broken.append((str(p.relative_to(R)),target))
assert not broken,broken
(A/'checks/library-validation.json').write_text(json.dumps(dict(source_sha=SHA,result='PASS',public_images_verified=len(public),registered_public_assets_closed=True,relative_markdown_links_missing=0,source_sites=832,control_sites=598,tasks=60,branches=509,product_source_changed=False,qualification='Integrity and publication checks only; semantic coverage remains PARTIAL. Native IAB original is JPEG, remaining public images PNG. sips reads dimensions without rewriting image bytes.'),indent=2)+'\n')
files=[]
for p in sorted([*A.rglob('*'),R/'docs/UI_UX_DESIGN.md']):
    if not p.is_file() or '__pycache__' in p.parts or p.suffix=='.pyc' or p.name in ('manifest.json','manifest.sha256'):continue
    assert p.suffix not in ('.sqlite','.db','.onnx','.enc'),p
    if p.suffix in ('.md','.json','.csv','.py'):
        s=p.read_text()
        assert '/Users/'+'user/' not in s,f'Private absolute path: {p}'
        if p.suffix!='.py':
            assert not re.search(r'/private/var/|/Volumes/(?!…|\.\.\.)[^\s"<>]+',s),f'Private path: {p}'
    files.append(dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=digest(p)))
manifest=dict(schema_version=1,source_sha=SHA,evidence_branch='audit/issue-6-current-experience',sealed_at=datetime.now(timezone.utc).isoformat(),status=summary['status'],environment=dict(os='macOS 26.0 arm64 VM',timezone='America/Los_Angeles',source_runtime='dev whole-image/hash synthetic; separate approved source ONNX supplement',native_display_css='1280x802',native_window_css='1280x695',native_content_css='1280x608',native_dpr=2,css_viewports=['1440x900 Day','1366x768 Day','1280x800 Night','900x700 Night','1440x900 Night'],themes=['Day','Night']),counts=summary,capture_metadata='audit-results/issue-6/capture-register.json',private_genuine_metadata='audit-results/issue-6/private-evidence-register.json',files=files,hash_scope='SHA-256 over unchanged file bytes; excludes manifest itself, its checksum and Python cache. Evidence commit and archive verification are external receipts to avoid circular identifiers.',privacy='Public synthetic originals and explicitly marked sanitized derivatives only. Private untouched originals stay outside Git. No credentials, snapshots, databases, exports, models or raw logs included.')
(A/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(A/'manifest.sha256').write_text(digest(A/'manifest.json')+'  manifest.json\n')
print(json.dumps(summary,indent=2))
