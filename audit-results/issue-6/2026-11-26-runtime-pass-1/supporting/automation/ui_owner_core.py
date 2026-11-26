import asyncio,re,os,json
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 # assume owner still signed in; close any menu/modal
 await page.keyboard.press('Escape'); await page.wait_for_timeout(300)
 # core nav captures
 for n,sp in [('People','20-owner-populated/people-list'),('Events','20-owner-populated/events-list'),('World','20-owner-populated/world-explore'),('Review photos','20-owner-populated/review-home'),('Check a photo','20-owner-populated/check-home'),('Settings','20-owner-populated/settings-home')]:
  await nav(page,n,sp)
 # world connections populated
 await nav(page,'World')
 try:
  await page.get_by_role('button',name='Connections').click(timeout=2000); await page.wait_for_timeout(900); await shot(page,'20-owner-populated/world-connections')
  rec('world connections','ok')
 except Exception as e: rec('world connections','error',str(e)[:160])
 # People -> Bilal using card open control (button text Open profile within card)
 await nav(page,'People')
 try:
  card=page.locator('main').get_by_text('Bilal Khan',exact=True).first
  await card.scroll_into_view_if_needed(timeout=2000)
  # click nearest card's Open profile if possible, fallback first Open profile after text
  await page.locator('button',has_text='Open profile').nth(1).click(timeout=2500)
  await page.wait_for_timeout(1000)
 except Exception as e:
  rec('open bilal fallback','error',str(e)[:150])
  try: await page.get_by_text('Bilal Khan',exact=True).first.click(timeout=1500); await page.wait_for_timeout(1000)
  except Exception as e2: rec('open bilal text','error',str(e2)[:150])
 await shot(page,'21-owner-bilal/profile-overview')
 txt=await body(page)
 rec('bilal profile opened','verified' if 'Bilal Khan' in txt and 'Identity Information' in txt else 'unclear',txt[:100].replace('\n',' '))
 # long note
 if await click_name(page,'Read full note','21-owner-bilal/long-note-expanded'):
  txt=await body(page); rec('F05 long note','verified' if 'Show less' in txt else 'unclear','expanded state')
 # all profile tabs
 for tab in ['Photos','Sightings','Events','Associations','Activity']:
  try:
   await page.get_by_role('tab',name=re.compile(tab,re.I)).click(timeout=2000); await page.wait_for_timeout(550)
   await shot(page,'21-owner-bilal/tab-'+tab.lower())
   rec('bilal '+tab,'ok')
  except Exception as e: rec('bilal '+tab,'error',str(e)[:150])
 # return overview, edit notes drawer
 try:
  await page.get_by_role('tab',name='Overview').click(timeout=1200); await page.wait_for_timeout(300)
 except Exception: pass
 try:
  # click Edit split button then menu item Notes/Edit Notes if present
  await page.get_by_role('button',name=re.compile('^Edit',re.I)).first.click(timeout=1800); await page.wait_for_timeout(350)
  await shot(page,'21-owner-bilal/edit-menu')
  clicked=False
  for label in ['Edit Notes','Notes']:
   try: await page.get_by_text(label,exact=True).last.click(timeout=1000); clicked=True; break
   except Exception: pass
  if clicked:
   await page.wait_for_timeout(700); await shot(page,'21-owner-bilal/notes-editor-mentions')
   txt=await body(page); rec('F20/PR85 mention chips','verified' if '@Asha Rao' in txt else 'unclear','mention visible in editor')
   # cancel without altering fixture
   await click_name(page,'Cancel','21-owner-bilal/notes-editor-cancel')
  else: rec('notes editor open','error','menu item not found')
 except Exception as e: rec('notes editor','error',str(e)[:180])
 # graph and keyboard
 if await click_name(page,'Open Person Graph','22-owner-graph/bilal-graph'):
  try:
   await page.get_by_label('Refresh Person Graph').click(timeout=1800); await page.wait_for_timeout(200)
   for _ in range(4): await page.keyboard.press('Tab'); await page.wait_for_timeout(80)
   await shot(page,'22-owner-graph/edge-keyboard-focus')
   await page.keyboard.press('Enter'); await page.wait_for_timeout(700)
   await shot(page,'22-owner-graph/edge-evidence-inspector')
   txt=await body(page)
   rec('F02/PR88 graph keyboard edge','verified' if 'Evidence types' in txt or 'Provenance summary' in txt else 'unclear','Enter opened inspector')
  except Exception as e: rec('graph keyboard','error',str(e)[:200])
 # events details/corrections
 await nav(page,'Events','23-owner-events/list')
 try:
  await page.get_by_text('Morning Audit Briefing').first.click(timeout=2500); await page.wait_for_timeout(800); await shot(page,'23-owner-events/morning-detail')
 except Exception as e: rec('open morning event','error',str(e)[:160])
 for nm in ['Correct Event','Correct Participants','Correct Relations']:
  ok=await click_name(page,nm,'23-owner-events/'+nm.lower().replace(' ','-'))
  if ok:
   txt=await body(page); rec('dialog '+nm,'verified' if nm in txt else 'unclear','dialog visible')
   await press_escape(page)
 # attach media click: capture whatever appears after click
 try:
  await page.get_by_role('button',name='Attach Media').click(timeout=2000); await page.wait_for_timeout(1000); await shot(page,'23-owner-events/attach-media-after-click')
  txt=await body(page); rec('attach media entry','verified' if 'Choose' in txt or 'Upload' in txt or 'Attach' in txt else 'unclear',txt[:120].replace('\n',' '))
 except Exception as e: rec('attach media entry','error',str(e)[:180])
 flush(); await p.stop()
asyncio.run(main())
