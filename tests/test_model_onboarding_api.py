from __future__ import annotations

import http.client
import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path

from sentriface.api_server import create_server
from sentriface.auth import AUTH_COOKIE_NAME


PASSWORD = "correct horse battery staple"


class ModelOnboardingApiTest(unittest.TestCase):
    def test_model_upload_streams_locally_and_calculates_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = create_server(
                port=0,
                data_dir=root / "data",
                runtime="onnx",
                debug=False,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                _, token = server.auth.signup_initial("owner", "Owner", PASSWORD)
                body = b"local onnx model bytes"
                status, payload = self._raw_request(
                    server,
                    "POST",
                    "/api/models/upload?kind=detector&filename=det_500m.onnx",
                    body,
                    cookie=f"{AUTH_COOKIE_NAME}={token}",
                )

                self.assertEqual(status, 201)
                self.assertEqual(payload["filename"], "det_500m.onnx")
                self.assertEqual(payload["size"], len(body))
                self.assertEqual(payload["sha256"], hashlib.sha256(body).hexdigest())
                self.assertEqual(len(payload["upload_id"]), 32)
                self.assertNotIn("path", payload)
                staged = (
                    root / "data" / "models" / ".model-authority" / "uploads"
                    / payload["upload_id"] / "content"
                )
                self.assertEqual(staged.read_bytes(), body)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_missing_onnx_models_start_authenticated_setup_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = create_server(
                port=0,
                data_dir=root / "data",
                runtime="onnx",
                debug=False,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                administrator, token = server.auth.signup_initial("owner", "Owner", PASSWORD)
                cookie = f"{AUTH_COOKIE_NAME}={token}"
                status, payload = self._request(server, "GET", "/api/models/status", cookie=cookie)
                self.assertEqual(status, 200)
                self.assertFalse(payload["ready"])
                self.assertTrue(payload["can_configure"])
                self.assertEqual(payload["combinations"]["research"][0]["name"], "InsightFace buffalo_s")
                self.assertTrue(payload["combinations"]["commercial"])
                self.assertNotIn(str(root), json.dumps(payload))

                status, payload = self._request(server, "GET", "/api/profile", cookie=cookie)
                self.assertEqual(status, 428)
                self.assertEqual(payload["code"], "models_required")

                server.auth.create_user(administrator, "reader", "Reader", "reader password long enough", ["viewer"])
                _, reader_token = server.auth.login("reader", "reader password long enough")
                reader_cookie = f"{AUTH_COOKIE_NAME}={reader_token}"
                status, payload = self._request(server, "GET", "/api/models/status", cookie=reader_cookie)
                self.assertEqual(status, 200)
                self.assertFalse(payload["can_configure"])
                self.assertNotIn("models_dir", payload)
                self.assertNotIn("detector_target", payload)
                self.assertNotIn("recognizer_target", payload)
                status, payload = self._request(
                    server,
                    "POST",
                    "/api/models/install",
                    {},
                    cookie=reader_cookie,
                )
                self.assertEqual(status, 403)
                self.assertEqual(payload["code"], "permission_denied")

                status, payload = self._request(server, "POST", "/api/auth/logout", {}, cookie=cookie)
                self.assertEqual(status, 200)
                self.assertTrue(payload["logged_out"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_removed_model_file_returns_active_session_to_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model_dir = root / "data" / "models"
            server = create_server(
                port=0,
                data_dir=root / "data",
                runtime="onnx",
                debug=False,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                _, token = server.auth.signup_initial("owner", "Owner", PASSWORD)
                model_dir.mkdir(parents=True, exist_ok=True)
                for name in ("detector.onnx", "recognizer.onnx", "calibration.json", "model-usage.json"):
                    (model_dir / name).write_bytes(name.encode("utf-8"))
                server.model_ready = True
                server.model_error = ""
                server._capture_model_fingerprints()
                (model_dir / "detector.onnx").unlink()

                status, payload = self._request(
                    server,
                    "GET",
                    "/api/profile",
                    cookie=f"{AUTH_COOKIE_NAME}={token}",
                )
                self.assertEqual(status, 428)
                self.assertEqual(payload["code"], "models_required")
                self.assertIn("detector.onnx", payload["error"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

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
            return response.status, json.loads(raw.decode("utf-8"))
        finally:
            connection.close()

    @staticmethod
    def _raw_request(server, method: str, path: str, body: bytes, *, cookie: str = ""):
        headers = {
            "X-SentriFace-Session": server.session_token,
            "Content-Type": "application/octet-stream",
        }
        if cookie:
            headers["Cookie"] = cookie
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            server.server_port,
            timeout=20,
        )
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8"))
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
