"""Explicit, serializable extraction settings."""
from dataclasses import asdict, dataclass, fields
from math import isfinite
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class ExtractionConfig:
    rows: int = 80
    cols: int = 28
    threshold: float = 150.0
    min_total_response: float = 5000.0
    relative_occupancy: float = 0.2
    max_gap_seconds: float = 1.0
    min_segment_seconds: float = 5.0
    min_frames: int = 6
    smoothing_seconds: float = 0.25
    trim_fraction: float = 0.0
    timezone: str = "Europe/Rome"
    check_filename_date: bool = True
    legacy_skip_first_line: bool = False
    qc_min_segment_seconds: float = 10.0
    qc_max_gap_loss_fraction: float = 0.1
    qc_frozen_seconds: float = 2.0

    def __post_init__(self):
        for name in ("rows", "cols", "min_frames"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.min_frames < 3:
            raise ValueError("min_frames must be at least 3")
        for name in ("threshold", "min_total_response", "relative_occupancy", "max_gap_seconds",
                     "min_segment_seconds", "smoothing_seconds", "trim_fraction",
                     "qc_min_segment_seconds", "qc_max_gap_loss_fraction", "qc_frozen_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise ValueError(f"{name} must be a finite number")
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.threshold > 65535:
            raise ValueError("threshold exceeds the 16-bit sensor range")
        for name in ("min_total_response", "max_gap_seconds", "min_segment_seconds", "qc_frozen_seconds"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be greater than zero")
        if not 0 <= self.relative_occupancy <= 1:
            raise ValueError("relative_occupancy must be between 0 and 1")
        if not 0 <= self.trim_fraction < 0.5:
            raise ValueError("trim_fraction must be in [0, 0.5)")
        if not 0 <= self.qc_max_gap_loss_fraction <= 1:
            raise ValueError("qc_max_gap_loss_fraction must be between 0 and 1")
        for name in ("check_filename_date", "legacy_skip_first_line"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid timezone: {self.timezone!r}; install tzdata on Windows") from exc

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, values):
        if not isinstance(values, dict):
            raise ValueError("Configuration must be a JSON object")
        unknown = set(values) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown configuration keys: {sorted(unknown)}")
        return cls(**values)
