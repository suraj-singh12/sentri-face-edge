import asyncio, os, re, json, time
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
BASE='http://127.0.0.1:8765/'
ROOT='/home/ubuntu/issue6-runtime-audit'
OUT=ROOT+'/screenshots'
LOG=[]
def rec(step,status='ok',detail=''):
 LOG.append({'time':time.time(),'step':step,'status':status,'detail':detail}); print(status.upper(),step,detail)
def flush():
 open(ROOT+'/ui-audit-log.json','w').write(json.dumps(LOG,indent=2))
async def connect():
 p=await async_playwright().start(); b=await p.chromium.connect_over_cdp('http://localhost:29229')
 ctx=b.contexts[0]; page=ctx.pages[0] if ctx.pages else await ctx.new_page()
 page.set_default_timeout(5000)
 return p,b,ctx,page
async def shot(page,name):
 path=os.path.join(OUT,name+'.png'); os.makedirs(os.path.dirname(path),exist_ok=True)
 await page.screenshot(path=path,full_page=True); rec('screenshot','ok',name)
async def body(page): return await page.locator('body').inner_text()
async def login(page,username,password):
 await page.goto(BASE); await page.wait_for_timeout(1000)
 txt=await body(page)
 if 'Sign in to continue' in txt:
  await page.locator('input').nth(0).fill(username)
  await page.locator('input[type=password]').nth(0).fill(password)
  await shot(page,'auth/'+username+'-login-filled')
  await page.get_by_role('button',name='Sign in').click(); await page.wait_for_timeout(1800)
 txt=await body(page)
 if 'Choose a new password' in txt or 'Set a new password' in txt or 'new password' in txt.lower() and 'Sign in' not in txt:
  # complete required reset with a deterministic audit password
  new='<REDACTED_TEST_PASSWORD>'
  pw=page.locator('input[type=password]')
  if await pw.count()>=2:
   await pw.nth(0).fill(new); await pw.nth(1).fill(new)
   await page.get_by_role('button',name=re.compile('password|continue',re.I)).last.click(); await page.wait_for_timeout(1500)
 await shot(page,'auth/'+username+'-signed-in')
 rec('login','ok',username)
async def logout(page):
 try:
  await page.get_by_label('Open account menu').click(timeout=1500); await page.wait_for_timeout(300)
  await shot(page,'auth/account-menu-before-signout')
  await page.get_by_role('button',name='Sign out').click(timeout=1500); await page.wait_for_timeout(900)
  await shot(page,'auth/signed-out')
  rec('logout','ok')
 except Exception as e: rec('logout','error',str(e)[:200])
async def nav(page,name,shotname=None):
 try:
  await page.get_by_role('tab',name=re.compile('^'+re.escape(name)+'$',re.I)).first.click(); await page.wait_for_timeout(900)
  if shotname: await shot(page,shotname)
  rec('nav '+name,'ok')
  return True
 except Exception as e: rec('nav '+name,'error',str(e)[:200]); return False
async def click_name(page,name,shotname=None,exact=False,timeout=3000):
 try:
  loc=page.get_by_role('button',name=re.compile(('^' if exact else '')+re.escape(name)+('$' if exact else ''),re.I)).first
  await loc.click(timeout=timeout); await page.wait_for_timeout(700)
  if shotname: await shot(page,shotname)
  rec('click '+name,'ok')
  return True
 except Exception as e: rec('click '+name,'error',str(e)[:180]); return False
async def press_escape(page):
 await page.keyboard.press('Escape'); await page.wait_for_timeout(250)
