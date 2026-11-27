import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect(); await nav(page,'People')
 try:
  await page.locator('button',has_text='Manual Audit Person').first.click(timeout=1500); await page.wait_for_timeout(700); await shot(page,'11-lifecycle/manual-person-profile')
  rec('open manual profile','ok')
 except Exception as e: rec('open manual profile','error',str(e)[:150])
 try:
  await page.get_by_role('button',name=re.compile('^Archive$')).click(timeout=1800); await page.wait_for_timeout(500); await shot(page,'11-lifecycle/archive-confirmation')
  txt=await body(page)
  rec('archive confirmation','verified' if 'Archive' in txt[-1000:] and ('Cancel' in txt[-1000:] or 'Confirm' in txt[-1000:]) else 'unclear',txt[-700:].replace('\n',' | '))
 except Exception as e: rec('archive confirmation','error',str(e)[:180])
 print((await body(page))[-1400:])
 print('buttons',await page.locator('button').evaluate_all('(x)=>x.map((e)=>({t:e.textContent.trim(),vis:!!e.offsetParent,dis:e.disabled})).filter(x=>x.vis).slice(-15)'))
 # confirm if explicit archive button in dialog
 try:
  btns=page.get_by_role('button',name=re.compile('Archive Person|Confirm archive|Archive$',re.I))
  await btns.last.click(timeout=1500); await page.wait_for_timeout(1000); await shot(page,'11-lifecycle/after-archive')
  txt=await body(page); rec('archive action','verified' if 'Archived' in txt or 'archived' in txt[-600:] else 'unclear',txt[-450:].replace('\n',' | '))
 except Exception as e: rec('archive action','error',str(e)[:180])
 print((await body(page))[-1000:])
 flush(); await p.stop()
asyncio.run(main())
