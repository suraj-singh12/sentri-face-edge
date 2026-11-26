"""Verify world evidence-filter behavior + connections."""
import sys; sys.path.insert(0, "/home/ubuntu/audit6")
from common import *
from sflib import sign_in

with sync_playwright() as pw:
    br = browser(pw)
    ctx = br.new_context(viewport=VIEWPORT)
    ctx.set_default_timeout(7000)
    page = ctx.new_page()
    sign_in(page, *ADMIN)
    page.wait_for_timeout(1200)
    page.get_by_role("tab", name="World", exact=True).click()
    page.wait_for_timeout(2200)
    # open the Evidence select
    ev = page.locator("input").and_(page.locator("[value]")).first
    sel = page.get_by_role("textbox", name=re.compile(r"Evidence", re.I))
    if not sel.count():
        # mantine select: find input near label
        sel = page.locator("main input").nth(1)
    sel.click()
    page.wait_for_timeout(800)
    shot(page, "w-04-evidence-options")
    opts = page.locator("[role='option'], .mantine-Select-option, .mantine-Combobox-option")
    print("evidence options:", [opts.nth(i).inner_text()[:40] for i in range(min(opts.count(), 8))], flush=True)
    # select all evidence types if checkboxes exist
    page.keyboard.press("Escape")
    # set min evidence to 1
    num = page.locator("main input[type='number']").first
    if num.count():
        num.fill("1")
    page.get_by_role("button", name="Apply").click()
    page.wait_for_timeout(2200)
    page.locator("main").get_by_text("Meera Iyer").first.click()
    page.wait_for_timeout(2500)
    shot(page, "w-05-after-evidence1")
    insp = page.locator("main").inner_text()
    i0 = insp.find("Inspector")
    print("inspector:", insp[i0:i0+500].replace("\n", " | ")[:450], flush=True)
    # connections tab
    conn = page.get_by_role("tab", name=re.compile(r"^Connections"))
    print("conn tabs:", conn.count(), flush=True)
    if conn.count():
        conn.first.click()
        page.wait_for_timeout(1800)
        shot(page, "w-02-connections")
        print("conn text:", page.locator("main").inner_text()[:600].replace("\n", " | "), flush=True)
    ctx.close(); br.close()
