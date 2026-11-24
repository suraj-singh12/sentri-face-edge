"""Opt-in browser smoke test of key operator workflows in synthetic dev mode.

Synthetic mode treats each whole image as one face and matches by image bytes, so
this checks UI workflow wiring only, never recognition accuracy.
Run with SENTRIFACE_BROWSER_SMOKE=1 (optionally SENTRIFACE_QA_CHROMIUM=<browser path>).
"""
from __future__ import annotations

import time
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
def app(served_app):
    yield served_app


@pytest.fixture
def served_app(tmp_path):
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
                yield page, errors, tmp_path, server
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
    page.get_by_role("button", name="Confirm Event grouping").wait_for()
    page.get_by_role("button", name="One Event").click()
    page.get_by_role("button", name="Confirm Event grouping").click()
    expect(page.get_by_text("Event 1 of 1")).to_be_visible()
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
    resume = page.get_by_role("button", name="Review skipped now (1)")
    expect(resume).to_be_visible()
    expect(page.get_by_role("button", name="Continue to Relations")).to_be_disabled()
    _shot(page, "04-queue-deferred")
    resume.click()
    expect(page.get_by_text("Showing 2 of 2 pending groups")).to_be_visible()

    for resolved in (2, 3):
        page.get_by_role("button", name="Discard", exact=True).first.click()
        confirm = page.get_by_role("dialog", name="Discard this group?")
        confirm.get_by_role("button", name=re.compile("^Discard")).click()
        confirm.wait_for(state="hidden")
        expect(page.get_by_text(f"{resolved} of 3 faces resolved")).to_be_visible()
    page.get_by_role("button", name="Continue to Relations").click()
    page.get_by_role("button", name="Complete Review").click()
    expect(page.get_by_text("Event finalized")).to_be_visible()
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
    correct = page.get_by_role("button", name="Correct Event", exact=True)
    correct.click()
    dialog = page.get_by_role("dialog").filter(has=page.get_by_label("Event / occasion"))
    dialog.get_by_role("button", name="Save correction").click()
    dialog.wait_for(state="hidden")
    expect(page.get_by_text("No changes to save")).to_be_visible()

    correct.click()
    _field(dialog, "Event / occasion").fill("Corrected smoke occasion")
    dialog.get_by_role("button", name="Save correction").click()
    dialog.wait_for(state="hidden")
    expect(page.get_by_text("Event details corrected")).to_be_visible()
    expect(page.get_by_role("heading", name="Corrected smoke occasion")).to_be_visible()
    page.get_by_text("Correction and provenance history").click()
    assert page.get_by_text("Event interpretation reviewed").count() == 0
    _shot(page, "05b-correction-feedback")


def test_operator_workflows_smoke(app):
    page, errors, tmp, _server = app
    _sign_up(page)
    _shot(page, "01-signed-in")
    _check_photo(page, tmp)
    _review_photos(page, tmp)
    _correction_feedback(page)
    _saved_location_suggestions(page)
    _erase_face(page, _server)
    assert not errors, errors


def _erase_face(page, server):
    engine = server.engine
    person = next(p.person for p in engine.store.list_persons() if p.person.name == "Smoke Person")
    embedding = engine.store.list_embeddings_for_person(person.person_id)[0]
    engine.delete_embedding(embedding.embedding_id, "smoke-erase-remove", actor={"username": "smoke-owner"}, source="smoke")
    page.reload()
    page.get_by_role("tab", name="People", exact=True).click()
    page.get_by_role("button", name=re.compile(r"^Deleted Faces")).click()
    page.get_by_role("button", name="Erase from live library").first.click()
    dialog = page.get_by_role("dialog", name="Erase this face?")
    typed = _field(dialog, "Type ERASE to confirm")
    expect(typed).to_be_focused()
    expect(dialog.get_by_role("button", name="Erase face", exact=True)).to_be_disabled()
    dialog.get_by_role("button", name="Close").click()
    dialog.wait_for(state="hidden")
    assert any(face["embedding_id"] == embedding.embedding_id for face in engine.list_deleted_embeddings())
    page.get_by_role("button", name="Erase from live library").first.click()
    _field(dialog, "Type ERASE to confirm").fill("ERASE")
    _field(dialog, "Type ERASE to confirm").press("Enter")
    dialog.wait_for(state="hidden")
    assert all(face["embedding_id"] != embedding.embedding_id for face in engine.list_deleted_embeddings())
    _shot(page, "06-face-erased")


