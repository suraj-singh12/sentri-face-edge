"""Pass A5: compact — notes/mentions, sightings, associations, activity."""
import sys; sys.path.insert(0, "/home/ubuntu/audit6")
from common import *
from sflib import sign_in

with sync_playwright() as pw:
    br = browser(pw)
    ctx = br.new_context(viewport=VIEWPORT)
    ctx.set_default_timeout(9000)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    sign_in(page, *ADMIN)
    page.wait_for_timeout(1000)
    page.get_by_role("tab", name="People", exact=True).click()
    page.wait_for_timeout(1800)
    page.get_by_text("Open profile").first.click()
    page.wait_for_timeout(1800)
    panel = page.get_by_role("tabpanel", name="People")

    # sightings
    panel.get_by_role("tab", name=re.compile(r"^Sightings")).click()
    page.wait_for_timeout(1200)
    shot(page, "pa-12-sightings")
    # events subtab
    panel.get_by_role("tab", name=re.compile(r"^Events")).click()
    page.wait_for_timeout(1200)
    shot(page, "pa-11-profile-events")
    # associations detail
    panel.get_by_role("tab", name=re.compile(r"^Associations")).click()
    page.wait_for_timeout(1200)
    shot(page, "pa-09-associations")
    # activity
    panel.get_by_role("tab", name=re.compile(r"^Activity")).click()
    page.wait_for_timeout(1200)
    shot(page, "pa-10-activity")
    # add a note with mention: open notes editing via Edit menu or overview notes area
    panel.get_by_role("tab", name="Overview", exact=True).click()
    page.wait_for_timeout(800)
    # find notes edit affordance
    edit_note = page.get_by_role("button", name=re.compile(r"note", re.I))
    print("note buttons:", [edit_note.nth(i).inner_text()[:40] for i in range(min(edit_note.count(), 6))], flush=True)
    if edit_note.count():
        edit_note.first.click()
        page.wait_for_timeout(1000)
        shot(page, "pa-13-note-editor")
    print("ERRORS:", errors, flush=True)
    ctx.close(); br.close()
