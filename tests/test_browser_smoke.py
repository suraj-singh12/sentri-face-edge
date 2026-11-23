"""Opt-in browser smoke test of key operator workflows in synthetic dev mode.

Synthetic mode treats each whole image as one face and matches by image bytes, so
this checks UI workflow wiring only, never recognition accuracy.
Run with SENTRIFACE_BROWSER_SMOKE=1 (optionally SENTRIFACE_QA_CHROMIUM=<browser path>).
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SENTRIFACE_BROWSER_SMOKE"),
    reason="Opt-in browser smoke test; set SENTRIFACE_BROWSER_SMOKE=1",
)

PASSWORD = "Smoke-test-password-123"
SHOTS = Path(os.environ.get("SENTRIFACE_SMOKE_SHOTS", "")) if os.environ.get("SENTRIFACE_SMOKE_SHOTS") else None


def _field(scope, label):
    return scope.get_by_label(re.compile(r"^" + re.escape(label) + r"\s*\*?$")).and_(scope.locator("input, textarea"))


def _image(path: Path, seed: int) -> Path:
    import cv2
    import numpy as np

    rng = np.random.default_rng(seed)
    image = rng.integers(0, 255, size=(240, 240, 3), dtype=np.uint8)
    cv2.circle(image, (120, 120), 70, (200, 180, 160), -1)
    cv2.imwrite(str(path), image)
    return path


@pytest.fixture
def app(tmp_path):
    from playwright.sync_api import sync_playwright
    from sentriface.api_server import create_server

    server = create_server(port=0, data_dir=tmp_path / "data", runtime="dev")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            executable = os.environ.get("SENTRIFACE_QA_CHROMIUM") or None
            browser = playwright.chromium.launch(executable_path=executable)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            context.set_default_timeout(15000)
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            try:
                yield page, errors, tmp_path
            finally:
                if SHOTS:
                    _shot(page, "zz-last")
                    (SHOTS / "zz-last.txt").write_text(page.locator("body").inner_text())
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def _shot(page, name):
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"{name}.png"))


def _sign_up(page):
    page.get_by_role("button", name="Create account", exact=True).click()
    expect(page.get_by_text("Account name is required")).to_be_visible()
    _field(page, "Account name").fill("smoke-owner")
    _field(page, "Password").fill(PASSWORD)
    _field(page, "Confirm password").fill(PASSWORD)
    page.get_by_role("button", name="Create account", exact=True).click()
    _field(page, "I understand that my data may not be recoverable without a safety copy.").check()
    page.get_by_role("button", name="Skip for now", exact=True).click()
    page.get_by_role("tab", name="Check a photo", exact=True).wait_for()


def expect(locator):
    from playwright.sync_api import expect as playwright_expect

    return playwright_expect(locator)


def _location(page, dialog, value):
    _field(dialog, "Location").fill(value)
    try:
        expect(page.get_by_role("option", name=f"Create “{value}”")).to_be_visible()
    except AssertionError:
        _shot(page, f"fail-location-{value}")
        raise
    _field(dialog, "Location").press("Tab")
    expect(page.get_by_role("option", name=f"Create “{value}”")).to_be_hidden()


def _upload_check_photo(page, tmp, seed):
    page.locator("input[type=file]").first.set_input_files(str(_image(tmp / f"check-{seed}.png", seed)))
    dialog = page.get_by_role("dialog", name="Event details")
    dialog.wait_for()
    return dialog


def _check_photo(page, tmp):
    # Event details can be cancelled (Cancel/Escape), which clears the photo.
    _upload_check_photo(page, tmp, 1)
    page.keyboard.press("Escape")
    page.get_by_role("dialog", name="Event details").wait_for(state="hidden")
    expect(page.get_by_text("Choose an image to recognize")).to_be_visible()

    dialog = _upload_check_photo(page, tmp, 2)
    dialog.get_by_role("button", name="Confirm Event").click()
    expect(dialog.get_by_text("Event / occasion is required")).to_be_visible()
    expect(dialog.get_by_text("Location is required")).to_be_visible()
    _field(dialog, "Event / occasion").fill("Smoke meeting")
    _location(page, dialog, "Pune")
    dialog.get_by_role("button", name="Confirm Event").click()
    dialog.wait_for(state="hidden")

    # A fully discarded photo explains why it cannot be completed.
    page.get_by_role("button", name="Discard Face").click()
    expect(page.get_by_text("Every face is discarded, so there is nothing to save. Use Clear")).to_be_visible()
    expect(page.get_by_role("button", name="Complete Review")).to_be_disabled()
    _shot(page, "02-check-all-discarded")
    page.get_by_role("button", name=re.compile(r"^Clear")).click()
    page.get_by_text("Choose an image to recognize").wait_for()


def _review_photos(page, tmp):
    page.get_by_role("tab", name="Review photos", exact=True).click()
    inputs = page.locator("input[type=file][multiple]:not([webkitdirectory])")
    inputs.first.set_input_files([str(_image(tmp / f"queue-{seed}.png", seed)) for seed in (11, 12, 13)])
    page.get_by_role("button", name="Confirm Encounter grouping").wait_for()
    page.get_by_role("button", name="One Encounter").click()
    page.get_by_role("button", name="Confirm Encounter grouping").click()
    expect(page.get_by_text("Encounter 1 of 1")).to_be_visible()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(4000)
    page.get_by_role("button", name="Review", exact=True).first.click()
    dialog = page.get_by_role("dialog", name="Event details")
    dialog.wait_for()
    _field(dialog, "Event / occasion").fill("Smoke review")
    _location(page, dialog, "Mumbai")
    dialog.get_by_role("button", name="Confirm Event").click()
    dialog.wait_for(state="hidden")

    # Draft group 1 as a new person, defer group 2, then bring it back (issue #36 dead-end).
    page.get_by_role("button", name="Create new person").click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    expect(page.get_by_text("Name is required")).to_be_visible()
    _field(page, "Rank").fill("Smoke")
    _field(page, "Name").fill("Smoke Person")
    _field(page, "Country").fill("India")
    page.get_by_role("option", name="India", exact=True).click()
    _field(page, "Tag").click()
    page.get_by_role("option").first.click()
    _field(page, "With how many individuals").fill("1")
    page.get_by_role("button", name="Confirm", exact=True).click()
    expect(page.get_by_text("1 of 3 faces resolved")).to_be_visible()
    page.wait_for_load_state("networkidle")

    page.get_by_role("button", name="Review", exact=True).first.click()
    page.get_by_role("button", name="Skip for now").click()
    resume = page.get_by_role("button", name="Review deferred now (1)")
    expect(resume).to_be_visible()
    expect(page.get_by_role("button", name="Continue to Relations")).to_be_disabled()
    _shot(page, "04-queue-deferred")
    resume.click()
    expect(page.get_by_text("Showing 2 of 2 pending groups")).to_be_visible()

    for resolved in (2, 3):
        page.get_by_role("button", name="Discard", exact=True).first.click()
        confirm = page.get_by_role("dialog", name="Discard this entire group?")
        confirm.get_by_role("button", name=re.compile("^Discard")).click()
        confirm.wait_for(state="hidden")
        expect(page.get_by_text(f"{resolved} of 3 faces resolved")).to_be_visible()
    page.get_by_role("button", name="Continue to Relations").click()
    page.get_by_role("button", name="Complete Review").click()
    expect(page.get_by_text("Encounter finalized")).to_be_visible()
    _shot(page, "05-queue-completed")


def _saved_location_suggestions(page):
    # The finalized Encounter's location is offered after three letters; unmatched text offers one create option.
    page.get_by_role("tab", name="People", exact=True).click()
    page.get_by_role("button", name="Add without photo", exact=True).click()
    dialog = page.get_by_role("dialog", name="Add person without a photograph")
    place = _field(dialog, "Place Seen")
    place.fill("mum")
    expect(page.get_by_role("option", name="Mumbai", exact=True)).to_be_visible()
    place.fill("Zzq Town")
    expect(page.get_by_role("option", name="Create “Zzq Town”")).to_be_visible()
    expect(page.get_by_role("option")).to_have_count(1)
    _shot(page, "06-location-suggestions")


def _correction_feedback(page):
    page.get_by_role("tab", name="Events", exact=True).click()
    page.locator(".encounter-list-row").first.click()
    correct = page.get_by_role("button", name="Correct Encounter", exact=True)
    correct.click()
    dialog = page.get_by_role("dialog").filter(has=page.get_by_label("Event / occasion"))
    dialog.get_by_role("button", name="Save correction").click()
    dialog.wait_for(state="hidden")
    expect(page.get_by_text("No changes to save")).to_be_visible()

    correct.click()
    _field(dialog, "Event / occasion").fill("Corrected smoke occasion")
    dialog.get_by_role("button", name="Save correction").click()
    dialog.wait_for(state="hidden")
    expect(page.get_by_text("Encounter details corrected")).to_be_visible()
    expect(page.get_by_role("heading", name="Corrected smoke occasion")).to_be_visible()
    page.get_by_text("Correction and provenance history").click()
    assert page.get_by_text("Encounter interpretation reviewed").count() == 0
    _shot(page, "05b-correction-feedback")


def test_operator_workflows_smoke(app):
    page, errors, tmp = app
    _sign_up(page)
    _shot(page, "01-signed-in")
    _check_photo(page, tmp)
    _review_photos(page, tmp)
    _correction_feedback(page)
    _saved_location_suggestions(page)
    assert not errors, errors
