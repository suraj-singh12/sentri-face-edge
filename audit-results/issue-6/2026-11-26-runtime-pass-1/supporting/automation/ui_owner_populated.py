import asyncio,re,os,json
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 await login(page,'owner','<REDACTED_TEST_PASSWORD>')
 # primary populated screens
 for n,sp in [('People','10-owner-people/list-populated'),('Events','11-owner-events/list-populated'),('World','12-owner-world/explore-populated'),('Review photos','13-owner-review/home'),('Check a photo','14-owner-check/home'),('Settings','15-owner-settings/home')]:
  await nav(page,n,sp)
 # People filters/menus populated
 await nav(page,'People')
 for label,name in [('Filter','10-owner-people/filter-open'),('Group by: Country','10-owner-people/group-menu'),('Sort: Priority','10-owner-people/sort-menu')]:
  await click_name(page,label,name); await press_escape(page)
 # Open Bilal profile and capture all main tabs
 await click_name(page,'Open Bilal Khan','10-owner-people/bilal-profile')
 for tab in ['Photos','Sightings','Events','Associations','Activity']:
  try:
   await page.get_by_role('tab',name=re.compile(tab,re.I)).click(timeout=1600); await page.wait_for_timeout(600)
   await shot(page,'10-owner-people/bilal-tab-'+tab.lower())
   rec('bilal tab '+tab,'ok')
  except Exception as e: rec('bilal tab '+tab,'error',str(e)[:160])
 # back to overview/read full note
 try:
  await page.get_by_role('tab',name='Overview').click(timeout=1000); await page.wait_for_timeout(300)
 except Exception: pass
 if await click_name(page,'Read full note','10-owner-people/bilal-long-note-expanded'):
  rec('F05 long note expansion','verified')
 # open graph, keyboard edge selection
 await click_name(page,'Open Person Graph','16-owner-graph/bilal-graph')
 try:
  # focus graph edge by starting from refresh then tabbing through controls
  await page.get_by_label('Refresh Person Graph').click(timeout=1500); await page.wait_for_timeout(250)
  for _ in range(4): await page.keyboard.press('Tab'); await page.wait_for_timeout(80)
  await shot(page,'16-owner-graph/edge-keyboard-focused')
  await page.keyboard.press('Enter'); await page.wait_for_timeout(700)
  await shot(page,'16-owner-graph/edge-evidence-opened')
  txt=await body(page)
  rec('F02 graph keyboard edge','verified' if 'Evidence types' in txt or 'Provenance summary' in txt else 'unclear', 'inspector visible='+str('Evidence types' in txt))
 except Exception as e: rec('F02 graph keyboard edge','error',str(e)[:200])
 # back to profile using explicit control
 await click_name(page,'Back to person profile','10-owner-people/bilal-profile-after-graph')
 # notes editor mention chips, then cancel (non-destructive)
 try:
  await page.get_by_role('button',name=re.compile('Edit',re.I)).first.click(timeout=1800); await page.wait_for_timeout(400)
  await shot(page,'10-owner-people/bilal-edit-menu')
  await click_name(page,'Edit Notes','10-owner-people/bilal-notes-editor')
  txt=await body(page)
  rec('note mention chips','verified' if '@Asha Rao' in txt else 'unclear','editor contains mention chip')
  await click_name(page,'Cancel','10-owner-people/bilal-notes-cancelled')
 except Exception as e: rec('notes editor','error',str(e)[:200])
 # events list/detail/correction dialogs
 await nav(page,'Events','11-owner-events/list-before-detail')
 # open Morning Audit Briefing card/text
 try:
  await page.get_by_text('Morning Audit Briefing').first.click(timeout=2500); await page.wait_for_timeout(900)
  await shot(page,'11-owner-events/morning-detail')
  rec('event detail open','ok')
 except Exception as e: rec('event detail open','error',str(e)[:180])
 # inspect visible action buttons and open correction menus/dialogs without saving
 for nm in ['Correct Participants','Correct Event details','Attach Media']:
  ok=await click_name(page,nm,'11-owner-events/'+nm.lower().replace(' ','-')+'-dialog')
  if ok: await press_escape(page)
 # world explore/connections populated
 await nav(page,'World','12-owner-world/explore-final')
 await click_name(page,'Connections','12-owner-world/connections-final')
 # capture dark mode on populated screen
 try:
  await page.get_by_label('Switch to dark mode').click(timeout=1200); await page.wait_for_timeout(500); await shot(page,'17-visual/world-dark-mode')
  await page.get_by_label('Switch to light mode').click(timeout=1200); await page.wait_for_timeout(400); await shot(page,'17-visual/world-light-mode')
 except Exception as e: rec('theme toggle','error',str(e)[:150])
 await logout(page)
 flush(); await p.stop()
asyncio.run(main())
