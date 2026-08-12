from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sentriface.paths import (
    database_dir,
    default_data_dir,
    default_detector_model,
    default_recognizer_model,
    managed_data_dir,
)


@dataclass(frozen=True)
class HardwareProfile:
    cpu_count: int
    memory_gb: float | None
    tier: str
    reason: str


@dataclass(frozen=True)
class RuntimeConfig:
    """Configuration tuned for low-end CPU-only machines."""

    data_dir: Path = field(default_factory=default_data_dir)
    db_name: str = "sentriface.db"

    embedding_dim: int = 512
    top_k: int = 3

    # Matching policy is authoritative in the backend and returned to clients.
    high_confidence: float = 0.60
    medium_confidence: float = 0.50
    possible_confidence: float = 0.40

    min_detector_confidence: float = 0.55
    min_face_size: int = 48
    min_quality_score: float = 0.55
    warn_quality_score: float = 0.72

    blur_threshold: float = 35.0
    dark_threshold: float = 35.0
    bright_threshold: float = 220.0

    max_workers: int = 1
    onnx_intra_threads: int = 1
    max_image_edge: int = 960
    detector_input_size: int = 640
    batch_size: int = 1

    prefer_small_models: bool = True
    index_backend: str = "linear"
    hardware_tier: str = "low"

    detector_model: Path = field(default_factory=default_detector_model)
    recognizer_model: Path = field(default_factory=default_recognizer_model)

    collect_metrics: bool = False

    backup_retention_limit: int = 10
    automatic_backup_interval_hours: int = 24

    storage_key: bytes | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    @property
    def db_path(self) -> Path:
        return database_dir(self.data_dir) / self.db_name

    @property
    def face_dir(self) -> Path:
        return managed_data_dir(self.data_dir) / "faces"

    @property
    def index_dir(self) -> Path:
        return managed_data_dir(self.data_dir) / "index"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"


def config_for_hardware(
    profile: HardwareProfile,
    data_dir: Path | None = None,
) -> RuntimeConfig:
    """Choose safe defaults from a lightweight hardware profile."""

    data_dir = data_dir or default_data_dir()

    if profile.tier == "high":
        return RuntimeConfig(
            data_dir=data_dir,
            max_workers=3,
            onnx_intra_threads=4,
            max_image_edge=1280,
            batch_size=4,
            prefer_small_models=False,
            index_backend="hnswlib",
            hardware_tier=profile.tier,
        )

    if profile.tier == "medium":
        return RuntimeConfig(
            data_dir=data_dir,
            max_workers=2,
            onnx_intra_threads=2,
            max_image_edge=1120,
            batch_size=2,
            prefer_small_models=False,
            index_backend="hnswlib",
            hardware_tier=profile.tier,
        )

    return RuntimeConfig(
        data_dir=data_dir,
        max_workers=1,
        onnx_intra_threads=1,
        max_image_edge=880,
        batch_size=1,
        prefer_small_models=True,
        index_backend="linear",
        hardware_tier=profile.tier,
    )