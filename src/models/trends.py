"""Observed time points and reproducible, versioned trend calculations."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TrendPoint:
    timestamp: str
    value: Optional[float]
    is_partial: Optional[bool]


@dataclass(frozen=True)
class TrendMetrics:
    latest_value: float
    recent_mean: float
    previous_mean: float
    growth_percent: Optional[float]
    slope: float  # Interest-index points per elapsed day, not percentage growth.
    volatility: float  # Population standard deviation, in interest-index points.
    trend: str
    valid_points: int
    excluded_points: int
    window_points_used: int
    previous_start: str
    previous_end: str
    recent_start: str
    recent_end: str
    rising_threshold_percent: float
    declining_threshold_percent: float
    classification_reason: str
    method: str = "adjacent_equal_windows_ols_per_day_v1"
