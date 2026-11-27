import asyncio
from auditlib import *
async def main():
 p,b,ctx,page=await connect()
 await page.goto(BASE); await page.wait_for_timeout(1000)
 if 'Skip for now' in await body(page):
  await page.locator('input[type=checkbox]').check()
  await shot(page,'00-setup/skip-safety-acknowledged')
  await page.get_by_role('button',name='Skip for now').click(); await page.wait_for_timeout(2500)
 await shot(page,'00-setup/after-onboarding')
 print(await body(page))
 print('buttons',await page.locator('button').all_inner_texts())
 await p.stop()
asyncio.run(main())
