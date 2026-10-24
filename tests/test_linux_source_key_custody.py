import secrets
import sys
from pathlib import Path

import pytest

from sentriface import api_server, secure_storage
from sentriface.secure_files import write_protected_bytes, read_protected_bytes
from sentriface.storage.sqlite_store import SQLiteIdentityStore


# Linux's POSIX ownership and local source-key custody are not available on
# Windows/macOS. Portable OS-vault behavior has its own cross-platform tests.
pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux source-key custody only")


@pytest.fixture
def source_authority(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    return tmp_path / "source-dev"


def acquire(root):
    return secure_storage.load_linux_source_master_key(root, explicit_source_onnx=True)


def test_persistent_independent_authority_keys(source_authority):
    first = acquire(source_authority)
    assert len(first) == 32
    assert secrets.compare_digest(first, acquire(source_authority))
    assert not secrets.compare_digest(first, acquire(source_authority.with_name("other-dev")))
    assert (source_authority / secure_storage.LINUX_SOURCE_KEY_NAME).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
def test_default_os_vault_and_test_vault_are_unchanged(source_authority, monkeypatch, test_keyring, platform):
    monkeypatch.setattr(sys, "platform", platform)
    key = secure_storage.load_or_create_master_key(source_authority)
    assert secrets.compare_digest(key, secure_storage.load_or_create_master_key(source_authority))
    assert test_keyring.calls
    assert not (source_authority / secure_storage.LINUX_SOURCE_KEY_NAME).exists()
    if platform != "linux":
        with pytest.raises(secure_storage.StorageSecurityError, match="explicit unpackaged"):
            acquire(source_authority)


@pytest.mark.parametrize("packaged", ["frozen", "compiled"])
def test_packaged_linux_rejects_local_custody(source_authority, monkeypatch, packaged):
    if packaged == "frozen":
        monkeypatch.setattr(sys, "frozen", True)
    else:
        monkeypatch.setattr(secure_storage, "__compiled__", object(), raising=False)
    with pytest.raises(secure_storage.StorageSecurityError, match="explicit unpackaged"):
        acquire(source_authority)
    assert not source_authority.exists()


def test_no_implicit_fallback_when_os_vault_fails(source_authority, monkeypatch):
    import keyring
    from keyring.errors import KeyringError

    def unavailable(*args):
        raise KeyringError("unavailable")
    monkeypatch.setattr(keyring, "get_password", unavailable)
    with pytest.raises(secure_storage.StorageSecurityError, match="OS|operating-system"):
        secure_storage.load_or_create_master_key(source_authority)
    with pytest.raises(secure_storage.StorageSecurityError, match="explicit unpackaged"):
        secure_storage.load_linux_source_master_key(source_authority, explicit_source_onnx=False)
    assert not source_authority.exists()


def test_non_checkout_rejects_local_custody(source_authority, monkeypatch, tmp_path):
    monkeypatch.setattr(secure_storage, "__file__", str(tmp_path / "non-source/src/sentriface/secure_storage.py"))
    with pytest.raises(secure_storage.StorageSecurityError, match="explicit unpackaged"):
        acquire(source_authority)


@pytest.mark.parametrize("failure", ["missing", "wrong", "corrupt", "copied", "permissions", "symlink"])
def test_existing_encrypted_authority_fails_closed(source_authority, failure):
    key = acquire(source_authority)
    database = source_authority / "sentriface.db"
    store = SQLiteIdentityStore(database, database_key=key)
    store.initialize()
    before = database.read_bytes()
    path = source_authority / secure_storage.LINUX_SOURCE_KEY_NAME
    if failure == "missing":
        path.unlink()
    elif failure == "wrong":
        path.write_bytes(path.read_bytes()[:-32] + secrets.token_bytes(32))
    elif failure == "corrupt":
        path.write_bytes(b"broken record")
    elif failure == "copied":
        other = source_authority.with_name("other-dev")
        acquire(other)
        path.write_bytes((other / secure_storage.LINUX_SOURCE_KEY_NAME).read_bytes())
    elif failure == "permissions":
        path.chmod(0o644)
    else:
        other = path.with_name("key-target")
        path.rename(other)
        path.symlink_to(other)
    with pytest.raises(secure_storage.StorageSecurityError):
        acquire(source_authority)
    assert database.read_bytes() == before
    if failure == "missing":
        assert not path.exists()


def test_missing_key_with_only_encrypted_media_fails(source_authority):
    key = acquire(source_authority)
    write_protected_bytes(source_authority / "faces/sample.jpg", b"sample", key)
    (source_authority / secure_storage.LINUX_SOURCE_KEY_NAME).unlink()
    with pytest.raises(secure_storage.StorageSecurityError, match="missing"):
        acquire(source_authority)


def test_wrong_key_with_only_encrypted_logs_fails(source_authority):
    from sentriface.logging_config import EncryptedLogSink

    key = acquire(source_authority)
    EncryptedLogSink(source_authority / "logs/test.sflog", key).write("diagnostic")
    path = source_authority / secure_storage.LINUX_SOURCE_KEY_NAME
    path.write_bytes(path.read_bytes()[:-32] + secrets.token_bytes(32))
    with pytest.raises(secure_storage.StorageSecurityError):
        acquire(source_authority)


def test_source_server_uses_normal_sqlcipher_and_protected_files(source_authority, capfd):
    server = api_server.create_server(data_dir=source_authority, port=0, runtime="onnx", linux_source_onnx=True)
    try:
        key = server.config.storage_key
        assert key is not None
        assert secrets.compare_digest(key, acquire(source_authority))
        assert secure_storage.database_is_encrypted(server.config.db_path)
        path = source_authority / "faces/sample.jpg"
        write_protected_bytes(path, b"encryption remains active", key)
        assert read_protected_bytes(path, key) == b"encryption remains active"
        assert path.read_bytes() != b"encryption remains active"
        output = capfd.readouterr()
        assert key.hex() not in output.out + output.err
        assert repr(key) not in output.out + output.err
    finally:
        server.server_close()


def test_cannot_select_installed_product_authority(source_authority, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    with pytest.raises(secure_storage.StorageSecurityError, match="installed-product"):
        acquire(tmp_path / "sentriface")


@pytest.mark.parametrize("missing_key", [False, True])
def test_linux_reset_removes_only_default_dev_authority(source_authority, monkeypatch, tmp_path, missing_key):
    from scripts.reset_macos_dev_authority import reset

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = tmp_path / "Library/Application Support/SentriFace-Dev"
    acquire(root)
    if missing_key:
        (root / secure_storage.LINUX_SOURCE_KEY_NAME).unlink()
    unrelated = tmp_path / "unrelated"
    acquire(unrelated)
    production = root.with_name("SentriFace")
    production.mkdir()
    marker = production / "keep"
    marker.write_text("production")
    outside_models = tmp_path / "repository/models"
    outside_models.mkdir(parents=True)
    (outside_models / "model.onnx").write_bytes(b"untouched")
    (root / "models").symlink_to(outside_models, target_is_directory=True)
    reset(root, linux_source=True)
    assert not root.exists()
    assert marker.read_text() == "production"
    assert (outside_models / "model.onnx").read_bytes() == b"untouched"
    assert (unrelated / secure_storage.LINUX_SOURCE_KEY_NAME).exists()


def test_linux_reset_refuses_custom_authority(source_authority):
    from scripts.reset_macos_dev_authority import reset

    acquire(source_authority)
    with pytest.raises(ValueError, match="exact default"):
        reset(source_authority, linux_source=True)
    assert (source_authority / secure_storage.LINUX_SOURCE_KEY_NAME).exists()
