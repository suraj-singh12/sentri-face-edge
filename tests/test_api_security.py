from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from sentriface.api_server import create_server
from tests.api_auth_helpers import bootstrap_admin_cookie


class LocalApiSecurityTest(unittest.TestCase):
    def test_non_local_browser_origin_is_rejected(self) -> None:
        with self._running_server() as server:
            status, payload, headers = self._request(
                server,
                "POST",
                "/api/queue-cancel",
                {"job_id": "foreign-origin"},
                origin="https://attacker.example",
            )

            self.assertEqual(status, 403)
            self.assertIn("only from its own origin", payload["error"])
            self.assertEqual(headers["x-frame-options"], "DENY")
            self.assertIn("default-src 'self'", headers["content-security-policy"])
            self.assertEqual(headers["referrer-policy"], "no-referrer")

    def test_loopback_browser_origin_is_accepted(self) -> None:
        with self._running_server() as server:
            status, payload, _ = self._request(
                server,
                "POST",
                "/api/queue-cancel",
                {"job_id": "local-origin"},
                origin=f"http://127.0.0.1:{server.server_port}",
            )

            self.assertEqual(status, 200)
            self.assertTrue(payload["cancel_requested"])

    def test_reference_admission_cannot_be_forged_and_review_reads_remain_available(self) -> None:
        with self._running_server() as server:
            origin = f"http://127.0.0.1:{server.server_port}"
            status, payload, _ = self._request(server, "POST", "/api/photo-review", {
                "review_id": "forged-reference", "media_id": "source",
                "source": "reference-only", "faces": [],
            }, origin=origin)
            self.assertEqual(status, 400)
            self.assertIn("single-face admission", payload["error"])
            self.assertIsNone(server.engine.store.get_photo_review("forged-reference"))
            from sentriface.models import DetectedFace, FaceBox, MatchDecision, PendingAddition, QualityReport, QualityStatus
            server.engine.store.save_pending_addition(PendingAddition(
                pending_id="prepared-face", source_image="/managed/portrait.jpg",
                face=DetectedFace(FaceBox(1, 1, 10, 10, .99), .9),
                vector=(1., *([0.] * (server.engine.config.embedding_dim - 1))),
                matches=[], decision=MatchDecision.UNKNOWN,
                quality=QualityReport(QualityStatus.GOOD, .9)))
            server.engine.store.create_photo_review("readable", "source", [{
                "face_id": "face-1", "staged_face_type": "PENDING_ADDITION",
                "staged_face_id": "prepared-face"}], media_path="/managed/portrait.jpg", source="reference-only")
            status, payload, _ = self._request(server, "GET", "/api/photo-review?review_id=readable", {}, origin=origin)
            self.assertEqual(status, 200)
            self.assertEqual(payload["review_id"], "readable")

    @staticmethod
    def _running_server():
        class ServerContext:
            def __enter__(self):
                self.temporary = tempfile.TemporaryDirectory()
                self.server = create_server(
                    port=0,
                    data_dir=Path(self.temporary.name) / "data",
                    runtime="dev",
                    debug=False,
                )
                self.server._test_admin_cookie = bootstrap_admin_cookie(self.server)
                self.thread = threading.Thread(
                    target=self.server.serve_forever,
                    daemon=True,
                )
                self.thread.start()
                return self.server

            def __exit__(self, exc_type, exc, traceback):
                self.server.shutdown()
                self.server.server_close()
                self.thread.join(timeout=5)
                self.temporary.cleanup()

        return ServerContext()

    @staticmethod
    def _request(
        server,
        method: str,
        path: str,
        payload: dict,
        *,
        origin: str,
    ) -> tuple[int, dict, dict[str, str]]:
        body = json.dumps(payload).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            connection.request(
                method,
                path,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                    "Origin": origin,
                    "X-SentriFace-Session": server.session_token,
                    "Cookie": server._test_admin_cookie,
                },
            )
            response = connection.getresponse()
            response_body = json.loads(response.read().decode("utf-8"))
            headers = {key.casefold(): value for key, value in response.getheaders()}
            return response.status, response_body, headers
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
