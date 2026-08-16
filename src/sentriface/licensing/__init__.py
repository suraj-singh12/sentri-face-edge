"""Offline, operational licensing authority for packaged Windows releases."""

from .authority import (
    LicenseAuthority,
    LicenseResult,
    LicenseStatus,
    LicenseStoreError,
    MemoryLicenseStore,
    WindowsRegistryLicenseStore,
)
from .fingerprint import MachineFingerprintError, windows_machine_fingerprint

__all__ = [
    "LicenseAuthority",
    "LicenseResult",
    "LicenseStatus",
    "LicenseStoreError",
    "MachineFingerprintError",
    "MemoryLicenseStore",
    "WindowsRegistryLicenseStore",
    "windows_machine_fingerprint",
]
