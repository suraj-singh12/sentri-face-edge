import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect(); await nav(page,'Settings'); await page.wait_for_timeout(700); await shot(page,'50-settings/settings-home')
 txt=await body(page); rec('settings home runtime','verified' if 'Settings' in txt else 'unclear','settings visible')
 print(txt[-2200:])
 print('buttons',await page.locator('main button').all_inner_texts())
 # capture backup now dialog/banner flow
 try:
  await page.get_by_role('button',name='Back up now').first.click(timeout=1500); await page.wait_for_timeout(800); await shot(page,'50-settings/backup-now-flow')
  txt=await body(page); rec('backup now visible flow','verified' if 'Back up' in txt[-1500:] or 'backup' in txt[-1500:].lower() else 'unclear',txt[-700:].replace('\n',' | '))
 except Exception as e: rec('backup now visible flow','error',str(e)[:180])
 print((await body(page))[-1800:])
 flush(); await p.stop()
asyncio.run(main())
