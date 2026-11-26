import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 try:
  await page.get_by_role('button',name=re.compile('Accept 1 as Asha Rao',re.I)).click(timeout=2000); await page.wait_for_timeout(800); await shot(page,'32-queue-complete/followup-form')
  rec('accept asha','ok')
 except Exception as e: rec('accept asha','error',str(e)[:180])
 print((await body(page))[-3000:])
 print('inputs',await page.locator('input,textarea').evaluate_all('(x)=>x.map((e,i)=>({i,tag:e.tagName,type:e.type,ph:e.placeholder,val:e.value,vis:!!e.offsetParent}))'))
 print('buttons',await page.locator('main button').all_inner_texts())
 flush(); await p.stop()
asyncio.run(main())
