"""Pass G: archive confirm+restore, delete-to-bin+bin+restore, merge duplicates."""
import sys; sys.path.insert(0, "/home/ubuntu/audit6")
from common import *
from sflib import sign_in

def click_vis(scope, name_re, role="button", timeout=5000):
    loc = scope.get_by_role(role, name=name_re)
    for i in range(loc.count()):
        if loc.nth(i).is_visible():
            loc.nth(i).click(timeout=timeout)
            return True
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
    page.locator("input[placeholder*='Search']").fill("arjun")
    page.wait_for_timeout(900)
    cards = page.locator("main").get_by_text("Open profile")
    print("arjun cards:", cards.count(), flush=True)
    cards.first.click()
    page.wait_for_timeout(1800)
    # Archive
    click_vis(page, re.compile(r"^Archive"))
    page.wait_for_timeout(800)
    dlg = page.locator("[role='dialog'], .mantine-Modal-content")
    if dlg.count():
        click_vis(dlg.first, re.compile(r"Archive person"))
        page.wait_for_timeout(1800)
    shot(page, "m-04-archived")
    body = page.locator("main").inner_text()
    print("after archive contains 'rchived':", "rchived" in body, "| restore:", "estore" in body, flush=True)
    # restore if control exists
    if click_vis(page, re.compile(r"Restore")):
        page.wait_for_timeout(1500)
        shot(page, "m-05-restored")
        print("restored, archived still visible:", "rchived" in page.locator("main").inner_text()[:600], flush=True)
    # Merge: open More menu
    click_vis(page, re.compile(r"^More"))
    page.wait_for_timeout(700)
    click_vis(page, re.compile(r"Merge into another"), role="menuitem")
    page.wait_for_timeout(1200)
    shot(page, "m-06-merge-dialog")
    d = page.locator("[role='dialog'], .mantine-Modal-content, .mantine-Drawer-content")
    print("merge dialog:", d.first.inner_text()[:500] if d.count() else "none", flush=True)
    print("done", flush=True)
    ctx.close(); br.close()
