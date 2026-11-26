import asyncio,re,subprocess
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 # assumes Correct Event modal open from probe; verify or reopen
 if True:
  await login(page,'owner','<REDACTED_TEST_PASSWORD>'); await nav(page,'Events'); await page.get_by_text('Check Photo Audit Event',exact=True).first.click(); await page.wait_for_timeout(700); await page.get_by_role('button',name='Correct Event').click(); await page.wait_for_timeout(500)
 await shot(page,'70-stale/modal-before-external-change')
 # make a small unsaved UI edit, then mutate backend revision outside the modal
 try:
  await page.locator('input').nth(1).fill('Afternoon Audit UI edit')
  rec('stale modal edit','ok')
 except Exception as e: rec('stale modal edit','error',str(e)[:150])
 r=subprocess.run(['/home/ubuntu/sfe-dev/with-keyring.sh','/home/ubuntu/sfe-issue6-audit/.venv312/bin/python','/home/ubuntu/issue6-runtime-audit/stale_mutate.py'],cwd='/home/ubuntu/sfe-issue6-audit',capture_output=True,text=True)
 rec('stale external mutation','ok' if r.returncode==0 else 'error',(r.stdout+r.stderr)[-300:])
 try:
  await page.get_by_role('button',name='Save correction').click(timeout=1800); await page.wait_for_timeout(1300); await shot(page,'70-stale/stale-error-with-reload')
  txt=await body(page)
  rec('F08/PR87 stale correction recovery','verified' if 'Reload current Event' in txt and ('stale' in txt.lower() or 'changed' in txt.lower()) else 'unclear',txt[-500:].replace('\n',' | '))
 except Exception as e: rec('stale save','error',str(e)[:200])
 # click reload recovery
 try:
  await page.get_by_role('button',name='Reload current Event').click(timeout=1800); await page.wait_for_timeout(1000); await shot(page,'70-stale/after-reload-current-event')
  rec('stale reload control','verified')
 except Exception as e: rec('stale reload control','error',str(e)[:180])
 print((await body(page))[-1800:])
 flush(); await p.stop()
asyncio.run(main())
