import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect(); await nav(page,'World'); await page.wait_for_timeout(700); await shot(page,'40-world/populated-explore')
 txt=await body(page); rec('world populated explore','verified' if 'Asha Rao' in txt or 'Manual Audit Person' in txt or 'Connections' in txt else 'unclear',txt[-450:].replace('\n',' | '))
 print('buttons',(await page.locator('main button').all_inner_texts())[:50])
 # click connections tab/control
 try:
  await page.get_by_text('Connections',exact=True).last.click(timeout=1500); await page.wait_for_timeout(800); await shot(page,'40-world/populated-connections')
  txt=await body(page); rec('world connections populated','verified' if 'Asha Rao' in txt or 'Bilal Khan' in txt else 'unclear',txt[-500:].replace('\n',' | '))
 except Exception as e: rec('world connections populated','error',str(e)[:180])
 print((await body(page))[-1600:])
 flush(); await p.stop()
asyncio.run(main())
