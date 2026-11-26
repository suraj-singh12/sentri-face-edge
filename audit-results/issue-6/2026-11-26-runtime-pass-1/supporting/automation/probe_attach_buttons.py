import asyncio
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 print(await page.locator('main button').evaluate_all('(x)=>x.map((e,i)=>({i,t:e.textContent.trim(),dis:e.disabled,aria:e.getAttribute("aria-disabled"),cls:e.className,box:e.getBoundingClientRect().toJSON(),html:e.outerHTML.slice(0,220)}))'))
 await p.stop()
asyncio.run(main())
