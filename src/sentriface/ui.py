from __future__ import annotations

import argparse
import base64
import binascii
import json
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from sentriface.cli import build_dev_engine, build_onnx_engine
from sentriface.config import RuntimeConfig, config_for_hardware
from sentriface.engine import IMAGE_EXTENSIONS, FaceEngine
from sentriface.hardware import assess_hardware
from sentriface.models import (
    EmbeddingRecord,
    InitGroup,
    PendingAddition,
    Person,
    PersonMatch,
    PersonSummary,
    QualityReport,
    RecognitionResult,
    RejectedFace,
)

STATIC_DIR = Path(__file__).with_name("ui_static")
UPLOAD_RESIZE_LIMIT_BYTES = 1_000_000
UPLOAD_MAX_EDGE = 1600
DUPLICATE_MATCH_SCORE = 0.9999


class SentriFaceUiServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        engine: FaceEngine,
        config: RuntimeConfig,
        runtime: str,
        debug: bool = True,
    ) -> None:
        super().__init__(server_address, SentriFaceUiHandler)
        self.engine = engine
        self.config = config
        self.runtime = runtime
        self.debug = debug
        self.events: list[dict[str, Any]] = []

    def log_event(self, event: str, **details: Any) -> None:
        item = {"event": event, **details}
        self.events.append(item)
        self.events = self.events[-200:]
        if self.debug:
            print(f"[sentriface-ui] {event} {json.dumps(details, separators=(',', ':'), default=str)}")


