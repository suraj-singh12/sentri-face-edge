import secrets
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from sentriface.recovery import RecoveryService, RecoveryError, LINUX_SOURCE_RECOVERY_NAME, RECOVERY_KIT_NAME, recover_master_key
from sentriface.secure_storage import load_linux_source_master_key, StorageSecurityError, LINUX_SOURCE_KEY_NAME
from sentriface.storage.sqlite_store import SQLiteIdentityStore
from sentriface.backup_service import BackupService


def service(root):
    key = load_linux_source_master_key(root, explicit_source_onnx=True)
    store = SQLiteIdentityStore(root/'sentriface.db', database_key=key); store.initialize()
    backups = BackupService(store.db_path, root/'backups', data_dir=root, database_key=key)
    return RecoveryService(root, key, backups, linux_source_onnx=True), key


def test_source_recovery_persists_isolates_and_authenticates(tmp_path, capfd):
    recovery, key = service(tmp_path/'one')
    destination = tmp_path/'exports'
    result = recovery.configure(destination)
    code = result['recovery_code']
    path = recovery.data_dir/LINUX_SOURCE_RECOVERY_NAME
    assert path.stat().st_mode & 0o777 == 0o600
    assert code.encode() not in path.read_bytes()
    reopened, reopened_key = service(recovery.data_dir)
    assert reopened.status()['configured']
    assert reopened._load_code() == code
    assert secrets.compare_digest(key, reopened_key)
    other, other_key = service(tmp_path/'two')
    other_code = other.configure(tmp_path/'other-exports')['recovery_code']
    assert other_code != code and other_key != key
    assert recover_master_key(destination/RECOVERY_KIT_NAME, code) == key
    with pytest.raises(RecoveryError): recover_master_key(destination/RECOVERY_KIT_NAME, other_code)
    recovered_root = tmp_path/'fresh'
    restored_key = recover_master_key(destination/RECOVERY_KIT_NAME, code)
    assert load_linux_source_master_key(recovered_root, explicit_source_onnx=True, recovered_key=restored_key) == key
    assert load_linux_source_master_key(recovered_root, explicit_source_onnx=True) == key
    # Existing key identity is never overwritten by a different recovery kit.
    before = (recovered_root/LINUX_SOURCE_KEY_NAME).read_bytes()
    with pytest.raises(StorageSecurityError): load_linux_source_master_key(recovered_root, explicit_source_onnx=True, recovered_key=other_key)
    assert (recovered_root/LINUX_SOURCE_KEY_NAME).read_bytes() == before
    output = capfd.readouterr(); assert code not in output.out+output.err
    path.write_bytes((other.data_dir/LINUX_SOURCE_RECOVERY_NAME).read_bytes())
    with pytest.raises(RecoveryError): reopened.status()


@pytest.mark.parametrize('failure', ['missing', 'corrupt', 'unsafe', 'settings-corrupt', 'settings-invalid'])
def test_configured_source_custody_never_silently_rotates(tmp_path, failure):
    recovery, key = service(tmp_path/'authority')
    destination=tmp_path/'exports'; recovery.configure(destination)
    kit = (destination/RECOVERY_KIT_NAME).read_bytes()
    path=recovery.data_dir/LINUX_SOURCE_RECOVERY_NAME
    if failure=='missing': path.unlink()
    elif failure=='unsafe': path.chmod(0o644)
    elif failure=='settings-corrupt': recovery.settings_path.write_text('{')
    elif failure=='settings-invalid': recovery.settings_path.write_text('[]')
    else: path.write_bytes(b'corrupt')
    with pytest.raises(RecoveryError): recovery.configure(destination)
    assert (destination/RECOVERY_KIT_NAME).read_bytes() == kit


@pytest.mark.parametrize('mode', ['frozen','compiled','non-source'])
def test_source_recovery_requires_explicit_source_eligibility(tmp_path, monkeypatch, mode):
    recovery,key=service(tmp_path/'authority')
    if mode=='frozen': monkeypatch.setattr(sys,'frozen',True,raising=False)
    elif mode=='compiled': monkeypatch.setattr('sentriface.secure_storage.__compiled__',object(),raising=False)
    else: monkeypatch.setattr('sentriface.secure_storage.__file__',str(tmp_path/'installed/src/sentriface/secure_storage.py'))
    with pytest.raises(StorageSecurityError): recovery.configure(tmp_path/'exports')
    assert not (recovery.data_dir/LINUX_SOURCE_RECOVERY_NAME).exists()


@pytest.mark.parametrize('platform', ['darwin','win32','linux'])
def test_default_recovery_retains_os_vault(tmp_path, monkeypatch, test_keyring, platform):
    monkeypatch.setattr(sys,'platform',platform)
    recovery=RecoveryService(tmp_path, secrets.token_bytes(32), SimpleNamespace(retention_limit=10))
    code=recovery.configure(tmp_path.with_name(tmp_path.name+'-export'))['recovery_code']
    assert recovery._load_code()==code
    assert test_keyring.calls
    assert not (tmp_path/LINUX_SOURCE_RECOVERY_NAME).exists()
