import asyncio
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect(); print((await body(page))[:3000]); print('url',page.url)
 print('navbuttons',await page.locator('header button').all_inner_texts())
 print('main first buttons',(await page.locator('main button').all_inner_texts())[:30])
 await p.stop()
asyncio.run(main())
