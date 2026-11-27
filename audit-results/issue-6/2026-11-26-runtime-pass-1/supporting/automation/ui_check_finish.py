import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 try:
  ins=page.locator('input')
  await ins.nth(2).fill('Analyst')
  await ins.nth(3).fill('New Audit Person')
  await ins.nth(4).fill('India'); await page.wait_for_timeout(300)
  try: await page.get_by_text('India',exact=True).last.click(timeout=800)
  except Exception: pass
  await ins.nth(8).fill('1')
  await page.locator('textarea').first.fill('Created through Check a photo audit workflow.')
  await shot(page,'50-check-photo/new-person-filled')
  await page.get_by_role('button',name=re.compile('^Confirm$')).first.click(timeout=2000); await page.wait_for_timeout(1200); await shot(page,'50-check-photo/new-person-confirmed')
  rec('fill/confirm new person','ok')
 except Exception as e: rec('fill/confirm new person','error',str(e)[:220])
 print((await body(page))[-2500:])
 # complete review if decision resolved
 try:
  await page.get_by_role('button',name=re.compile('Complete Review',re.I)).first.click(timeout=2000); await page.wait_for_timeout(1400); await shot(page,'50-check-photo/review-completed')
  rec('complete check review','ok')
 except Exception as e: rec('complete check review','error',str(e)[:200])
 print((await body(page))[-2000:])
 flush(); await p.stop()
asyncio.run(main())
