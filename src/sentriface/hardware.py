from __future__ import annotations

import os
import platform

from sentriface.config import HardwareProfile


def assess_hardware() -> HardwareProfile:
    """Assess enough hardware detail to choose responsive CPU defaults."""

    cpu_count = os.cpu_count() or 1
    memory_gb = _memory_gb()

    if cpu_count <= 4 or (memory_gb is not None and memory_gb < 8):
        return HardwareProfile(
            cpu_count=cpu_count,
            memory_gb=memory_gb,
            tier="low",
            reason="limited CPU threads or memory; prioritize UI responsiveness",
        )

    if cpu_count <= 8 or (memory_gb is not None and memory_gb < 16):
        return HardwareProfile(
            cpu_count=cpu_count,
            memory_gb=memory_gb,
            tier="medium",
            reason="moderate CPU capacity; allow small parallel batches",
        )

    return HardwareProfile(
        cpu_count=cpu_count,
        memory_gb=memory_gb,
        tier="high",
        reason="ample CPU capacity; allow larger preprocessing batches",
    )


def _memory_gb() -> float | None:
    system = platform.system().lower()
    if system == "windows":
        return _windows_memory_gb()
    if system in {"linux", "darwin"}:
        return _posix_memory_gb()
    return None


def _windows_memory_gb() -> float | None:
    try:
        import ctypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return round(status.ullTotalPhys / (1024**3), 2)
    except Exception:
        return None


def _posix_memory_gb() -> float | None:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round((pages * page_size) / (1024**3), 2)
    except (ValueError, OSError, AttributeError):
        return None

