import pytest

from sentriface import api_server
from sentriface.os_network_policy import OsNetworkPolicyError, OsNetworkPolicyStatus


@pytest.fixture
def linux_checkout(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(api_server.sys, "platform", "linux")
    monkeypatch.setattr(api_server.sys, "frozen", False, raising=False)
    return tmp_path


@pytest.mark.parametrize("enforced", [False, True])
def test_linux_source_onnx_keeps_existing_policy_if_present(
    linux_checkout, monkeypatch, enforced,
):
    status = OsNetworkPolicyStatus(enforced, "systemd-ip-firewall", "fixture")
    monkeypatch.setattr(api_server, "inspect_os_network_policy", lambda: status)
    result = api_server._startup_network_policy(
        "onnx", allow_unpacked_source=True, source_root=linux_checkout,
    )
    assert result is (status if enforced else None)


def test_frozen_linux_cannot_use_source_exception(linux_checkout, monkeypatch):
    monkeypatch.setattr(api_server.sys, "frozen", True)
    with pytest.raises(ValueError, match="unpackaged Git checkout"):
        api_server._startup_network_policy(
            "onnx", allow_unpacked_source=True, source_root=linux_checkout,
        )


def test_compiled_linux_cannot_use_source_exception(linux_checkout, monkeypatch):
    monkeypatch.setattr(api_server, "__compiled__", object(), raising=False)
    with pytest.raises(ValueError, match="unpackaged Git checkout"):
        api_server._startup_network_policy(
            "onnx", allow_unpacked_source=True, source_root=linux_checkout,
        )


def test_linux_source_exception_requires_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(api_server.sys, "platform", "linux")
    with pytest.raises(ValueError, match="unpackaged Git checkout"):
        api_server._startup_network_policy(
            "onnx", allow_unpacked_source=True, source_root=tmp_path,
        )


def test_linux_source_exception_requires_onnx(linux_checkout):
    with pytest.raises(ValueError, match="requires --runtime onnx"):
        api_server._startup_network_policy(
            "dev", allow_unpacked_source=True, source_root=linux_checkout,
        )


def test_linux_without_explicit_source_intent_still_requires_os_policy(
    linux_checkout, monkeypatch,
):
    from sentriface import os_network_policy

    monkeypatch.setattr(
        os_network_policy.Path, "read_text", lambda *args, **kwargs: "0::/\n",
    )
    with pytest.raises(OsNetworkPolicyError, match="systemd service"):
        api_server._startup_network_policy("onnx", source_root=linux_checkout)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.0.2.1", "::1"])
def test_linux_source_exception_does_not_allow_non_ipv4_loopback_binding(
    linux_checkout, monkeypatch, host,
):
    monkeypatch.setattr(
        api_server, "inspect_os_network_policy",
        lambda: OsNetworkPolicyStatus(False, "systemd-ip-firewall", "fixture"),
    )
    policy = api_server._startup_network_policy(
        "onnx", allow_unpacked_source=True, source_root=linux_checkout,
    )
    with pytest.raises(ValueError, match="IPv4 loopback"):
        api_server.create_server(
            host=host, data_dir=linux_checkout / "data", runtime="onnx",
            os_network_policy=policy,
        )
