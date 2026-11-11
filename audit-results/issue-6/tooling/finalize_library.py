"""Promote only reviewed, non-sensitive captures; preserve original bytes.
Run from repository root after capture processes stop. Does not delete originals.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,shutil,struct
import subprocess
ROOT=Path.cwd();A=ROOT/'audit-results/issue-6';P=ROOT/'qa-fixtures/runs/issue-6-audit';C=P/'captures'
SHA='b457f0a723e845dd1a92a07a577072c85146c89a'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def size(p):
 raw=p.read_bytes()
 if raw.startswith(b'\x89PNG'):return dict(zip(('width','height'),struct.unpack('>II',raw[16:24])))
 info=subprocess.check_output(['sips','-g','pixelWidth','-g','pixelHeight',str(p)],text=True)
 return {k:int(next(x.split(':')[1] for x in info.splitlines() if label in x)) for k,label in [('width','pixelWidth'),('height','pixelHeight')]}
r=json.loads((P/'capture-metadata.json').read_text())
for x in r:
 j,s=x['journey'],x['step']
 if (j,s) in [('J06',1),('J06',2),('J17',2),('J20',6),('J25',1)]:
  x['public_candidate']=False;x.pop('sanitized_file',None);x.pop('sanitized_sha256',None)
  x['publication_reason']='Withheld: local path, filled credential form, or rejected capture attribution; see journey/review.'
 if j=='J17' and s==2:
  x.update(state='Audit-session-header-error-before-resume',role='Unauthenticated',capture_acceptance='REJECTED as attachment state; QA harness header issue')
 if j=='J20' and s==6:x['state']='Operator-account-form-before-creation'
 if j=='J25' and s==1:x.update(state='People-library-before-keyboard-setup-retry',capture_acceptance='REJECTED as keyboard evidence; no keyboard test occurred')
 if j=='J01' and s in (1,2):x['role']='Unauthenticated'
 if j=='J04' and s==2:x['state']='Edit-menu-open'
 if j=='J31' and s==1:x['state']='People-initial-read-pending-zero-count'
 if j=='J31' and s==7:x['state']='Recently-seen-loading-retaining-selection'
 if j=='J32':x['kind']='source ONNX model setup; no inference'
 if j=='J32' and s==4:x['state']='Detector-ready-matcher-not-yet-ready-private'
 if j=='J27' and s==3:x['state']='People-collection-after-merge'
 if j=='J28' and s==2:x['state']='People-collection-after-tombstone'
 if j=='J33' and s==2:x['state']='Group-discard-refused-Event-details-required'
 if j=='J34' and s==5:x['state']='New-Person-form-country-picker-not-saved'
 if j=='J30' and s==2:x['state']='Poor-accepted-option-selected-not-committed'
 if 'Headed-native-People' in x['file']:
  x.update(viewport={'width':1280,'height':608},device_scale_factor=2,capture_surface='headed browser content viewport',native_window_css={'width':1280,'height':695})
 x.setdefault('capture_surface','full browser content viewport; not stitched; OS chrome excluded')
 x.setdefault('scroll',None)
 x['fixture_context']='Media-free layout authority:30 synthetic People/30 Encounters/0 photos; domain prepared while stopped' if j=='J31' else ('Fresh source ONNX setup authority; existing local operator-supplied model files; no inference in these frames' if j=='J32' else 'Dedicated disposable source dev authority; non-sensitive synthetic identities and generated image bytes; whole-image detector/hash embedder')
# Native originals are additional captures, not replacements for browser captures.
for p in sorted(C.glob('*Native-full-window-*.png'))+sorted(C.glob('*Native-IAB-signin.jpg')):
 if any(x['file']==p.name for x in r):continue
 parts=p.stem.split('_');ux=parts[0];iab='IAB' in p.name
 r.append(dict(file=p.name,ux=ux,journey='J40',step=0 if iab else int(parts[2].split('-')[1]),state='Native IAB sign-in' if iab else p.stem.split('_',3)[3],role='Unauthenticated' if iab else 'Administrator',kind='synthetic',public_candidate=True,source_sha=SHA,sha256=digest(p),captured_at=datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat(),capture_time_qualification='File mtime; tool capture time not separately logged',viewport={'width':615,'height':599} if iab else {'width':1280,'height':608},device_scale_factor=None if iab else 2,native_window_css=None if iab else {'width':1280,'height':695},native_display_css=None if iab else {'width':1280,'height':802},capture_surface='native in-app browser content' if iab else 'full native macOS browser window including chrome',fixture_context='Empty sign-in' if iab else 'Same disposable synthetic dev authority; no genuine photograph',scroll=None))
for i,x in enumerate(r,1):
 x['capture_id']=f'CAP-{i:04d}';p=C/x['file'];assert digest(p)==x['sha256'],x['file'];x['raster_pixels']=size(p)
 if x.get('sanitized_file'):
  file=x['sanitized_file'];assert digest(C/file)==x['sanitized_sha256'];x['publication']='SANITIZED separate capture; original private'
 elif x.get('public_candidate') is True:file=x['file'];x['publication']='ORIGINAL unmodified full capture'
 else:x['publication']='PRIVATE';continue
 dest=A/'screenshots'/x['ux']/file;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/file,dest)
 x['public_file']=str(dest.relative_to(A));x['public_sha256']=digest(dest)
(P/'capture-metadata.json').write_text(json.dumps(r,indent=2))
# Raw accessibility snapshots, passwords, model declarations, databases and logs never promoted.
public=[{k:v for k,v in x.items() if k not in ('public_candidate',)} for x in r]
(A/'capture-register.json').write_text(json.dumps(public,indent=2))
private=[]
for d in [P/'genuine',*sorted(P.glob('genuine-20*'))]:
 report=json.loads((d/'private-report.json').read_text()) if (d/'private-report.json').exists() else {}
 for p in sorted(d.glob('*.png')):
  private.append({'private_asset_id':str(p.relative_to(P)),'sha256':digest(p),'raster_pixels':size(p),'source_sha':SHA,'journey':'J41','role':'Administrator','kind':'genuine ONNX; approved existing local photo pair','publication':'PRIVATE; no image bytes in Git','attempt_result':report.get('result'),'qualification':'Endpoint-response/transient unless stable-*; final successful attempt genuine-20261110-060856 includes independently inspected stable completed/refreshed/restarted profiles.'})
(A/'private-evidence-register.json').write_text(json.dumps(private,indent=2))
print(json.dumps({'capture_records':len(r),'published_images':sum('public_file'in x for x in r),'private_genuine_images':len(private),'published_bytes':sum((A/x['public_file']).stat().st_size for x in r if 'public_file'in x)}))
