"""Minimal API client for the running dev server."""
import json, urllib.request, urllib.error, secrets

BASE = "http://127.0.0.1:8765"

class Api:
    def __init__(self, username, password):
        self.window = secrets.token_hex(8)
        html = urllib.request.urlopen(BASE + "/").read().decode()
        import re as _re
        m = _re.search(r'name="sentriface-session-token" content="([^"]+)"', html)
        self.session = m.group(1) if m else secrets.token_hex(8)
        self.cookie = None
        self.login(username, password)

    def _req(self, method, path, payload=None, raw=False):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(BASE + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("X-SentriFace-Window", self.window)
        req.add_header("X-SentriFace-Session", self.session)
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            resp = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            raise RuntimeError(f"{method} {path} -> {e.code}: {body}")
        sc = resp.headers.get("Set-Cookie")
        if sc:
            self.cookie = sc.split(";")[0]
        body = resp.read()
        return body if raw else json.loads(body or b"{}")

    def login(self, username, password):
        return self._req("POST", "/api/auth/login", {"username": username, "password": password})

    def get(self, path):
        return self._req("GET", path)

    def post(self, path, payload):
        return self._req("POST", path, payload)
