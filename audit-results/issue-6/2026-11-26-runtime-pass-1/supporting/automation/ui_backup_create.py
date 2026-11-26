import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 try:
  await page.get_by_role('button',name='Create backup').last.click(timeout=1500); await page.wait_for_timeout(1800); await shot(page,'50-settings/after-create-backup')
  txt=await body(page); rec('create backup action','verified' if 'Backup' in txt[-1200:] and ('created' in txt[-1200:].lower() or 'complete' in txt[-1200:].lower() or 'safety copy' not in txt.lower()) else 'unclear',txt[-600:].replace('\n',' | '))
 except Exception as e: rec('create backup action','error',str(e)[:180])
 try:
  await page.get_by_role('button',name='Backups & restore').click(timeout=1500); await page.wait_for_timeout(800); await shot(page,'50-settings/backups-restore-section')
  txt=await body(page); rec('backups restore section','verified' if 'restore' in txt.lower() else 'unclear','section opened')
 except Exception as e: rec('backups restore section','error',str(e)[:180])
 print((await body(page))[-1800:])
 print('buttons',await page.locator('main button').all_inner_texts())
 flush(); await p.stop()
asyncio.run(main())
