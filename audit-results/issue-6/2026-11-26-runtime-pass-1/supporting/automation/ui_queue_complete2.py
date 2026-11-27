import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 # change people picker filter from biometric-only to all if possible
 try:
  await page.get_by_role('combobox').click(timeout=1500); await page.wait_for_timeout(400); await shot(page,'32-queue-complete/person-picker-filter-open')
  print((await body(page))[-1200:])
 except Exception as e: rec('picker filter open','error',str(e)[:180])
 for label in ['All Profiles','All people','All','No Photos']:
  try:
   await page.get_by_text(label,exact=True).last.click(timeout=900); await page.wait_for_timeout(500); await shot(page,'32-queue-complete/person-picker-filter-'+label.lower().replace(' ','-'))
   rec('picker filter '+label,'ok'); break
  except Exception: pass
 print((await body(page))[-1800:])
 print('buttons',await page.locator('main button').all_inner_texts())
 flush(); await p.stop()
asyncio.run(main())
