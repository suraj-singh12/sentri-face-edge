from __future__ import annotations

import base64
import http.client
import json
import tempfile
import threading
import types
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentriface.licensing.authority import (
    LicenseAuthority,
    LicenseStatus,
    MAX_TOKEN_BYTES,
    MemoryLicenseStore,
    LicenseStoreError,
    WindowsRegistryLicenseStore,
    canonical_payload,
)
from sentriface.licensing.fingerprint import MachineFingerprintError, windows_machine_fingerprint
from sentriface.api_server import _license_exempt_endpoint, _required_capability, create_server


MACHINE = "SFE-MC-ABCDE-FGHIJ-KLMNO-PQRST-UVWX"
NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def signing_key():
    return Ed25519PrivateKey.generate()


def _claims(**changes):
    payload = {
        "version": 2,
        "product": "SentriFaceEdge",
        "license_id": str(uuid4()),
        "key_id": "test-only",
        "machine": MACHINE,
        "edition": "commercial",
        "license_type": "perpetual",
        "issued_at": "2026-08-16T11:00:00Z",
        "expires_at": None,
    }
    payload.update(changes)
    return payload


def _segment(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _token(key, claims=None, *, payload_bytes=None):
    raw = payload_bytes if payload_bytes is not None else canonical_payload(claims or _claims())
    return f"SFE2.{_segment(raw)}.{_segment(key.sign(raw))}"


def _authority(key, *, store=None, machine=MACHINE):
    public = key.public_key().public_bytes_raw()
    return LicenseAuthority(
        public_keys={"test-only": public},
        store=store or MemoryLicenseStore(),
        machine_id_provider=lambda: machine,
        clock=lambda: NOW,
    )


def test_valid_license_activates_and_status_never_returns_token(signing_key):
    store = MemoryLicenseStore()
    authority = _authority(signing_key, store=store)
    token = _token(signing_key)
    result = authority.activate(token)
    assert result.licensed
    assert store.token == token
    payload = authority.status().as_dict(enforced=True)
    assert payload["licensed"] is True
    assert token not in json.dumps(payload)


@pytest.mark.parametrize(
    ("claims", "code"),
    [
        (_claims(key_id="unknown"), "license_key_unknown"),
        (_claims(product="Other"), "license_product_mismatch"),
        (_claims(version=3), "license_version_unsupported"),
        (_claims(version=2.0), "license_version_unsupported"),
        (_claims(machine="SFE-MC-WRONG"), "license_machine_mismatch"),
        (_claims(extra="value"), "license_claims_invalid"),
        ({key: value for key, value in _claims().items() if key != "edition"}, "license_claims_invalid"),
        (_claims(license_id="not-a-uuid"), "license_claims_invalid"),
        (_claims(issued_at="not-a-time"), "license_claims_invalid"),
    ],
)
def test_strict_claim_refusals(signing_key, claims, code):
    assert _authority(signing_key).verify(_token(signing_key, claims)).code == code


def test_wrong_signature_and_malformed_token_refuse(signing_key):
    other = Ed25519PrivateKey.generate()
    authority = _authority(signing_key)
    assert authority.verify(_token(other)).code == "license_signature_invalid"
    assert authority.verify("SFE2.bad").code == "license_token_malformed"
    assert authority.verify("x" * (MAX_TOKEN_BYTES + 1)).code == "license_token_oversized"


def test_noncanonical_and_duplicate_payload_refuse(signing_key):
    noncanonical = json.dumps(_claims(), sort_keys=False, indent=2).encode("ascii")
    assert _authority(signing_key).verify(_token(signing_key, payload_bytes=noncanonical)).code == "license_token_malformed"
    duplicate = b'{"edition":"commercial","edition":"commercial"}'
    assert _authority(signing_key).verify(_token(signing_key, payload_bytes=duplicate)).code == "license_token_malformed"


def test_expiry_and_future_issue_are_factual(signing_key):
    expired = _claims(
        license_type="subscription",
        expires_at="2026-08-16T11:30:00Z",
    )
    assert _authority(signing_key).verify(_token(signing_key, expired)).status == LicenseStatus.EXPIRED
    future = _claims(issued_at="2026-08-16T13:00:00Z")
    assert _authority(signing_key).verify(_token(signing_key, future)).code == "license_not_yet_valid"


def test_machine_fingerprint_is_versioned_normalized_and_fails_closed():
    one = windows_machine_fingerprint(machine_guid_reader=lambda: "{00112233-4455-6677-8899-AABBCCDDEEFF}")
    two = windows_machine_fingerprint(machine_guid_reader=lambda: "00112233-4455-6677-8899-aabbccddeeff")
    assert one == two
    assert one.startswith("SFE-MC-")
    assert "00112233" not in one
    with pytest.raises(MachineFingerprintError):
        windows_machine_fingerprint(machine_guid_reader=lambda: "")


def test_machine_identity_failure_is_redacted(signing_key):
    def unavailable():
        raise MachineFingerprintError("raw-sensitive-hardware-value")

    authority = LicenseAuthority(
        public_keys={"test-only": signing_key.public_key().public_bytes_raw()},
        store=MemoryLicenseStore(),
        machine_id_provider=unavailable,
    )
    payload = authority.status().as_dict(enforced=True)
    assert payload["code"] == "machine_identity_unavailable"
    assert "raw-sensitive" not in json.dumps(payload)


def test_invalid_activation_never_replaces_existing_token(signing_key):
    store = MemoryLicenseStore("existing")
    result = _authority(signing_key, store=store).activate("bad")
    assert not result.licensed
    assert store.token == "existing"


def test_registry_corruption_refuses_without_returning_raw_value(monkeypatch):
    class Key:
        def __enter__(self): return self
        def __exit__(self, *_): return None

    fake = types.SimpleNamespace(
        HKEY_CURRENT_USER=1,
        KEY_READ=2,
        REG_SZ=1,
        OpenKey=lambda *_: Key(),
        QueryValueEx=lambda *_: (b"raw-corrupt-license", 3),
    )
    monkeypatch.setattr("sentriface.licensing.authority.sys.platform", "win32")
    monkeypatch.setitem(__import__("sys").modules, "winreg", fake)
    with pytest.raises(LicenseStoreError) as caught:
        WindowsRegistryLicenseStore().load()
    assert "raw-corrupt-license" not in str(caught.value)


def test_license_routes_have_explicit_capabilities_and_recovery_exemptions():
    assert _required_capability("GET", "/api/license/status") == "view"
    assert _required_capability("POST", "/api/license/activate") == "license_administer"
    for method, path in (
        ("POST", "/api/backups"),
        ("POST", "/api/backups/restore"),
        ("POST", "/api/integrity/check"),
        ("POST", "/api/recovery/configure"),
        ("POST", "/api/models/install"),
        ("GET", "/api/profile"),
    ):
        assert _license_exempt_endpoint(method, path), path
    assert not _license_exempt_endpoint("POST", "/api/person-create")
    assert not _license_exempt_endpoint("POST", "/api/recognize")


def test_api_requires_admin_refuses_actor_spoof_and_blocks_product_mutation(signing_key):
    pytest.importorskip("keyring")
    pytest.importorskip("sqlcipher3")
    with tempfile.TemporaryDirectory() as temporary:
        server = create_server(port=0, data_dir=__import__("pathlib").Path(temporary) / "data", runtime="dev")
        server.license = _authority(signing_key, store=MemoryLicenseStore())
        server.license.enforced = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, _, headers = _request(server, "POST", "/api/auth/signup", {
                "username": "owner", "display_name": "Owner", "password": "owner password long enough",
            })
            assert status == 201
            admin_cookie = headers["set-cookie"].split(";", 1)[0]
            admin = server.auth.authenticate(admin_cookie.split("=", 1)[1])
            server.auth.create_user(admin, "viewer", "Viewer", "viewer password long enough", ["viewer"])
            status, _, headers = _request(server, "POST", "/api/auth/login", {
                "username": "viewer", "password": "viewer password long enough",
            })
            assert status == 200
            viewer_cookie = headers["set-cookie"].split(";", 1)[0]

            assert _request(server, "POST", "/api/license/activate", {"token": _token(signing_key)}, cookie=viewer_cookie)[0] == 403
            status, payload, _ = _request(
                server, "POST", "/api/license/activate",
                {"token": _token(signing_key), "actor": "spoofed"}, cookie=admin_cookie,
            )
            assert status == 422
            assert payload["reason"] == "invalid_license_activation_payload"
            status, payload, _ = _request(server, "POST", "/api/person-create", {"name": "Blocked"}, cookie=admin_cookie)
            assert status == 402
            assert payload["code"] == "license_required"

            token = _token(signing_key)
            status, payload, _ = _request(server, "POST", "/api/license/activate", {"token": token}, cookie=admin_cookie)
            assert status == 200
            assert payload["licensed"] is True
            assert token not in json.dumps(payload)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def _request(server, method, path, payload=None, *, cookie=""):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"X-SentriFace-Session": server.session_token}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = cookie
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=20)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read()), {key.casefold(): value for key, value in response.getheaders()}
    finally:
        connection.close()
