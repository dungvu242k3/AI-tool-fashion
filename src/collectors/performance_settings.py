"""Bounded collection policy. Environment settings never supply market evidence."""
import math
import os
from dataclasses import dataclass, fields

SOURCES = ("google_trends", "amazon", "reddit")


@dataclass(frozen=True, slots=True)
class PerformanceSettings:
    max_workers: int = 3
    google_trends_concurrency: int = 1
    amazon_concurrency: int = 1
    reddit_concurrency: int = 1
    slot_wait_seconds: float = 30.0
    google_trends_cache_ttl: float = 300.0
    amazon_cache_ttl: float = 300.0
    reddit_cache_ttl: float = 120.0
    cache_max_entries: int = 64
    cache_max_bytes: int = 32 * 1024 * 1024
    snapshot_max_bytes: int = 8 * 1024 * 1024
    snapshot_run_max_bytes: int = 64 * 1024 * 1024

    def __post_init__(self):
        integer_bounds = {
            "max_workers": (1, 3), **{f"{source}_concurrency": (1, 4) for source in SOURCES},
            "cache_max_entries": (1, 512), "cache_max_bytes": (1024, 128 * 1024 * 1024),
            "snapshot_max_bytes": (1024, 32 * 1024 * 1024),
            "snapshot_run_max_bytes": (1024, 256 * 1024 * 1024),
        }
        for name, (minimum, maximum) in integer_bounds.items():
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
        for name in ("slot_wait_seconds", *(f"{source}_cache_ttl" for source in SOURCES)):
            value = getattr(self, name)
            minimum, maximum = (0.01, 300) if name == "slot_wait_seconds" else (0, 3600)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not minimum <= value <= maximum):
                raise ValueError(f"Invalid {name}")
        if self.snapshot_max_bytes > self.snapshot_run_max_bytes:
            raise ValueError("Per-snapshot limit exceeds run limit")

    @classmethod
    def from_env(cls):
        defaults = cls()
        values = {}
        for item in fields(cls):
            key = f"TREND_PERF_{item.name.upper()}"
            raw = os.getenv(key)
            if raw is not None:
                try:
                    values[item.name] = int(raw) if type(getattr(defaults, item.name)) is int else float(raw)
                except ValueError as exc:
                    raise ValueError(f"Invalid setting: {key}") from exc
        return cls(**values)
