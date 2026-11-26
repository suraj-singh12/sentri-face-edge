import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 # assume group review open
 try:
  await page.get_by_role('button',name='Choose a person to accept').click(timeout=1800); await page.wait_for_timeout(500); await shot(page,'33-attach-real/person-chooser')
  rec('attach real chooser','ok')
 except Exception as e: rec('attach real chooser','error',str(e)[:150])
 print((await body(page))[-1400:])
 print('inputs',await page.locator('input').evaluate_all('(x)=>x.map((e,i)=>({i,val:e.value,ph:e.placeholder,vis:!!e.offsetParent,role:e.getAttribute("role")})).filter(x=>x.vis)'))
 print('buttons',await page.locator('main button').all_inner_texts())
 # select person by text if visible; otherwise open combobox then choose
 try:
  await page.get_by_text('New Audit Person',exact=True).last.click(timeout=1500)
 except Exception:
  try:
   combo=page.locator('input[role=combobox]').last
   await combo.click(timeout=1200); await page.wait_for_timeout(300)
   await page.get_by_text('New Audit Person',exact=True).last.click(timeout=1500)
  except Exception as e: rec('attach real select person','error',str(e)[:160])
 await page.wait_for_timeout(400); await shot(page,'33-attach-real/person-selected')
 txt=await body(page)
 rec('attach real select person','verified' if 'Accept 1 as New Audit Person' in txt else 'unclear',txt[-500:].replace('\n',' | '))
 print('buttons2',await page.locator('main button').all_inner_texts())
 # click accept
 try:
  await page.get_by_role('button',name=re.compile('Accept .*New Audit Person')).click(timeout=1800); await page.wait_for_timeout(700); await shot(page,'33-attach-real/followup-details')
  rec('attach real accept','ok')
 except Exception as e: rec('attach real accept','error',str(e)[:180])
 print((await body(page))[-1800:])
 print('inputs3',await page.locator('input,textarea').evaluate_all('(x)=>x.map((e,i)=>({i,type:e.type,val:e.value,ph:e.placeholder,vis:!!e.offsetParent,role:e.getAttribute("role")})).filter(x=>x.vis)'))
 print('buttons3',await page.locator('main button').all_inner_texts())
 flush(); await p.stop()
asyncio.run(main())