def test_discard_session_asks_first_and_stays_until_confirmed(app):
    page, errors, tmp, server = app
    _sign_up(page)
    page.get_by_role("tab", name="Review photos", exact=True).click()
    inputs = page.locator("input[type=file][multiple]:not([webkitdirectory])")
    inputs.first.set_input_files([str(_image(tmp / f"discard-{seed}.png", seed)) for seed in (61, 62)])
    page.get_by_role("button", name="Confirm Event grouping").wait_for()
    discard = page.get_by_role("button", name="Discard session", exact=True)
    discard.click()
    dialog = page.get_by_role("dialog", name="Discard this session?")
    page.mouse.click(5, 5)
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    dialog.wait_for(state="hidden")
    assert server.engine.store.list_init_sessions()
    discard.click()
    dialog.get_by_role("button", name="Discard session", exact=True).click()
    dialog.wait_for(state="hidden")
    expect(page.get_by_text("Queue session and its pending photos were discarded")).to_be_visible()
    assert server.engine.store.list_init_sessions() == []
    assert not errors, errors


def _people_card(page, name):
    return page.locator(".people-person-card-inner").filter(has_text=name)


def test_deleted_people_move_to_bin_and_restore_to_active(app):
    page, errors, _tmp, server = app
    _sign_up(page)
    store = server.engine.store
    binned = store.create_person("Bin Keeper")
    archived = store.create_person("Archive Keeper")
    store.archive_person(archived.person_id, "smoke-archive")
    page.reload()
    page.get_by_role("tab", name="People", exact=True).click()

    _people_card(page, "Bin Keeper").get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Delete Person…").click()
    dialog = page.get_by_role("dialog", name="Delete Bin Keeper?")
    expect(dialog.get_by_text("Bin Keeper moves to Bin")).to_be_visible()
    expect(dialog).not_to_contain_text("permanently")
    typed = _field(dialog, "Type DELETE to confirm")
    expect(typed).to_be_focused()
    confirm = dialog.get_by_role("button", name="Delete person", exact=True)
    typed.fill("delete")
    typed.press("Enter")
    expect(confirm).to_be_disabled()
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    dialog.wait_for(state="hidden")
    assert store.get_person(binned.person_id) is not None
    _people_card(page, "Bin Keeper").get_by_role("button", name="More actions").click()
    page.get_by_role("menuitem", name="Delete Person…").click()
    _field(dialog, "Type DELETE to confirm").fill("DELETE")
    _field(dialog, "Type DELETE to confirm").press("Enter")
    expect(page.get_by_text("Bin Keeper moved to Bin.", exact=False)).to_be_visible()
    _shot(page, "bin-01-deleted")
    assert store.get_person(binned.person_id) is None

    page.get_by_role("button", name=re.compile(r"^Archived")).click()
    expect(page.get_by_role("heading", name="Archived", exact=True)).to_be_visible()
    expect(_people_card(page, "Archive Keeper")).to_be_visible()
    expect(_people_card(page, "Bin Keeper")).to_have_count(0)

    page.get_by_role("button", name=re.compile(r"^Bin")).click()
    bin_card = _people_card(page, "Bin Keeper")
    expect(bin_card).to_be_visible()
    expect(_people_card(page, "Archive Keeper")).to_have_count(0)
    expect(bin_card.get_by_role("button", name="Open profile")).to_have_count(0)
    expect(bin_card.locator(".people-card-star")).to_have_count(0)
    expect(bin_card.get_by_role("button", name=re.compile("Bin Keeper"))).to_have_count(0)
    bin_name = bin_card.get_by_text("Bin Keeper", exact=True)
    bin_name.focus()
    expect(bin_name).to_be_focused()
    _shot(page, "bin-02-bin")

    bin_card.get_by_role("button", name="Restore", exact=True).click()
    dialog = page.get_by_role("dialog", name="Restore Bin Keeper?")
    dialog.get_by_role("button", name="Restore person", exact=True).click()
    expect(page.get_by_text("Restored from Bin. This person is active again.")).to_be_visible()
    expect(page.get_by_text("Bin is empty.")).to_be_visible()
    restored = store.get_person(binned.person_id)
    assert restored is not None and restored.deleted_at is None
    page.get_by_role("button", name=re.compile(r"^All People")).click()
    expect(_people_card(page, "Bin Keeper")).to_be_visible()
    _shot(page, "bin-03-restored")
    assert not errors, errors


def _admin_post(page, path, body):
    return page.evaluate(
        """async ([path, body]) => {
            const token = document.querySelector('meta[name="sentriface-session-token"]').content;
            const response = await fetch(path, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-SentriFace-Session": token },
                body: JSON.stringify(body),
            });
            return { status: response.status, body: await response.json() };
        }""",
        [path, body],
    )


