import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 await login(page,'owner','<REDACTED_TEST_PASSWORD>')
 await nav(page,'Check a photo','50-check-photo/initial-owner')
 print('fileinputs',await page.locator('input[type=file]').count())
 try:
  await page.locator('input[type=file]').first.set_input_files('/tmp/sfe-fixtures/audit-face-2.png')
  rec('check file selected','ok')
 except Exception as e: rec('check file selected','error',str(e)[:180])
 for i in range(4):
  await page.wait_for_timeout(1100); await shot(page,f'50-check-photo/result-{i+1}')
  txt=await body(page)
  if any(x in txt.lower() for x in ['match','no reliable','unknown person','candidate']): break
 print((await body(page))[:2500])
 print('buttons',await page.locator('main button').all_inner_texts())
 flush(); await p.stop()
asyncio.run(main())
