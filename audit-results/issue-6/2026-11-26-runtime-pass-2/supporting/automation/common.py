"""Shared helpers for the SentriFace Issue #6 audit."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect as pw_expect
import re, sys, json

BASE = "http://127.0.0.1:8765/"
SHOTS = Path("/home/ubuntu/audit6/shots")
ADMIN = ("audit-admin", "<REDACTED_TEST_PASSWORD>")
USERS = {  # username -> (password, roles, display)
    "audit-viewer":     ("<REDACTED_TEST_PASSWORD>", ["viewer"], "Vera Viewer"),
    "audit-operator":   ("<REDACTED_TEST_PASSWORD>", ["operator"], "Omar Operator"),
    "audit-custodian":  ("<REDACTED_TEST_PASSWORD>", ["custodian"], "Cara Custodian"),
    "audit-technician": ("<REDACTED_TEST_PASSWORD>", ["technician"], "Theo Technician"),
}
VIEWPORT = {"width": 1440, "height": 900}

def browser(pw, headless=True):
    return pw.chromium.launch(headless=headless)

def shot(page, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"))

def expect(loc):
    return pw_expect(loc)

def field(scope, label):
    pat = label if hasattr(label, "search") else re.compile(r"^" + re.escape(label) + r"\s*\*?$")
    return scope.get_by_label(pat).and_(scope.locator("input, textarea, select"))

def login(page, username, password):
    page.goto(BASE)
    # if already signed in as someone else, sign out first
    page.wait_for_timeout(2500)
    if page.get_by_role("button", name="Sign in", exact=True).count() or page.get_by_text("Sign in", exact=False).count():
        pass
    return page
