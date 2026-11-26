import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 # ensure owner on Check Photo Audit Event detail
 await login(page,'owner','<REDACTED_TEST_PASSWORD>')
 txt=await body(page)
 if 'Attach Media' not in txt:
  await nav(page,'Events'); await page.locator('button',has_text='Check Photo Audit Event').first.click(); await page.wait_for_timeout(1000)
 await shot(page,'33-attach-real/event-detail-before')
 try:
  await page.locator('input[type=file]').first.set_input_files('/tmp/sfe-fixtures/audit-face-3.png')
  rec('attach real file input','ok')
 except Exception as e: rec('attach real file input','error',str(e)[:180])
 await page.wait_for_timeout(2500); await shot(page,'33-attach-real/scan-review-target-context')
 txt=await body(page)
 rec('F07/PR88 attach target context','verified' if 'Attaching media to Check Photo Audit Event' in txt else 'unclear',txt[txt.find('Attaching media'):txt.find('Attaching media')+120] if 'Attaching media' in txt else 'missing')
 # open group review
 try:
  await page.get_by_role('button',name=re.compile('^Review$')).last.click(timeout=2500); await page.wait_for_timeout(800); await shot(page,'33-attach-real/group-review')
  rec('attach real open review','ok')
 except Exception as e: rec('attach real open review','error',str(e)[:180])
 print((await body(page))[-2200:])
 print('buttons',await page.locator('main button').all_inner_texts())
 flush(); await p.stop()
asyncio.run(main())
