import asyncio
from auditlib import *
async def main():
 p,b,ctx,page=await connect()
 await page.goto(BASE); await page.wait_for_timeout(1000)
 if 'Create the owner account' in await body(page):
  await page.locator('input').nth(0).fill('owner')
  await page.locator('input').nth(1).fill('Audit Owner')
  await page.locator('input[type=password]').nth(0).fill('<REDACTED_TEST_PASSWORD>')
  await page.locator('input[type=password]').nth(1).fill('<REDACTED_TEST_PASSWORD>')
  await shot(page,'00-setup/owner-create')
  await page.get_by_role('button',name='Create account').click()
  await page.wait_for_timeout(3000)
 await shot(page,'00-setup/post-signin')
 print(await body(page))
 print('buttons',await page.locator('button').all_inner_texts())
 await p.stop()
asyncio.run(main())
