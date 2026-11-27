import asyncio
from playwright.async_api import async_playwright
async def main():
 p=await async_playwright().start()
 b=await p.chromium.connect_over_cdp('http://localhost:29229')
 ctx=b.contexts[0]
 page=ctx.pages[0] if ctx.pages else await ctx.new_page()
 await page.goto('http://127.0.0.1:8765/')
 await page.wait_for_timeout(1500)
 print((await page.locator('body').inner_text())[:3000])
 print('buttons', await page.locator('button').all_inner_texts())
 await page.screenshot(path='/home/ubuntu/issue6-runtime-audit/screenshots/probe.png',full_page=True)
 await p.stop()
asyncio.run(main())
