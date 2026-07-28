from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from sentriface.api_server import create_server


class LocalApiSecurityTest(unittest.TestCase):
    def test_non_local_browser_origin_is_rejected(self) -> None:
        with self._running_server() as server:
            status, payload, headers = self._request(
                server.server_port,
                "POST",
                "/api/queue-cancel",
                {"job_id": "foreign-origin"},
                origin="https://attacker.example",
            )

            self.assertEqual(status, 403)
            self.assertIn("non-local browser origins", payload["error"])
            self.assertEqual(headers["x-frame-options"], "DENY")
            self.assertIn("default-src 'self'", headers["content-security-policy"])
            self.assertEqual(headers["referrer-policy"], "no-referrer")

    def test_loopback_browser_origin_is_accepted(self) -> None:
        with self._running_server() as server:
            status, payload, _ = self._request(
                server.server_port,
                "POST",
                "/api/queue-cancel",
                {"job_id": "local-origin"},
                origin="http://127.0.0.1:5173",
            )

            self.assertEqual(status, 200)
            self.assertTrue(payload["cancel_requested"])

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
        port: int,
        method: str,
        path: str,
        payload: dict,
        *,
        origin: str,
    ) -> tuple[int, dict, dict[str, str]]:
        body = json.dumps(payload).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request(
                method,
                path,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                    "Origin": origin,
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
