from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HardwareProfile:
    cpu_count: int
    memory_gb: float | None
    tier: str
    reason: str

# TODO: Check if confidence scores are same in UI and here, remove capability from UI.

@dataclass(frozen=True)
class RuntimeConfig:
    """Configuration tuned for low-end CPU-only machines."""

    data_dir: Path = Path("data")
    db_name: str = "sentriface.db"
    embedding_dim: int = 512
    top_k: int = 3
    high_confidence: float = 0.62
    medium_confidence: float = 0.48
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
    detector_model: Path = Path("models/det_500m.onnx")
    recognizer_model: Path = Path("models/w600k_r50.onnx")
    collect_metrics: bool = False
    backup_retention_limit: int = 10

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_name

    @property
    def face_dir(self) -> Path:
        return self.data_dir / "faces"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"


def config_for_hardware(
    profile: HardwareProfile,
    data_dir: Path = Path("data"),
) -> RuntimeConfig:
    """Choose safe defaults from a lightweight hardware profile."""

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