def test_new_sign_in_ends_old_window_and_admin_set_password_is_changed_first(app):
    page, errors, _tmp, _server = app
    _sign_up(page)
    created = _admin_post(page, "/api/users", {
        "username": "smoke-viewer", "display_name": "Smoke Viewer",
        "password": "viewer password long enough", "roles": ["viewer"],
    })
    assert created["status"] == 201, created
    assert created["body"]["user"]["must_change_password"] is True

    viewer_context = page.context.browser.new_context(viewport={"width": 1440, "height": 1000})
    viewer_context.set_default_timeout(15000)
    viewer = viewer_context.new_page()
    try:
        viewer.goto(page.url)
        _field(viewer, "Account name").fill("smoke-viewer")
        _field(viewer, "Password").fill("viewer password long enough")
        viewer.get_by_role("button", name="Sign in", exact=True).click()
        expect(viewer.get_by_role("heading", name="Choose a new password")).to_be_visible()
        expect(viewer.get_by_text("An administrator set this password. Choose your own before you continue.")).to_be_visible()
        assert viewer.get_by_role("tab", name="Check a photo", exact=True).count() == 0
        viewer.get_by_role("button", name="Save and continue", exact=True).click()
        expect(viewer.get_by_text("New password is required")).to_be_visible()
        _field(viewer, "New password").fill("viewer chosen password here")
        _field(viewer, "Confirm new password").fill("viewer chosen password here")
        viewer.get_by_role("button", name="Save and continue", exact=True).click()
        viewer.get_by_role("tab", name="Check a photo", exact=True).wait_for()

        page.evaluate("window.dispatchEvent(new Event('focus'))")
        expect(page.get_by_text("Your session ended")).to_be_visible()
        expect(page.get_by_text("You signed in from another window.", exact=False)).to_be_visible()
        expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
        assert page.get_by_text("Connection or operation error").count() == 0
    finally:
        viewer_context.close()
    assert not errors


def test_second_window_is_blocked_until_use_this_window(app):
    page, errors, _tmp, _server = app
    _sign_up(page)
    second = page.context.new_page()
    second.goto(page.url)
    expect(second.get_by_role("heading", name="SentriFace is open in another window")).to_be_visible()
    assert second.get_by_role("tab", name="Check a photo", exact=True).count() == 0
    second.get_by_role("button", name="Use this window", exact=True).click()
    second.get_by_role("tab", name="Check a photo", exact=True).wait_for()

    page.evaluate("window.dispatchEvent(new Event('focus'))")
    expect(page.get_by_role("heading", name="SentriFace is now being used in another window")).to_be_visible()
    page.get_by_role("button", name="Use this window", exact=True).click()
    page.get_by_role("tab", name="Check a photo", exact=True).wait_for()

    # Reloading the active window releases it first, so the reload is not blocked.
    page.reload()
    page.get_by_role("tab", name="Check a photo", exact=True).wait_for()
    second.close()
    assert not errors


ANOTHER_WINDOW_WATCH = """
window.__sawAnotherWindow = false;
new MutationObserver(() => {
  if (document.body && document.body.innerText.includes("open in another window")) window.__sawAnotherWindow = true;
}).observe(document, { subtree: true, childList: true, characterData: true });
"""


def _watch_for_window_block(page):
    """Record whether the next loaded page ever shows the "another window" screen."""
    page.add_init_script(ANOTHER_WINDOW_WATCH)


def test_reload_never_shows_another_window_even_if_the_release_is_late(app):
    page, errors, _tmp, server = app
    _sign_up(page)
    release = server.auth.release_window
    server.auth.release_window = lambda *args: (time.sleep(4), release(*args))
    try:
        _watch_for_window_block(page)
        page.reload()
        page.get_by_role("tab", name="Check a photo", exact=True).wait_for()
        assert page.evaluate("window.__sawAnotherWindow") is False

        # A second tab is still a second window.
        second = page.context.new_page()
        second.goto(page.url)
        expect(second.get_by_role("heading", name="SentriFace is open in another window")).to_be_visible()
        assert second.get_by_role("tab", name="Check a photo", exact=True).count() == 0
        second.close()
    finally:
        server.auth.release_window = release
    assert not errors


