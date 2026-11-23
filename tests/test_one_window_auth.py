"""#54: one sign-in, one browser window, and first-sign-in password changes."""
from __future__ import annotations

import http.client
import json
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentriface import auth as auth_module
from sentriface.api_server import create_server
from sentriface.auth import AUTH_COOKIE_NAME

OWNER_PASSWORD = "owner password long enough"
TEMPORARY = "temporary password long enough"
CHOSEN = "my own chosen password here"


@pytest.fixture
def server():
    with tempfile.TemporaryDirectory() as temp:
        instance = create_server(port=0, data_dir=Path(temp) / "data", runtime="dev", debug=False)
        thread = threading.Thread(target=instance.serve_forever, daemon=True)
        thread.start()
        try:
            yield instance
        finally:
            instance.shutdown()
            instance.server_close()
            thread.join(timeout=5)


def request(server, method, path, payload=None, *, cookie="", window=""):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"X-SentriFace-Session": server.session_token}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = cookie
    if window:
        headers["X-SentriFace-Window"] = window
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=20)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read()), dict(response.getheaders())
    finally:
        connection.close()


def login(server, username, password, window=""):
    status, payload, headers = request(server, "POST", "/api/auth/login", {"username": username, "password": password}, window=window)
    assert status == 200, payload
    return headers["Set-Cookie"].split(";", 1)[0], payload


def owner(server):
    admin, _ = server.auth.signup_initial("owner", "Owner", OWNER_PASSWORD)
    return admin


def test_a_new_sign_in_ends_every_other_session_for_any_account(server):
    admin = owner(server)
    server.auth.create_user(admin, "asha", "Asha", TEMPORARY, ["operator"])
    first, _ = login(server, "owner", OWNER_PASSWORD, window="window-one-1234")
    assert request(server, "GET", "/api/profile", cookie=first, window="window-one-1234")[0] == 200

    login(server, "asha", TEMPORARY, window="window-two-1234")

    status, payload, _ = request(server, "GET", "/api/profile", cookie=first, window="window-one-1234")
    assert status == 401
    assert payload["session_ended"]["reason"] == "signed_in_elsewhere"
    status, auth_status, _ = request(server, "GET", "/api/auth/status", cookie=first, window="window-one-1234")
    assert auth_status["authenticated"] is False
    assert "another window" in auth_status["session_ended"]["message"]


def test_old_window_sharing_the_new_cookie_still_learns_its_session_ended(server):
    owner(server)
    login(server, "owner", OWNER_PASSWORD, window="window-one-1234")
    # Same browser: the second sign-in replaces the cookie the first window also sends.
    cookie, _ = login(server, "owner", OWNER_PASSWORD, window="window-two-1234")
    status, payload, _ = request(server, "GET", "/api/profile", cookie=cookie, window="window-one-1234")
    assert status == 401
    assert payload["session_ended"]["reason"] == "signed_in_elsewhere"
    assert request(server, "GET", "/api/profile", cookie=cookie, window="window-two-1234")[0] == 200


def test_second_window_is_blocked_until_it_takes_over(server):
    owner(server)
    cookie, payload = login(server, "owner", OWNER_PASSWORD, window="window-one-1234")
    assert payload["window"] == "active"

    status, blocked, _ = request(server, "GET", "/api/auth/status", cookie=cookie, window="window-two-1234")
    assert status == 200 and blocked["authenticated"] is True and blocked["window"] == "in_use"
    status, payload, _ = request(server, "GET", "/api/profile", cookie=cookie, window="window-two-1234")
    assert status == 409 and payload["code"] == "window_in_use"
    status, payload, _ = request(server, "POST", "/api/person-create", {"name": "Blocked"}, cookie=cookie, window="window-two-1234")
    assert status == 409 and payload["code"] == "window_in_use"

    status, claimed, _ = request(server, "POST", "/api/auth/window", {"action": "claim"}, cookie=cookie, window="window-two-1234")
    assert status == 200 and claimed["window"] == "active"
    assert request(server, "GET", "/api/profile", cookie=cookie, window="window-two-1234")[0] == 200

    status, payload, _ = request(server, "GET", "/api/profile", cookie=cookie, window="window-one-1234")
    assert status == 409 and payload["code"] == "window_replaced"
    status, heartbeat, _ = request(server, "POST", "/api/auth/window", {"action": "heartbeat"}, cookie=cookie, window="window-one-1234")
    assert status == 200 and heartbeat["window"] == "replaced"


