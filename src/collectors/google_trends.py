"""Collect measured series through a replaceable provider and a bounded live cache."""
import hashlib
import json
import time
from dataclasses import asdict, replace
from urllib.parse import urlencode

from src.collectors.base import BaseCollector
from src.collectors.context import CollectionContext
from src.collectors.errors import CollectionError
from src.collectors.trends_cache import SHARED_TRENDS_CACHE, TrendsCache, TrendsSnapshot
from src.collectors.trends_provider import PytrendsProvider, TrendsProvider
from src.collectors.trends_settings import TrendsSettings, validate_keywords
from src.models.schemas import KeywordSignal
from src.processors.trend_metrics import calculate_trend_metrics, format_trend_signal


class GoogleTrendsCollector(BaseCollector[KeywordSignal]):
    def __init__(self, http_client=None, *, provider: TrendsProvider | None = None,
                 settings: TrendsSettings | None = None, cache: TrendsCache | None = None, sleep=time.sleep):
        # Validate policy before creating a session, so configuration failures cannot leak it.
        self.settings = settings if settings is not None else TrendsSettings.from_env()
        super().__init__("google_trends", http_client)
        self.provider = provider if provider is not None else PytrendsProvider()
        self.cache = cache if cache is not None else SHARED_TRENDS_CACHE
        self._sleep = sleep

    def _collect(self, niche: dict, context: CollectionContext[KeywordSignal]) -> None:
        try:
            raw_keywords = niche.get("seed_keywords")
            keywords = validate_keywords([niche["name"].lower()] if raw_keywords is None else raw_keywords)
            settings = replace(
                self.settings, geo=niche.get("geo", self.settings.geo),
                timeframe=niche.get("timeframe", self.settings.timeframe),
            )
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise CollectionError("invalid_input", "Keyword, geo hoặc timeframe Google Trends không hợp lệ.") from exc
        fetched_batch = False
        for offset in range(0, len(keywords), 5):
            batch = keywords[offset:offset + 5]
            key = self._cache_key(batch, settings)
            snapshot = self.cache.get(key) if settings.cache_ttl_seconds > 0 else None
            if snapshot is not None:
                self._reuse_snapshot(snapshot, context)
                continue
            if fetched_batch and settings.batch_delay_seconds:
                self._sleep(settings.batch_delay_seconds)
            fetched_batch = True
            warning_start, record_start = len(context.warnings), len(context.records)
            with context.capture("interest"):
                observations = self.provider.fetch(batch, settings, context)
                seen = set()
                for observation in observations:
                    if observation.keyword not in batch or observation.keyword in seen:
                        raise CollectionError("invalid_provider_result", "Provider trả keyword ngoài batch hoặc trùng lặp.")
                    seen.add(observation.keyword)
                    metrics = calculate_trend_metrics(
                        observation.points, window_points=settings.window_points,
                        rising_threshold_percent=settings.rising_threshold_percent,
                        declining_threshold_percent=settings.declining_threshold_percent,
                    )
                    if metrics is None:
                        context.warn(
                            "insufficient_series", "Không đủ bốn điểm đo hoàn tất để so sánh hai cửa sổ.",
                            request_id=observation.response.request_id, operation="interest",
                        )
                        continue
                    signal = KeywordSignal(
                        keyword=observation.keyword, trend=metrics.trend, score=metrics.latest_value,
                        signal_summary=format_trend_signal(metrics),
                        source="Google Trends", source_url="https://trends.google.com/trends/explore?" + urlencode({
                            "q": observation.keyword, "date": settings.timeframe, "geo": settings.geo,
                        }),
                        related_queries=list(observation.related_queries), suggestions=list(observation.suggestions),
                        time_series=list(observation.points), metrics=metrics,
                        geo=settings.geo, timeframe=settings.timeframe, comparison_keywords=list(batch),
                    )
                    if any(point.value is None or point.is_partial is None for point in observation.points):
                        context.warn("incomplete_series", "Time series có điểm thiếu số đo/trạng thái; không nội suy.", request_id=observation.response.request_id)
                    if metrics.trend == "unavailable":
                        context.warn("zero_baseline", "Kỳ trước bằng 0; không xác nhận tỷ lệ tăng trưởng.", request_id=observation.response.request_id)
                    context.add_records(
                        [signal], observation.response,
                        {"keywords": batch, "keyword": observation.keyword, "geo": settings.geo, "timeframe": settings.timeframe},
                        dependencies=observation.request_ids,
                    )
                if len(seen) != len(batch):
                    context.warn("missing_series", "Provider không trả đủ keyword đã truy vấn.", operation="interest")
            records = context.records[record_start:]
            if len(records) == len(batch) and len(context.warnings) == warning_start:
                needed = {request_id for record in records for request_id in record.provenance.request_ids}
                operations = {trace.operation_id for trace in context.request_metadata if trace.request_id in needed}
                traces = tuple(trace for trace in context.request_metadata if trace.operation_id in operations)
                self.cache.put(key, TrendsSnapshot(tuple(records), traces), settings.cache_ttl_seconds)
            if any(
                warning.operation != "suggestions" and warning.code in {"http_429", "source_cooldown", "retry_after_deferred"}
                for warning in context.warnings[warning_start:]
            ):
                break

    def _cache_key(self, batch, settings) -> str:
        payload = {"provider": self.provider.cache_namespace, "keywords": batch, "settings": asdict(settings)}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    @staticmethod
    def _reuse_snapshot(snapshot, context):
        existing = {trace.request_id for trace in context.request_metadata}
        context.request_metadata.extend(
            replace(trace, cache_reused=True) for trace in snapshot.requests if trace.request_id not in existing
        )
        context.records.extend(
            replace(record, provenance=replace(record.provenance, from_cache=True)) for record in snapshot.records
        )
