"""Pass A6: notes+mentions, archive, delete to bin, restore."""
import sys; sys.path.insert(0, "/home/ubuntu/audit6")
from common import *
from sflib import sign_in

with sync_playwright() as pw:
    br = browser(pw)
    ctx = br.new_context(viewport=VIEWPORT)
    ctx.set_default_timeout(9000)
    page = ctx.new_page()
    sign_in(page, *ADMIN)
    page.wait_for_timeout(1000)
    page.get_by_role("tab", name="People", exact=True).click()
    page.wait_for_timeout(1800)
    # open Meera profile (has 2 events)
    page.locator("input[placeholder*='Search']").fill("meera")
    page.wait_for_timeout(900)
    page.get_by_text("Open profile").first.click()
    page.wait_for_timeout(1800)
    shot(page, "pa-14-meera-profile")
    # look for note add affordance in overview notes card
    overview = page.locator("body").inner_text()
    print("has add note:", "note" in overview.lower())
    btns = page.get_by_role("button")
    labels = [btns.nth(i).inner_text()[:30] for i in range(min(btns.count(), 30))]
    print("buttons:", [l for l in labels if l.strip()][:25], flush=True)
    ctx.close(); br.close()
