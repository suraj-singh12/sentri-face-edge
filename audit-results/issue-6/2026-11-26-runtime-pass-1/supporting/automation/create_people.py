import asyncio
from auditlib import *
people=[('Asha Rao','Analyst','India','Audit Lab','2','Morning Audit Briefing'),('Bilal Khan','Analyst','India','Audit Lab','2','Morning Audit Briefing'),('Carla Mendes','Analyst','India','Audit Lab','1','Morning Audit Briefing')]
async def add(page,x):
 name,rank,country,place,count,occ=x
 await page.get_by_role('button',name='Add without photo').click(); await page.wait_for_timeout(300)
 ins=page.locator('input')
 # visible modal fields are after first three app inputs; use labels where possible by ordered indexes observed
 await ins.nth(3).fill(rank); await ins.nth(4).fill(name); await ins.nth(5).fill(country); await page.keyboard.press('Enter')
 await ins.nth(9).fill('2026-11-21'); await ins.nth(10).fill('09:30'); await ins.nth(11).fill(place)
 await ins.nth(12).click(); await page.wait_for_timeout(200); await page.get_by_text(count,exact=True).last.click()
 await ins.nth(13).fill(occ)
 await page.get_by_role('button',name='Create person').click(); await page.wait_for_timeout(1200)
async def main():
 p,b,ctx,page=await connect(); await page.goto(BASE); await page.wait_for_timeout(1200)
 for x in people:
  await add(page,x)
 await shot(page,'01-people/list-populated')
 print(await body(page)); await p.stop()
asyncio.run(main())
