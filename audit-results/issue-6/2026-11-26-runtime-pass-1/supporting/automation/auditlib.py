import asyncio, os, json, time
from playwright.async_api import async_playwright
BASE='http://127.0.0.1:8765/'
OUT='/home/ubuntu/issue6-runtime-audit/screenshots'
async def connect():
 p=await async_playwright().start()
 b=await p.chromium.connect_over_cdp('http://localhost:29229')
 ctx=b.contexts[0]
 page=ctx.pages[0] if ctx.pages else await ctx.new_page()
 return p,b,ctx,page
async def shot(page,name):
 os.makedirs(os.path.dirname(os.path.join(OUT,name+'.png')),exist_ok=True)
 await page.screenshot(path=os.path.join(OUT,name+'.png'),full_page=True)
 print(name)
async def body(page): return (await page.locator('body').inner_text())[:5000]
