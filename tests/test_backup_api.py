from __future__ import annotations

import http.client
import base64
import json
import tempfile
import threading
import unittest
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from sentriface.api_server import create_server
from tests.api_auth_helpers import bootstrap_admin_cookie
from sentriface.backup_crypto import MAGIC


class PortableBackupApiTest(unittest.TestCase):
    def test_restore_is_admin_only_session_attributed_and_model_independent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            server = create_server(port=0, data_dir=Path(temp) / "data", runtime="dev", debug=False)
            server._test_admin_cookie = bootstrap_admin_cookie(server)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, created = self._json_request(server, "POST", "/api/backups", {})
                self.assertEqual(status, 200)
                backup_id = created["backup"]["backup_id"]
                operation_id = str(uuid.uuid4())
                status, refused = self._json_request(server, "POST", "/api/backups/restore", {
                    "backup_id": backup_id,
                    "operation_id": operation_id,
                    "actor": {"display_name": "spoofed"},
                })
                self.assertEqual(status, 422)
                self.assertEqual(refused["reason"], "unsupported_restore_fields")

                server.model_ready = False
                status, payload = self._json_request(server, "POST", "/api/backups/restore", {
                    "backup_id": backup_id,
                    "operation_id": operation_id,
                    "reason": "administrator confirmed test restore",
                })
                self.assertEqual(status, 200)
                self.assertEqual(payload["restore"]["outcome"], "COMMITTED")
                operation = server.engine.store.get_operation(operation_id)
                self.assertEqual(operation["actor"]["display_name"], "Test Administrator")
                self.assertNotEqual(operation["actor"]["display_name"], "spoofed")

                retry_status, retry = self._json_request(server, "POST", "/api/backups/restore", {
                    "backup_id": backup_id,
                    "operation_id": operation_id,
                })
                self.assertEqual(retry_status, 200)
                self.assertEqual(retry["restore"], payload["restore"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_encrypted_download_import_and_wrong_password_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            server = create_server(port=0, data_dir=Path(temp) / "data", runtime="dev", debug=False)
            server._test_admin_cookie = bootstrap_admin_cookie(server)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, created = self._json_request(server, "POST", "/api/backups", {})
                self.assertEqual(status, 200)
                backup_id = created["backup"]["backup_id"]
                status, headers, encrypted = self._raw_request(
                    server,
                    "POST",
                    f"/api/backups/{backup_id}/encrypted-download",
                    json.dumps({"passphrase": "correct horse battery staple"}).encode("utf-8"),
                    {"Content-Type": "application/json"},
                )
                self.assertEqual(status, 200)
                self.assertIn(".sfbackup.enc", headers["content-disposition"])
                self.assertTrue(encrypted.startswith(MAGIC))
                self.assertFalse(encrypted.startswith(b"PK"))

                status, _, response = self._raw_request(
                    server,
                    "POST",
                    "/api/backups/import?filename=protected.sfbackup.enc",
                    encrypted,
                    self._passphrase_header("entirely wrong password"),
                )
                self.assertEqual(status, 400)
                self.assertIn("passphrase", json.loads(response)["error"].lower())

                status, _, response = self._raw_request(
                    server,
                    "POST",
                    "/api/backups/import?filename=protected.sfbackup.enc",
                    encrypted,
                    self._passphrase_header("correct horse battery staple"),
                )
                self.assertEqual(status, 200)
                imported = json.loads(response)["backup"]
                self.assertNotEqual(imported["backup_id"], backup_id)
                self.assertTrue(imported["verified"])
                self.assertEqual(list(server.config.backup_dir.glob(".decrypt-*.sfbackup")), [])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
    def test_plaintext_download_and_import_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            server = create_server(port=0, data_dir=Path(temp) / "data", runtime="dev", debug=False)
            server._test_admin_cookie = bootstrap_admin_cookie(server)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, created = self._json_request(server, "POST", "/api/backups", {})
                self.assertEqual(status, 200)
                backup_id = created["backup"]["backup_id"]
                status, _, _ = self._raw_request(
                    server, "GET", f"/api/backups/{backup_id}/download"
                )
                self.assertEqual(status, 404)
                status, payload = self._upload_backup(
                    server, "legacy.sfbackup", b"plaintext archive"
                )
                self.assertEqual(status, 422)
                self.assertEqual(payload["reason"], "unsupported_backup_type")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
    def test_bad_import_is_rejected_and_server_remains_usable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            server = create_server(
                port=0,
                data_dir=Path(temp) / "data",
                runtime="dev",
                debug=False,
            )
            server._test_admin_cookie = bootstrap_admin_cookie(server)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, payload = self._upload_backup(
                    server,
                    "broken.sfbackup",
                    b"not a zip archive",
                )
                self.assertEqual(status, 422)
                self.assertEqual(payload["reason"], "unsupported_backup_type")

                status, profile = self._json_request(server, "GET", "/api/profile")
                self.assertEqual(status, 200)
                self.assertEqual(profile["runtime"], "dev")

                status, payload = self._upload_backup(
                    server,
                    "wrong.zip",
                    b"not a backup",
                )
                self.assertEqual(status, 422)
                self.assertEqual(payload["code"], "invalid_input")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def _json_request(
        self,
        server,
        method: str,
        path: str,
        payload: dict | None = None,
    ) -> tuple[int, dict]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        status, _, response = self._raw_request(server, method, path, body, headers)
        return status, json.loads(response.decode("utf-8"))

    def _upload_backup(
        self,
        server,
        filename: str,
        payload: bytes,
    ) -> tuple[int, dict]:
        from urllib.parse import quote

        status, _, response = self._raw_request(
            server,
            "POST",
            f"/api/backups/import?filename={quote(filename)}",
            payload,
            {"Content-Type": "application/octet-stream"},
        )
        return status, json.loads(response.decode("utf-8"))

    def _passphrase_header(self, passphrase: str) -> dict[str, str]:
        encoded = base64.urlsafe_b64encode(passphrase.encode("utf-8")).decode("ascii").rstrip("=")
        return {
            "Content-Type": "application/octet-stream",
            "X-SentriFace-Backup-Passphrase": encoded,
        }
    def _raw_request(
        self,
        server,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            server.server_port,
            timeout=20,
        )
        try:
            authorized = {**(headers or {}), "X-SentriFace-Session": server.session_token, "Cookie": server._test_admin_cookie}
            connection.request(method, path, body=body, headers=authorized)
            response = connection.getresponse()
            return (
                response.status,
                {key.lower(): value for key, value in response.getheaders()},
                response.read(),
            )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
