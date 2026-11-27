import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 # fill count and sighting note in followup
 try:
  count=page.locator('input[placeholder="Select count"]').first
  await count.click(timeout=1500); await page.keyboard.press('1'); await page.keyboard.press('Enter'); await page.wait_for_timeout(250)
  if (await count.input_value()) not in ('1','1 person'):
   await count.fill('1')
  await page.locator('textarea').first.fill('Attached media audit sighting note.')
  rec('attach followup fields','ok',await count.input_value())
 except Exception as e: rec('attach followup fields','error',str(e)[:180])
 try:
  await page.get_by_role('button',name='Confirm').click(timeout=1800); await page.wait_for_timeout(1000); await shot(page,'33-attach-real/face-resolved')
  rec('attach confirm face','ok')
 except Exception as e: rec('attach confirm face','error',str(e)[:180])
 txt=await body(page)
 rec('attach face resolved state','verified' if '1 of 1 faces resolved' in txt else 'unclear',txt[txt.find('0 of 1') if '0 of 1' in txt else txt.find('1 of 1'):][:160] if 'of 1' in txt else 'missing')
 print((await body(page))[-1800:])
 print('buttons',await page.locator('main button').all_inner_texts())
 # continue relations and complete
 try:
  await page.get_by_role('button',name='Continue to Relations').click(timeout=1800); await page.wait_for_timeout(800); await shot(page,'33-attach-real/relations-step')
  rec('attach relations step','ok')
 except Exception as e: rec('attach relations step','error',str(e)[:180])
 print((await body(page))[-1800:])
 print('buttonsR',await page.locator('main button').all_inner_texts())
 try:
  await page.get_by_role('button',name=re.compile('Complete Review|Complete review')).click(timeout=1800); await page.wait_for_timeout(1500); await shot(page,'33-attach-real/after-complete-review')
  txt=await body(page)
  rec('attach complete review','verified' if 'Review completed' in txt or 'Face decision saved' in txt else 'unclear',txt[-550:].replace('\n',' | '))
 except Exception as e: rec('attach complete review','error',str(e)[:180])
 print((await body(page))[-1800:])
 flush(); await p.stop()
asyncio.run(main())
