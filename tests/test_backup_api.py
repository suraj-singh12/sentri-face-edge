from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from sentriface.api_server import create_server


class PortableBackupApiTest(unittest.TestCase):
    def test_create_download_import_and_restore_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            server = create_server(port=0, data_dir=data_dir, runtime="dev", debug=False)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                source = data_dir / "uploads" / "original.jpg"
                crop = data_dir / "faces" / "crop.jpg"
                source.parent.mkdir(parents=True, exist_ok=True)
                crop.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(b"original")
                crop.write_bytes(b"crop")
                person = server.engine.store.create_person("Portable Person")
                server.engine.store.add_embedding(
                    person.person_id,
                    [0.0] * server.engine.config.embedding_dim,
                    quality_score=1.0,
                    source_image=str(source),
                    crop_path=str(crop),
                )

                status, created = self._json_request(server, "POST", "/api/backups", {})
                self.assertEqual(status, 200)
                backup = created["backup"]
                self.assertTrue(backup["portable"])
                self.assertTrue(backup["complete"])
                self.assertEqual(backup["file_count"], 2)

                status, headers, archive_bytes = self._raw_request(
                    server,
                    "GET",
                    f"/api/backups/{backup['backup_id']}/download",
                )
                self.assertEqual(status, 200)
                self.assertIn(".sfbackup", headers["content-disposition"])
                with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
                    self.assertEqual(
                        set(archive.namelist()),
                        {
                            "backup.json",
                            "database/sentriface.db",
                            *[
                                item["archive_path"]
                                for item in json.loads(
                                    archive.read("backup.json").decode("utf-8")
                                )["assets"]
                            ],
                        },
                    )

                status, imported = self._upload_backup(
                    server,
                    "round-trip.sfbackup",
                    archive_bytes,
                )
                self.assertEqual(status, 200)
                imported_backup = imported["backup"]
                self.assertTrue(imported_backup["complete"])
                self.assertNotEqual(imported_backup["backup_id"], backup["backup_id"])

                server.engine.store.rename_person(person.person_id, "Changed")
                status, restored = self._json_request(
                    server,
                    "POST",
                    "/api/backups/restore",
                    {
                        "backup_id": imported_backup["backup_id"],
                        "operation_id": str(uuid.uuid4()),
                    },
                )
                self.assertEqual(status, 200)
                self.assertTrue(restored["restore"]["restored"])
                self.assertEqual(
                    server.engine.get_person(person.person_id).name,
                    "Portable Person",
                )
                restored_embedding = server.engine.list_person_embeddings(person.person_id)[0]
                self.assertTrue(Path(restored_embedding.source_image).is_file())
                self.assertTrue(Path(restored_embedding.crop_path).is_file())
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
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, payload = self._upload_backup(
                    server,
                    "broken.sfbackup",
                    b"not a zip archive",
                )
                self.assertEqual(status, 400)
                self.assertIn("invalid", payload["error"].lower())

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
            connection.request(method, path, body=body, headers=headers or {})
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
