import asyncio
from ui_audit_lib import *
async def main():
 p,b,ctx,page=await connect()
 # close menu with escape, navigate People for stable visual comparison
 await page.keyboard.press('Escape'); await nav(page,'People'); await page.wait_for_timeout(500)
 await shot(page,'90-theme/people-light')
 rec('light theme capture','ok',await page.evaluate('document.documentElement.getAttribute("data-mantine-color-scheme")'))
 try:
  await page.get_by_label('Switch to dark mode').click(timeout=1200); await page.wait_for_timeout(400); await shot(page,'90-theme/people-dark')
  rec('dark theme toggle/capture','verified',await page.evaluate('document.documentElement.getAttribute("data-mantine-color-scheme")'))
 except Exception as e: rec('dark theme toggle/capture','error',str(e)[:180])
 try:
  await page.get_by_label('Switch to light mode').click(timeout=1200); await page.wait_for_timeout(300); await shot(page,'90-theme/people-light-restored')
  rec('light theme restore','verified',await page.evaluate('document.documentElement.getAttribute("data-mantine-color-scheme")'))
 except Exception as e: rec('light theme restore','error',str(e)[:180])
 flush(); await p.stop()
asyncio.run(main())
