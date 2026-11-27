"""Opt-in disposable media-free layout fixture using existing QA/store methods.
Run only against a fresh audit root. Not inference, photos, UI creation acceptance,
or a performance benchmark. Refuses reuse of any existing authority.
"""
from pathlib import Path
import secrets,json,sys
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
from sentriface.storage.sqlite_store import SQLiteIdentityStore
from sentriface.secure_storage import load_or_create_master_key
from sentriface.auth import AuthService,RECOVERY_RISK_ACKNOWLEDGEMENT_VERSION
from tests.test_world_graph_v2 import WorldGraphV2Test
private=ROOT/'qa-fixtures/runs/issue-6-audit'
root=private/'dense-authority'
if root.exists():raise SystemExit('Refusing existing fixture authority')
root.mkdir(mode=0o700)
key=load_or_create_master_key(root);store=SQLiteIdentityStore(root/'sentriface.db',database_key=key);store.initialize()
people=[store.create_person(f'Fixture {i+1:02d} — long synthetic identity label',metadata={'rank':'Layout fixture','country':['United States','Canada','United Kingdom'][i%3],'importance':'Regular'},notes='Non-sensitive domain fixture. This long note tests information access and wrapping. '*3) for i in range(30)]
oracle=WorldGraphV2Test()
for i in range(30):
 ids=[p.person_id for p in people[:8]] if i<2 else [people[i%30].person_id]
 oracle._observe(store,f'issue6-layout-{i}',ids,observed_at=f'2026-11-{9-i%3:02d}T12:00:00+00:00',location=['Synthetic East','Synthetic West','Synthetic North'][i%3])
password=secrets.token_urlsafe(24);auth=AuthService(root/'sentriface.db',key);owner,_=auth.signup_initial('dense-owner','Layout fixture administrator',password);auth.acknowledge_recovery_risk(owner,RECOVERY_RISK_ACKNOWLEDGEMENT_VERSION)
p=private/'dense-credentials.json';p.write_text(json.dumps({'password':password}));p.chmod(0o600)
(private/'dense-fixture-summary.json').write_text(json.dumps({'people':30,'encounters':30,'genuine_photographs':0,'inference_executed':False,'method':'Existing WorldGraphV2Test._observe and store.create_person; stopped fresh authority; read/display evidence only'},indent=2))
print('Fresh media-free layout fixture:30 People,30 Encounters,0 photographs')
