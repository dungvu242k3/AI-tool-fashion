"""Replaceable provider interface; pytrends-specific parsing stays behind this boundary."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, Sequence

from src.collectors.context import CollectionContext
from src.collectors.errors import ResponseParseError
from src.collectors.google_trends_client import ObservedTrendReq
from src.collectors.http import HTTPResponse
from src.collectors.trends_settings import TrendsSettings
from src.models.trends import TrendPoint
from src.utils.helpers import optional_float


@dataclass(frozen=True)
class TrendObservation:
    keyword: str
    points: tuple[TrendPoint, ...]
    related_queries: tuple[str, ...]
    suggestions: tuple[str, ...]
    response: HTTPResponse
    request_ids: tuple[str, ...]


class TrendsProvider(Protocol):
    cache_namespace: str

    def fetch(
        self, keywords: Sequence[str], settings: TrendsSettings, context: CollectionContext,
    ) -> list[TrendObservation]: ...


def _query_strings(values, limit=10) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        value.strip() for value in values
        if isinstance(value, str) and value.strip() and len(value) <= 200
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    ))[:limit]


class PytrendsProvider:
    cache_namespace = "google-trends:pytrends-4.9.2:timeline-v1"
    SUGGESTIONS_URL = "https://suggestqueries.google.com/complete/search"

    def __init__(self):
        self._client = None
        self._context = None

    def fetch(self, keywords, settings, context):
        if not 1 <= len(keywords) <= 5:
            raise ValueError("Google Trends supports at most five keywords per batch")
        query = {"keywords": list(keywords), "geo": settings.geo, "timeframe": settings.timeframe}
        if self._context is not context:
            self._client = ObservedTrendReq(context, query)
            self._context = context
        else:
            self._client.begin_batch(query)
        client = self._client
        client.build_payload(list(keywords), cat=0, timeframe=settings.timeframe, geo=settings.geo)
        payload = client.interest_payload()
        primary = client.responses["interest"][-1]
        series = self._parse_timeline(payload, keywords, primary)
        related = {}
        with context.capture("related_queries"):
            related = client.related_queries() or {}
        observations = []
        for keyword in keywords:
            queries = []
            for kind in ("rising", "top"):
                frame = (related.get(keyword) or {}).get(kind)
                if frame is not None and "query" in frame.columns:
                    queries.extend(frame["query"].head(5).tolist())
            related_queries = _query_strings(queries)
            dependencies = client.successful_request_ids(keyword, include_related=bool(related_queries))
            suggestions = ()
            if settings.suggestions_enabled:
                with context.capture("suggestions"):
                    response = context.fetch(
                        "GET", self.SUGGESTIONS_URL, operation="suggestions",
                        query={"keyword": keyword, "language": "en", "kind": "autocomplete_not_trend"},
                        params={"client": "firefox", "hl": "en", "q": keyword},
                        headers={"Accept": "application/json"},
                    )
                    if len(response.text) > 100_000:
                        raise ResponseParseError("payload_too_large", "Google Suggest trả nội dung vượt giới hạn.", request_id=response.request_id)
                    result = response.json()
                    if not isinstance(result, list) or len(result) < 2 or result[0] != keyword or not isinstance(result[1], list):
                        raise ResponseParseError("invalid_suggestions", "Google Suggest trả cấu trúc không hợp lệ.", request_id=response.request_id)
                    suggestions = _query_strings(result[1][:50])
                    if suggestions:
                        dependencies.append(response.request_id)
            observations.append(TrendObservation(
                keyword, series[keyword], related_queries, suggestions, primary, tuple(dependencies),
            ))
        return observations

    @staticmethod
    def _parse_timeline(payload, keywords, response):
        data = payload.get("default")
        rows = data.get("timelineData") if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) > 10_000:
            raise ResponseParseError("invalid_series", "Google Trends trả time series không hợp lệ hoặc vượt giới hạn.", request_id=response.request_id)
        result = {keyword: [] for keyword in keywords}
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ResponseParseError("invalid_series", "Time series có điểm đo không hợp lệ.", request_id=response.request_id)
            epoch = optional_float(row.get("time"))
            try:
                if epoch is None:
                    raise ValueError("Missing timestamp")
                timestamp = datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")
            except (ValueError, OverflowError, OSError) as exc:
                raise ResponseParseError("invalid_series", "Time series có timestamp không hợp lệ.", request_id=response.request_id) from exc
            if timestamp in seen:
                raise ResponseParseError("invalid_series", "Time series có timestamp trùng.", request_id=response.request_id)
            seen.add(timestamp)
            values = row.get("value")
            for index, keyword in enumerate(keywords):
                value = optional_float(values[index]) if isinstance(values, list) and index < len(values) else None
                if value is not None and not 0 <= value <= 100:
                    value = None
                # Match pytrends' documented-by-code decoder: omitted false flags
                # are complete; explicit null/malformed flags remain unknown.
                partial = row.get("isPartial", False)
                if isinstance(partial, list):
                    partial = partial[index] if index < len(partial) else None
                result[keyword].append(TrendPoint(timestamp, value, partial if isinstance(partial, bool) else None))
        return {keyword: tuple(sorted(points, key=lambda point: point.timestamp)) for keyword, points in result.items()}
