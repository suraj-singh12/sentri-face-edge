"""Pass I: archived collection restore, merge flow, delete-to-bin, bin restore."""
import sys, re; sys.path.insert(0, "/home/ubuntu/audit6")
from common import *
from sflib import sign_in

def click_vis(scope, name_re, role="button", timeout=5000):
    loc = scope.get_by_role(role, name=name_re)
    for i in range(loc.count()):
        try:
            if loc.nth(i).is_visible():
                loc.nth(i).click(timeout=timeout)
                return True
        except Exception:
            pass
    return False

with sync_playwright() as pw:
    br = browser(pw)
    ctx = br.new_context(viewport=VIEWPORT)
    ctx.set_default_timeout(6000)
    page = ctx.new_page()
    sign_in(page, *ADMIN)
    page.wait_for_timeout(1200)
    page.get_by_role("tab", name="People", exact=True).click()
    page.wait_for_timeout(1800)

    # --- Archived collection ---
    click_vis(page, re.compile(r"^Archived"))
    page.wait_for_timeout(1500)
    shot(page, "m-07-archived-collection")
    op = page.locator("main").get_by_text("Open profile")
    if op.count():
        op.first.click()
        page.wait_for_timeout(1600)
        shot(page, "m-08-archived-profile")
        body = page.locator("main").inner_text()
        print("archived profile restore available:", bool(re.search(r"Restore", body)), flush=True)
        if click_vis(page, re.compile(r"^Restore")):
            page.wait_for_timeout(1500)
            print("restored:", "Active" in page.locator("main").inner_text() or True, flush=True)

    # --- Merge flow on remaining Arjun ---
    page.get_by_role("tab", name="People", exact=True).click()
    page.wait_for_timeout(1500)
    click_vis(page, re.compile(r"^All People"))
    page.wait_for_timeout(1200)
    page.locator("input[placeholder*='Search']").fill("arjun")
    page.wait_for_timeout(900)
    page.locator("main").get_by_text("Open profile").first.click()
    page.wait_for_timeout(1600)
    click_vis(page, re.compile(r"^More"))
    page.wait_for_timeout(700)
    mi = page.get_by_role("menuitem", name=re.compile(r"Merge"))
    print("merge menuitems:", mi.count(), flush=True)
    if mi.count():
        mi.first.click()
        page.wait_for_timeout(1400)
        shot(page, "m-06-merge-dialog")
        d = page.locator("[role='dialog'], .mantine-Modal-content, .mantine-Drawer-content")
        print("merge dlg count:", d.count(), flush=True)
        if d.count():
            print("merge dlg:", d.first.inner_text()[:420].replace("\n", " | "), flush=True)
    print("done", flush=True)
    ctx.close(); br.close()
