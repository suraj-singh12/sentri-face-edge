"""Opt-in browser regression tests for the six Issue #6 operator flow families.

Synthetic dev mode (whole-image detector, hash embedder) validates workflow wiring,
authorization and persistence only, never recognition accuracy. The multi-face test
patches the dev detector in-process so one generated image yields several faces.
Run with SENTRIFACE_BROWSER_SMOKE=1 (optionally SENTRIFACE_QA_CHROMIUM=<browser path>).
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

import pytest

from test_browser_smoke import PASSWORD, _field, _image, _location, _sign_up, expect

pytestmark = pytest.mark.skipif(
    not os.environ.get("SENTRIFACE_BROWSER_SMOKE"),
    reason="Opt-in browser regression test; set SENTRIFACE_BROWSER_SMOKE=1",
)

STRIP = 240


class _App:
    def __init__(self, browser, base, tmp):
        self.browser, self.base, self.tmp = browser, base, tmp

    def page(self):
        context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        context.set_default_timeout(15000)
        page = context.new_page()
        page.goto(self.base)
        return page


@pytest.fixture
def app(tmp_path):
    from playwright.sync_api import sync_playwright
    from sentriface.api_server import create_server

    server = create_server(port=0, data_dir=tmp_path / "data", runtime="dev")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.environ.get("SENTRIFACE_QA_CHROMIUM") or None)
            try:
                yield _App(browser, f"http://127.0.0.1:{server.server_port}/", tmp_path)
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@pytest.fixture
def multi_face(monkeypatch):
    from sentriface.components import dev_components
    from sentriface.components.dev_components import _image_size
    from sentriface.models import DetectedFace, FaceBox

    def detect(self, image_path: Path):
        width, height = _image_size(image_path, self.storage_key)
        return [
            DetectedFace(box=FaceBox(x=i * STRIP, y=0, width=STRIP, height=height, confidence=1.0), quality_score=1.0, crop_path=None)
            for i in range(width // STRIP)
        ]

    monkeypatch.setattr(dev_components.WholeImageFaceDetector, "detect", detect)


def _wide_image(path: Path, faces: int, seed: int) -> Path:
    import cv2
    import numpy as np

    rng = np.random.default_rng(seed)
    image = rng.integers(0, 255, size=(STRIP, STRIP * faces, 3), dtype=np.uint8)
    cv2.imwrite(str(path), image)
    return path


def _api(page, path):
    return page.evaluate(
        """async (path) => {
            const token = document.querySelector('meta[name="sentriface-session-token"]').content;
            const response = await fetch(path, {headers: {"X-SentriFace-Session": token}});
            return {status: response.status, body: await response.json().catch(() => null)};
        }""",
        path,
    )


def _persons(page):
    body = _api(page, "/api/persons")["body"]
    return body if isinstance(body, list) else body.get("persons", body.get("items", []))


def _tab(page, name):
    page.get_by_role("tab", name=name, exact=True).click()


def _sign_in(page, username, password):
    page.get_by_role("textbox", name="Account name").fill(username)
    page.get_by_role("textbox", name="Password").fill(password)
    page.get_by_role("button", name="Sign in", exact=True).click()


def _sign_out(page):
    page.get_by_role("button", name=re.compile("account menu", re.I)).click()
    page.get_by_role("menuitem", name="Sign out").click()
    page.get_by_role("button", name="Sign in", exact=True).wait_for()


def _event_details(page, dialog, occasion, location):
    _field(dialog, "Event / occasion").fill(occasion)
    _location(page, dialog, location)
    dialog.get_by_role("button", name="Confirm Event").click()
    dialog.wait_for(state="hidden")


def _check_photo(page, path, occasion="Regression event", location="Pune"):
    _tab(page, "Check a photo")
    page.locator("input[type=file]").first.set_input_files(str(path))
    dialog = page.get_by_role("dialog", name="Event details")
    dialog.wait_for()
    _event_details(page, dialog, occasion, location)


def _new_person_form(page, name):
    page.get_by_role("button", name="Create new person").click()
    _field(page, "Rank").fill("Rgr")
    _field(page, "Name").fill(name)
    _field(page, "Country").fill("India")
    page.get_by_role("option", name="India", exact=True).click()
    _field(page, "Tag").click()
    page.get_by_role("option").first.click()
    _field(page, "With how many individuals").fill("1")
    page.get_by_role("button", name="Confirm", exact=True).click()


def _settings(page, section):
    _tab(page, "Settings")
    page.get_by_role("button", name=section).first.click()


def _add_account(page, username, role):
    _settings(page, "User accounts")
    page.get_by_role("button", name="Add account").click()
    dialog = page.get_by_role("dialog")
    _field(dialog, "Username").fill(username)
    _field(dialog, "Display name").fill(username.title())
    dialog.get_by_label(re.compile("password", re.I)).and_(dialog.locator("input")).first.fill(PASSWORD)
    if role != "Viewer":
        dialog.get_by_label("Roles").click()
        page.get_by_role("option", name=role, exact=True).click()
        page.keyboard.press("Escape")
    dialog.get_by_role("button", name=re.compile("^Create")).click()
    expect(page.get_by_text("Machine account created").last).to_be_visible()
    page.get_by_role("dialog").wait_for(state="hidden")


def test_multi_face_review_persists_only_after_every_face_is_decided(app, multi_face):
    page = app.page()
    _sign_up(page)
    _check_photo(page, _wide_image(app.tmp / "three.png", 3, 7), occasion="Multi-face check")
    expect(page.get_by_text("3 faces detected")).to_be_visible()
    _new_person_form(page, "Multi Alpha")
    complete = page.get_by_role("button", name="Complete Review")
    expect(complete).to_be_disabled()
    assert _persons(page) == []

    page.get_by_role("button").filter(has_text=re.compile(r"^Face 02")).first.click()
    page.get_by_role("button", name="Discard Face").click()
    page.reload()
    page.get_by_role("button").filter(has_text=re.compile(r"^Face 03")).first.wait_for()
    expect(page.get_by_role("button", name="Complete Review")).to_be_disabled()
    assert _persons(page) == []

    page.get_by_role("button").filter(has_text=re.compile(r"^Face 03")).first.click()
    page.get_by_role("button", name="Discard Face").click()
    page.get_by_role("button", name="Complete Review").click()
    expect(page.get_by_text("Review completed")).to_be_visible()
    assert [p.get("display_name") or p.get("name") for p in _persons(page)] == ["Multi Alpha"]
    _tab(page, "Events")
    expect(page.get_by_text("Multi-face check")).to_be_visible()


def test_change_password_rejects_bad_input_and_revokes_old_password(app):
    page = app.page()
    _sign_up(page)
    page.get_by_role("button", name=re.compile("account menu", re.I)).click()
    page.get_by_role("menuitem", name="Change password").click()
    dialog = page.get_by_role("dialog", name="Change password")
    fields = dialog.locator("input[type=password]")
    new = "Changed-password-456"
    fields.nth(0).fill("Wrong-current-000")
    fields.nth(1).fill(new)
    fields.nth(2).fill(new + "x")
    expect(dialog.get_by_text("Passwords do not match")).to_be_visible()
    save = dialog.get_by_role("button", name="Change password")
    expect(save).to_be_disabled()
    fields.nth(2).fill(new)
    save.click()
    expect(page.get_by_text("Current password is incorrect").first).to_be_visible()
    expect(dialog).to_be_visible()
    fields.nth(0).fill(PASSWORD)
    save.click()
    expect(page.get_by_text("Password changed. Sign in again.")).to_be_visible()
    page.get_by_role("button", name="Sign in", exact=True).wait_for()
    _sign_in(page, "smoke-owner", PASSWORD)
    expect(page.get_by_text("Username or password is incorrect")).to_be_visible()
    _sign_in(page, "smoke-owner", new)
    page.get_by_role("tab", name="Check a photo", exact=True).wait_for()


def test_roles_limit_navigation_and_disabled_accounts_cannot_sign_in(app):
    admin = app.page()
    _sign_up(admin)
    _add_account(admin, "reg-viewer", "Viewer")
    _add_account(admin, "reg-technician", "Technician")

    viewer = app.page()
    _sign_in(viewer, "reg-viewer", PASSWORD)
    viewer.get_by_role("tab", name="Check a photo", exact=True).wait_for()
    assert viewer.get_by_role("tab").all_inner_texts() == ["Check a photo", "People", "Events", "World"]
    assert _api(viewer, "/api/backups")["status"] == 403

    technician = app.page()
    _sign_in(technician, "reg-technician", PASSWORD)
    technician.get_by_role("tab", name="Settings", exact=True).wait_for()
    assert "Review photos" not in technician.get_by_role("tab").all_inner_texts()
    _settings(technician, "Backups & restore")
    expect(technician.get_by_role("button", name=re.compile("^Import")).first).to_be_disabled()
    assert _api(technician, "/api/backups")["status"] == 200

    admin.locator(".mantine-Card-root").filter(has_text="reg-technician").get_by_role("button", name="Manage").click()
    dialog = admin.get_by_role("dialog", name=re.compile("Manage"))
    dialog.get_by_label("Disable this account").check()
    dialog.get_by_role("button", name="Save roles").click()
    expect(admin.locator(".mantine-Card-root").filter(has_text="reg-technician").get_by_text("Disabled", exact=True)).to_be_visible()
    assert _api(technician, "/api/persons")["status"] == 401
    signin = app.page()
    _sign_in(signin, "reg-technician", PASSWORD)
    expect(signin.get_by_text("This account is disabled")).to_be_visible()


def _enroll_from_photo(page, tmp, name, occasion, seed):
    _check_photo(page, _image(tmp / f"{seed}.png", seed), occasion=occasion, location=f"Site {seed}")
    _new_person_form(page, name)
    page.get_by_role("button", name="Complete Review").click()
    expect(page.get_by_text("Review completed")).to_be_visible()


def _open_event(page, occasion):
    _tab(page, "Events")
    page.get_by_text(occasion).first.click()
    page.get_by_role("button", name="Correct Encounter").wait_for()


def _correct_occasion(page, value):
    page.get_by_role("button", name="Correct Encounter").click()
    dialog = page.get_by_role("dialog").filter(has=page.get_by_label("Event / occasion"))
    _field(dialog, "Event / occasion").fill(value)
    return dialog


def test_encounter_correction_persists_history_and_refuses_stale_revision(app):
    page = app.page()
    _sign_up(page)
    _enroll_from_photo(page, app.tmp, "Corr Alpha", "Original occasion", 21)

    other = app.page()
    _sign_in(other, "smoke-owner", PASSWORD)
    _open_event(other, "Original occasion")
    stale = _correct_occasion(other, "Stale occasion")

    _open_event(page, "Original occasion")
    dialog = _correct_occasion(page, "Corrected occasion")
    dialog.get_by_role("button", name=re.compile("^Save")).click()
    dialog.wait_for(state="hidden")
    expect(page.get_by_text("Corrected occasion").first).to_be_visible()

    stale.get_by_role("button", name=re.compile("^Save")).click()
    expect(stale).to_be_visible()
    other.reload()
    _tab(other, "Events")
    expect(other.get_by_text("Corrected occasion").first).to_be_visible()
    expect(other.get_by_text("Stale occasion")).to_have_count(0)


def _open_profile(page, name):
    _tab(page, "People")
    page.get_by_text(name).first.click()
    page.get_by_role("button", name="More", exact=True).wait_for()


def _backups(page):
    body = _api(page, "/api/backups")["body"]
    return body if isinstance(body, list) else body.get("backups", [])


def _person(page, name):
    body = _api(page, "/api/persons")["body"]
    return next(p for p in body["persons"] + body["archived_persons"] if p.get("name") == name or name in str(p))


def test_archive_restore_and_delete_keep_history(app):
    page = app.page()
    _sign_up(page)
    _enroll_from_photo(page, app.tmp, "Life Alpha", "Lifecycle event", 31)
    _open_profile(page, "Life Alpha")

    page.get_by_role("button", name="More", exact=True).click()
    page.get_by_role("menuitem", name=re.compile("^Archive")).click()
    dialog = page.get_by_role("dialog", name="Archive this person?")
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    dialog.wait_for(state="hidden")
    assert _person(page, "Life Alpha")["archived"] is False
    page.get_by_role("button", name="More", exact=True).click()
    page.get_by_role("menuitem", name=re.compile("^Archive")).click()
    dialog.get_by_role("button", name=re.compile("^Archive")).click()
    expect(page.get_by_text(re.compile("Person moved to Archived"))).to_be_visible()
    assert _person(page, "Life Alpha")["archived"] is True

    page.get_by_role("button", name=re.compile(r"^Archived \d")).click()
    page.get_by_text("Life Alpha").first.click()
    page.get_by_role("button", name="Restore", exact=True).click()
    restore = page.get_by_role("dialog", name="Restore this person?")
    restore.get_by_role("button", name=re.compile("^Restore")).click()
    expect(page.get_by_text("Person restored").first).to_be_visible()
    restore.wait_for(state="hidden")
    assert _person(page, "Life Alpha")["archived"] is False

    page.get_by_role("button", name="More", exact=True).click()
    page.get_by_role("menuitem", name=re.compile("^Delete Person")).click()
    dialog = page.get_by_role("dialog", name=re.compile(r"^Delete .Life Alpha.\?$"))
    expect(dialog.get_by_text("This person moves to Bin")).to_be_visible()
    confirm = dialog.get_by_role("button", name=re.compile("^Delete"))
    dialog.get_by_label("Type DELETE to confirm").fill("delete")
    expect(confirm).to_be_disabled()
    dialog.get_by_label("Type DELETE to confirm").fill("DELETE")
    confirm.click()
    dialog.wait_for(state="hidden")
    assert _person(page, "Life Alpha")["deleted"] is True
    page.get_by_role("button", name=re.compile(r"^Bin \d")).click()
    expect(page.get_by_text("Life Alpha").first).to_be_visible()
    _tab(page, "Events")
    page.get_by_text("Lifecycle event").first.click()
    expect(page.get_by_text(re.compile(r"Life Alpha.*\(deleted\)")).first).to_be_visible()


def test_backup_restore_replaces_data_after_cancel_and_keeps_safety_copy(app):
    page = app.page()
    _sign_up(page)
    _enroll_from_photo(page, app.tmp, "Kept Alpha", "Before backup", 41)
    _settings(page, "Backups & restore")
    page.get_by_role("button", name="Create Backup").first.click()
    page.get_by_role("dialog").get_by_role("button", name="Create Backup").click()
    rows = page.get_by_role("button", name=re.compile("^Restore backup"))
    expect(rows.first).to_be_enabled()
    backups_before = len(_backups(page))

    _enroll_from_photo(page, app.tmp, "Later Bravo", "After backup", 42)
    assert any("Later Bravo" in str(p) for p in _persons(page))
    _settings(page, "Backups & restore")
    rows.first.click()
    dialog = page.get_by_role("dialog", name="Restore portable backup?")
    dialog.get_by_role("button", name="Cancel").click()
    dialog.wait_for(state="hidden")
    assert any("Later Bravo" in str(p) for p in _persons(page))

    rows.first.click()
    dialog.get_by_role("button", name=re.compile("^Restore")).click()
    expect(page.get_by_role("tab", name="Check a photo", exact=True)).to_have_attribute("aria-selected", "true")
    page.wait_for_load_state("load")
    names = str(_persons(page))
    assert "Kept Alpha" in names and "Later Bravo" not in names
    assert len(_backups(page)) > backups_before
