import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect(); await nav(page,'People')
 try:
  await page.get_by_role('button',name=re.compile('Add without photo',re.I)).first.click(timeout=1200); await page.wait_for_timeout(500); await shot(page,'10-people/add-person-modal-current')
 except Exception as e: print('open err',e)
 print('inputs',await page.locator('input,textarea').evaluate_all('(x)=>x.map((e,i)=>({i,type:e.type,val:e.value,ph:e.placeholder,vis:!!e.offsetParent,role:e.getAttribute("role"),label:e.getAttribute("aria-label")})).filter(x=>x.vis)'))
 print('buttons',await page.locator('main button,[role=dialog] button').evaluate_all('(x)=>x.map((e,i)=>({i,t:e.textContent.trim(),vis:!!e.offsetParent,dis:e.disabled})).filter(x=>x.vis)'))
 print((await body(page))[-1600:])
 await p.stop()
asyncio.run(main())
