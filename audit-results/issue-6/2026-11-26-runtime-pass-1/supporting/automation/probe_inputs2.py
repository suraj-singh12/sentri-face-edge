import asyncio
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 print(await page.locator('input').evaluate_all('(xs)=>xs.map((e,i)=>({i,type:e.type,ph:e.placeholder,val:e.value,role:e.getAttribute("role"),vis:!!e.offsetParent,cls:e.className.slice(0,50)}))'))
 print('combobox',await page.locator('[role=combobox]').count())
 print(await page.locator('[role=combobox]').evaluate_all('(xs)=>xs.map(e=>({val:e.value,ph:e.placeholder,cls:e.className.slice(0,40)}))'))
 await p.stop()
asyncio.run(main())
