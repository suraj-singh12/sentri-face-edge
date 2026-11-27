"""Pass B: Events list/detail/correction + World explore/connections."""
import sys; sys.path.insert(0, "/home/ubuntu/audit6")
from common import *
from sflib import sign_in

with sync_playwright() as pw:
    br = browser(pw)
    ctx = br.new_context(viewport=VIEWPORT)
    ctx.set_default_timeout(9000)
    page = ctx.new_page()
    sign_in(page, *ADMIN)
    page.wait_for_timeout(1200)

    # ---- Events list ----
    page.get_by_role("tab", name="Events", exact=True).click()
    page.wait_for_timeout(1800)
    shot(page, "ev-01-list")
    print("== events list ==", flush=True)
    print(page.locator("main").inner_text()[:900], flush=True)

    # open first event
    open_evt = page.get_by_text(re.compile(r"Open|View", re.I))
    card = page.locator("main [class*='Card'], main .mantine-Card-root").first
    btn = page.get_by_role("button", name=re.compile(r"open event|view event|details", re.I))
    print("evt open buttons:", btn.count(), flush=True)
    if btn.count():
        btn.first.click()
    else:
        # try clicking the card title
        page.locator("main").get_by_text(re.compile(r"Evening|Festival|Supply|Morning|Convoy")).first.click()
    page.wait_for_timeout(2000)
    shot(page, "ev-02-detail")
    print("== event detail ==", flush=True)
    print(page.locator("main").inner_text()[:1200], flush=True)
    ctx.close(); br.close()
