import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 await shot(page,'32-queue-complete/review-start')
 # open person picker
 try:
  await page.get_by_role('button',name='Browse People').click(timeout=2000); await page.wait_for_timeout(700); await shot(page,'32-queue-complete/person-picker')
  print((await body(page))[:1800])
 except Exception as e: rec('browse people','error',str(e)[:200])
 # choose Asha Rao
 try:
  await page.get_by_text('Asha Rao',exact=True).last.click(timeout=2000); await page.wait_for_timeout(500); await shot(page,'32-queue-complete/person-selected')
 except Exception as e: rec('select asha','error',str(e)[:180])
 # accept selected person button variants
 for label in ['Accept selected person','Accept person','Accept','Use selected person']:
  try:
   await page.get_by_role('button',name=re.compile(label,re.I)).first.click(timeout=1200); await page.wait_for_timeout(700); await shot(page,'32-queue-complete/accept-clicked')
   rec('accept '+label,'ok'); break
  except Exception: pass
 print((await body(page))[:2500])
 # fill followup form if visible; inspect inputs/buttons
 print('buttons',await page.locator('main button').all_inner_texts())
 print('inputs',await page.locator('input').evaluate_all('(x)=>x.map(e=>({type:e.type,ph:e.placeholder,val:e.value}))'))
 flush(); await p.stop()
asyncio.run(main())