def _reference_only_event(engine, tmp):
    import shutil
    import uuid

    person = engine.store.create_person("Attach Owner")
    observation = engine.store.create_observation("smoke-attach-create", participant_ids=[person.person_id])
    engine.store._finalize_observation_without_graph_evidence(observation.observation_id, "smoke-attach-finalize")
    reference = _image(tmp / "reference.png", 41)
    upload = tmp / "reference-upload.png"
    shutil.copy(reference, upload)
    review = engine.prepare_reference_review(reference, person.person_id)
    engine.confirm_reference(review["review_id"], person.person_id, str(uuid.uuid4()), no_context_acknowledged=True,
                             recognition_state="GOOD", actor={"username": "smoke-owner"})
    return upload


def test_failed_attach_media_keeps_retry_and_cancel_until_cancelled(served_app):
    page, errors, tmp, server = served_app
    _sign_up(page)
    upload = _reference_only_event(server.engine, tmp)
    page.reload()
    page.get_by_role("tab", name="Events", exact=True).click()
    page.get_by_text("Unnamed Event").first.click()
    with page.expect_file_chooser() as chooser:
        page.get_by_role("button", name="Attach Media").click()
    chooser.value.set_files(str(upload))
    expect(page.get_by_text("This image is Reference Only biometric material").first).to_be_visible()
    page.get_by_role("tab", name="Review photos", exact=True).click()
    for attempt in range(2):
        expect(page.get_by_text("Attach Media draft")).to_be_visible()
        with page.expect_response(lambda response: "/api/queue-scan" in response.url) as retry:
            page.get_by_role("button", name="Retry Attach Media").click()
        assert retry.value.status >= 400, attempt
        assert "Reference Only" in retry.value.text(), attempt
        expect(page.get_by_text("This image is Reference Only biometric material").last).to_be_visible()
        expect(page.get_by_role("button", name="Retry Attach Media")).to_be_visible()
        expect(page.get_by_role("button", name="Cancel Attach Media")).to_be_visible()
        expect(page.get_by_text("No new media to attach")).to_have_count(0)
        deadline = time.monotonic() + 10
        while (statuses := [session.status for session in server.engine.store.list_init_sessions()]) != ["processing_failed"]:
            assert time.monotonic() < deadline, (attempt, statuses)
            time.sleep(0.1)
        expect(page.get_by_role("button", name="Retry Attach Media")).to_be_enabled()
    _shot(page, "53-attach-retry-kept")
    page.get_by_role("button", name="Cancel Attach Media").click()
    confirm = page.get_by_role("dialog", name=re.compile("^Cancel attaching"))
    confirm.get_by_role("button", name="Keep draft").click()
    confirm.wait_for(state="hidden")
    expect(page.get_by_role("button", name="Retry Attach Media")).to_be_visible()
    page.get_by_role("button", name="Cancel Attach Media").click()
    confirm.get_by_role("button", name="Cancel attachment").click()
    confirm.wait_for(state="hidden")
    expect(page.get_by_text("Attach Media draft")).to_have_count(0)
    assert server.engine.store.list_init_sessions() == []
    assert errors == []


def test_nested_folder_upload_suggests_one_encounter_per_subfolder(app):
    page, errors, tmp, _server = app
    _sign_up(page)
    for relative, seed in (("Trip/Day1/a.png", 51), ("Trip/Day1/b.png", 52), ("Trip/Day2/c.png", 53)):
        target = tmp / "folder" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _image(target, seed)
    page.get_by_role("tab", name="Review photos", exact=True).click()
    page.locator("input[type=file][webkitdirectory]").set_input_files(str(tmp / "folder" / "Trip"))
    page.get_by_role("button", name="Confirm Event grouping").wait_for()
    suggest = page.get_by_role("button", name="Suggest grouping")
    expect(suggest).to_be_enabled()
    expect(page.get_by_text("Suggestions need distinct uploaded subfolders")).to_have_count(0)
    suggest.click()
    expect(page.get_by_text("Event 1: 2 photos")).to_be_visible()
    expect(page.get_by_text("Event 2: 1 photo", exact=True)).to_be_visible()
    _shot(page, "53-nested-suggested")
    assert errors == []


TOAST = ".sentriface-toast-stack[data-position='top-right'] .mantine-Notification-root"
TOAST_KEY = "sentriface.toastPosition.v1"


def _clear_toasts(page):
    page.evaluate("() => document.querySelectorAll('.sentriface-toast-stack .mantine-Notification-closeButton').forEach(b => b.click())")
    expect(page.locator(TOAST)).to_have_count(0)


