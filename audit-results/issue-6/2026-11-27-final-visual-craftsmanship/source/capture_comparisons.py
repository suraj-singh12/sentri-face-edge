import asyncio,re,os,sys
from pathlib import Path
from playwright.async_api import async_playwright
BASE='http://127.0.0.1:8765/'
ROOT=Path('/home/ubuntu/visual-review/final-prototype')
CSS=(ROOT/'visual-system.css').read_text()
JS=(ROOT/'apply-prototype.js').read_text()
OUT=ROOT/'captures'; OUT.mkdir(exist_ok=True)
mode=sys.argv[1] if len(sys.argv)>1 else 'current'
async def snap(page,name):
 path=OUT/f'{name}-{mode}.png'
 await page.screenshot(path=str(path),full_page=True)
 print(mode,name)
async def click_tab(page,name):
 await page.get_by_role('tab',name=re.compile('^'+re.escape(name)+'$',re.I)).first.click(); await page.wait_for_timeout(1200)
async def login(page):
 await page.goto(BASE); await page.wait_for_timeout(1400)
 txt=await page.locator('body').inner_text()
 if 'Sign in' in txt:
  if mode=='current': await snap(page,'authentication-signin')
  else:
   await page.add_style_tag(content=(__import__('pathlib').Path('/home/ubuntu/visual-review/final-prototype/visual-system.css').read_text()))
   await page.evaluate((__import__('pathlib').Path('/home/ubuntu/visual-review/final-prototype/apply-prototype.js').read_text()))
   await page.wait_for_timeout(200); await snap(page,'authentication-signin')
  await page.locator('input').nth(0).fill('owner'); await page.locator('input[type=password]').nth(0).fill('owner-passphrase-1')
  await page.get_by_role('button',name='Sign in').click(); await page.wait_for_timeout(1800)
 txt=await page.locator('body').inner_text()
 if 'Use this window' in txt:
  await page.get_by_role('button',name='Use this window').click(); await page.wait_for_timeout(1800)
async def finish(page,name):
 if mode=='proposed':
  await page.add_style_tag(content=CSS)
  await page.evaluate(JS)
  await page.wait_for_timeout(220)
 await snap(page,name)
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(headless=True,executable_path='/home/ubuntu/.local/bin/google-chrome',args=['--no-sandbox'])
  ctx=await b.new_context(viewport={'width':1440,'height':900},device_scale_factor=1)
  page=await ctx.new_page(); page.set_default_timeout(3500)
  await login(page)
  await finish(page,'01-check-photo-empty')
  try:
   await page.get_by_label(re.compile('notifications',re.I)).click(); await page.wait_for_timeout(600)
   await finish(page,'02-notifications-open'); await page.keyboard.press('Escape'); await page.wait_for_timeout(250)
  except Exception as e: print('miss notifications',str(e)[:80])
  await click_tab(page,'Review photos'); await finish(page,'03-review-queue-list')
  try:
   await page.get_by_role('button',name=re.compile('^Review')).last.click(); await page.wait_for_timeout(1600); await finish(page,'04-event-dialog')
   try:
    await page.locator('.mantine-Modal-close, button[aria-label="Close"]').first.click(timeout=1200)
   except Exception: await page.keyboard.press('Escape')
   await page.wait_for_timeout(700); await finish(page,'05-review-recognition')
  except Exception as e: print('miss review detail',str(e)[:100])
  await click_tab(page,'People'); await finish(page,'06-people-grid')
  try:
   # list icon is the right-most compact view control in the toolbar
   await page.locator('button').filter(has=page.locator('svg')).last.click(timeout=1200); await page.wait_for_timeout(700); await finish(page,'07-people-list')
  except Exception as e: print('miss people list',str(e)[:80])
  try:
   await page.get_by_text('Asha Rao',exact=True).first.click(); await page.wait_for_timeout(1400); await finish(page,'08-person-overview')
  except Exception as e: print('miss person',str(e)[:100])
  try:
   await page.get_by_role('tab',name=re.compile('^Photos')).first.click(); await page.wait_for_timeout(900); await finish(page,'09-person-photos')
   await page.locator('img').nth(1).click(timeout=1500); await page.wait_for_timeout(900); await finish(page,'10-photo-details')
   await page.keyboard.press('Escape'); await page.wait_for_timeout(300)
  except Exception as e: print('miss photos',str(e)[:100])
  try:
   await page.get_by_role('button',name=re.compile('^Edit$')).click(timeout=1600); await page.wait_for_timeout(250)
   await page.get_by_text('Edit profile',exact=True).last.click(timeout=1600); await page.wait_for_timeout(1400); await finish(page,'11-person-edit-drawer')
   await page.keyboard.press('Escape'); await page.wait_for_timeout(350)
  except Exception as e: print('miss edit drawer',str(e)[:100])
  try:
   await page.get_by_role('button',name=re.compile('^More')).click(timeout=1600); await page.wait_for_timeout(450); await finish(page,'12-person-more-menu'); await page.keyboard.press('Escape'); await page.wait_for_timeout(250)
  except Exception as e: print('miss more',str(e)[:100])
  try:
   await page.get_by_role('tab',name=re.compile('^Graph')).first.click(timeout=1600); await page.wait_for_timeout(1300); await finish(page,'13-person-graph')
  except Exception as e: print('miss graph',str(e)[:100])
  await click_tab(page,'Events'); await finish(page,'14-events-list')
  try:
   # open first event row/details affordance
   row=page.locator('tr, .mantine-Card-root').filter(has_text=re.compile('Unknown|AUDIT|Event',re.I)).first
   await row.click(timeout=1600); await page.wait_for_timeout(1200); await finish(page,'15-event-details')
   await page.keyboard.press('Escape'); await page.wait_for_timeout(300)
  except Exception as e: print('miss event details',str(e)[:100])
  await click_tab(page,'World'); await finish(page,'16-world-explore')
  try:
   await page.get_by_role('button',name=re.compile('Connections')).click(timeout=1500); await page.wait_for_timeout(1300); await finish(page,'17-world-connections')
  except Exception as e: print('miss connections',str(e)[:100])
  await click_tab(page,'Settings'); await finish(page,'18-settings-license')
  try:
   await page.get_by_text('User accounts',exact=True).first.click(timeout=1600); await page.wait_for_timeout(1200); await finish(page,'19-settings-user-accounts')
  except Exception as e: print('miss users',str(e)[:100])
  # dark theme representative
  try:
   await page.locator('.header-actions button').first.click(timeout=1200); await page.wait_for_timeout(700); await finish(page,'20-settings-dark')
   await page.locator('.header-actions button').first.click(timeout=1200); await page.wait_for_timeout(300)
  except Exception as e: print('miss dark',str(e)[:100])
  # narrow representative on People
  try:
   await click_tab(page,'People'); await page.set_viewport_size({'width':900,'height':760}); await page.wait_for_timeout(700); await finish(page,'21-people-narrow')
  except Exception as e: print('miss narrow',str(e)[:100])
  await b.close()
asyncio.run(main())
