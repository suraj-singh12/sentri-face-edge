from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from sentriface.api_server import create_server
from sentriface.auth import AUTH_COOKIE_NAME, AuthError


PASSWORD = "correct horse battery staple"


class AuthenticationApiTest(unittest.TestCase):
    def test_first_run_signup_cookie_status_and_logout(self) -> None:
        with self._running_server() as server:
            status, payload, _ = self._request(server, "GET", "/api/profile")
            self.assertEqual(status, 428)
            self.assertEqual(payload["code"], "setup_required")

            status, payload, headers = self._request(server, "POST", "/api/auth/signup", {
                "username": "owner", "display_name": "Machine Owner", "password": PASSWORD,
            })
            self.assertEqual(status, 201)
            self.assertTrue(payload["authenticated"])
            cookie_header = headers["set-cookie"]
            self.assertIn("HttpOnly", cookie_header)
            self.assertIn("SameSite=Strict", cookie_header)
            cookie = cookie_header.split(";", 1)[0]

            status, payload, _ = self._request(server, "GET", "/api/auth/status", cookie=cookie)
            self.assertEqual(status, 200)
            self.assertEqual(payload["user"]["roles"], ["administrator"])

            status, payload, headers = self._request(server, "POST", "/api/auth/logout", {}, cookie=cookie)
            self.assertEqual(status, 200)
            self.assertTrue(payload["logged_out"])
            self.assertIn("Max-Age=0", headers["set-cookie"])

    def test_backend_enforces_each_role_boundary(self) -> None:
        with self._running_server() as server:
            admin, _ = server.auth.signup_initial("owner", "Owner", PASSWORD)
            users = {}
            for role in ("viewer", "operator", "custodian", "technician"):
                users[role] = server.auth.create_user(admin, role, role.title(), f"{role} password long enough", [role])

            viewer_cookie = self._login_cookie(server, "viewer", "viewer password long enough")
            status, profile, _ = self._request(server, "GET", "/api/profile", cookie=viewer_cookie)
            self.assertEqual(status, 200)
            self.assertNotIn("db_path", profile)
            self.assertEqual(self._request(server, "GET", "/api/events", cookie=viewer_cookie)[0], 403)
            self.assertEqual(self._request(server, "POST", "/api/person-archive", {"person_id": "missing"}, cookie=viewer_cookie)[0], 403)
            self.assertEqual(self._request(server, "POST", "/api/backups/restore", {"backup_id": "missing"}, cookie=viewer_cookie)[0], 403)

            operator_cookie = self._login_cookie(server, "operator", "operator password long enough")
            self.assertEqual(self._request(server, "POST", "/api/queue-cancel", {"job_id": "role-test"}, cookie=operator_cookie)[0], 200)
            self.assertEqual(self._request(server, "POST", "/api/person-archive", {"person_id": "missing"}, cookie=operator_cookie)[0], 403)
            self.assertEqual(self._request(server, "POST", "/api/backups/restore", {"backup_id": "missing"}, cookie=operator_cookie)[0], 403)

            custodian_cookie = self._login_cookie(server, "custodian", "custodian password long enough")
            self.assertNotEqual(self._request(server, "POST", "/api/person-archive", {"person_id": "missing"}, cookie=custodian_cookie)[0], 403)
            self.assertEqual(self._request(server, "POST", "/api/backups/restore", {"backup_id": "missing"}, cookie=custodian_cookie)[0], 403)

            technician_cookie = self._login_cookie(server, "technician", "technician password long enough")
            self.assertEqual(self._request(server, "GET", "/api/events", cookie=technician_cookie)[0], 200)
            status, created, _ = self._request(server, "POST", "/api/backups", {}, cookie=technician_cookie)
            self.assertEqual(status, 200)
            backup_id = created["backup"]["backup_id"]
            self.assertEqual(self._request(server, "DELETE", f"/api/backups/{backup_id}?confirm={backup_id}", cookie=technician_cookie)[0], 403)
            self.assertEqual(self._request(server, "POST", "/api/backups/restore", {"backup_id": backup_id}, cookie=technician_cookie)[0], 403)

    def test_disaster_recovery_requires_explicit_administrator_acknowledgement(self) -> None:
        with self._running_server() as server:
            admin, _ = server.auth.signup_initial("owner", "Machine Owner", PASSWORD)
            server.auth.create_user(admin, "viewer", "Viewer", "viewer password long enough", ["viewer"])
            admin_cookie = self._login_cookie(server, "owner", PASSWORD)
            viewer_cookie = self._login_cookie(server, "viewer", "viewer password long enough")

            status, readiness, _ = self._request(server, "GET", "/api/recovery/readiness", cookie=viewer_cookie)
            self.assertEqual(status, 200)
            self.assertFalse(readiness["ready"])
            self.assertFalse(readiness["acknowledged"])
            self.assertNotIn("destination", readiness)

            status, destinations, _ = self._request(server, "GET", "/api/recovery/destinations", cookie=admin_cookie)
            self.assertEqual(status, 200)
            self.assertIsInstance(destinations["destinations"], list)
            self.assertEqual(self._request(server, "GET", "/api/recovery/destinations", cookie=viewer_cookie)[0], 403)

            status, _, _ = self._request(
                server,
                "POST",
                "/api/recovery/acknowledge",
                {"acknowledge_risk": True, "acknowledgement_version": readiness["acknowledgement_version"]},
                cookie=viewer_cookie,
            )
            self.assertEqual(status, 403)

            status, payload, _ = self._request(
                server,
                "POST",
                "/api/recovery/acknowledge",
                {"acknowledge_risk": False, "acknowledgement_version": readiness["acknowledgement_version"]},
                cookie=admin_cookie,
            )
            self.assertEqual(status, 422)
            self.assertEqual(payload["reason"], "acknowledgement_required")

            status, payload, _ = self._request(
                server,
                "POST",
                "/api/recovery/acknowledge",
                {"acknowledge_risk": True, "acknowledgement_version": readiness["acknowledgement_version"]},
                cookie=admin_cookie,
            )
            self.assertEqual(status, 200)
            self.assertTrue(payload["readiness"]["acknowledged"])
            self.assertFalse(payload["readiness"]["ready"])
            self.assertEqual(payload["readiness"]["acknowledged_by"], "Machine Owner")

            status, profile, _ = self._request(server, "GET", "/api/profile", cookie=viewer_cookie)
            self.assertEqual(status, 200)
            self.assertTrue(profile["recovery_readiness"]["acknowledged"])
            self.assertNotIn("recovery", profile)
    def test_lockout_and_last_administrator_protection(self) -> None:
        with self._running_server() as server:
            admin, _ = server.auth.signup_initial("owner", "Owner", PASSWORD)
            with self.assertRaises(AuthError) as caught:
                server.auth.update_user(admin, admin.user_id, "Owner", ["viewer"], False)
            self.assertEqual(caught.exception.code, "last_administrator")
            for _ in range(4):
                status, payload, _ = self._request(server, "POST", "/api/auth/login", {"username": "owner", "password": "wrong password value"})
                self.assertEqual(status, 401)
                self.assertEqual(payload["code"], "invalid_credentials")
            status, payload, _ = self._request(server, "POST", "/api/auth/login", {"username": "owner", "password": "wrong password value"})
            self.assertEqual(status, 429)
            self.assertEqual(payload["code"], "account_locked")
            self.assertEqual(self._request(server, "POST", "/api/auth/login", {"username": "owner", "password": PASSWORD})[0], 429)
            recovered = server.auth.emergency_reset_administrator("owner", "new administrator password")
            self.assertEqual(recovered.username, "owner")
            self.assertEqual(self._request(server, "POST", "/api/auth/login", {"username": "owner", "password": "new administrator password"})[0], 200)

    @staticmethod
    def _running_server():
        class Context:
            def __enter__(self):
                self.temp = tempfile.TemporaryDirectory()
                self.server = create_server(port=0, data_dir=Path(self.temp.name) / "data", runtime="dev", debug=False)
                self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
                self.thread.start()
                return self.server

            def __exit__(self, exc_type, exc, traceback):
                self.server.shutdown()
                self.server.server_close()
                self.thread.join(timeout=5)
                self.temp.cleanup()
        return Context()

    def _login_cookie(self, server, username: str, password: str) -> str:
        status, _, headers = self._request(server, "POST", "/api/auth/login", {"username": username, "password": password})
        self.assertEqual(status, 200)
        return headers["set-cookie"].split(";", 1)[0]

    @staticmethod
    def _request(server, method: str, path: str, payload: dict | None = None, *, cookie: str = ""):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"X-SentriFace-Session": server.session_token}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if cookie:
            headers["Cookie"] = cookie
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=20)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8")), {key.casefold(): value for key, value in response.getheaders()}
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
