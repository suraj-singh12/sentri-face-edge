"""Pass D2: robust world + settings + mutations, tolerant of failures."""
import sys; sys.path.insert(0, "/home/ubuntu/audit6")
from common import *
from sflib import sign_in

def vis_click(page, text_or_pattern, timeout=4000):
    loc = page.locator("main").get_by_text(text_or_pattern) if isinstance(text_or_pattern, str) else page.locator("main").get_by_text(text_or_pattern)
    n = loc.count()
    for i in range(n):
        el = loc.nth(i)
        if el.is_visible():
            el.click(timeout=timeout)
            return True
    return False

with sync_playwright() as pw:
    br = browser(pw)
    ctx = br.new_context(viewport=VIEWPORT)
    ctx.set_default_timeout(6000)
    page = ctx.new_page()
    sign_in(page, *ADMIN)
    page.wait_for_timeout(1200)
    try:
        page.get_by_role("tab", name="World", exact=True).click()
        page.wait_for_timeout(2200)
        ok = vis_click(page, "Meera Iyer")
        page.wait_for_timeout(2500)
        shot(page, "w-03-canvas-person")
        print("world click:", ok, flush=True)
    except Exception as e:
        print("world fail:", str(e)[:90], flush=True)
    try:
        page.get_by_role("tab", name=re.compile(r"Connection")).first.click()
        page.wait_for_timeout(1600)
        shot(page, "w-02-connections")
    except Exception as e:
        print("conn fail:", str(e)[:90], flush=True)
    # settings sections
    try:
        page.get_by_role("tab", name="Settings", exact=True).click()
        page.wait_for_timeout(1800)
        for i, sec in enumerate(["License & activation", "Backups & restore", "User accounts", "Integrity & recovery", "System details", "Activity log", "About & support"]):
            try:
                btn = page.locator("main").get_by_role("button", name=re.compile(re.escape(sec)))
                for j in range(btn.count()):
                    if btn.nth(j).is_visible():
                        btn.nth(j).click(); break
                page.wait_for_timeout(1600)
                shot(page, f"st-{i+2:02d}-{sec.split()[0].lower()}")
            except Exception as e:
                print(sec, "FAIL", str(e)[:70], flush=True)
    except Exception as e:
        print("settings fail:", str(e)[:90], flush=True)
    print("done", flush=True)
    ctx.close(); br.close()
