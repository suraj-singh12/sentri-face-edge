from __future__ import annotations

import html
import json
import secrets
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from sentriface.licensing.activation import save_activation_key
from sentriface.licensing.fingerprint import generate_machine_id


_MAX_ACTIVATION_REQUEST = 32 * 1024


def run_activation_ui() -> bool:
    """Show a loopback-only activation page and return after activation or exit."""

    token = secrets.token_urlsafe(32)
    state = _ActivationState(token=token, machine_id=generate_machine_id())
    server = _ActivationServer(("127.0.0.1", 0), state)
    server.timeout = 1
    url = f"http://127.0.0.1:{server.server_port}/?token={token}"
    webbrowser.open(url, new=1)
    started_at = time.monotonic()
    try:
        while not state.activated:
            server.handle_request()
            if state.browser_seen and time.monotonic() - state.last_activity > 30:
                break
            if not state.browser_seen and time.monotonic() - started_at > 60:
                break
    finally:
        server.server_close()
    return state.activated


class _ActivationState:
    def __init__(self, *, token: str, machine_id: str) -> None:
        self.token = token
        self.machine_id = machine_id
        self.activated = False
        self.browser_seen = False
        self.last_activity = time.monotonic()
        self.lock = threading.Lock()

    def touch(self) -> None:
        with self.lock:
            self.browser_seen = True
            self.last_activity = time.monotonic()


class _ActivationServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: _ActivationState) -> None:
        self.activation_state = state
        super().__init__(address, _ActivationHandler)


class _ActivationHandler(BaseHTTPRequestHandler):
    server: _ActivationServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/" or parse_qs(parsed.query).get("token", [""])[0] != self.server.activation_state.token:
            self._json({"error": "Activation session is not authorized"}, HTTPStatus.UNAUTHORIZED)
            return
        self.server.activation_state.touch()
        body = _activation_page(
            self.server.activation_state.machine_id,
            self.server.activation_state.token,
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if not self._authorized_request():
            self._json({"error": "Activation session is not authorized"}, HTTPStatus.UNAUTHORIZED)
            return
        self.server.activation_state.touch()
        parsed = urlparse(self.path)
        if parsed.path == "/heartbeat":
            self._json({"ok": True})
            return
        if parsed.path != "/activate":
            self._json({"error": "Unknown activation endpoint"}, HTTPStatus.NOT_FOUND)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > _MAX_ACTIVATION_REQUEST:
            self._json({"error": "Activation key is required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Activation request must be an object")
            key = str(payload.get("key") or "").strip()
            save_activation_key(key, machine_id=self.server.activation_state.machine_id)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self._json({"error": "The activation key is invalid for this machine"}, HTTPStatus.BAD_REQUEST)
            return
        self.server.activation_state.activated = True
        self._json({"ok": True})

    def _authorized_request(self) -> bool:
        host = self.headers.get("Host", "").casefold()
        expected_host = f"127.0.0.1:{self.server.server_port}"
        origin = self.headers.get("Origin", "").casefold()
        expected_origin = f"http://{expected_host}"
        supplied = self.headers.get("X-SentriFace-Activation", "")
        return (
            host == expected_host
            and origin == expected_origin
            and secrets.compare_digest(supplied, self.server.activation_state.token)
        )

    def _json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _security_headers(self) -> None:
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'",
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")


def _activation_page(machine_id: str, token: str) -> str:
    safe_machine_id = html.escape(machine_id)
    script_token = json.dumps(token)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Activate SentriFace Edge</title>
  <style>
    :root {{ color-scheme: light dark; font-family: Inter, Segoe UI, sans-serif; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #0b1218; color: #eef6f6; }}
    main {{ width: min(560px, calc(100vw - 40px)); padding: 30px; border: 1px solid #29434a; border-radius: 14px; background: #121e25; box-shadow: 0 20px 60px #0007; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; }}
    p {{ color: #b8c8cc; line-height: 1.5; }}
    label {{ display: block; margin: 22px 0 7px; font-weight: 700; }}
    .machine {{ display: flex; gap: 8px; }}
    input {{ box-sizing: border-box; width: 100%; padding: 12px; border: 1px solid #3b5961; border-radius: 8px; background: #0c171d; color: inherit; font: inherit; }}
    button {{ padding: 12px 16px; border: 0; border-radius: 8px; background: #18a69b; color: #041514; font-weight: 800; cursor: pointer; white-space: nowrap; }}
    button.secondary {{ background: #253b43; color: #e8f1f2; }}
    button:disabled {{ opacity: .6; cursor: wait; }}
    #activate {{ width: 100%; margin-top: 16px; }}
    #status {{ min-height: 22px; margin: 12px 0 0; color: #ffb4a9; }}
    #status.success {{ color: #72e0bd; }}
  </style>
</head>
<body>
  <main>
    <h1>SentriFace is not activated</h1>
    <p>Copy this machine ID to obtain an activation key, then paste the key below.</p>
    <label for="machine">Machine ID</label>
    <div class="machine">
      <input id="machine" value="{safe_machine_id}" readonly>
      <button id="copy" class="secondary" type="button">Copy</button>
    </div>
    <label for="key">Activation key</label>
    <input id="key" autocomplete="off" spellcheck="false" autofocus>
    <button id="activate" type="button">Activate now</button>
    <p id="status" role="status"></p>
  </main>
  <script>
    const token = {script_token};
    const headers = {{ "Content-Type": "application/json", "X-SentriFace-Activation": token }};
    const status = document.getElementById("status");
    document.getElementById("copy").addEventListener("click", async () => {{
      const machine = document.getElementById("machine");
      try {{ await navigator.clipboard.writeText(machine.value); }}
      catch {{ machine.select(); document.execCommand("copy"); }}
      status.textContent = "Machine ID copied.";
      status.className = "success";
    }});
    document.getElementById("activate").addEventListener("click", async () => {{
      const button = document.getElementById("activate");
      const key = document.getElementById("key").value.trim();
      if (!key) {{ status.textContent = "Enter an activation key."; return; }}
      button.disabled = true;
      status.textContent = "Checking activation key…";
      status.className = "";
      try {{
        const response = await fetch("/activate", {{ method: "POST", headers, body: JSON.stringify({{ key }}) }});
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Activation failed");
        status.textContent = "SentriFace is activated. The application is starting…";
        status.className = "success";
      }} catch (error) {{
        status.textContent = error.message || "Activation failed";
        button.disabled = false;
      }}
    }});
    setInterval(() => fetch("/heartbeat", {{ method: "POST", headers }}).catch(() => {{}}), 5000);
  </script>
</body>
</html>"""
