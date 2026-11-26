"""Real SentriFace application authority + HTTP client used by the experiments.

Every fixture write goes through the loopback HTTP API of the real
``create_server`` application with the genuine ONNX runtime (buffalo_s), the
same request sequence the React Queue/People/Events UI sends. Admission of
the models uses the real ``sentriface.model_setup`` CLI.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from . import env  # noqa: F401  (installs keyring + determinism seams first)
from .env import DET, ROOT

from sentriface.api_server import create_server  # noqa: E402
from sentriface.auth import AUTH_COOKIE_NAME  # noqa: E402

ASSETS = Path("/projects/sandbox/assets/buffalo_s")
KIT = Path(os.environ.get("ISSUE89_KIT", "/projects/sandbox/kit"))
ADMIN = ("custodian", "Fixture Custodian", "fixture custodian password 89")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def admit_models(data_dir: Path) -> None:
    command = [sys.executable, "-m", "sentriface.model_setup", "--models-dir", str(data_dir / "models"),
               "--detector-source", str(ASSETS / "det_500m.onnx"), "--detector-sha256", sha256(ASSETS / "det_500m.onnx"),
               "--recognizer-source", str(ASSETS / "w600k_mbf.onnx"), "--recognizer-sha256", sha256(ASSETS / "w600k_mbf.onnx"),
               "--usage-basis", "noncommercial-research", "--authorized-by", "Issue 89 experiment (disposable authority)",
               "--accept-model-responsibility"]
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError(f"model admission failed: {result.stdout}\n{result.stderr}")


class ApiError(RuntimeError):
    def __init__(self, status, payload, method, path):
        super().__init__(f"{method} {path} -> {status}: {payload}")
        self.status, self.payload = status, payload


class App:
    """One running SentriFace application over a disposable authority."""

    def __init__(self, data_dir: Path, *, fresh: bool = False, index: str | None = None):
        self.data_dir = Path(data_dir)
        if fresh:
            if self.data_dir.exists():
                shutil.rmtree(self.data_dir)
            self.data_dir.mkdir(parents=True)
            admit_models(self.data_dir)
        self.index_backend = index
        self.server = None
        self.thread = None
        self.cookie = None
        self.window = str(uuid.UUID(int=89))

    # ------------------------------------------------------------ lifecycle
    def start(self):
        # Startup and sign-in use the real clock/UUIDs: they only write security
        # audit/session rows, which are an allowed (justified) difference.
        self.server = create_server(port=0, data_dir=self.data_dir, runtime="onnx")
        if not self.server.model_ready:
            raise RuntimeError(f"ONNX runtime not ready: {self.server.model_error}")
        if self.index_backend:
            self.use_index(self.index_backend)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self._sign_in()
        return self

    def use_index(self, backend: str):
        from sentriface.components.hnsw_index import HnswFaceIndex
        from sentriface.components.linear_index import LinearFaceIndex
        engine = self.server.engine
        index = HnswFaceIndex(engine.config.embedding_dim) if backend == "hnsw" else LinearFaceIndex()
        engine.index.replace(index)
        engine._rebuild_index()
        self.index_backend = backend

    def _sign_in(self):
        auth = self.server.auth
        if auth.setup_required():
            # One deterministic custodian account so actor JSON (user_id) embedded in
            # notes/journal rows is identical between independently built authorities.
            with DET.step("auth.signup", "2026-01-01T00:00:00+00:00"):
                _, token = auth.signup_initial(*ADMIN, window_id=self.window)
        else:
            _, token = auth.login(ADMIN[0], ADMIN[2], window_id=self.window)
        self.cookie = f"{AUTH_COOKIE_NAME}={token}"

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=10)
            self.server = None

    def restart(self):
        self.stop()
        return self.start()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    @property
    def store(self):
        return self.server.engine.store

    @property
    def engine(self):
        return self.server.engine

    # ------------------------------------------------------------- transport
    def request(self, method, path, payload=None, *, raw=None, content_type=None, cookie=True, expect=200, timeout=600):
        if raw is not None:
            body = raw
        else:
            body = json.dumps(payload).encode() if payload is not None else None
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=timeout)
        headers = {"X-SentriFace-Session": self.server.session_token, "X-SentriFace-Window": self.window, "Host": "127.0.0.1"}
        if cookie:
            headers["Cookie"] = self.cookie if cookie is True else cookie
        if body is not None:
            headers.update({"Content-Type": content_type or "application/json", "Content-Length": str(len(body))})
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read()
            ctype = response.getheader("Content-Type") or ""
            parsed = json.loads(data) if "json" in ctype and data else data
        finally:
            connection.close()
        if expect is not None and response.status != expect:
            raise ApiError(response.status, parsed, method, path)
        return parsed if expect is not None else (response.status, parsed)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, payload=None, **kw):
        return self.request("POST", path, payload or {}, **kw)

    # --------------------------------------------------------------- uploads
    def upload(self, photos: list[str]) -> str:
        """Upload kit photos exactly as the Queue UI does (upload-chunk)."""
        upload_id = str(uuid.uuid4())
        stored = []
        for name in photos:
            path = KIT / f"{name}.jpg"
            result = self.request("POST", f"/api/upload-chunk?upload_id={upload_id}&filename={name}.jpg&relative_path={name}.jpg",
                                  raw=path.read_bytes(), content_type="image/jpeg")
            stored.append(result)
        return stored[0]["stored_path"] if len(photos) == 1 else stored[0]["path"]

    def scan(self, photos: list[str], *, target=None, revision=None, session_id=None, quality_only=True):
        path = self.upload(photos)
        result = self.post("/api/queue-scan", {"path": path, "job_id": str(uuid.uuid4()), "total_files": len(photos),
                                               "uploaded_files": len(photos), "force_bad_quality": True,
                                               "quality_only": quality_only, "target_observation_id": target,
                                               "expected_revision": revision, "session_id": session_id})
        return result
