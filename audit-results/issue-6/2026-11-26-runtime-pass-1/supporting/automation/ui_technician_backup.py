import asyncio
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 # sign out current owner if needed
 try:
  await page.get_by_text("Audit Owner",exact=False).first.click(timeout=800); await page.wait_for_timeout(250); await page.get_by_text("Sign out",exact=True).last.click(timeout=800); await page.wait_for_timeout(700)
 except Exception: pass
 await login(page,'technician1','<REDACTED_TEST_PASSWORD>')
 txt=await body(page)
 rec('technician backup affordance visible','verified' if 'Back up now' in txt else 'not-visible','backup visible='+str('Back up now' in txt))
 if 'Back up now' in txt:
  try:
   await page.get_by_role('button',name='Back up now').first.click(timeout=1500); await page.wait_for_timeout(900); await shot(page,'40-roles/technician/backup-now-outcome')
   txt=await body(page)
   rec('technician backup outcome','verified',txt[-700:].replace('\n',' | '))
  except Exception as e: rec('technician backup outcome','error',str(e)[:180])
 print((await body(page))[-1200:])
 flush(); await p.stop()
asyncio.run(main())
