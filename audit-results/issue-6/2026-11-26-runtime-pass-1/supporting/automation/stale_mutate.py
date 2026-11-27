from pathlib import Path
from dataclasses import replace
from sentriface.cli import build_dev_engine
from sentriface.config import config_for_hardware
from sentriface.hardware import assess_hardware
from sentriface.secure_storage import load_or_create_master_key
import uuid
data=Path('/home/ubuntu/issue6-runtime-audit/data')
c=config_for_hardware(assess_hardware(),data_dir=data); c=replace(c,storage_key=load_or_create_master_key(data)); e=build_dev_engine(data,c)
oid='fd751f03-b15f-5924-b25d-7d509c7b557c'
d=e.store.get_encounter_read(oid)
print('before revision',d['revision'])
r=e.store.correct_encounter(oid,str(uuid.uuid4()),expected_revision=d['revision'],event_details={'event_notes':'Changed outside the open correction modal to create a controlled stale revision.'},actor={'user_id':'fixture','username':'owner','display_name':'Audit Owner','roles':['administrator']},source='stale-fixture')
print('mutated',r)
print('after revision',e.store.get_encounter_read(oid)['revision'])
