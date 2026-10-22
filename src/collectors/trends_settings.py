"""Bounded Google Trends inputs and tunable analysis policy; no user-supplied URLs."""
import math
import os
import re
from dataclasses import dataclass, fields
from datetime import date

from src.config import GOOGLE_TRENDS_GEO, GOOGLE_TRENDS_TIMEFRAME


@dataclass(frozen=True)
class TrendsSettings:
    geo: str = GOOGLE_TRENDS_GEO
    timeframe: str = GOOGLE_TRENDS_TIMEFRAME
    window_points: int = 7
    rising_threshold_percent: float = 15.0
    declining_threshold_percent: float = -15.0
    cache_ttl_seconds: float = 300.0
    batch_delay_seconds: float = 2.0
    suggestions_enabled: bool = True

    def __post_init__(self):
        if not isinstance(self.geo, str) or not re.fullmatch(r"(?:[A-Z]{2}(?:-[A-Z0-9]{1,3})?)?", self.geo):
            raise ValueError("Invalid Google Trends geo")
        if not isinstance(self.timeframe, str) or not self._valid_timeframe(self.timeframe):
            raise ValueError("Invalid Google Trends timeframe")
        if isinstance(self.window_points, bool) or not isinstance(self.window_points, int) or not 2 <= self.window_points <= 365:
            raise ValueError("window_points must be between 2 and 365")
        limits = {
            "rising_threshold_percent": (0, 10000), "declining_threshold_percent": (-100, 0),
            "cache_ttl_seconds": (0, 3600), "batch_delay_seconds": (0, 60),
        }
        for name, (low, high) in limits.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"Invalid Google Trends setting: {name}")
        if self.rising_threshold_percent <= 0 or self.declining_threshold_percent >= 0:
            raise ValueError("Trend thresholds must straddle zero")
        if not isinstance(self.suggestions_enabled, bool):
            raise ValueError("suggestions_enabled must be boolean")

    @staticmethod
    def _valid_timeframe(value: str) -> bool:
        if re.fullmatch(r"today (?:1|3|12)-m|today 5-y|now (?:1|4)-H|now (?:1|7)-d|all", value):
            return True
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{4}-\d{2}-\d{2}", value):
            return False
        try:
            start, end = (date.fromisoformat(item) for item in value.split())
            return date(2004, 1, 1) <= start <= end
        except ValueError:
            return False

    @classmethod
    def from_env(cls):
        values = {}
        for item in fields(cls):
            raw = os.getenv(f"TREND_GOOGLE_{item.name.upper()}")
            if raw is None:
                continue
            if item.name in {"geo", "timeframe"}:
                values[item.name] = raw
            elif item.name == "suggestions_enabled":
                if raw.lower() not in {"true", "false"}:
                    raise ValueError("TREND_GOOGLE_SUGGESTIONS_ENABLED must be true or false")
                values[item.name] = raw.lower() == "true"
            else:
                try:
                    values[item.name] = int(raw) if item.name == "window_points" else float(raw)
                except ValueError as exc:
                    raise ValueError(f"Invalid setting: TREND_GOOGLE_{item.name.upper()}") from exc
        return cls(**values)


def validate_keywords(value) -> list[str]:
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 50:
        raise ValueError("Google Trends requires between 1 and 50 keywords")
    keywords, seen = [], set()
    for keyword in value:
        if (
            not isinstance(keyword, str) or not keyword.strip() or len(keyword) > 200
            or any(ord(char) < 32 or ord(char) == 127 for char in keyword)
        ):
            raise ValueError("Invalid Google Trends keyword")
        keyword = keyword.strip()
        if keyword.casefold() not in seen:
            keywords.append(keyword)
            seen.add(keyword.casefold())
    return keywords