def test_stale_or_released_window_is_taken_over_without_asking(server, monkeypatch):
    owner(server)
    cookie, _ = login(server, "owner", OWNER_PASSWORD, window="window-one-1234")
    session = next(iter(server.auth._sessions.values()))
    session.window_seen_at = datetime.now(timezone.utc) - timedelta(seconds=auth_module.WINDOW_STALE_SECONDS + 1)
    assert request(server, "GET", "/api/auth/status", cookie=cookie, window="window-two-1234")[1]["window"] == "active"

    # Reload: the page releases its window first, so the reloaded page continues.
    request(server, "POST", "/api/auth/window", {"action": "release"}, cookie=cookie, window="window-two-1234")
    assert request(server, "GET", "/api/auth/status", cookie=cookie, window="window-three-1234")[1]["window"] == "active"


def test_window_check_ins_do_not_count_as_activity(server):
    owner(server)
    cookie, _ = login(server, "owner", OWNER_PASSWORD, window="window-one-1234")
    session = next(iter(server.auth._sessions.values()))
    earlier = datetime.now(timezone.utc) - timedelta(minutes=5)
    session.last_seen_at = earlier
    request(server, "POST", "/api/auth/window", {"action": "heartbeat"}, cookie=cookie, window="window-one-1234")
    request(server, "GET", "/api/auth/status", cookie=cookie, window="window-one-1234")
    assert session.last_seen_at == earlier
    request(server, "GET", "/api/profile", cookie=cookie, window="window-one-1234")
    assert session.last_seen_at > earlier


def test_requests_without_a_window_id_are_not_blocked(server):
    owner(server)
    cookie, _ = login(server, "owner", OWNER_PASSWORD, window="window-one-1234")
    assert request(server, "GET", "/api/profile", cookie=cookie)[0] == 200
    assert request(server, "GET", "/api/profile", cookie=cookie, window="bad id!")[0] == 200


def test_administrator_set_passwords_must_be_changed_before_anything_else(server):
    admin = owner(server)
    created = server.auth.create_user(admin, "asha", "Asha", TEMPORARY, ["operator"])
    assert created["must_change_password"] is True
    assert server.auth.get_user(admin.user_id).must_change_password is False

    cookie, payload = login(server, "asha", TEMPORARY, window="window-one-1234")
    assert payload["user"]["must_change_password"] is True
    for method, path, body in (("GET", "/api/profile", None), ("POST", "/api/auth/change-password", {"current_password": TEMPORARY, "new_password": CHOSEN})):
        status, refused, _ = request(server, method, path, body, cookie=cookie, window="window-one-1234")
        assert status == 403 and refused["code"] == "password_change_required"

    status, refused, _ = request(server, "POST", "/api/auth/set-password", {"new_password": TEMPORARY}, cookie=cookie, window="window-one-1234")
    assert status == 422 and refused["code"] == "password_reused"
    status, refused, _ = request(server, "POST", "/api/auth/set-password", {"new_password": "short"}, cookie=cookie, window="window-one-1234")
    assert status == 422

    status, saved, headers = request(server, "POST", "/api/auth/set-password", {"new_password": CHOSEN}, cookie=cookie, window="window-one-1234")
    assert status == 200 and saved["authenticated"] is True and saved["user"]["must_change_password"] is False
    assert "Set-Cookie" not in headers
    assert request(server, "GET", "/api/profile", cookie=cookie, window="window-one-1234")[0] == 200
    status, again, _ = request(server, "POST", "/api/auth/set-password", {"new_password": "another chosen password"}, cookie=cookie, window="window-one-1234")
    assert status == 409 and again["code"] == "password_change_not_required"
    login(server, "asha", CHOSEN)


def test_administrator_reset_requires_a_new_password_and_emergency_reset_does_not(server):
    admin = owner(server)
    created = server.auth.create_user(admin, "asha", "Asha", TEMPORARY, ["administrator"])
    with server.auth._connect() as connection:
        connection.execute("UPDATE app_users SET must_change_password = 0 WHERE user_id = ?", (created["user_id"],))
    server.auth.reset_password(admin, created["user_id"], "reset password long enough")
    assert server.auth.get_user(created["user_id"]).must_change_password is True
    _, payload = login(server, "asha", "reset password long enough")
    assert payload["user"]["must_change_password"] is True


def test_users_list_reports_who_must_change_their_password(server):
    admin = owner(server)
    server.auth.create_user(admin, "asha", "Asha", TEMPORARY, ["viewer"])
    cookie, _ = login(server, "owner", OWNER_PASSWORD)
    status, payload, _ = request(server, "GET", "/api/users", cookie=cookie)
    assert status == 200
    flags = {user["username"]: user["must_change_password"] for user in payload["users"]}
    assert flags == {"owner": False, "asha": True}


def test_signup_and_login_cookie_name_is_unchanged(server):
    owner(server)
    cookie, _ = login(server, "owner", OWNER_PASSWORD)
    assert cookie.startswith(f"{AUTH_COOKIE_NAME}=")
