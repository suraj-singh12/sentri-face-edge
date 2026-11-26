import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 # assumes notes editor is open from probe; if not reopen
 txt=await body(page)
 if 'Selected mentions' not in txt:
  await login(page,'owner','<REDACTED_TEST_PASSWORD>'); await nav(page,'People'); await page.locator('button',has_text='Open profile').nth(1).click(); await page.wait_for_timeout(700)
  await page.get_by_role('button',name=re.compile('^Edit',re.I)).first.click(); await page.wait_for_timeout(300); await page.get_by_text('Edit notes',exact=True).last.click(); await page.wait_for_timeout(600)
 await shot(page,'60-notes/before-empty-selected-mention')
 try:
  await page.locator('textarea').first.fill('')
  await shot(page,'60-notes/note-emptied-chip-still-selected')
  rec('empty note edit','ok')
 except Exception as e: rec('empty note edit','error',str(e)[:180])
 try:
  await page.get_by_role('button',name='Save notes').click(timeout=1800); await page.wait_for_timeout(1400); await shot(page,'60-notes/after-empty-save')
  txt=await body(page)
  rec('F20/PR85 empty note retirement','verified' if 'No notes added.' in txt else 'unclear','No notes added visible; associations text='+('Associations' in txt and txt[txt.find('Associations'):txt.find('Associations')+30] or 'n/a'))
 except Exception as e: rec('empty note save','error',str(e)[:200])
 print((await body(page))[-1800:])
 flush(); await p.stop()
asyncio.run(main())
