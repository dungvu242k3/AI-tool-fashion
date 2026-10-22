"""Validate observed series and independently reproduce the published trend metrics."""
from urllib.parse import parse_qs, urlsplit

from src.collectors.evidence_validation import aware_timestamp, finite_number, valid_text
from src.collectors.trends_settings import TrendsSettings
from src.models.trends import TrendMetrics, TrendPoint
from src.processors.trend_metrics import calculate_trend_metrics, format_trend_signal


def valid_keyword_signal(record, traces: dict) -> bool:
    if (
        not valid_text(record.keyword, 200) or record.source != "Google Trends"
        or not valid_text(record.signal_summary, 2000, empty=True, multiline=True)
        or not isinstance(record.time_series, list) or not 4 <= len(record.time_series) <= 10_000
        or not isinstance(record.metrics, TrendMetrics) or not finite_number(record.score, 0, 100)
        or not isinstance(record.trend, str) or record.trend not in {"rising", "stable", "declining", "unavailable"}
        or not isinstance(record.comparison_keywords, list) or not 1 <= len(record.comparison_keywords) <= 5
        or any(not valid_text(value, 200) for value in record.comparison_keywords)
        or len(set(record.comparison_keywords)) != len(record.comparison_keywords)
        or record.keyword not in record.comparison_keywords
    ):
        return False
    for values in (record.related_queries, record.suggestions):
        if not isinstance(values, list) or len(values) > 10 or any(not valid_text(value, 200) for value in values):
            return False
    settings = TrendsSettings(geo=record.geo, timeframe=record.timeframe)
    primary = traces[record.provenance.request_id]
    if primary.operation != "interest" or primary.method != "GET":
        return False
    query = record.provenance.query
    if (query.get("keyword") != record.keyword or query.get("keywords") != record.comparison_keywords
            or query.get("geo") != settings.geo or query.get("timeframe") != settings.timeframe
            or primary.query.get("keywords") != record.comparison_keywords or primary.query.get("geo") != record.geo
            or primary.query.get("timeframe") != record.timeframe):
        return False
    parts = urlsplit(record.source_url)
    params = parse_qs(parts.query, keep_blank_values=True)
    if (parts.scheme != "https" or parts.netloc != "trends.google.com" or parts.path != "/trends/explore"
            or parts.fragment or params != {"q": [record.keyword], "date": [record.timeframe], "geo": [record.geo]}):
        return False
    primary_parts = urlsplit(primary.url)
    if primary_parts.path != "/trends/api/widgetdata/multiline":
        return False
    dependencies = [traces[key] for key in record.provenance.request_ids]
    if record.related_queries and not any(trace.operation == "related_queries" and trace.query.get("related_keyword") == record.keyword for trace in dependencies):
        return False
    if record.suggestions and not any(trace.operation == "suggestions" and trace.query.get("keyword") == record.keyword for trace in dependencies):
        return False
    previous = None
    for point in record.time_series:
        if not isinstance(point, TrendPoint):
            return False
        moment = aware_timestamp(point.timestamp)
        if (moment is None or moment > aware_timestamp(primary.completed_at) or (previous is not None and moment <= previous)
                or (point.value is not None and not finite_number(point.value, 0, 100))
                or (point.is_partial is not None and not isinstance(point.is_partial, bool))):
            return False
        previous = moment
    metric = record.metrics
    if (isinstance(metric.window_points_used, bool) or not isinstance(metric.window_points_used, int)
            or not 2 <= metric.window_points_used <= 365
            or not finite_number(metric.rising_threshold_percent, 0.000001, 10000)
            or not finite_number(metric.declining_threshold_percent, -100, -0.000001)):
        return False
    for name in ("latest_value", "recent_mean", "previous_mean", "slope", "volatility"):
        if not finite_number(getattr(metric, name), -1e20, 1e20):
            return False
    if metric.growth_percent is not None and not finite_number(metric.growth_percent, -100, 1e20):
        return False
    if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000
           for value in (metric.valid_points, metric.excluded_points)):
        return False
    expected = calculate_trend_metrics(record.time_series, window_points=metric.window_points_used,
                                       rising_threshold_percent=metric.rising_threshold_percent,
                                       declining_threshold_percent=metric.declining_threshold_percent)
    return (expected is not None and expected == metric and record.score == expected.latest_value and record.trend == expected.trend
            and (not record.signal_summary or record.signal_summary == format_trend_signal(expected)))