def _refresh_toast(page):
    page.get_by_role("button", name="Refresh", exact=True).click()
    toast = page.locator(TOAST).filter(has_text="App data refreshed")
    expect(toast).to_have_count(1)
    page.wait_for_timeout(400)
    return toast.bounding_box()


def _overlaps(a, b):
    return a["x"] < b["x"] + b["width"] and a["x"] + a["width"] > b["x"] and a["y"] < b["y"] + b["height"] and a["y"] + a["height"] > b["y"]


def _assert_dialog_buttons_uncovered(page, dialog, room=True):
    """With room the stack moves clear of the dialog; without room the dialog is drawn above it."""
    expect(dialog).to_be_visible()
    page.wait_for_timeout(400)
    buttons = dialog.get_by_role("button")
    toasts = page.locator(TOAST)
    assert toasts.count() >= 1
    for index in range(buttons.count()):
        button = buttons.nth(index)
        box = button.bounding_box()
        if not box:
            continue
        name = button.get_attribute("aria-label") or button.inner_text()
        if room:
            for toast_index in range(toasts.count()):
                assert not _overlaps(box, toasts.nth(toast_index).bounding_box()), name
        assert button.evaluate("""b => {
            const r = b.getBoundingClientRect();
            const points = [[0.5, 0.5], [0.1, 0.1], [0.9, 0.1], [0.1, 0.9], [0.9, 0.9]];
            return points.every(([x, y]) => b.contains(document.elementFromPoint(r.x + r.width * x, r.y + r.height * y)));
        }"""), name


def _fail_password_change(page, times):
    page.get_by_role("button", name="Open account menu").click()
    page.get_by_role("menuitem", name="Change password").click()
    dialog = page.get_by_role("dialog", name="Change password")
    _field(dialog, "Current password").fill("wrong-password-1")
    _field(dialog, "New password").fill("Another-password-123")
    _field(dialog, "Confirm new password").fill("Another-password-123")
    for _ in range(times):
        dialog.get_by_role("button", name="Change password").click()
        page.wait_for_timeout(500)
    return dialog


def test_toasts_move_are_remembered_reset_and_never_cover_dialog_buttons(app):
    page, errors, _tmp, _server = app
    _sign_up(page)
    _clear_toasts(page)
    width = page.viewport_size["width"]
    reset = page.get_by_role("button", name="Move messages back to the top right")

    home = _refresh_toast(page)
    assert abs(home["x"] + home["width"] - (width - 16)) <= 2 and home["y"] < 140, home
    expect(reset).to_have_count(0)

    page.mouse.move(home["x"] + 60, home["y"] + home["height"] / 2)
    page.mouse.down()
    page.mouse.move(width / 2, 430, steps=12)
    page.mouse.up()
    moved = page.locator(TOAST).first.bounding_box()
    assert abs(moved["x"] - (width / 2 - 60)) <= 4 and abs(moved["y"] - (430 - moved["height"] / 2)) <= 4, moved
    assert page.evaluate(f"() => localStorage.getItem('{TOAST_KEY}')")
    expect(reset).to_have_count(1)
    _clear_toasts(page)

    page.reload()
    page.get_by_role("tab", name="Check a photo", exact=True).wait_for()
    _clear_toasts(page)
    again = _refresh_toast(page)
    assert abs(again["x"] - moved["x"]) <= 4 and abs(again["y"] - moved["y"]) <= 60, (again, moved)
    expect(reset).to_have_count(1)
    _clear_toasts(page)

    # The saved spot is where the dialog opens; the stack must make way for its buttons.
    dialog = _fail_password_change(page, 3)
    _assert_dialog_buttons_uncovered(page, dialog)
    expect(reset).to_have_count(0)
    _shot(page, "58-dialog-moved-stack")
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    _clear_toasts(page)

    _refresh_toast(page)
    reset.first.click()
    expect(reset).to_have_count(0)
    assert page.evaluate(f"() => localStorage.getItem('{TOAST_KEY}')") is None
    page.wait_for_timeout(400)
    back = page.locator(TOAST).first.bounding_box()
    assert abs(back["x"] + back["width"] - (width - 16)) <= 2 and back["y"] < 140, back
    _clear_toasts(page)

    dialog = _fail_password_change(page, 5)
    _assert_dialog_buttons_uncovered(page, dialog)
    page.keyboard.press("Escape")

    page.set_viewport_size({"width": 390, "height": 844})
    _clear_toasts(page)
    dialog = _fail_password_change(page, 3)
    _assert_dialog_buttons_uncovered(page, dialog, room=False)
    _shot(page, "58-dialog-narrow")
    assert errors == []
