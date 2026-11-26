import asyncio, os, json, re
from auditlib import *
async def safe_shot(page,path):
 try: await shot(page,path)
 except Exception as e: print('shotfail',path,e)
async def click_text(page,text):
 try:
  await page.get_by_role('button',name=re.compile('^'+re.escape(text)+'$',re.I)).first.click(timeout=1500); await page.wait_for_timeout(700); return True
 except Exception: return False
async def main():
 p,b,ctx,page=await connect(); await page.goto(BASE); await page.wait_for_timeout(1200)
 # dismiss any modal left open
 await page.keyboard.press('Escape'); await page.wait_for_timeout(400)
 coverage=[]
 for nav,path in [('Check a photo','02-check-photo/home'),('Review photos','03-review/home'),('People','01-people/home'),('Events','04-events/home'),('World','05-world/home'),('Settings','06-settings/home')]:
  ok=await click_text(page,nav); await safe_shot(page,path); coverage.append({'screen':nav,'opened':ok})
 # People controls/menus/dialogs
 await click_text(page,'People')
 for label,name in [('Filter','01-people/filter-popover'),('Group by: Country','01-people/group-menu'),('Sort: Priority','01-people/sort-menu'),('Add without photo','01-people/add-person-dialog')]:
  ok=await click_text(page,label); await safe_shot(page,name); coverage.append({'screen':name,'opened':ok}); await page.keyboard.press('Escape'); await page.wait_for_timeout(200)
 # Check photo states
 await click_text(page,'Check a photo'); await safe_shot(page,'02-check-photo/initial')
 # Review photos states
 await click_text(page,'Review photos'); await safe_shot(page,'03-review/initial')
 # Events + correction/create affordances
 await click_text(page,'Events'); await safe_shot(page,'04-events/initial')
 # World explore/connections and drilldowns if present
 await click_text(page,'World'); await safe_shot(page,'05-world/explore')
 for label,name in [('Connections','05-world/connections'),('Explore','05-world/explore-toggle')]:
  ok=await click_text(page,label); await safe_shot(page,name); coverage.append({'screen':name,'opened':ok})
 # Settings navigation: click every visible sidebar/nav button heuristically
 await click_text(page,'Settings'); await page.wait_for_timeout(700); await safe_shot(page,'06-settings/initial')
 buttons=await page.locator('main button').all_inner_texts()
 seen=set()
 for i,t in enumerate(buttons):
  clean=' '.join(t.split())[:40]
  if not clean or clean in seen or len(clean)>35: continue
  seen.add(clean)
  try:
   loc=page.locator('main button').filter(has_text=clean.split('\n')[0]).first
   await loc.click(timeout=800); await page.wait_for_timeout(500)
   fn='06-settings/'+re.sub('[^a-z0-9]+','-',clean.lower()).strip('-')[:45]
   await safe_shot(page,fn); coverage.append({'screen':'settings '+clean,'opened':True})
  except Exception: pass
 # account menu and theme
 try:
  await page.get_by_label('Open account menu').click(timeout=1000); await page.wait_for_timeout(400); await safe_shot(page,'07-shell/account-menu'); await page.keyboard.press('Escape')
 except Exception: pass
 try:
  await page.get_by_label('Switch to dark mode').click(timeout=1000); await page.wait_for_timeout(500); await safe_shot(page,'07-shell/dark-mode')
 except Exception: pass
 os.makedirs('/home/ubuntu/issue6-runtime-audit',exist_ok=True)
 open('/home/ubuntu/issue6-runtime-audit/crawl-coverage.json','w').write(json.dumps(coverage,indent=2))
 print('done',len(coverage)); await p.stop()
asyncio.run(main())
