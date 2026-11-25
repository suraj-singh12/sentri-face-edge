"""#54: one sign-in, one browser window, and first-sign-in password changes."""
from __future__ import annotations

from contextlib import contextmanager
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


def request(server, method, path, payload=None, *, cookie="", window="", reloaded_from=""):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"X-SentriFace-Session": server.session_token}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = cookie
    if window:
        headers["X-SentriFace-Window"] = window
    if reloaded_from:
        headers["X-SentriFace-Reloaded-From"] = reloaded_from
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


def test_a_reloaded_tab_takes_over_its_own_window_before_the_release_arrives(server):
    owner(server)
    cookie, _ = login(server, "owner", OWNER_PASSWORD, window="window-old-1234")
    # The reloaded page asks first; the old page's release is still on its way.
    status, payload, _ = request(server, "GET", "/api/auth/status", cookie=cookie, window="window-new-1234", reloaded_from="window-old-1234")
    assert status == 200 and payload["window"] == "active"
    request(server, "POST", "/api/auth/window", {"action": "release"}, cookie=cookie, window="window-old-1234")
    assert request(server, "GET", "/api/profile", cookie=cookie, window="window-new-1234")[0] == 200
    assert request(server, "GET", "/api/profile", cookie=cookie, window="window-old-1234")[1]["code"] == "window_replaced"


def test_reload_takeover_is_refused_unless_it_names_this_sessions_active_window(server):
    owner(server)
    login(server, "owner", OWNER_PASSWORD, window="window-one-1234")
    # A newer sign-in ends the first session; its window cannot hand over the new one.
    cookie, _ = login(server, "owner", OWNER_PASSWORD, window="window-two-1234")
    for reloaded_from in ("window-one-1234", "window-unknown-1234", "bad id!"):
        payload = request(server, "GET", "/api/auth/status", cookie=cookie, window="window-three-1234", reloaded_from=reloaded_from)[1]
        assert payload["window"] == "in_use", reloaded_from

    # A replaced window is no longer the active owner, so it cannot hand over either.
    request(server, "POST", "/api/auth/window", {"action": "claim"}, cookie=cookie, window="window-three-1234")
    payload = request(server, "GET", "/api/auth/status", cookie=cookie, window="window-four-1234", reloaded_from="window-two-1234")[1]
    assert payload["window"] == "in_use"

    # Only the status check carries the takeover; other requests stay blocked.
    status, refused, _ = request(server, "GET", "/api/profile", cookie=cookie, window="window-four-1234", reloaded_from="window-three-1234")
    assert status == 409 and refused["code"] == "window_in_use"
    assert request(server, "GET", "/api/profile", cookie=cookie, window="window-three-1234")[0] == 200


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


def test_emergency_reset_in_another_process_ends_the_running_servers_session(server):
    owner(server)
    created = server.auth.create_user(server.auth.get_user(server.auth.list_users()[0]["user_id"]), "asha", "Asha", TEMPORARY, ["administrator"])
    cookie, payload = login(server, "asha", TEMPORARY, window="window-one-1234")
    assert payload["user"]["must_change_password"] is True
    # The recovery command runs as a separate process with its own AuthService.
    auth_module.AuthService(server.auth.db_path, server.auth.database_key).emergency_reset_administrator("asha", "custodian chosen password")
    status, refused, _ = request(server, "GET", "/api/profile", cookie=cookie, window="window-one-1234")
    assert status == 401 and refused["session_ended"]["reason"] == "password_reset"
    assert server.auth.get_user(created["user_id"]).must_change_password is False


def test_forced_password_change_keeps_its_own_session_bound_to_the_new_password(server):
    owner(server)
    server.auth.create_user(server.auth.get_user(server.auth.list_users()[0]["user_id"]), "asha", "Asha", TEMPORARY, ["operator"])
    cookie, _ = login(server, "asha", TEMPORARY, window="window-one-1234")
    assert request(server, "POST", "/api/auth/set-password", {"new_password": CHOSEN}, cookie=cookie, window="window-one-1234")[0] == 200
    assert request(server, "GET", "/api/profile", cookie=cookie, window="window-one-1234")[0] == 200


