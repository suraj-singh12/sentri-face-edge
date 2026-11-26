import asyncio
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 print(await page.locator('input').evaluate_all('(xs)=>xs.map(e=>({type:e.type,accept:e.accept,multiple:e.multiple,display:getComputedStyle(e).display,vis:getComputedStyle(e).visibility,cls:e.className.slice(0,40)}))'))
 print('file inputs',await page.locator('input[type=file]').count())
 await p.stop()
asyncio.run(main())
