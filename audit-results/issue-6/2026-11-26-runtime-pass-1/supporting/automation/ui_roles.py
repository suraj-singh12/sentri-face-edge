import asyncio,re,json,os
from ui_audit_lib import *
ROLES=[('viewer1','Viewer'),('operator1','Operator'),('custodian1','Custodian'),('technician1','Technician'),('owner','Administrator')]
PASS={'viewer1':'<REDACTED_TEST_PASSWORD>','operator1':'<REDACTED_TEST_PASSWORD>','custodian1':'<REDACTED_TEST_PASSWORD>','technician1':'<REDACTED_TEST_PASSWORD>','owner':'<REDACTED_TEST_PASSWORD>'}
async def signout(page):
 try:
  await page.get_by_label('Open account menu').click(timeout=1800); await page.wait_for_timeout(300)
  await page.get_by_text('Sign out',exact=True).click(timeout=1800); await page.wait_for_timeout(900)
  rec('signout','ok')
 except Exception as e: rec('signout','error',str(e)[:150])
async def open_bilal(page):
 await nav(page,'People')
 try:
  # choose the Open profile in the Bilal card by index/text fallback
  buttons=page.locator('button',has_text='Open profile')
  if await buttons.count()>=2: await buttons.nth(1).click(timeout=2200)
  else: await page.get_by_text('Bilal Khan',exact=True).first.click(timeout=2200)
  await page.wait_for_timeout(800); return True
 except Exception as e: rec('open bilal role','error',str(e)[:150]); return False
async def main():
 p,b,ctx,page=await connect()
 # sign out current owner if authenticated
 await signout(page)
 matrix=[]
 for username,label in ROLES:
  await login(page,username,PASS[username])
  txt=await body(page)
  navs=[]
  for n in ['Check a photo','Review photos','People','Events','World','Settings']:
   try:
    if await page.get_by_role('tab',name=re.compile('^'+n+'$',re.I)).count(): navs.append(n)
   except Exception: pass
  row={'role':label,'nav':navs,'initial_contains_readonly':'Read-only access:' in txt}
  await shot(page,f'40-roles/{label.lower()}/landing')
  # profile behavior
  if 'People' in navs:
   if await open_bilal(page):
    await shot(page,f'40-roles/{label.lower()}/bilal-profile')
    txt2=await body(page)
    row['profile_readonly_explanation']='Read-only access:' in txt2
    row['profile_has_edit']='Edit' in txt2
    row['profile_has_add_face']='Add Face' in txt2
    # capture long note read expansion where available
    try:
     await page.get_by_role('button',name='Read full note').click(timeout=1000); await page.wait_for_timeout(350); await shot(page,f'40-roles/{label.lower()}/bilal-long-note-expanded')
     row['long_note_expand']=True
    except Exception: row['long_note_expand']=False
  # events behavior
  if 'Events' in navs:
   await nav(page,'Events',f'40-roles/{label.lower()}/events-list')
   try:
    await page.get_by_text('Morning Audit Briefing').first.click(timeout=1800); await page.wait_for_timeout(600)
    await shot(page,f'40-roles/{label.lower()}/event-detail')
    txt3=await body(page)
    row['event_readonly_explanation']='Read-only access:' in txt3
    row['event_has_correct']='Correct Event' in txt3
    row['event_has_attach']='Attach Media' in txt3
   except Exception as e: row['event_open_error']=str(e)[:100]
  # settings screen if present
  if 'Settings' in navs:
   await nav(page,'Settings',f'40-roles/{label.lower()}/settings')
  # world screen if present
  if 'World' in navs:
   await nav(page,'World',f'40-roles/{label.lower()}/world')
  matrix.append(row)
  open(f'/home/ubuntu/issue6-runtime-audit/role-{label.lower()}-summary.json','w').write(json.dumps({'row':row,'body_excerpt':(await body(page))[:3000]},indent=2))
  await signout(page)
 open('/home/ubuntu/issue6-runtime-audit/role-matrix.json','w').write(json.dumps(matrix,indent=2))
 flush(); await p.stop()
asyncio.run(main())
