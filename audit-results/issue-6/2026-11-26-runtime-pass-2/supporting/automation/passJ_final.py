"""Pass J: backup create (custodian), delete-to-bin+restore, merge, dark theme, narrow."""
import sys, re; sys.path.insert(0, "/home/ubuntu/audit6")
from common import *
from sflib import sign_in, skip_backup_gate

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
    ctx.set_default_timeout(8000)
    page = ctx.new_page()

    # ---- 1. custodian backup journey ----
    sign_in(page, "audit-custodian", "<REDACTED_TEST_PASSWORD>")
    page.wait_for_timeout(1200)
    skip_backup_gate(page)
    page.get_by_role("tab", name="Settings", exact=True).click()
    page.wait_for_timeout(1500)
    try:
        click_vis(page, re.compile(r"Backups & restore"))
        page.wait_for_timeout(1200)
        click_vis(page, re.compile(r"Create Backup"))
        page.wait_for_timeout(1500)
        shot(page, "j-01-backup-dialog")
        dlg = page.locator("[role='dialog'], .mantine-Modal-content")
        if dlg.count():
            print("backup dlg:", dlg.first.inner_text()[:300].replace("\n", " | "), flush=True)
            # confirm creation with defaults
            if click_vis(dlg.first, re.compile(r"Create|Confirm|Start")):
                page.wait_for_timeout(6000)
        shot(page, "j-02-backup-after")
        print("backup list now:", "No backups yet" not in page.locator("main").inner_text(), flush=True)
    except Exception as e:
        print("backup FAIL", str(e)[:90], flush=True)
    ctx.close()

    # ---- 2. admin: delete-to-bin + bin + merge + themes ----
    ctx = br.new_context(viewport=VIEWPORT)
    ctx.set_default_timeout(8000)
    page = ctx.new_page()
    sign_in(page, *ADMIN)
    page.wait_for_timeout(1200)
    skip_backup_gate(page)
    page.get_by_role("tab", name="People", exact=True).click()
    page.wait_for_timeout(1800)
    # delete the no-photo person? search for one of the duplicates: use 'arjun'
    page.locator("input[placeholder*='Search']").fill("arjun")
    page.wait_for_timeout(900)
    page.locator("main").get_by_text("Open profile").first.click()
    page.wait_for_timeout(1800)
    click_vis(page, re.compile(r"^More"))
    page.wait_for_timeout(700)
    mi = page.get_by_role("menuitem", name=re.compile(r"Delete Person"))
    if mi.count():
        mi.first.click()
        page.wait_for_timeout(1200)
        shot(page, "j-03-delete-dialog")
        dlg = page.locator("[role='dialog'], .mantine-Modal-content")
        print("delete dlg:", dlg.first.inner_text()[:400].replace("\n", " | ") if dlg.count() else "none", flush=True)
    else:
        print("no delete menuitem", flush=True)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ---- merge attempt ----
    click_vis(page, re.compile(r"^More"))
    page.wait_for_timeout(700)
    mm = page.get_by_role("menuitem", name=re.compile(r"Merge into another"))
    if mm.count():
        mm.first.click()
        page.wait_for_timeout(1500)
        shot(page, "j-04-merge-dialog")
        dlg = page.locator("[role='dialog'], .mantine-Modal-content, .mantine-Drawer-content")
        print("merge dlg:", dlg.first.inner_text()[:450].replace("\n", " | ") if dlg.count() else "none", flush=True)
    else:
        print("no merge menuitem", flush=True)
    page.keyboard.press("Escape")

    # ---- dark theme ----
    page.wait_for_timeout(600)
    page.keyboard.press("Escape")
    # theme toggle is the moon icon in header — try clicking first header button
    hdr = page.locator("header button, .mantine-ActionIcon-root")
    try:
        page.locator("button[aria-label*='theme'], button[aria-label*='dark'], button[aria-label*='Dark'], button[aria-label*='light'], button[aria-label*='Light']").first.click(timeout=3000)
    except Exception:
        # fallback: click first action icon in top-right group
        page.locator(".mantine-ActionIcon-root").first.click(timeout=3000)
    page.wait_for_timeout(1200)
    shot(page, "j-05-dark-theme")
    print("done", flush=True)
    ctx.close()

    # ---- narrow window ----
    ctx = br.new_context(viewport={"width": 760, "height": 900})
    ctx.set_default_timeout(7000)
    page = ctx.new_page()
    sign_in(page, *ADMIN)
    page.wait_for_timeout(1500)
    skip_backup_gate(page)
    shot(page, "j-06-narrow-home")
    page.get_by_role("tab", name="People", exact=True).click()
    page.wait_for_timeout(1600)
    shot(page, "j-07-narrow-people")
    print("done2", flush=True)
    ctx.close()
    br.close()
