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