class SentriFaceUiHandler(SimpleHTTPRequestHandler):
    server: SentriFaceUiServer

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        if parsed.path == "/":
            return str(STATIC_DIR / "index.html")
        return str(STATIC_DIR / parsed.path.lstrip("/"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/profile":
                self._json(self._profile())
                return
            if parsed.path == "/api/persons":
                self._json({"persons": [_person_summary(item, self.server.engine) for item in self.server.engine.list_persons()]})
                return
            if parsed.path == "/api/person":
                person_id = _query_value(parsed.query, "person_id")
                person = self.server.engine.get_person(person_id)
                if person is None:
                    raise KeyError(f"Unknown person: {person_id}")
                embeddings = self.server.engine.list_person_embeddings(person_id)
                self._json(
                    {
                        "person": _person(person),
                        "embeddings": [_embedding(record) for record in embeddings],
                    }
                )
                return
            if parsed.path == "/api/pending":
                self._json({"pending": [_pending(self.server.engine, item) for item in self.server.engine.list_pending_additions()]})
                return
            if parsed.path == "/api/events":
                self._json({"events": self.server.events[-80:]})
                return
            if parsed.path == "/api/init-groups":
                session_id = _query_value(parsed.query, "session_id")
                groups = self.server.engine.list_init_groups(session_id)
                self._json({"groups": [_init_group(group) for group in groups]})
                return
            if parsed.path == "/media":
                self._media(_query_value(parsed.query, "path"))
                return
            super().do_GET()
        except Exception as exc:  # noqa: BLE001 - local UI should surface errors clearly.
            self._error(exc)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/upload":
                saved_path = _save_upload(
                    self.server.config.data_dir,
                    _required(payload, "filename"),
                    _required(payload, "data"),
                )
                self.server.log_event(
                    "upload",
                    filename=payload.get("filename"),
                    path=str(saved_path),
                    stored_size=saved_path.stat().st_size,
                )
                self._json({"path": str(saved_path), "stored_size": saved_path.stat().st_size})
                return
            if parsed.path == "/api/upload-batch":
                saved_dir, count = _save_upload_batch(
                    self.server.config.data_dir,
                    payload.get("files", []),
                )
                self.server.log_event("upload-batch", path=str(saved_dir), files=count)
                self._json({"path": str(saved_dir), "files": count})
                return
            if parsed.path == "/api/recognize":
                image_path = Path(_required(payload, "path"))
                self.server.engine.reset_metrics()
                results = self.server.engine.recognize(image_path)
                self.server.log_event("recognize", path=str(image_path), faces=len(results))
                self._json(
                    {
                        "faces": [_recognition(self.server.engine, result, index) for index, result in enumerate(results, 1)],
                        "metrics": self.server.engine.metrics_snapshot(),
                    }
                )
                return
            if parsed.path == "/api/recognize-batch":
                source = Path(_required(payload, "path"))
                images = _image_paths(source)
                if not images:
                    raise KeyError(f"No supported images found: {source}")
                self.server.engine.reset_metrics()
                batch = [
                    {
                        "image": str(image_path),
                        "faces": [
                            _recognition(self.server.engine, result, index)
                            for index, result in enumerate(self.server.engine.recognize(image_path), 1)
                        ],
                    }
                    for image_path in images
                ]
                self.server.log_event("recognize-batch", path=str(source), images=len(images))
                self._json({"batch": batch, "metrics": self.server.engine.metrics_snapshot()})
                return
            if parsed.path == "/api/recognition-accept-existing":
                image_path = Path(_required(payload, "path"))
                person_id = _required(payload, "person_id")
                if self.server.engine.get_person(person_id) is None:
                    raise KeyError(f"Unknown person: {person_id}")
                self.server.engine.reset_metrics()
                additions = self.server.engine.prepare_additions(image_path)
                if not additions:
                    raise KeyError("No acceptable faces found")
                if _has_duplicate_embedding(additions[0].vector, self.server.engine.list_person_embeddings(person_id)):
                    person = self.server.engine.get_person(person_id)
                    self.server.log_event("recognition-duplicate", path=str(image_path), person_id=person_id)
                    self._json(
                        {
                            "duplicate": True,
                            "person_id": person_id,
                            "name": person.name if person else person_id,
                            "metrics": self.server.engine.metrics_snapshot(),
                        }
                    )
                    return
                embedding_id = self.server.engine.confirm_existing_person(additions[0], person_id)
                self.server.log_event("recognition-accept-existing", path=str(image_path), person_id=person_id)
                self._json({"embedding_id": embedding_id, "metrics": self.server.engine.metrics_snapshot()})
                return
            if parsed.path == "/api/recognition-new":
                image_path = Path(_required(payload, "path"))
                name = _required(payload, "name")
                self.server.engine.reset_metrics()
                additions = self.server.engine.prepare_additions(image_path)
                if not additions:
                    raise KeyError("No acceptable faces found")
                person_id = self.server.engine.confirm_new_person(additions[0], name)
                self.server.log_event("recognition-new", path=str(image_path), person_id=person_id)
                self._json({"person_id": person_id, "metrics": self.server.engine.metrics_snapshot()})
                return
            if parsed.path == "/api/enroll":
                image_path = Path(_required(payload, "path"))
                name = _required(payload, "name")
                self.server.engine.reset_metrics()
                additions = self.server.engine.prepare_additions(image_path, bool(payload.get("force_bad_quality", False)))
                if not additions:
                    raise KeyError("No acceptable faces found")
                person_id = self.server.engine.confirm_new_person(additions[0], name)
                self.server.log_event("enroll", path=str(image_path), person_id=person_id)
                self._json({"person_id": person_id, "metrics": self.server.engine.metrics_snapshot()})
                return
            if parsed.path == "/api/queue-add":
                image_path = Path(_required(payload, "path"))
                self.server.engine.reset_metrics()
                prepared = self.server.engine.queue_additions(image_path, bool(payload.get("force_bad_quality", False)))
                self.server.log_event(
                    "queue-add",
                    path=str(image_path),
                    accepted=len(prepared.accepted),
                    rejected=len(prepared.rejected),
                )
                self._json(
                    {
                        "pending": [_pending(self.server.engine, item) for item in prepared.accepted],
                        "rejected": [_rejected(item, index) for index, item in enumerate(prepared.rejected, 1)],
                        "metrics": self.server.engine.metrics_snapshot(),
                    }
                )
                return
            if parsed.path == "/api/confirm-new":
                pending_id = _required(payload, "pending_id")
                name = _required(payload, "name")
                person_id = self.server.engine.confirm_pending_as_new_person(pending_id, name)
                self.server.log_event("confirm-new", pending_id=pending_id, person_id=person_id)
                self._json({"person_id": person_id})
                return
            if parsed.path == "/api/confirm-existing":
                pending_id = _required(payload, "pending_id")
                person_id = _required(payload, "person_id")
                embedding_id = self.server.engine.confirm_pending_as_existing_person(pending_id, person_id)
                self.server.log_event("confirm-existing", pending_id=pending_id, person_id=person_id)
                self._json({"embedding_id": embedding_id})
                return
            if parsed.path == "/api/reject-pending":
                pending_id = _required(payload, "pending_id")
                self.server.engine.reject_pending_addition(pending_id)
                self.server.log_event("reject-pending", pending_id=pending_id)
                self._json({"rejected": 1})
                return
            if parsed.path == "/api/init-scan":
                source = Path(_required(payload, "path"))
                self.server.engine.reset_metrics()
                session = self.server.engine.create_init_session(source, bool(payload.get("force_bad_quality", False)))
                groups = self.server.engine.list_init_groups(session.session_id)
                self.server.log_event("init-scan", path=str(source), session_id=session.session_id, groups=len(groups))
                self._json(
                    {
                        "session_id": session.session_id,
                        "groups": [_init_group(group) for group in groups],
                        "metrics": self.server.engine.metrics_snapshot(),
                    }
                )
                return
            if parsed.path == "/api/init-confirm":
                person_id = self.server.engine.confirm_init_group(
                    _required(payload, "session_id"),
                    _required(payload, "group_id"),
                    _required(payload, "name"),
                )
                self.server.log_event("init-confirm", person_id=person_id)
                self._json({"person_id": person_id})
                return
            if parsed.path == "/api/init-confirm-existing":
                count = self.server.engine.confirm_init_group_existing(
                    _required(payload, "session_id"),
                    _required(payload, "group_id"),
                    _required(payload, "person_id"),
                )
                self.server.log_event("init-confirm-existing", embeddings=count)
                self._json({"embeddings": count})
                return
            if parsed.path == "/api/init-reject":
                self.server.engine.reject_init_group(_required(payload, "session_id"), _required(payload, "group_id"))
                self.server.log_event("init-reject", group_id=payload.get("group_id"))
                self._json({"rejected": 1})
                return
            if parsed.path == "/api/init-reset":
                self.server.engine.reset_init_group(_required(payload, "session_id"), _required(payload, "group_id"))
                self.server.log_event("init-reset", group_id=payload.get("group_id"))
                self._json({"status": "pending"})
                return
            if parsed.path == "/api/backup-db":
                target = Path(_required(payload, "path"))
                self.server.engine.backup_database(target)
                self.server.log_event("backup-db", path=str(target))
                self._json({"backup": str(target)})
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
        except Exception as exc:  # noqa: BLE001 - local UI should surface errors clearly.
            self._error(exc)

    def log_message(self, format: str, *args: Any) -> None:
        if self.server.debug:
            print(f"[sentriface-ui:http] {self.address_string()} {format % args}")

    def _profile(self) -> dict[str, Any]:
        config = self.server.config
        return {
            "runtime": self.server.runtime,
            "hardware_tier": config.hardware_tier,
            "data_dir": str(config.data_dir),
            "db_path": str(config.db_path),
            "max_workers": config.max_workers,
            "onnx_intra_threads": config.onnx_intra_threads,
            "max_image_edge": config.max_image_edge,
            "high_confidence": config.high_confidence,
            "medium_confidence": config.medium_confidence,
            "min_quality_score": config.min_quality_score,
        }

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, exc: Exception) -> None:
        self.server.log_event("error", message=str(exc).strip("'"))
        self._json({"error": str(exc).strip("'")}, status=400)

    def _media(self, raw_path: str) -> None:
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            raise KeyError(f"Media file not found: {path}")
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise KeyError(f"Unsupported media file: {path}")
        data = path.read_bytes()
        content_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
        }.get(path.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    data_dir: Path = Path("data"),
    runtime: str = "dev",
    debug: bool = True,
) -> SentriFaceUiServer:
    profile = assess_hardware()
    config = config_for_hardware(profile, data_dir=data_dir)
    engine = build_dev_engine(data_dir, config) if runtime == "dev" else build_onnx_engine(config)
    engine.initialize()
    server = SentriFaceUiServer((host, port), engine=engine, config=config, runtime=runtime, debug=debug)
    server.log_event("startup", runtime=runtime, data_dir=str(data_dir), address=f"http://{host}:{server.server_port}")
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="SentriFace Edge local UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--runtime", choices=("dev", "onnx"), default="dev")
    parser.add_argument("--quiet-debug", action="store_true", help="Disable verbose UI debug logs")
    args = parser.parse_args()

    server = create_server(
        host=args.host,
        port=args.port,
        data_dir=args.data_dir,
        runtime=args.runtime,
        debug=not args.quiet_debug,
    )
    print(f"SentriFace UI running at http://{args.host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("SentriFace UI stopped")
    finally:
        server.server_close()
    return 0


def _required(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None or str(value).strip() == "":
        raise KeyError(f"Missing required field: {key}")
    return str(value)


def _query_value(query: str, key: str) -> str:
    values = parse_qs(query).get(key)
    if not values:
        raise KeyError(f"Missing required query: {key}")
    return values[0]


def _image_paths(source: Path) -> list[Path]:
    if source.is_file():
        return [source] if source.suffix.lower() in IMAGE_EXTENSIONS else []
    if not source.exists():
        raise KeyError(f"Source path does not exist: {source}")
    return sorted(path for path in source.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def _save_upload(data_dir: Path, filename: str, data_url: str, upload_subdir: Path = Path("uploads")) -> Path:
    suffix = Path(filename).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise KeyError(f"Unsupported upload type: {suffix or filename}")
    if "," in data_url:
        _, encoded = data_url.split(",", 1)
    else:
        encoded = data_url
    try:
        data = base64.b64decode(encoded, validate=True)
    except binascii.Error as exc:
        raise KeyError("Invalid upload data") from exc
    if not data:
        raise KeyError("Upload is empty")
    if len(data) > UPLOAD_RESIZE_LIMIT_BYTES:
        data, suffix = _reduce_upload_image(data)
    upload_dir = data_dir / upload_subdir
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"{uuid.uuid4().hex}{suffix}"
    target.write_bytes(data)
    return target


def _save_upload_batch(data_dir: Path, files: list[dict[str, Any]]) -> tuple[Path, int]:
    if not files:
        raise KeyError("No files selected")
    batch_subdir = Path("uploads") / "batches" / uuid.uuid4().hex
    batch_dir = data_dir / batch_subdir
    count = 0
    for item in files:
        filename = _required(item, "filename")
        relative_path = str(item.get("relative_path") or filename)
        data_url = _required(item, "data")
        suffix = Path(filename).suffix.lower()
        if suffix not in IMAGE_EXTENSIONS:
            continue
        safe_path = _safe_relative_upload_path(relative_path)
        saved = _save_upload(data_dir, safe_path.name, data_url, batch_subdir / safe_path.parent)
        count += int(saved.exists())
    if count == 0:
        raise KeyError("No supported image files selected")
    return batch_dir, count


def _safe_relative_upload_path(relative_path: str) -> Path:
    parts = [
        part
        for part in Path(relative_path).parts
        if part not in {"", ".", ".."} and not Path(part).is_absolute()
    ]
    if not parts:
        raise KeyError("Invalid upload path")
    return Path(*parts)


def _reduce_upload_image(data: bytes) -> tuple[bytes, str]:
    cv2 = _cv2()
    np = _numpy()
    encoded = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise KeyError("Could not decode uploaded image for size reduction")

    height, width = image.shape[:2]
    longest = max(height, width)
    if longest > UPLOAD_MAX_EDGE:
        scale = UPLOAD_MAX_EDGE / float(longest)
        image = cv2.resize(
            image,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    for quality in (92, 88, 84, 80, 76, 72, 68):
        ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            raise KeyError("Could not encode uploaded image")
        reduced = buffer.tobytes()
        if len(reduced) <= UPLOAD_RESIZE_LIMIT_BYTES:
            return reduced, ".jpg"

    while len(reduced) > UPLOAD_RESIZE_LIMIT_BYTES:
        height, width = image.shape[:2]
        if max(height, width) <= 640:
            return reduced, ".jpg"
        image = cv2.resize(
            image,
            (max(1, int(width * 0.85)), max(1, int(height * 0.85))),
            interpolation=cv2.INTER_AREA,
        )
        ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 76])
        if not ok:
            raise KeyError("Could not encode uploaded image")
        reduced = buffer.tobytes()
    return reduced, ".jpg"


def _cv2() -> Any:
    try:
        import cv2

        return cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for upload size reduction") from exc


def _numpy() -> Any:
    try:
        import numpy

        return numpy
    except ImportError as exc:
        raise RuntimeError("NumPy is required for upload size reduction") from exc


def _recognition(engine: FaceEngine, result: RecognitionResult, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "decision": result.decision.value,
        "box": _box(result.face),
        "quality": _quality(result.quality),
        "matches": [_match(engine, match, rank) for rank, match in enumerate(result.matches, 1)],
    }


def _pending(engine: FaceEngine, pending: PendingAddition) -> dict[str, Any]:
    return {
        "pending_id": pending.pending_id,
        "source_image": pending.source_image,
        "crop_path": pending.face.crop_path,
        "decision": pending.decision.value,
        "box": _box(pending.face),
        "quality": _quality(pending.quality),
        "matches": [_match(engine, match, rank) for rank, match in enumerate(pending.matches, 1)],
        "created_at": pending.created_at,
    }


def _rejected(rejected: RejectedFace, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "source_image": rejected.source_image,
        "box": _box(rejected.face),
        "quality": _quality(rejected.quality),
    }


def _person(person: Person) -> dict[str, Any]:
    return {
        "person_id": person.person_id,
        "name": person.name,
        "metadata": person.metadata,
        "created_at": person.created_at,
    }


def _person_summary(summary: PersonSummary, engine: FaceEngine | None = None) -> dict[str, Any]:
    embeddings = engine.list_person_embeddings(summary.person.person_id) if engine else []
    return {
        **_person(summary.person),
        "embedding_count": summary.embedding_count,
        "representative_image": _representative_image(embeddings),
    }


def _embedding(record: EmbeddingRecord) -> dict[str, Any]:
    return {
        "embedding_id": record.embedding_id,
        "person_id": record.person_id,
        "quality_score": record.quality_score,
        "source_image": record.source_image,
        "crop_path": record.crop_path,
        "created_at": record.created_at,
    }


def _init_group(group: InitGroup) -> dict[str, Any]:
    return {
        "group_id": group.group_id,
        "session_id": group.session_id,
        "status": group.status,
        "faces": [
            {
                "init_face_id": face.init_face_id,
                "source_image": face.source_image,
                "crop_path": face.face.crop_path,
                "box": _box(face.face),
                "quality": _quality(face.quality),
            }
            for face in group.faces
        ],
    }


def _match(engine: FaceEngine, match: PersonMatch, rank: int) -> dict[str, Any]:
    person = engine.get_person(match.person_id)
    embeddings = engine.list_person_embeddings(match.person_id) if person else []
    representative = _representative_image(embeddings)
    return {
        "rank": rank,
        "person_id": match.person_id,
        "name": person.name if person else "unknown",
        "score": match.score,
        "embedding_ids": list(match.embedding_ids),
        "embeddings_matched": match.embeddings_matched,
        "representative_image": representative,
    }


def _representative_image(embeddings: list[EmbeddingRecord]) -> str | None:
    for record in embeddings:
        if record.crop_path:
            return record.crop_path
    for record in embeddings:
        if record.source_image:
            return record.source_image
    return None


def _has_duplicate_embedding(vector: tuple[float, ...], embeddings: list[EmbeddingRecord]) -> bool:
    return any(_cosine(vector, record.vector) >= DUPLICATE_MATCH_SCORE for record in embeddings)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _box(face) -> dict[str, Any]:
    return {
        "x": face.box.x,
        "y": face.box.y,
        "width": face.box.width,
        "height": face.box.height,
        "confidence": face.box.confidence,
        "quality_score": face.quality_score,
        "crop_path": face.crop_path,
    }


def _quality(report: QualityReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {"status": report.status.value, "score": report.score, "reasons": list(report.reasons)}


if __name__ == "__main__":
    raise SystemExit(main())
