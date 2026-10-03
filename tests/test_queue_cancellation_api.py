from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from sentriface.api_server import create_server, SentriFaceApiHandler
from tests.api_auth_helpers import bootstrap_admin_cookie


class QueueCancellationApiTest(unittest.TestCase):
    def test_cancel_endpoint_stops_scan_and_removes_partial_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            upload_dir = data_dir / "uploads" / "batch"
            upload_dir.mkdir(parents=True)
            cv2.imwrite(str(upload_dir / "face.jpg"), np.full((160, 160, 3), 120, dtype=np.uint8))

            server = create_server(port=0, data_dir=data_dir, runtime="dev", debug=False)
            test_case = self
            class CleanupOrderedProgress(dict):
                def __setitem__(self, job_id, progress):
                    if progress.get("status") == "cancelled":
                        test_case.assertTrue(server.queue_progress_lock.locked())
                        test_case.assertNotIn(job_id, server.queue_cancellations)
                        test_case.assertNotIn(job_id, server.active_queue_jobs)
                        test_case.assertEqual(server.engine.list_init_sessions(), [])
                        test_case.assertFalse(upload_dir.exists())
                    super().__setitem__(job_id, progress)
            server.queue_progress = CleanupOrderedProgress(server.queue_progress)
            server._test_admin_cookie = bootstrap_admin_cookie(server)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, cancelled = self._post(server, "/api/queue-cancel", {"job_id": "job-1"})
                self.assertEqual(status, 200)
                self.assertTrue(cancelled["cancel_requested"])

                status, result = self._post(
                    server,
                    "/api/queue-scan",
                    {
                        "job_id": "job-1",
                        "path": str(upload_dir),
                        "total_files": 1,
                        "uploaded_files": 1,
                    },
                )
                self.assertEqual(status, 200)
                self.assertTrue(result["cancelled"])
                self.assertEqual(result["groups"], [])
                self.assertEqual(server.queue_progress_snapshot("job-1")["status"], "cancelled")
                self.assertEqual(server.engine.list_init_sessions(), [])
                self.assertFalse(upload_dir.exists())
                self.assertNotIn("job-1", server.queue_cancellations)
                self.assertNotIn("job-1", server.active_queue_jobs)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_terminal_response_cleanup_stress(self) -> None:
        original_json = SentriFaceApiHandler._json
        def checked_publication(handler, payload, *args, **kwargs):
            if isinstance(payload, dict) and payload.get("cancelled"):
                job_id = payload["job_id"]
                self.assertNotIn(job_id, handler.server.queue_cancellations)
                self.assertNotIn(job_id, handler.server.active_queue_jobs)
                self.assertEqual(handler.server.engine.list_init_sessions(), [])
            return original_json(handler, payload, *args, **kwargs)
        with patch.object(SentriFaceApiHandler, "_json", checked_publication):
            for iteration in range(20):
                with self.subTest(iteration=iteration):
                    self.test_cancel_endpoint_stops_scan_and_removes_partial_session()

    @staticmethod
    def _post(server, path: str, payload: dict) -> tuple[int, dict]:
        body = json.dumps(payload).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            connection.request(
                "POST",
                path,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                    "X-SentriFace-Session": server.session_token,
                    "Cookie": server._test_admin_cookie,
                },
            )
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
