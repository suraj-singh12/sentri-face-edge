import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 # fill event details modal if still open
 try:
  await page.locator('input').nth(2).fill('Check Photo Audit Event')
  await page.locator('input').nth(6).fill('Audit Lab')
  await page.locator('textarea').first.fill('Event note for check-photo audit.')
  await shot(page,'50-check-photo/event-details-filled')
  await page.get_by_role('button',name='Confirm Event').click(timeout=1800); await page.wait_for_timeout(900); await shot(page,'50-check-photo/event-details-confirmed')
  rec('check event details','ok')
 except Exception as e: rec('check event details','error',str(e)[:200])
 print((await body(page))[-2200:])
 print('inputs',await page.locator('input,textarea').evaluate_all('(x)=>x.map((e,i)=>({i,type:e.type,ph:e.placeholder,val:e.value,vis:!!e.offsetParent,role:e.getAttribute("role")}))'))
 print('buttons',await page.locator('main button').all_inner_texts())
 # choose new person path
 try:
  await page.get_by_role('button',name=re.compile('New Person',re.I)).first.click(timeout=1800); await page.wait_for_timeout(700); await shot(page,'50-check-photo/new-person-form')
  rec('new person path','ok')
 except Exception as e: rec('new person path','error',str(e)[:180])
 print((await body(page))[-2500:])
 print('inputs2',await page.locator('input,textarea').evaluate_all('(x)=>x.map((e,i)=>({i,type:e.type,ph:e.placeholder,val:e.value,vis:!!e.offsetParent,role:e.getAttribute("role")}))'))
 flush(); await p.stop()
asyncio.run(main())
