import asyncio
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect(); print((await body(page))[:2500]); print('buttons',await page.locator('main button').all_inner_texts()); print('inputs',await page.locator('input').evaluate_all('(x)=>x.map(e=>({type:e.type,ph:e.placeholder,val:e.value}))'))
 await p.stop()
asyncio.run(main())
