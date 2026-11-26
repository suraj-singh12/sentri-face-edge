import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 try:
  inputs=page.locator('input')
  ctry=inputs.nth(5)
  await ctry.click(); await page.keyboard.press('Control+A'); await page.keyboard.type('India'); await page.wait_for_timeout(400)
  await shot(page,'10-people/country-dropdown-india')
  try: await page.get_by_role('option',name='India').click(timeout=1200)
  except Exception: await page.get_by_text('India',exact=True).last.click(timeout=1200)
  rec('manual add country select','ok')
 except Exception as e: rec('manual add country select','error',str(e)[:180])
 print('vals',await page.locator('input').evaluate_all('(x)=>x.map((e,i)=>({i,v:e.value,vis:!!e.offsetParent})).filter(x=>x.vis)'))
 try:
  await page.get_by_role('button',name='Create person').click(timeout=1800); await page.wait_for_timeout(1300); await shot(page,'10-people/after-create-without-photo-retry')
  txt=await body(page)
  rec('manual add without photo','verified' if 'Manual Audit Person' in txt and ('Person added' in txt or 'created' in txt.lower() or 'Open profile' in txt[-900:]) else 'unclear',txt[-500:].replace('\n',' | '))
 except Exception as e: rec('manual add without photo retry','error',str(e)[:180])
 print((await body(page))[-1400:])
 flush(); await p.stop()
asyncio.run(main())
