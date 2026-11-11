"""Issue #6 capture helper. Run with repository Python 3.12 -i; no product patches.
Screenshots are full CSS viewport, not full-page stitched captures. Credentials
and raw accessibility snapshots remain private. Public promotion is a separate review.
"""
import json, os, sys, secrets, hashlib, platform, time, re
from pathlib import Path
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
ROOT=Path.cwd()
PRIVATE=ROOT/'qa-fixtures/runs/issue-6-audit'
BASE_URL=os.environ.get('SENTRIFACE_AUDIT_BASE_URL','http://127.0.0.1:8765')
OUT=PRIVATE/'captures'; OUT.mkdir(parents=True,exist_ok=True)
pw=sync_playwright().start()
browser=pw.chromium.launch(headless=True)
context=browser.new_context(**({'storage_state':str(PRIVATE/'browser-state.json')} if (PRIVATE/'browser-state.json').exists() else {}),base_url=BASE_URL,viewport={'width':1440,'height':900},device_scale_factor=1,accept_downloads=True)
context.set_default_timeout(7000)
page=context.new_page()
password=json.loads((PRIVATE/'credentials.json').read_text())['audit-owner'] if (PRIVATE/'credentials.json').exists() else secrets.token_urlsafe(24)
records=json.loads((PRIVATE/'capture-metadata.json').read_text()) if (PRIVATE/'capture-metadata.json').exists() else []
def snap():
    print(page.locator('body').aria_snapshot())
def cap(ux,journey,state,role='Administrator',kind='synthetic',public=True):
    page.wait_for_timeout(250)
    name=f'{ux}_{journey}_Step-{1+sum(r["journey"]==journey for r in records):02d}_{state}.png'
    path=OUT/name
    page.screenshot(path=str(path),full_page=False)
    paths=page.locator('p,code,pre').filter(has_text=re.compile(r'/Users/|/private/|/var/folders/|/Volumes/')).filter(visible=True)
    sensitive=paths.count()>0
    record=dict(file=name,ux=ux,journey=journey,step=1+sum(r['journey']==journey for r in records),state=state,role=role,kind=kind,public_candidate=public and not sensitive,captured_at=datetime.now(timezone.utc).isoformat(),viewport=page.viewport_size,device_scale_factor=1,theme=page.locator('html').get_attribute('data-mantine-color-scheme'),source_sha='b457f0a723e845dd1a92a07a577072c85146c89a',sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    record['scroll']={'x':page.evaluate('window.scrollX'),'y':page.evaluate('window.scrollY')}
    if sensitive and public:
        name2=name.replace('.png','_SANITIZED.png')
        page.screenshot(path=str(OUT/name2),full_page=False,mask=[paths],mask_color='#555555')
        record.update(sanitized_file=name2,sanitized_sha256=hashlib.sha256((OUT/name2).read_bytes()).hexdigest(),sanitization='Separate browser screenshot masking local-path text. Mask can also occlude foreground overlays; unmodified original retained privately.')
    records.append(record)
    (PRIVATE/'capture-metadata.json').write_text(json.dumps(records,indent=2))
    (OUT/(name+'.txt')).write_text(page.locator('body').aria_snapshot())
    context.storage_state(path=str(PRIVATE/'browser-state.json'))
    print(str(path))
def click(name,role='button'):
    page.get_by_role(role,name=name,exact=True).click(); page.wait_for_timeout(250)
def field(label):
    import re
    return page.get_by_label(re.compile('^'+re.escape(label)+r'\s*\*?$')).and_(page.locator('input,textarea'))
def select(label,value):
    field(label).click(); page.get_by_role('option',name=value,exact=True).click()
def tab(name):
    page.get_by_role('tablist').first.get_by_role('tab',name=name,exact=True).click();page.wait_for_timeout(250)
page.goto(BASE_URL); page.wait_for_timeout(800)
context.set_extra_http_headers({'X-SentriFace-Session':page.locator('meta[name="sentriface-session-token"]').get_attribute('content')})
snap()
