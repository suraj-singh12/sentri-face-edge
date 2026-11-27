import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 await page.keyboard.press('Escape'); await page.wait_for_timeout(300)
 # ensure on event detail
 txt=await body(page)
 if 'Morning Audit Briefing' not in txt or 'Attach Media' not in txt:
  await nav(page,'Events')
  await page.get_by_text('Morning Audit Briefing').first.click(); await page.wait_for_timeout(700)
 await shot(page,'30-attach-media/before-file-selection')
 try:
  await page.locator('input[type=file]').first.set_input_files('/tmp/sfe-fixtures/audit-face-1.png')
  rec('attach file input','ok')
 except Exception as e: rec('attach file input','error',str(e)[:200])
 for i,w in enumerate([1000,1500,2000,2500]):
  await page.wait_for_timeout(w); await shot(page,f'30-attach-media/progress-{i+1}')
  txt=await body(page)
  print('STATE',i,txt[:700].replace('\n',' | '))
  if 'Event 1 of 1' in txt or 'Attaching media' in txt or 'Review' in txt and 'face' in txt.lower(): break
 # Try opening/selecting pending group/review visible buttons/cards
 for label in ['Select','Review','Start review','1 face','Scan']:
  try:
   await page.get_by_role('button',name=re.compile(label,re.I)).first.click(timeout=1000); await page.wait_for_timeout(700); await shot(page,'30-attach-media/after-'+label.lower().replace(' ','-'))
   rec('attach click '+label,'ok')
   break
  except Exception: pass
 print((await body(page))[:2500])
 flush(); await p.stop()
asyncio.run(main())
