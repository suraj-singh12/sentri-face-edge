import requests,re,uuid,json,sys,time
BASE='http://127.0.0.1:8765'
def login(username,password):
 s=requests.Session(); html=s.get(BASE+'/').text
 token=re.search(r'name="sentriface-session-token" content="([^"]+)',html).group(1)
 h={'X-SentriFace-Session':token,'X-SentriFace-Window':str(uuid.uuid4()),'Content-Type':'application/json'}
 r=s.post(BASE+'/api/auth/login',headers=h,json={'username':username,'password':password}); print('login',username,r.status_code)
 if r.status_code>=400: print(r.text); sys.exit(1)
 return s,h,r.json()
def post(s,h,path,body,ok=True):
 body.setdefault('operation_id',str(uuid.uuid4()))
 r=s.post(BASE+path,headers=h,json=body)
 print(path,r.status_code,r.text[:180].replace('\n',' '))
 if ok and r.status_code>=400: raise SystemExit(1)
 return r.json() if r.text else {}
def get(s,h,path):
 r=s.get(BASE+path,headers=h); print(path,r.status_code,r.text[:120].replace('\n',' '))
 if r.status_code>=400: raise SystemExit(1)
 return r.json()
s,h,status=login('owner','<REDACTED_TEST_PASSWORD>')
people={}
defs=[
 ('Asha Rao','Analyst','India','Audit Lab','2','Morning Audit Briefing','audit-fixture'),
 ('Bilal Khan','Analyst','India','Audit Lab','2','Morning Audit Briefing','audit-fixture'),
 ('Carla Mendes','Analyst','India','Audit Lab','1','Morning Audit Briefing','audit-fixture'),
 ('Devika Iyer','Analyst','India','Audit Lab','1','Afternoon Audit','audit-fixture'),
 ('Zedekiah Vale','Observer','India','Audit Lab','1','Afternoon Audit','audit-fixture'),
]
for name,rank,country,place,count,occ,tag in defs:
 if name in (s.get(BASE+'/api/persons',headers=h).text or ''): continue
 p=post(s,h,'/api/person-create',{'name':name,'rank':rank,'country':country,'importance':'Regular','tags':[tag],'seen_date':'2026-11-21','seen_time':'09:30','place_seen':place,'individual_count':int(count),'event_occasion':occ,'added_by':'Audit Owner'})
 people[name]=p['person']['person_id']
# if already present, collect IDs
if len(people)<len(defs):
 data=get(s,h,'/api/persons')
 for x in data.get('persons',[]):
  if x.get('name') in dict((d[0],d) for d in defs): people[x['name']]=x['person_id']
print('people',people)
# notes and mentions
longnote=('This is a long audit note paragraph with important context, repeated so the reading panel must either wrap, scroll, clip, or provide an obvious full-read path. '*12)+'Mention: @Asha Rao'
post(s,h,'/api/person-notes',{'person_id':people['Bilal Khan'],'notes':longnote,'expected_previous_notes':'','mentioned_person_ids':[people['Asha Rao']]})
post(s,h,'/api/person-notes',{'person_id':people['Asha Rao'],'notes':'Met during the morning audit briefing with @Bilal Khan and @Zedekiah Vale.','expected_previous_notes':'','mentioned_person_ids':[people['Bilal Khan'],people['Zedekiah Vale']]})
# manual association
post(s,h,'/api/person-association',{'first_person_id':people['Carla Mendes'],'second_person_id':people['Devika Iyer']},ok=False)
# make first event shared by adding Bilal to Asha's initial event if possible
page=get(s,h,'/api/encounters?limit=20')
open('/home/ubuntu/issue6-runtime-audit/seed-encounters.json','w').write(json.dumps(page,indent=2))
events=page.get('events') or []
target=None
for e in events:
 txt=json.dumps(e)
 if people['Asha Rao'] in txt and 'Morning Audit Briefing' in txt: target=e; break
if target:
 oid=target.get('observation_id') or target.get('event_id') or target.get('id')
 rev=target.get('revision') or target.get('current_revision')
 print('target',oid,rev,target.keys())
 if oid and rev:
  post(s,h,'/api/encounter-correct',{'observation_id':oid,'expected_revision':rev,'participant_correction':{'action':'ADD','person_id':people['Bilal Khan']}},ok=False)
# create role accounts; then set their required passwords through their own first login
roles=[('viewer1','Viewer User',['viewer']),('operator1','Operator User',['operator']),('custodian1','Custodian User',['custodian']),('technician1','Technician User',['technician'])]
for username,disp,rr in roles:
 post(s,h,'/api/users',{'username':username,'display_name':disp,'password':'TemporaryPass123!','roles':rr},ok=False)
for username,disp,rr in roles:
 try:
  ss,hh,st=login(username,'TemporaryPass123!')
  if st.get('password_change_required') or st.get('user',{}).get('must_change_password'):
   r=ss.post(BASE+'/api/auth/set-password',headers=hh,json={'new_password':'<REDACTED_TEST_PASSWORD>'})
   print('set-password',username,r.status_code,r.text[:100])
 except Exception as e: print('role setup err',username,e)
# summarize final projections
summary={'persons':get(s,h,'/api/persons'), 'encounters':get(s,h,'/api/encounters?limit=20')}
open('/home/ubuntu/issue6-runtime-audit/seed-summary.json','w').write(json.dumps(summary,indent=2))
print('seed complete')
