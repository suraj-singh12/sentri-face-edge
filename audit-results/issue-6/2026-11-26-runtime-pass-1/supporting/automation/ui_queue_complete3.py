import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 try:
  await page.get_by_text('No Biometric Profiles',exact=True).last.click(timeout=1500); await page.wait_for_timeout(600); await shot(page,'32-queue-complete/person-picker-no-biometric')
  print((await body(page))[-1500:])
 except Exception as e: rec('choose no biometric','error',str(e)[:180])
 # choose Asha if visible
 try:
  await page.get_by_text('Asha Rao',exact=True).last.click(timeout=1800); await page.wait_for_timeout(500); await shot(page,'32-queue-complete/person-selected-asha')
  rec('select Asha','ok')
 except Exception as e: rec('select Asha','error',str(e)[:180])
 # inspect buttons
 print('buttons',await page.locator('main button').all_inner_texts())
 # accept person using choose button
 for label in ['Choose a person to accept','Accept selected person','Accept']:
  try:
   await page.get_by_role('button',name=re.compile('^'+re.escape(label)+'$',re.I)).first.click(timeout=1300); await page.wait_for_timeout(700); await shot(page,'32-queue-complete/accept-asha')
   rec('accept','ok'); break
  except Exception: pass
 print((await body(page))[-2500:])
 print('inputs',await page.locator('input').evaluate_all('(x)=>x.map(e=>({type:e.type,ph:e.placeholder,val:e.value,vis:!!e.offsetParent}))'))
 flush(); await p.stop()
asyncio.run(main())
