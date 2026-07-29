from __future__ import annotations

import ipaddress
import os
import socket
import threading
from pathlib import Path
from typing import Any


class OfflineViolationError(OSError):
    """Raised when code attempts a non-loopback network operation."""


_lock = threading.Lock()
_installed = False
_original_bind = socket.socket.bind
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_sendto = socket.socket.sendto
_original_getaddrinfo = socket.getaddrinfo
_original_gethostbyname = socket.gethostbyname
_original_gethostbyname_ex = socket.gethostbyname_ex
_original_gethostbyaddr = socket.gethostbyaddr
_original_getnameinfo = socket.getnameinfo


def require_local_path(path: Path) -> Path:
    """Reject obvious filesystem paths that would access a remote machine."""
    raw = str(path)
    if raw.startswith(("\\\\", "//")):
        raise OfflineViolationError("SentriFace blocked a network filesystem path")
    expanded = path.expanduser()
    if os.name == "nt" and expanded.drive:
        import ctypes

        drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{expanded.drive}\\")
        if drive_type == 4:  # DRIVE_REMOTE
            raise OfflineViolationError("SentriFace blocked a mapped network drive")
    return expanded


def install_offline_guard() -> None:
    """Block Python socket traffic to every destination except loopback."""
    global _installed
    with _lock:
        if _installed:
            return
        socket.socket.bind = _guarded_bind
        socket.socket.connect = _guarded_connect
        socket.socket.connect_ex = _guarded_connect_ex
        socket.socket.sendto = _guarded_sendto
        socket.getaddrinfo = _guarded_getaddrinfo
        socket.gethostbyname = _guarded_gethostbyname
        socket.gethostbyname_ex = _guarded_gethostbyname_ex
        socket.gethostbyaddr = _guarded_gethostbyaddr
        socket.getnameinfo = _guarded_getnameinfo
        _installed = True


def offline_guard_installed() -> bool:
    return _installed


def _guarded_bind(sock: socket.socket, address: Any):
    _require_loopback_address(sock.family, address)
    return _original_bind(sock, address)


def _guarded_connect(sock: socket.socket, address: Any):
    _require_loopback_address(sock.family, address)
    return _original_connect(sock, address)


def _guarded_connect_ex(sock: socket.socket, address: Any):
    _require_loopback_address(sock.family, address)
    return _original_connect_ex(sock, address)


def _guarded_sendto(sock: socket.socket, data: bytes, *args):
    if not args:
        raise OfflineViolationError("SentriFace blocked a network datagram without a destination")
    address = args[-1]
    _require_loopback_address(sock.family, address)
    return _original_sendto(sock, data, *args)


def _guarded_getaddrinfo(host, *args, **kwargs):
    _require_loopback_host(host)
    return _original_getaddrinfo(host, *args, **kwargs)


def _guarded_gethostbyname(host):
    _require_loopback_host(host)
    return _original_gethostbyname(host)


def _guarded_gethostbyname_ex(host):
    _require_loopback_host(host)
    return _original_gethostbyname_ex(host)


def _guarded_gethostbyaddr(host):
    _require_loopback_host(host)
    return _original_gethostbyaddr(host)


def _guarded_getnameinfo(sockaddr, flags):
    if not isinstance(sockaddr, tuple) or not sockaddr:
        raise OfflineViolationError("SentriFace blocked name resolution for an invalid address")
    _require_loopback_host(sockaddr[0])
    return _original_getnameinfo(sockaddr, flags)


def _require_loopback_host(host: Any) -> None:
    if host is not None and not _is_loopback_host(host):
        raise OfflineViolationError(f"SentriFace blocked name resolution outside localhost: {host}")


def _require_loopback_address(family: int, address: Any) -> None:
    if family in {getattr(socket, "AF_UNIX", -1)}:
        return
    if family not in {socket.AF_INET, socket.AF_INET6}:
        raise OfflineViolationError("SentriFace blocked a non-local socket family")
    if not isinstance(address, tuple) or not address or not _is_loopback_host(address[0]):
        raise OfflineViolationError(f"SentriFace blocked a non-loopback network destination: {address}")


def _is_loopback_host(host: Any) -> bool:
    normalized = str(host).strip().strip("[]").casefold()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False
