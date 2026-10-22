"""Pure calculations on complete, measured points; never interpolate missing data."""
from datetime import datetime
from math import isfinite
from statistics import fmean, pstdev
from typing import Sequence

from src.models.trends import TrendMetrics, TrendPoint


def format_trend_signal(metrics: TrendMetrics) -> str:
    """Only publish a textual signal that can be reproduced from measured metrics."""
    growth = f"{metrics.growth_percent:.2f}%" if metrics.growth_percent is not None else "chưa xác định (kỳ trước bằng 0)"
    return f"Interest cuối kỳ hoàn tất: {metrics.latest_value:g}/100; thay đổi trung bình hai cửa sổ: {growth}."


def calculate_trend_metrics(
    points: Sequence[TrendPoint], *, window_points: int = 7,
    rising_threshold_percent: float = 15, declining_threshold_percent: float = -15,
) -> TrendMetrics | None:
    if not 2 <= window_points <= 365 or not (
        isfinite(rising_threshold_percent) and rising_threshold_percent > 0
        and isfinite(declining_threshold_percent) and -100 <= declining_threshold_percent < 0
    ):
        raise ValueError("Invalid trend calculation policy")
    valid = []
    for point in points:
        moment = datetime.fromisoformat(point.timestamp)
        if moment.utcoffset() is None:
            raise ValueError("Trend timestamps require an explicit timezone")
        if (
            point.is_partial is False and point.value is not None
            and not isinstance(point.value, bool) and isfinite(point.value) and 0 <= point.value <= 100
        ):
            valid.append((moment, point))
    valid.sort(key=lambda item: item[0])
    if len({moment for moment, _ in valid}) != len(valid):
        raise ValueError("Duplicate trend timestamps")
    if len(valid) < 4:
        return None
    width = min(window_points, len(valid) // 2)
    sample = valid[-2 * width:]
    previous, recent = sample[:width], sample[width:]
    previous_mean = fmean(point.value for _, point in previous)
    recent_mean = fmean(point.value for _, point in recent)
    growth = (recent_mean - previous_mean) / previous_mean * 100 if previous_mean else (0.0 if recent_mean == 0 else None)
    trend, reason = "unavailable", "zero_baseline"
    if growth is not None:
        trend = "rising" if growth >= rising_threshold_percent else (
            "declining" if growth <= declining_threshold_percent else "stable"
        )
        reason = "threshold_comparison"
    origin = sample[0][0]
    days = [(moment - origin).total_seconds() / 86400 for moment, _ in sample]
    values = [point.value for _, point in sample]
    mean_x, mean_y = fmean(days), fmean(values)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(days, values)) / sum((x - mean_x) ** 2 for x in days)
    return TrendMetrics(
        latest_value=recent[-1][1].value,
        recent_mean=recent_mean, previous_mean=previous_mean, growth_percent=growth,
        slope=slope, volatility=pstdev(values), trend=trend,
        valid_points=len(valid), excluded_points=len(points) - len(valid), window_points_used=width,
        previous_start=previous[0][1].timestamp, previous_end=previous[-1][1].timestamp,
        recent_start=recent[0][1].timestamp, recent_end=recent[-1][1].timestamp,
        rising_threshold_percent=rising_threshold_percent, declining_threshold_percent=declining_threshold_percent,
        classification_reason=reason,
    )
