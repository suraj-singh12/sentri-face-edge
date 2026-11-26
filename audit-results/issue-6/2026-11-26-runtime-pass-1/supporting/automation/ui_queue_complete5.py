import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 try:
  await page.get_by_placeholder('Select count').click(timeout=1500); await page.wait_for_timeout(300); await shot(page,'32-queue-complete/count-options')
  await page.get_by_role('option',name='2').click(timeout=1500)
 except Exception as e:
  rec('count select','error',str(e)[:180])
  try: await page.get_by_placeholder('Select count').fill('2')
  except Exception as e2: rec('count fill fallback','error',str(e2)[:150])
 try:
  await page.locator('textarea').first.fill('Sighting note added during attach-media review with @Bilal Khan.')
 except Exception: pass
 await shot(page,'32-queue-complete/followup-filled')
 try:
  await page.get_by_role('button',name=re.compile('^Confirm$')).click(timeout=1800); await page.wait_for_timeout(1200); await shot(page,'32-queue-complete/after-confirm')
  rec('confirm followup','ok')
 except Exception as e: rec('confirm followup','error',str(e)[:200])
 print((await body(page))[-3000:])
 print('buttons',await page.locator('main button').all_inner_texts())
 flush(); await p.stop()
asyncio.run(main())
