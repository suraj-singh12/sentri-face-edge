import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 # assumes modal open; fill first two text fields as name/rank and controls
 try:
  inputs=page.locator('input')
  await inputs.nth(3).fill('Manual Audit Person')
  await inputs.nth(4).fill('Analyst')
  await inputs.nth(5).click(); await page.keyboard.type('India'); await page.keyboard.press('Enter')
  await inputs.nth(11).fill('Audit Lab')
  c=inputs.nth(12); await c.click(); await page.keyboard.press('1'); await page.keyboard.press('Enter'); await page.wait_for_timeout(200)
  await inputs.nth(13).fill('Manual Add Audit')
  await page.locator('textarea').first.fill('Manual add without photo audit note.')
  await shot(page,'10-people/add-without-photo-filled')
  rec('manual add fields','ok','count='+await c.input_value())
 except Exception as e: rec('manual add fields','error',str(e)[:180])
 try:
  await page.get_by_role('button',name='Create person').click(timeout=1800); await page.wait_for_timeout(1200); await shot(page,'10-people/after-create-without-photo')
  txt=await body(page)
  rec('manual add without photo','verified' if 'Manual Audit Person' in txt and ('Person added' in txt or 'created' in txt.lower()) else 'unclear',txt[-450:].replace('\n',' | '))
 except Exception as e: rec('manual add without photo','error',str(e)[:180])
 print((await body(page))[-1200:])
 flush(); await p.stop()
asyncio.run(main())
