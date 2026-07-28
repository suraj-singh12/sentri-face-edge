from __future__ import annotations

import json
import tempfile
import threading
import urllib.request
from pathlib import Path

from sentriface.api_server import STATIC_DIR, create_server


def main() -> int:
    index = STATIC_DIR / "index.html"
    assets = STATIC_DIR / "assets"
    if not index.is_file() or not assets.is_dir() or not any(assets.iterdir()):
        raise RuntimeError("Installed package is missing the compiled frontend")

    with tempfile.TemporaryDirectory() as temporary:
        server = create_server(
            host="127.0.0.1",
            port=0,
            data_dir=Path(temporary) / "data",
            runtime="dev",
            debug=False,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=10) as response:
                health = json.load(response)
            if health.get("status") != "ok":
                raise RuntimeError(f"Unexpected health response: {health}")
            with urllib.request.urlopen(base_url, timeout=10) as response:
                html = response.read().decode("utf-8")
            if '<div id="root"></div>' not in html:
                raise RuntimeError("Installed server did not return the application shell")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)
    print("installed package smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
