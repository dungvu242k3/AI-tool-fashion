"""Validated HTTP policy; no retries are hidden inside the underlying session."""
import math
import os
from dataclasses import dataclass, fields
from typing import ClassVar, FrozenSet, Tuple


@dataclass(frozen=True)
class HTTPPolicy:
    connect_timeout: float = 5.0
    read_timeout: float = 20.0
    max_attempts: int = 3
    backoff_base: float = 0.75
    backoff_cap: float = 8.0
    retry_wait_budget: float = 30.0
    max_redirects: int = 3
    max_response_bytes: int = 4 * 1024 * 1024

    RETRY_STATUSES: ClassVar[FrozenSet[int]] = frozenset({429, 500, 502, 503, 504})

    def __post_init__(self) -> None:
        for name in ("connect_timeout", "read_timeout", "backoff_base", "backoff_cap", "retry_wait_budget"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.connect_timeout > 120 or self.read_timeout > 300 or self.retry_wait_budget > 300:
            raise ValueError("HTTP timeout/retry budget exceeds production limit")
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int) or not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be an integer between 1 and 10")
        if isinstance(self.max_redirects, bool) or not isinstance(self.max_redirects, int) or not 0 <= self.max_redirects <= 10:
            raise ValueError("max_redirects must be an integer between 0 and 10")
        if self.backoff_base > self.backoff_cap:
            raise ValueError("backoff_base must not exceed backoff_cap")
        if type(self.max_response_bytes) is not int or not 1024 <= self.max_response_bytes <= 16 * 1024 * 1024:
            raise ValueError("max_response_bytes must be between 1024 and 16777216")

    @property
    def timeout(self) -> Tuple[float, float]:
        return self.connect_timeout, self.read_timeout

    @classmethod
    def from_env(cls) -> "HTTPPolicy":
        values = {}
        integer_fields = {"max_attempts", "max_redirects", "max_response_bytes"}
        for item in fields(cls):
            key = f"TREND_HTTP_{item.name.upper()}"
            raw = os.getenv(key)
            if raw is not None:
                try:
                    values[item.name] = int(raw) if item.name in integer_fields else float(raw)
                except ValueError as exc:
                    raise ValueError(f"Invalid setting: {key}") from exc
        return cls(**values)
