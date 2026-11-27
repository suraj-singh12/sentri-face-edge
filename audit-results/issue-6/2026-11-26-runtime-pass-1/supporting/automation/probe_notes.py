import asyncio,re
from ui_audit_lib import *
async def open_bilal(page):
 await nav(page,'People')
 await page.locator('button',has_text='Open profile').nth(1).click(); await page.wait_for_timeout(800)
async def main():
 p,b,ctx,page=await connect(); await login(page,'owner','<REDACTED_TEST_PASSWORD>'); await open_bilal(page)
 await page.get_by_role('button',name=re.compile('^Edit',re.I)).first.click(); await page.wait_for_timeout(400)
 print('menu text',(await body(page))[-1000:])
 try: await page.get_by_text('Edit notes',exact=True).last.click(timeout=1500)
 except Exception as e: print('editnotes err',e)
 await page.wait_for_timeout(700); await shot(page,'60-notes/editor-opened-probe')
 print('buttons',await page.locator('button').evaluate_all('(xs)=>xs.map((e,i)=>({i,t:e.textContent.trim(),aria:e.getAttribute("aria-label"),vis:!!e.offsetParent,disabled:e.disabled})).filter(x=>x.vis)'))
 print('inputs',await page.locator('input,textarea').evaluate_all('(xs)=>xs.map((e,i)=>({i,tag:e.tagName,type:e.type,ph:e.placeholder,val:e.value,vis:!!e.offsetParent})).filter(x=>x.vis)'))
 print((await body(page))[-2500:])
 await p.stop()
asyncio.run(main())
