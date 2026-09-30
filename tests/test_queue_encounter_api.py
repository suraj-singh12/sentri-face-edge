from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from sentriface.api_server import create_server
from sentriface.models import DetectedFace, FaceBox, InitFace, QualityReport, QualityStatus
from tests.api_auth_helpers import bootstrap_admin_cookie


class QueueEncounterApiTest(unittest.TestCase):
    def test_draft_endpoints_commit_only_after_relations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            server = create_server(port=0, data_dir=Path(temp) / "data", runtime="dev", debug=False)
            server._test_admin_cookie = bootstrap_admin_cookie(server)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                store = server.engine.store
                session = store.create_init_session("/managed/api-queue")
                media = ["/managed/api-one.jpg", "/managed/api-two.jpg"]
                store.save_init_session_media(session.session_id, media)
                vector = (1.0, *([0.0] * (server.engine.config.embedding_dim - 1)))
                store.save_init_faces([InitFace(
                    init_face_id=f"api-face-{index}", session_id=session.session_id,
                    group_id=f"api-group-{index}", source_image=path,
                    face=DetectedFace(FaceBox(1, 1, 10, 10, 0.9), 0.9), vector=vector,
                    quality=QualityReport(QualityStatus.GOOD, 0.9),
                ) for index, path in enumerate(media)])
                status, snapshot = self._request(server, "GET", f"/api/queue-encounters?session_id={session.session_id}")
                self.assertEqual(status, 200)
                self.assertEqual(len(snapshot["media"]), 2)
                media_id = snapshot["media"][0]["media_id"]
                selection = {"session_id": session.session_id, "media_id": media_id, "excluded": True}
                status, removed = self._request(server, "POST", "/api/queue-media-selection", selection)
                self.assertEqual(status, 200)
                self.assertTrue(next(item for item in removed["media"] if item["media_id"] == media_id)["excluded"])
                status, _ = self._request(server, "POST", "/api/queue-encounters-plan", {"session_id": session.session_id, "media_groups": [[item["media_id"] for item in snapshot["media"]]]})
                self.assertNotEqual(status, 200)
                status, _ = self._request(server, "POST", "/api/queue-media-selection", {**selection, "excluded": False})
                self.assertEqual(status, 200)
                status, planned = self._request(server, "POST", "/api/queue-encounters-plan", {
                    "session_id": session.session_id,
                    "media_groups": [[item["media_id"] for item in snapshot["media"]]],
                })
                self.assertEqual(status, 200)
                review_id = planned["reviews"][0]["review_id"]
                status, _ = self._request(server, "POST", "/api/queue-media-selection", selection)
                self.assertNotEqual(status, 200)
                status, event = self._request(server, "POST", "/api/queue-encounter-event", {
                    "review_id": review_id,
                    "event_details": {"date": "2026-09-28", "time_precision": "unknown", "event_occasion": "Meeting"},
                })
                self.assertEqual(status, 200)
                self.assertEqual(event["review"]["phase"], "IDENTITIES")
                status, groups = self._request(server, "GET", f"/api/queue-groups?session_id={session.session_id}")
                self.assertEqual(status, 200)
                first_group = next(group for group in groups["groups"] if any(
                    face["init_face_id"] == "api-face-0" for face in group["faces"]
                ))
                status, skipped = self._request(server, "POST", "/api/queue-skip", {
                    "session_id": session.session_id, "group_id": first_group["group_id"],
                })
                self.assertEqual(status, 200)
                self.assertEqual(skipped["review"]["identity_resolved"], 0)
                self.assertEqual(store.query_encounters()["events"], [])
                status, rejected_skip = self._request(server, "POST", "/api/queue-encounter-decision", {
                    "review_id": review_id, "face_ids": ["api-face-0"], "decision": "SKIP",
                })
                self.assertNotEqual(status, 200)
                for index in range(2):
                    status, decision = self._request(server, "POST", "/api/queue-encounter-decision", {
                        "review_id": review_id, "face_ids": [f"api-face-{index}"],
                        "decision": "ACCEPT_NEW_PERSON", "new_person_key": f"api-person-{index}",
                        "new_person_name": f"Person {index}",
                    })
                    self.assertEqual(status, 200)
                    self.assertEqual(decision["review"]["identity_resolved"], index + 1)
                self.assertEqual(store.query_encounters()["events"], [])
                status, ready = self._request(server, "POST", "/api/queue-encounter-identities-complete", {
                    "review_id": review_id,
                })
                self.assertEqual(status, 200)
                pair = ready["review"]["relation_candidates"][0]
                status, relation = self._request(server, "POST", "/api/queue-encounter-relation", {
                    "review_id": review_id, "first_ref": pair["first_ref"],
                    "second_ref": pair["second_ref"], "disposition": "EXCLUDE",
                })
                self.assertEqual(status, 200)
                self.assertEqual(relation["review"]["relations"][0]["disposition"], "EXCLUDE")
                completion = {"review_id": review_id, "operation_id": str(uuid.uuid4())}
                status, completed = self._request(server, "POST", "/api/queue-encounter-complete", completion)
                self.assertEqual(status, 200)
                self.assertEqual(completed["result"]["graph_evidence_count"], 0)
                retry_status, retry = self._request(server, "POST", "/api/queue-encounter-complete", completion)
                self.assertEqual(retry_status, 200)
                self.assertEqual(retry["result"], completed["result"])
                self.assertEqual(len(store.query_encounters()["events"]), 1)
                self.assertEqual(len(store.list_observation_media(completed["result"]["observation_id"])), 2)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_draft_duplicate_guard_and_combined_candidates_after_regrouping(self):
        with tempfile.TemporaryDirectory() as temp:
            server = create_server(port=0, data_dir=Path(temp) / "data", runtime="dev", debug=False)
            server._test_admin_cookie = bootstrap_admin_cookie(server)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                store = server.engine.store
                session = store.create_init_session("/managed/draft-api")
                paths = [f"/managed/draft-api-{index}.jpg" for index in range(3)]
                store.save_init_session_media(session.session_id, paths)
                vector = (1.0, *([0.0] * (server.engine.config.embedding_dim - 1)))
                store.save_init_faces([InitFace(init_face_id=f"draft-api-{index}", session_id=session.session_id, group_id=f"group_{index:04d}", source_image=path, face=DetectedFace(FaceBox(1, 1, 10, 10, 0.9), 0.9), vector=vector, quality=QualityReport(QualityStatus.BAD if index == 0 else QualityStatus.GOOD, 0.9)) for index, path in enumerate(paths)])
                _, planned = self._request(server, "POST", "/api/queue-encounters-plan", {"session_id": session.session_id, "media_groups": [[item["media_id"] for item in store.list_init_session_media(session.session_id)]]})
                review_id = planned["reviews"][0]["review_id"]
                self._request(server, "POST", "/api/queue-encounter-event", {"review_id": review_id, "event_details": {"time_precision": "unknown"}})
                first = {"review_id": review_id, "face_ids": ["draft-api-0"], "decision": "ACCEPT_NEW_PERSON", "new_person_key": "tony", "new_person_name": "Tony", "quality_choices": {"draft-api-0": "PROOF_ONLY"}}
                status, _ = self._request(server, "POST", "/api/queue-encounter-decision", first)
                self.assertEqual(status, 200)
                status, duplicate = self._request(server, "POST", "/api/proof-only-duplicate-check", {"review_id": review_id, "session_id": session.session_id, "group_id": "stale-scan-group", "face_ids": ["draft-api-1"]})
                self.assertEqual(status, 200)
                self.assertEqual(duplicate["candidates"][0]["draft_person_key"], "tony")
                attempt = {**first, "face_ids": ["draft-api-1"], "new_person_key": "tony2", "new_person_name": "Tony 2"}
                status, _ = self._request(server, "POST", "/api/queue-encounter-decision", attempt)
                self.assertNotEqual(status, 200)
                self.assertEqual(store.get_encounter_review(review_id)["identity_resolved"], 1)
                status, _ = self._request(server, "POST", "/api/queue-encounter-decision", {**attempt, "new_person_key": "tony", "new_person_name": "Tony"})
                self.assertEqual(status, 200)
                for quality_only in (True, False):
                    status, _ = self._request(server, "POST", "/api/queue-quality-policy", {"session_id": session.session_id, "quality_only": quality_only})
                    self.assertEqual(status, 200)
                    status, groups = self._request(server, "GET", f"/api/queue-groups?session_id={session.session_id}")
                    self.assertEqual(status, 200)
                    self.assertEqual(groups["quality_only"], quality_only)
                    self.assertEqual(groups["groups"][0]["matches"][0]["draft_person_key"], "tony")
                    self.assertTrue(groups["groups"][0]["matches"][0]["draft_created"])
                    status, browse = self._request(server, "GET", f"/api/queue-person-candidates?session_id={session.session_id}&group_id={groups['groups'][0]['group_id']}")
                    self.assertEqual(status, 200)
                    self.assertEqual(browse["candidates"][0]["name"], "Tony")
                self.assertEqual(store.list_embeddings(), [])
                self.assertEqual(store.list_persons(), [])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    @staticmethod
    def _request(server, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            headers = {
                "X-SentriFace-Session": server.session_token,
                "Cookie": server._test_admin_cookie,
            }
            if body is not None:
                headers.update({"Content-Type": "application/json", "Content-Length": str(len(body))})
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
