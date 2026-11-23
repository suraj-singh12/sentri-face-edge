from __future__ import annotations

from sentriface.auth import AUTH_COOKIE_NAME


def bootstrap_admin_cookie(server) -> str:
    if not hasattr(server, "_test_admin_cookie"):
        _, token = server.auth.signup_initial(
            "test-admin",
            "Test Administrator",
            "test administrator password",
        )
        server._test_admin_cookie = f"{AUTH_COOKIE_NAME}={token}"
    return server._test_admin_cookie

def clear_required_password(server, user_id: str) -> None:
    """Act as if the account already chose its own password after an administrator set one."""
    with server.auth._connect() as connection:
        connection.execute("UPDATE app_users SET must_change_password = 0 WHERE user_id = ?", (user_id,))


class SignInEachTime:
    """Cookie per account, signing in again on every lookup.

    SentriFace allows one sign-in at a time, so a test that acts as several
    accounts signs in as each one right before acting.
    """

    def __init__(self, server, credentials: dict[str, tuple[str, str]], *, cookie: bool = True) -> None:
        self.server, self.credentials, self.cookie = server, credentials, cookie

    def __iter__(self):
        return iter(self.credentials)

    def __getitem__(self, key: str) -> str:
        _, token = self.server.auth.login(*self.credentials[key])
        return f"{AUTH_COOKIE_NAME}={token}" if self.cookie else token
