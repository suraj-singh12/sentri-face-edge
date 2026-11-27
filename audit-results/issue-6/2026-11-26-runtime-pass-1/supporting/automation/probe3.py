import asyncio
from auditlib import *
async def main():
 p,b,ctx,page=await connect(); await page.goto(BASE); await page.wait_for_timeout(800)
 await page.get_by_role('button',name='Add without photo').click(); await page.wait_for_timeout(500)
 await shot(page,'01-people/add-person-dialog-empty')
 print(await body(page))
 print('inputs',await page.locator('input').evaluate_all('(x)=>x.map(e=>({ph:e.placeholder,type:e.type,val:e.value}))'))
 print('buttons',await page.locator('button').all_inner_texts())
 await p.stop()
asyncio.run(main())
