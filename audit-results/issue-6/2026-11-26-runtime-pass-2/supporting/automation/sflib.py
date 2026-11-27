"""Seeding library — drives real UI flows."""
import sys; sys.path.insert(0, "/home/ubuntu/audit6")
from common import *

def sign_in(page, username, password):
    page.goto(BASE); page.wait_for_timeout(2000)
    if page.get_by_role("button", name="Sign in", exact=True).count():
        field(page, "Account name").fill(username)
        field(page, "Password").fill(password)
        page.get_by_role("button", name="Sign in", exact=True).click()
        page.wait_for_timeout(2500)

def skip_backup_gate(page):
    if page.get_by_role("button", name="Skip for now", exact=True).count():
        try:
            page.get_by_text("I understand that my data may not be recoverable").click()
            page.get_by_role("button", name="Skip for now", exact=True).click()
            page.wait_for_timeout(1500)
        except Exception:
            pass

def pick_location(page, location):
    fld = field(page, "Location")
    fld.fill(location)
    page.wait_for_timeout(900)
    opt = page.get_by_role("option", name=f"Create “{location}”")
    if opt.count():
        opt.first.click()
    else:
        # maybe existing location suggestion appears
        opt2 = page.get_by_role("option", name=re.compile(re.escape(location), re.I))
        if opt2.count():
            opt2.first.click()
        else:
            page.keyboard.press("Tab")
    page.wait_for_timeout(300)

def fill_event_details(page, occasion, date, location, time_mode="Unknown", time_start=None, time_end=None, approx=None, context="", note=None, mention=None):
    field(page, "Event / occasion").fill(occasion)
    field(page, "Date").fill(date)
    if time_mode != "Unknown":
        ts = page.get_by_label(re.compile(r"^Time"))
        ts.first.click()
        page.wait_for_timeout(500)
        page.get_by_role("option", name=time_mode, exact=True).click()
        page.wait_for_timeout(500)
        if time_mode == "Start and end" and time_start:
            field(page, "Start time").fill(time_start)
            if time_end: field(page, "End time").fill(time_end)
        elif time_mode == "Approximate" and approx:
            field(page, re.compile(r"^Approximate")).fill(approx)
    pick_location(page, location)
    if context:
        try: field(page, "Context").fill(context)
        except Exception: pass

def new_person_in_group(page, name, note_shot=None):
    """Inside an open group review: create a new person with the given name."""
    btn = page.get_by_role("button", name="Create new person", exact=True)
    btn.click()
    page.wait_for_timeout(800)
    return True
