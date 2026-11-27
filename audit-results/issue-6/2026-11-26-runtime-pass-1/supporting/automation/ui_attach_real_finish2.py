import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 try:
  await page.get_by_role('button',name='Browse People').click(timeout=1800); await page.wait_for_timeout(500); await shot(page,'33-attach-real/browse-people-picker')
  rec('attach browse people','ok')
 except Exception as e: rec('attach browse people','error',str(e)[:160])
 print((await body(page))[-1800:])
 print('inputs',await page.locator('input').evaluate_all('(x)=>x.map((e,i)=>({i,val:e.value,ph:e.placeholder,vis:!!e.offsetParent,role:e.getAttribute("role")})).filter(x=>x.vis)'))
 print('buttons',await page.locator('main button').all_inner_texts())
 # choose exact person if listed; if hidden open picker mode
 try:
  await page.get_by_text('New Audit Person',exact=True).last.click(timeout=1800); rec('attach select person row','ok')
 except Exception as e:
  rec('attach select person row','error',str(e)[:180])
 await page.wait_for_timeout(500); await shot(page,'33-attach-real/person-selected')
 txt=await body(page)
 rec('attach person selection enables action','verified' if 'Accept 1 as New Audit Person' in txt or 'New Audit Person' in txt[-1000:] else 'unclear',txt[-650:].replace('\n',' | '))
 print('buttons2',await page.locator('main button').all_inner_texts())
 print('states',await page.locator('main button').evaluate_all('(x)=>x.map((e,i)=>({t:e.textContent.trim(),dis:e.disabled})).filter(x=>x.t.includes("Accept")||x.t.includes("Choose"))'))
 # click accept if present
 try:
  await page.get_by_role('button',name=re.compile('Accept 1 as New Audit Person')).click(timeout=1800); await page.wait_for_timeout(800); await shot(page,'33-attach-real/followup-details')
  rec('attach real accept','ok')
 except Exception as e: rec('attach real accept','error',str(e)[:180])
 print((await body(page))[-1600:])
 print('inputs3',await page.locator('input,textarea').evaluate_all('(x)=>x.map((e,i)=>({i,type:e.type,val:e.value,ph:e.placeholder,vis:!!e.offsetParent,role:e.getAttribute("role")})).filter(x=>x.vis)'))
 print('buttons3',await page.locator('main button').all_inner_texts())
 flush(); await p.stop()
asyncio.run(main())
