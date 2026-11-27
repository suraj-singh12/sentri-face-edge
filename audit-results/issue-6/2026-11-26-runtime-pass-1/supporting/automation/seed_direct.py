from pathlib import Path
from dataclasses import replace
import uuid, json
from sentriface.cli import build_dev_engine
from sentriface.config import config_for_hardware
from sentriface.hardware import assess_hardware
from sentriface.secure_storage import load_or_create_master_key

data=Path('/home/ubuntu/issue6-runtime-audit/data')
config=config_for_hardware(assess_hardware(),data_dir=data)
config=replace(config,storage_key=load_or_create_master_key(data))
engine=build_dev_engine(data,config)
store=engine.store
people={p.person.name:p.person.person_id for p in store.list_persons()}
print('people',people)
actor={'user_id':'fixture','username':'owner','display_name':'Audit Owner','roles':['administrator']}
# create and finalize representative shared multi-person event if no finalized events exist
existing=store.query_encounters(limit=5).get('events',[])
print('existing events',len(existing))
if not existing:
 obs=store.create_observation(str(uuid.uuid4()),observed_at='2026-11-21T09:30:00+00:00',location='Audit Lab',context={
  'occasion':'Morning Audit Briefing','start_time':'09:30','end_time':'10:00','time_precision':'exact','context':'internal','event_notes':'Shared synthetic audit briefing fixture.','individual_count':2,
 },source='fixture-seed',actor=actor,participant_ids=[people['Asha Rao'],people['Bilal Khan'],people['Carla Mendes']])
 fin=store._finalize_observation_without_graph_evidence(obs.observation_id,str(uuid.uuid4()),source='fixture-seed',actor=actor)
 print('finalized',fin)
# second single-person event for corrections/filter variety
if len(store.query_encounters(limit=10).get('events',[]))<2:
 obs=store.create_observation(str(uuid.uuid4()),observed_at='2026-11-22T14:00:00+00:00',location='Audit Lab',context={
  'occasion':'Afternoon Audit','start_time':'14:00','end_time':'','time_precision':'approximate','context':'internal','event_notes':'Single participant fixture.','individual_count':1,
 },source='fixture-seed',actor=actor,participant_ids=[people['Devika Iyer']])
 fin=store._finalize_observation_without_graph_evidence(obs.observation_id,str(uuid.uuid4()),source='fixture-seed',actor=actor)
 print('finalized2',fin)
print('events now',len(store.query_encounters(limit=10).get('events',[])))
print(json.dumps(store.query_encounters(limit=10),indent=2)[:4000])
