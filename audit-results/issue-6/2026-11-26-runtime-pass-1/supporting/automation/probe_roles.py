import asyncio
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 data=await page.locator('main button').evaluate_all('(xs)=>xs.slice(0,20).map(e=>({t:e.textContent.trim(),role:e.getAttribute("role"),aria:e.getAttribute("aria-selected"),cls:e.className.slice(0,40)}))')
 print(data)
 print('tabs',await page.locator('[role=tab]').all_inner_texts())
 await p.stop()
asyncio.run(main())
