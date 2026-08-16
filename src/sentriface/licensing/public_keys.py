"""Public verification trust roots. Private signing material never belongs here."""

from __future__ import annotations

import base64


# Selected from the reviewed prototype as the production trust root. The
# corresponding private key is intentionally external to source, builds, and CI.
PRODUCTION_KEY_ID = "prod-2026-01"
_PRODUCTION_PUBLIC_KEY_B64 = "NsoX64zWUy3M7zwCVgN1BgUOhgGNeWC49U5sSKr8prU="


def production_public_keys() -> dict[str, bytes]:
    return {PRODUCTION_KEY_ID: base64.b64decode(_PRODUCTION_PUBLIC_KEY_B64, validate=True)}
