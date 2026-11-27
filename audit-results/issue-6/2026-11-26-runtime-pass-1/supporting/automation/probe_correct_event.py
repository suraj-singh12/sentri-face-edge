import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect(); await login(page,'owner','<REDACTED_TEST_PASSWORD>'); await nav(page,'Events')
 try:
  await page.get_by_text('Afternoon Audit',exact=True).first.click(timeout=2000); await page.wait_for_timeout(800); await shot(page,'70-stale/afternoon-detail')
  await page.get_by_role('button',name='Correct Event').click(timeout=1800); await page.wait_for_timeout(600); await shot(page,'70-stale/correct-event-open')
 except Exception as e: print('open err',e)
 print('inputs',await page.locator('input,textarea').evaluate_all('(x)=>x.map((e,i)=>({i,type:e.type,ph:e.placeholder,val:e.value,vis:!!e.offsetParent,role:e.getAttribute("role")})).filter(x=>x.vis)'))
 print('buttons',await page.locator('button').evaluate_all('(x)=>x.map((e,i)=>({i,t:e.textContent.trim(),vis:!!e.offsetParent,disabled:e.disabled})).filter(x=>x.vis)'))
 print((await body(page))[-1800:])
 await p.stop()
asyncio.run(main())
