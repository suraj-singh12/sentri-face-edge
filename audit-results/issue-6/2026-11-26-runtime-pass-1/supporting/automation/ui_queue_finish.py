import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 await shot(page,'32-queue-complete/ready-for-relations')
 try:
  await page.get_by_role('button',name='Continue to Relations').click(timeout=2000); await page.wait_for_timeout(800); await shot(page,'32-queue-complete/relations-step')
  rec('continue relations','ok')
 except Exception as e: rec('continue relations','error',str(e)[:180])
 print((await body(page))[-3000:])
 print('buttons',await page.locator('main button').all_inner_texts())
 # try complete with default retained/include decisions
 for label in ['Complete Event','Complete review','Finish Event','Save Event']:
  try:
   await page.get_by_role('button',name=re.compile(label,re.I)).first.click(timeout=1300); await page.wait_for_timeout(1200); await shot(page,'32-queue-complete/event-completed')
   rec('complete event','ok'); break
  except Exception: pass
 print((await body(page))[-2200:])
 flush(); await p.stop()
asyncio.run(main())
