"""Paired browser verification of Database A and Database B' in the real React UI.

    PLAYWRIGHT_BROWSERS_PATH=... python -m experiments.issue89.browser_verify S1:H2 S5:H2 S6:H2 S1:L

For each authority the real application is started (genuine ONNX runtime),
the operator signs in through the UI, and the same sequence of screens is
captured: People, a Person profile, Events, World Explore, World Connections
and Check a photo with a held-out genuine probe photograph. The rendered text
of each screen is also saved so the pair can be diffed, not only eyeballed.
Run after the corresponding run_scenario experiment (it reuses its authorities).
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from .build import authority
from .harness import experimental_api, read_fixes
from .harness.app import ADMIN, KIT, App
from .run_scenario import EVIDENCE

SCREENS = {"S1": ("Birch", "fir-8"), "S2": ("Alder", "alder-8"), "S5": ("Juniper", "juniper-8"), "S6": ("Elm", "elm-8"),
           "S4": ("Maple", "maple-8"), "S8": ("Hazel", "hazel-8"), "S3": ("Dogwood", "kauri-8"), "S7": ("Birch", "kauri-8")}


def _field(scope, label):
    # Same locator as scripts/qa_browser.py (Mantine adds a required asterisk).
    return scope.get_by_label(re.compile(r"^" + re.escape(label) + r"\s*\*?$")).and_(scope.locator("input, textarea"))


def _sign_in(page):
    _field(page, "Account name").fill(ADMIN[0])
    _field(page, "Password").fill(ADMIN[2])
    page.get_by_role("button", name="Sign in", exact=True).click()
    page.wait_for_timeout(1500)
    ack = _field(page, "I understand that my data may not be recoverable without a safety copy.")
    if ack.count():
        ack.check()
        page.get_by_role("button", name="Skip for now", exact=True).click()
        page.wait_for_timeout(800)


def _tab(page, name):
    page.get_by_role("tab", name=name, exact=True).click()
    page.wait_for_timeout(1800)


def capture(app: App, out: Path, person: str, probe: str) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    texts = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{app.server.server_port}/")
        page.wait_for_timeout(1500)
        _sign_in(page)

        def shot(name):
            # The repository is public: every photograph (LFW research images) is
            # blurred in committed screenshots; layout, text and counts stay visible.
            page.add_style_tag(content="img, canvas, image, [style*='background-image'] {filter: blur(14px) !important}")
            page.wait_for_timeout(300)
            page.screenshot(path=str(out / f"{name}.jpg"), full_page=False, type="jpeg", quality=70)
            texts[name] = page.locator("body").inner_text()

        _tab(page, "People")
        shot("1-people")
        page.get_by_placeholder("Search by name, ID or tag...").fill(person)
        page.wait_for_timeout(1200)
        expand = page.get_by_text("UNKNOWN COUNTRY")
        if expand.count() and not page.get_by_text("Open profile").count():
            expand.first.click()
            page.wait_for_timeout(800)
        opener = page.get_by_text("Open profile", exact=True)
        if opener.count():
            opener.first.click()
            page.wait_for_timeout(2500)
            shot("2-person")
            back = page.get_by_role("button", name="Back to people", exact=True)
            if back.count():
                back.first.click()
                page.wait_for_timeout(800)
        _tab(page, "Events")
        shot("3-events")
        _tab(page, "World")
        page.wait_for_timeout(2500)
        shot("4-world-explore")
        connections = page.get_by_text("Connections", exact=True)
        if connections.count():
            connections.first.click()
            page.wait_for_timeout(3000)
            shot("5-world-connections")
        _tab(page, "Check a photo")
        page.locator("input[type=file]").first.set_input_files(str(KIT / f"{probe}.jpg"))
        page.wait_for_timeout(9000)
        # The Event-details prompt opens over the results; Cancel would discard the
        # staged review, so hide the overlay *visually only* for the screenshot.
        page.add_style_tag(content=".mantine-Modal-root{display:none !important}")
        page.wait_for_timeout(500)
        shot("6-check-a-photo")
        texts["_page_errors"] = "\n".join(errors)
        browser.close()
    (out / "texts.json").write_text(json.dumps(texts, indent=1))
    return texts


def _clean(text: str) -> list[str]:
    # Relative-time phrases depend on the wall clock of the capture moment.
    return [re.sub(r"\b\d+ (seconds?|minutes?) ago\b", "<time ago>", line) for line in text.splitlines() if line.strip()]


def run(pair: str) -> dict:
    sid, variant = pair.split(":")
    if variant in ("H2", "L"):
        read_fixes.install()
    experimental_api.install("hard" if variant != "L" else "logical", fixes=True)
    person, probe = SCREENS.get(sid, ("Alder", "alder-8"))
    result = {}
    texts = {}
    for db, label in (("A", "A"), ("B", "Bprime")):
        app = App(authority(sid, db)).start()
        try:
            texts[label] = capture(app, EVIDENCE / f"{sid}-{variant}" / "screens" / label, person, probe)
        finally:
            app.stop()
    for screen in sorted(set(texts["A"]) & set(texts["Bprime"])):
        a, b = _clean(texts["A"][screen]), _clean(texts["Bprime"][screen])
        diff = [line for line in difflib.unified_diff(a, b, "A", "Bprime", lineterm="", n=0) if not line.startswith(("---", "+++", "@@"))]
        result[screen] = {"identical_text": not diff, "diff": diff[:40]}
    (EVIDENCE / f"{sid}-{variant}" / "screens" / "text-diff.json").write_text(json.dumps(result, indent=1))
    return result


if __name__ == "__main__":
    for pair in sys.argv[1:]:
        outcome = run(pair)
        print(pair, json.dumps({k: (v["identical_text"], v["diff"][:6]) for k, v in outcome.items()}, indent=1)[:4000])
