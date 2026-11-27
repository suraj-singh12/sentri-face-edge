import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 # account menu theme control
 try:
  await page.locator('header button, nav button').first.click(timeout=1000)
 except Exception: pass
 try:
  await page.get_by_text('Audit Owner',exact=False).first.click(timeout=1200); await page.wait_for_timeout(400)
  await shot(page,'90-theme/account-menu-before')
  print((await body(page))[:1200])
 except Exception as e: print('menu err',str(e)[:160])
 # look for theme buttons/menu item
 for lab in ['Light mode','Dark mode','Appearance','Theme']:
  try:
   await page.get_by_text(lab,exact=True).last.click(timeout=900); await page.wait_for_timeout(500); await shot(page,'90-theme/after-'+lab.lower().replace(' ','-'))
   rec('theme toggle '+lab,'ok')
   break
  except Exception: pass
 txt=await body(page)
 print(txt[:1000]); print('theme',await page.evaluate('document.documentElement.getAttribute("data-mantine-color-scheme")'))
 flush(); await p.stop()
asyncio.run(main())
