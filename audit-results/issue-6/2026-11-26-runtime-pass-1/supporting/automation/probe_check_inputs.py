import asyncio
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 print(await page.locator('input,textarea').evaluate_all('(x)=>x.map((e,i)=>({i,tag:e.tagName,type:e.type,ph:e.placeholder,val:e.value,vis:!!e.offsetParent,role:e.getAttribute("role")}))'))
 print('selects',await page.locator('[role=combobox]').evaluate_all('(x)=>x.map((e,i)=>({i,val:e.value,ph:e.placeholder}))'))
 print('buttons',await page.locator('main button').all_inner_texts())
 await p.stop()
asyncio.run(main())