def test_sign_in_never_writes_back_a_password_changed_meanwhile(server, monkeypatch):
    admin = owner(server)
    created = server.auth.create_user(admin, "asha", "Asha", TEMPORARY, ["operator"])
    real = auth_module.PASSWORD_HASHER

    class ChangesPasswordDuringVerify:
        def hash(self, password):
            return real.hash(password)

        def check_needs_rehash(self, _stored):
            return True

        def verify(self, stored, password):
            result = real.verify(stored, password)
            with server.auth._connect() as connection:
                connection.execute(
                    "UPDATE app_users SET password_hash = ?, must_change_password = 0 WHERE user_id = ?",
                    (real.hash(CHOSEN), created["user_id"]),
                )
            return result

    monkeypatch.setattr(auth_module, "PASSWORD_HASHER", ChangesPasswordDuringVerify())
    server.auth.login("asha", TEMPORARY)
    monkeypatch.setattr(auth_module, "PASSWORD_HASHER", real)
    with pytest.raises(auth_module.AuthError):
        server.auth.login("asha", TEMPORARY)
    server.auth.login("asha", CHOSEN)


def test_sign_in_racing_an_emergency_reset_does_not_keep_the_old_password(server, monkeypatch):
    owner(server)
    real = auth_module.PASSWORD_HASHER

    class ResetDuringVerify:
        def hash(self, password):
            return real.hash(password)

        def check_needs_rehash(self, _stored):
            return False

        def verify(self, stored, password):
            result = real.verify(stored, password)
            auth_module.AuthService(server.auth.db_path, server.auth.database_key).emergency_reset_administrator("owner", "custodian chosen password")
            return result

    monkeypatch.setattr(auth_module, "PASSWORD_HASHER", ResetDuringVerify())
    _, token = server.auth.login("owner", OWNER_PASSWORD)
    monkeypatch.setattr(auth_module, "PASSWORD_HASHER", real)
    assert server.auth.authenticate(token) is None
    assert server.auth.session_end_reason(token) == "password_reset"


def test_check_in_while_the_new_password_is_saved_keeps_the_session(server, monkeypatch):
    owner(server)
    server.auth.create_user(server.auth.get_user(server.auth.list_users()[0]["user_id"]), "asha", "Asha", TEMPORARY, ["operator"])
    user, token = server.auth.login("asha", TEMPORARY)
    audit = server.auth._audit
    seen = []

    def commit_then_check_in(connection, *args):
        audit(connection, *args)
        connection.commit()
        seen.append(server.auth.authenticate(token))

    monkeypatch.setattr(server.auth, "_audit", commit_then_check_in)
    server.auth.set_required_password(user, token, CHOSEN)
    assert seen and seen[0] is not None
    assert server.auth.authenticate(token) is not None


def test_stale_check_in_read_after_the_new_password_is_saved_keeps_the_session(server, monkeypatch):
    owner(server)
    server.auth.create_user(server.auth.get_user(server.auth.list_users()[0]["user_id"]), "asha", "Asha", TEMPORARY, ["operator"])
    user, token = server.auth.login("asha", TEMPORARY)
    with server.auth._connect() as connection:
        stale = connection.execute("SELECT * FROM app_users WHERE user_id = ?", (user.user_id,)).fetchone()
    server.auth.set_required_password(user, token, CHOSEN)
    real_connect = server.auth._connect
    reads = []

    class StaleRead:
        def execute(self, *args):
            return self

        def fetchone(self):
            return stale

    @contextmanager
    def stale_first_read():
        if not reads:
            reads.append(True)
            yield StaleRead()
            return
        with real_connect() as connection:
            yield connection

    monkeypatch.setattr(server.auth, "_connect", stale_first_read)
    assert server.auth.authenticate(token) is not None
    assert reads
