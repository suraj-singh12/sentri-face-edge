import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 # capture enabled/disabled review actions precondition
 attrs=await page.locator('main button').evaluate_all('(xs)=>xs.map(e=>({t:e.textContent.trim(),disabled:e.disabled}))')
 open('/home/ubuntu/issue6-runtime-audit/queue-button-states.json','w').write(__import__('json').dumps(attrs,indent=2))
 await shot(page,'31-queue-review/pending-group-precondition')
 for action,folder in [('Discard Event','event'),('Discard session','session'),('Discard','group')]:
  try:
   # exact first/last selection: group discard is last Discard
   if action=='Discard': loc=page.get_by_role('button',name='Discard').last
   else: loc=page.get_by_role('button',name=re.compile('^'+re.escape(action)+'$',re.I)).first
   await loc.click(timeout=2000); await page.wait_for_timeout(600)
   await shot(page,f'31-queue-review/{folder}-discard-confirmation')
   txt=await body(page)
   rec('PR86 '+action+' confirmation','verified' if 'confirm' in txt.lower() or 'discard' in txt.lower() and 'cancel' in txt.lower() else 'unclear','dialog/cancel visible')
   # cancel dialog if possible
   try: await page.get_by_role('button',name=re.compile('^Cancel$',re.I)).last.click(timeout=1200); await page.wait_for_timeout(400)
   except Exception: await page.keyboard.press('Escape'); await page.wait_for_timeout(300)
   await shot(page,f'31-queue-review/{folder}-discard-cancelled')
  except Exception as e: rec('destructive '+action,'error',str(e)[:200])
 # open group review
 try:
  await page.get_by_role('button',name=re.compile('^Review$')).last.click(timeout=2000); await page.wait_for_timeout(800)
  await shot(page,'31-queue-review/group-review-open')
  print((await body(page))[:2500])
  rec('group review open','ok')
 except Exception as e: rec('group review open','error',str(e)[:200])
 flush(); await p.stop()
asyncio.run(main())
