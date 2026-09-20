from __future__ import annotations

import json
from pathlib import Path
import threading
import urllib.request
from typing import Any

from sentriface.runtime_hardening import InstanceLock
from sentriface.secure_files import read_protected_bytes, write_protected_bytes
from sentriface.secure_storage import (
    KEYRING_SERVICE,
    _keyring_account,
    connect_database,
    load_or_create_master_key,
)


SELF_TEST_PREFIX = "sentriface-release-self-test-"


def _record(checks: list[dict[str, Any]], name: str, **details: Any) -> None:
    checks.append({"name": name, "status": "PASS", **details})


def _validate_owned_root(data_dir: Path) -> Path:
    resolved = data_dir.expanduser().resolve()
    if not any(part.casefold().startswith(SELF_TEST_PREFIX) for part in resolved.parts):
        raise RuntimeError(
            "Release self-test data directory must be an explicitly test-owned "
            f"{SELF_TEST_PREFIX}* path"
        )
    if resolved.exists() and any(resolved.iterdir()):
        raise RuntimeError("Release self-test data directory must start empty")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def run_release_self_test(
    data_dir: Path,
    report_path: Path,
    *,
    detector_model: Path | None = None,
    recognizer_model: Path | None = None,
) -> dict[str, Any]:
    data_dir = _validate_owned_root(data_dir)
    report_path = report_path.resolve()
    checks: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "contract": "sentriface.packaged-runtime-self-test",
        "contract_version": 1,
        "status": "FAIL",
        "checks": checks,
    }
    account = _keyring_account(data_dir)
    credential_created = False
    server = None
    server_thread = None
    cleanup_error = ""
    try:
        import keyring

        if keyring.get_password(KEYRING_SERVICE, account) is not None:
            raise RuntimeError("Release self-test credential ownership collision")
        master_key = load_or_create_master_key(data_dir)
        credential_created = True
        if load_or_create_master_key(data_dir) != master_key:
            raise RuntimeError("Windows keyring did not return the created test key")
        _record(checks, "windows-keyring-create-retrieve")

        database = data_dir / "native-self-test.db"
        connection = connect_database(database, master_key)
        try:
            connection.execute("CREATE TABLE self_test(value TEXT NOT NULL)")
            connection.execute("INSERT INTO self_test VALUES ('ok')")
            connection.commit()
            value = connection.execute("SELECT value FROM self_test").fetchone()[0]
        finally:
            connection.close()
        if value != "ok" or database.read_bytes().startswith(b"SQLite format 3"):
            raise RuntimeError("SQLCipher encrypted database self-test failed")
        _record(checks, "sqlcipher-encrypted-database")

        protected = data_dir / "native-self-test.bin"
        payload = b"sentriface-release-self-test"
        write_protected_bytes(protected, payload, master_key)
        if read_protected_bytes(protected, master_key) != payload:
            raise RuntimeError("Secure-file round trip failed")
        _record(checks, "secure-file-round-trip")

        import cv2
        import numpy

        image = numpy.zeros((4, 4, 3), dtype=numpy.uint8)
        converted = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if converted.shape != (4, 4):
            raise RuntimeError("OpenCV native operation returned an unexpected result")
        _record(checks, "opencv-native-operation", version=cv2.__version__)

        import onnxruntime

        providers = list(onnxruntime.get_available_providers())
        if "CPUExecutionProvider" not in providers:
            raise RuntimeError("ONNX Runtime CPUExecutionProvider is unavailable")
        _record(
            checks,
            "onnxruntime-cpu-provider",
            version=onnxruntime.__version__,
            providers=providers,
        )

        supplied = [detector_model, recognizer_model]
        if any(supplied) and not all(supplied):
            raise RuntimeError("Both detector and recognizer self-test models are required")
        if detector_model and recognizer_model:
            model_facts = []
            for role, model in (
                ("detector", detector_model),
                ("recognizer", recognizer_model),
            ):
                model = model.resolve(strict=True)
                session = onnxruntime.InferenceSession(
                    str(model),
                    providers=["CPUExecutionProvider"],
                )
                model_facts.append(
                    {
                        "role": role,
                        "inputs": len(session.get_inputs()),
                        "outputs": len(session.get_outputs()),
                        "provider": session.get_providers()[0],
                    }
                )
            _record(checks, "external-onnx-model-sessions", models=model_facts)
            report["external_model_session_acceptance"] = "PASS"
        else:
            report["external_model_session_acceptance"] = "PENDING_NO_INPUTS"
        report["model_onboarding_acceptance"] = "PENDING_NOT_EXERCISED"

        from sentriface.api_server import create_server

        server = create_server(
            host="127.0.0.1",
            port=0,
            data_dir=data_dir,
            runtime="dev",
            debug=False,
        )
        server_thread = threading.Thread(
            target=server.serve_forever,
            name="sentriface-release-self-test-server",
        )
        server_thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        request_headers = {"X-SentriFace-Session": server.session_token}
        health_request = urllib.request.Request(
            f"{base_url}/api/health",
            headers=request_headers,
        )
        with urllib.request.urlopen(health_request, timeout=10) as response:
            health = json.load(response)
        if health.get("status") != "ok":
            raise RuntimeError("Loopback health endpoint did not report ready")
        shell_request = urllib.request.Request(base_url, headers=request_headers)
        with urllib.request.urlopen(shell_request, timeout=10) as response:
            html = response.read().decode("utf-8")
        if '<div id="root"></div>' not in html:
            raise RuntimeError("Compiled frontend shell was not served")
        _record(checks, "loopback-http-and-frontend")

        server.shutdown()
        server.server_close()
        server = None
        server_thread.join(timeout=10)
        if server_thread.is_alive():
            raise RuntimeError("Loopback server thread did not terminate")
        server_thread = None

        probe = InstanceLock(data_dir).acquire()
        probe.release()
        _record(checks, "clean-shutdown-and-instance-lock-release")
        report["status"] = "PASS"
    except Exception as exc:
        report["error"] = str(exc).strip("'") or type(exc).__name__
    finally:
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception as exc:
                cleanup_error = f"server cleanup failed: {exc}"
        if server_thread is not None:
            server_thread.join(timeout=10)
            if server_thread.is_alive():
                cleanup_error = "server thread remained alive"
        if credential_created:
            try:
                import keyring
                from keyring.errors import PasswordDeleteError

                try:
                    keyring.delete_password(KEYRING_SERVICE, account)
                except PasswordDeleteError as exc:
                    raise RuntimeError("test credential disappeared before owned cleanup") from exc
                if keyring.get_password(KEYRING_SERVICE, account) is not None:
                    raise RuntimeError("test credential remains after owned cleanup")
                _record(checks, "windows-keyring-owned-cleanup")
            except Exception as exc:
                cleanup_error = f"credential cleanup failed: {exc}"
        if cleanup_error:
            report["status"] = "FAIL"
            report["cleanup_error"] = cleanup_error
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if report["status"] != "PASS":
        raise RuntimeError(
            report.get("cleanup_error") or report.get("error") or "release self-test failed"
        )
    return report
