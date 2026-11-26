"""Pass H2: role passes with correct sign-in helper."""
import sys, re; sys.path.insert(0, "/home/ubuntu/audit6")
from common import *
from sflib import sign_in, skip_backup_gate

ROLES = [
    ("viewer", "audit-viewer", "<REDACTED_TEST_PASSWORD>"),
    ("operator", "audit-operator", "<REDACTED_TEST_PASSWORD>"),
    ("custodian", "audit-custodian", "<REDACTED_TEST_PASSWORD>"),
    ("technician", "audit-technician", "<REDACTED_TEST_PASSWORD>"),
]

with sync_playwright() as pw:
    br = browser(pw)
    for role, user, pw_ in ROLES:
        ctx = br.new_context(viewport=VIEWPORT)
        ctx.set_default_timeout(7000)
        page = ctx.new_page()
        try:
            sign_in(page, user, pw_)
            body = page.locator("body").inner_text()
            if re.search(r"change your password|new password|must change", body, re.I):
                shot(page, f"r-{role}-0-forcedpw")
                npf = field(page, re.compile(r"New password"))
                if npf.count():
                    npw = pw_ + "x"
                    npf.first.fill(npw)
                    cf = field(page, re.compile(r"Confirm"))
                    if cf.count(): cf.first.fill(npw)
                    btn = page.get_by_role("button", name=re.compile(r"change|save|continue", re.I))
                    if btn.count():
                        btn.first.click()
                        page.wait_for_timeout(2500)
                print(f"{role}: forced pw change completed", flush=True)
            else:
                print(f"{role}: no forced pw change screen", flush=True)
            # backup gate?
            gate = page.locator("body").inner_text()
            if "Skip for now" in gate or "backup" in gate.lower()[:4000]:
                shot(page, f"r-{role}-0b-gate")
            skip_backup_gate(page)
            page.wait_for_timeout(1000)
            shot(page, f"r-{role}-1-landing")
            main = page.locator("body").inner_text()
            navs = [t for t in ["Check a photo", "Review photos", "People", "Events", "World", "Settings"] if t in main]
            banners = [b for b in ["safety copy", "changes since your last backup", "Demo mode"] if b.lower() in main.lower()]
            print(f"{role} navs={navs} banners={banners}", flush=True)
            page.get_by_role("tab", name="People", exact=True).click()
            page.wait_for_timeout(1500)
            shot(page, f"r-{role}-2-people")
            pt = page.locator("main").inner_text()
            print(f"{role} people: addwo={'Add without photo' in pt}", flush=True)
            st_tab = page.get_by_role("tab", name="Settings", exact=True)
            if st_tab.count():
                st_tab.click()
                page.wait_for_timeout(1500)
                shot(page, f"r-{role}-3-settings")
                st = page.locator("main").inner_text()
                print(f"{role} settings:", [s for s in ["License", "Backups", "User accounts", "Integrity", "System details", "Activity log", "About", "Technical"] if s in st], flush=True)
        except Exception as e:
            print(role, "FAIL", str(e)[:100], flush=True)
        ctx.close()
    br.close()
print("done", flush=True)
