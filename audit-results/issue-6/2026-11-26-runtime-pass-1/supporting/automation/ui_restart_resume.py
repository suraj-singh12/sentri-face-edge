import asyncio,re
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 try:
  await page.reload(); await page.wait_for_timeout(1200); await shot(page,'80-restart/after-server-restart-reload')
  rec('browser reload after server restart','ok')
 except Exception as e: rec('browser reload after server restart','error',str(e)[:180])
 # sign in again if needed, then inspect persisted records
 try:
  if 'Sign in' in (await body(page)) or 'Username' in (await body(page)):
   await login(page,'owner','<REDACTED_TEST_PASSWORD>')
 except Exception as e: rec('post-restart login','error',str(e)[:180])
 await shot(page,'80-restart/post-restart-shell')
 txt=await body(page)
 rec('post-restart data shell','verified' if 'You have changes since your last backup' in txt else 'unclear','shell visible')
 await nav(page,'People'); await page.wait_for_timeout(600); await shot(page,'80-restart/people-persisted')
 txt=await body(page)
 rec('post-restart people persistence','verified' if all(n in txt for n in ['Asha Rao','Bilal Khan','New Audit Person']) else 'unclear','names present='+str([n in txt for n in ['Asha Rao','Bilal Khan','New Audit Person']]))
 await nav(page,'Events'); await page.wait_for_timeout(600); await shot(page,'80-restart/events-persisted')
 txt=await body(page)
 rec('post-restart event persistence','verified' if 'Check Photo Audit Event' in txt and '2 media' in txt else 'partial','Check event/media marker present: '+str(('Check Photo Audit Event' in txt,'2 media' in txt)))
 await nav(page,'Review photos'); await page.wait_for_timeout(800); await shot(page,'80-restart/review-session-resumed')
 txt=await body(page)
 rec('review scan-session persistence after restart','verified' if 'Active session' in txt and 'Attaching media to Morning Audit Briefing' in txt else 'unclear',txt[-600:].replace('\n',' | '))
 print(txt[-1600:])
 flush(); await p.stop()
asyncio.run(main())
