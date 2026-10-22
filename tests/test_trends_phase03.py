"""Phase-3-only tests. Synthetic response fixtures never enter production reports."""
import json
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from statistics import pstdev
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.http_policy import HTTPPolicy
from src.collectors.trends_cache import TrendsCache, TrendsSnapshot
from src.collectors.trends_settings import TrendsSettings
from src.collectors.validation import validate_collection_result
from src.models.schemas import NicheData
from src.models.trends import TrendPoint
from src.pipeline import execute_pipeline
from src.processors.data_processor import DataProcessor
from src.processors.source_health import aggregate_source_health
from src.processors.trend_metrics import calculate_trend_metrics
from src.reporters.evidence_renderer import EvidenceRenderer


def points(values, *, step_days=1):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [TrendPoint((start + timedelta(days=index * step_days)).isoformat(), value, False) for index, value in enumerate(values)]


def settings(**kwargs):
    return TrendsSettings(**{"suggestions_enabled": False, "batch_delay_seconds": 0, **kwargs})


def collector(http, **kwargs):
    return GoogleTrendsCollector(http.client, **{"settings": settings(), "cache": TrendsCache(), **kwargs})


def test_metrics_have_reproducible_units_and_no_score_boost():
    series = points([10, 20, 30, 40], step_days=2)
    result = calculate_trend_metrics(series, window_points=2)
    assert result.previous_mean == 15
    assert result.recent_mean == 35
    assert result.growth_percent == pytest.approx(400 / 3)
    assert result.slope == pytest.approx(5)  # 10 interest points every two days.
    assert result.volatility == pytest.approx(pstdev([10, 20, 30, 40]))
    assert result.latest_value == 40
    assert result.window_points_used == 2
    assert result.previous_end == series[1].timestamp
    assert result.recent_start == series[2].timestamp


@pytest.mark.parametrize(("values", "growth", "trend"), [
    ([0, 0, 0, 0], 0, "stable"),
    ([0, 0, 5, 10], None, "unavailable"),
    ([20, 20, 10, 10], -50, "declining"),
    ([20, 20, 23, 23], 15, "rising"),
    ([20, 20, 17, 17], -15, "declining"),
    ([20, 20, 21, 21], 5, "stable"),
])
def test_classification_boundaries_and_zero_baseline(values, growth, trend):
    result = calculate_trend_metrics(points(values))
    assert result.growth_percent == growth
    assert result.trend == trend
    json.dumps(asdict(result), allow_nan=False)


def test_thresholds_and_equal_adjacent_windows_are_configurable():
    result = calculate_trend_metrics(points([99, 10, 10, 12, 12]), window_points=2, rising_threshold_percent=25)
    assert result.previous_mean == 10
    assert result.recent_mean == 12
    assert result.growth_percent == 20
    assert result.trend == "stable"


def test_missing_partial_and_unknown_completion_points_are_not_imputed():
    series = points([10, 20, 30, 40, None, 100, 99])
    series[-2] = replace(series[-2], is_partial=True)
    series[-1] = replace(series[-1], is_partial=None)
    result = calculate_trend_metrics(series)
    assert result.latest_value == 40
    assert result.excluded_points == 3
    assert result.valid_points == 4
    assert calculate_trend_metrics(series[2:]) is None
    with pytest.raises(ValueError, match="Duplicate"):
        calculate_trend_metrics([*series[:4], series[0]])


def test_collector_retains_full_series_and_separates_autocomplete(http_factory, response_factory, trends_script):
    script = trends_script([10, 20, 30, 40, 99], partials=[False] * 4 + [True])
    script += [response_factory(payload=["query one", ["<img src=x onerror=alert(1)>", "related fixture", "related fixture"]])]
    http = http_factory(script)
    result = collector(http, settings=settings(suggestions_enabled=True)).collect({"name": "fixture", "seed_keywords": ["query one"]})
    assert result.status == "success"
    record = result.records[0]
    assert len(record.time_series) == 5
    assert record.time_series[-1].is_partial is True
    assert record.time_series[-1].value == 99
    assert record.score == record.metrics.latest_value == 40
    assert record.related_queries == []
    assert record.suggestions == ["<img src=x onerror=alert(1)>", "related fixture"]
    assert result.request_metadata[-1].operation == "suggestions"
    assert result.request_metadata[-1].request_id in record.provenance.request_ids
    assert validate_collection_result("google_trends", result).status == "success"
    query = parse_qs(urlsplit(record.source_url).query, keep_blank_values=True)
    assert query == {"q": ["query one"], "date": [settings().timeframe], "geo": [""]}
    processed = DataProcessor()._process_keywords(result.records)
    assert processed[0].score == 40
    assert processed[0].to_dict()["time_series"][-1]["value"] == 99
    text = EvidenceRenderer.keywords(NicheData("fixture", "", keywords=processed))
    assert "Google Suggest" in text and "không phải tín hiệu tăng trưởng" in text
    assert "<img" not in text
    assert "volatility:" in text


def test_autocomplete_failure_keeps_interest_but_is_not_cached(http_factory, response_factory, trends_script):
    http = http_factory(trends_script() + [response_factory(403)])
    cache = TrendsCache()
    instance = collector(http, settings=settings(suggestions_enabled=True), cache=cache)
    niche = {"name": "fixture", "seed_keywords": ["query one"]}
    result = instance.collect(niche)
    assert result.status == "partial"
    assert result.records[0].metrics is not None
    assert result.records[0].suggestions == []
    assert cache.get(instance._cache_key(["query one"], instance.settings)) is None


def test_batches_are_deterministic_and_never_exceed_five(http_factory, response_factory):
    def batch_script(keywords):
        return [
            response_factory(text=")]}'\n" + json.dumps({"widgets": [{"id": "TIMESERIES", "token": "private-fixture-token", "request": {}}]}), headers={"Content-Type": "application/json"}),
            response_factory(text=")]}'\n" + json.dumps({"default": {"timelineData": [
                {"time": str(1761000000 + index * 86400), "value": [10 + index] * len(keywords), "isPartial": False}
                for index in range(4)
            ]}}), headers={"Content-Type": "application/json"}),
        ]
    keywords = [f"fixture {index}" for index in range(6)]
    http = http_factory([response_factory(), *batch_script(keywords[:5]), *batch_script(keywords[5:])])
    sleeps = []
    result = collector(http, settings=settings(batch_delay_seconds=1), sleep=sleeps.append).collect({"name": "fixture", "seed_keywords": keywords})
    assert result.status == "success"
    assert [record.keyword for record in result.records] == keywords
    assert [len(record.comparison_keywords) for record in result.records] == [5] * 5 + [1]
    assert [trace.query["keywords"] for trace in result.request_metadata if trace.operation == "explore"] == [keywords[:5], keywords[5:]]
    assert sleeps == [1]
    assert "private-fixture-token" not in json.dumps(result.status_dict(include_requests=True))


def test_exhausted_429_stops_remaining_batches_without_fabrication(http_factory, response_factory):
    http = http_factory([response_factory(429) for _ in range(3)], policy=HTTPPolicy(max_attempts=3))
    result = collector(http).collect({"name": "fixture", "seed_keywords": [f"fixture {i}" for i in range(6)]})
    assert result.status == "failed"
    assert result.records == []
    assert result.warnings[0].code == "http_429"
    assert len(result.request_metadata) == http.session.request.call_count == 3


@pytest.mark.parametrize("niche", [
    {"seed_keywords": "not a list"}, {"seed_keywords": ["x\nheader"]}, {"seed_keywords": ["x" * 201]},
    {"seed_keywords": ["x"] * 51}, {"geo": "http://127.0.0.1/"}, {"timeframe": "javascript:alert(1)"},
    {"timeframe": "2026-02-31 2026-03-01"},
])
def test_invalid_inputs_do_not_create_requests(niche, http_factory):
    http = http_factory([])
    result = collector(http).collect({"name": "fixture", **niche})
    assert result.status == "failed"
    assert result.warnings[0].code == "invalid_input"
    http.session.request.assert_not_called()


@pytest.mark.parametrize("changes", [
    {"window_points": 1}, {"cache_ttl_seconds": float("nan")}, {"cache_ttl_seconds": 3601},
    {"rising_threshold_percent": 0}, {"declining_threshold_percent": 1}, {"suggestions_enabled": "false"},
])
def test_invalid_settings_fail_before_network(changes):
    with pytest.raises(ValueError):
        settings(**changes)


def test_environment_configuration_is_validated(monkeypatch):
    monkeypatch.setenv("TREND_GOOGLE_GEO", "US")
    monkeypatch.setenv("TREND_GOOGLE_WINDOW_POINTS", "4")
    monkeypatch.setenv("TREND_GOOGLE_SUGGESTIONS_ENABLED", "false")
    result = TrendsSettings.from_env()
    assert result.geo == "US" and result.window_points == 4 and result.suggestions_enabled is False
    monkeypatch.setenv("TREND_GOOGLE_SUGGESTIONS_ENABLED", "yes")
    with pytest.raises(ValueError):
        TrendsSettings.from_env()


def test_cache_preserves_provenance_without_inventing_requests(http_factory, trends_script):
    http = http_factory(trends_script())
    instance = collector(http)
    niche = {"name": "fixture", "seed_keywords": ["query one"]}
    first, second = instance.collect(niche), instance.collect(niche)
    assert first.status == second.status == "success"
    assert first.records[0].provenance.retrieved_at == second.records[0].provenance.retrieved_at
    assert second.records[0].provenance.from_cache is True
    assert second.records[0].provenance.request_id == first.records[0].provenance.request_id
    assert all(trace.cache_reused for trace in second.request_metadata)
    assert second.status_dict()["request_count"] == 0
    assert second.status_dict()["live_attempted"] is False
    assert second.status_dict()["cached_record_count"] == 1
    assert http.session.request.call_count == 3
    assert validate_collection_result("google_trends", second).status == "success"
    health = aggregate_source_health({"one": {"google_trends": first}, "two": {"google_trends": second}})["google_trends"]
    assert health["request_count"] == 3 and health["cached_request_count"] == 3 and health["cached_record_count"] == 1


def test_cache_expires_and_does_not_serve_stale_data_on_failure(http_factory, response_factory, trends_script):
    clock = SimpleNamespace(now=0)
    cache = TrendsCache(clock=lambda: clock.now)
    http = http_factory(trends_script() + [response_factory(429)])
    instance = collector(http, settings=settings(cache_ttl_seconds=2), cache=cache)
    niche = {"name": "fixture", "seed_keywords": ["query one"]}
    assert instance.collect(niche).status == "success"
    clock.now = 2
    result = instance.collect(niche)
    assert result.status == "failed" and result.records == []
    assert len(result.request_metadata) == 1 and result.request_metadata[0].status_code == 429


def test_cache_is_bounded_lru_and_defensively_copied(http_factory, trends_script):
    http = http_factory(trends_script())
    result = collector(http).collect({"name": "fixture", "seed_keywords": ["query one"]})
    snapshot = TrendsSnapshot(tuple(result.records), tuple(result.request_metadata))
    cache = TrendsCache(max_entries=2)
    assert cache.put("one", snapshot, 60)
    cache.put("two", snapshot, 60)
    cached = cache.get("one")
    cached.records[0].time_series.clear()
    assert cache.get("one").records[0].time_series
    cache.put("three", snapshot, 60)
    assert cache.get("two") is None
    assert cache.get("one") is not None
    assert not TrendsCache(max_bytes=1).put("large", snapshot, 60)


def test_pipeline_cache_reuse_does_not_overwrite_fresh_attempts(tmp_path, http_factory, trends_script):
    from src.models.collection import CollectionResult
    http = http_factory(trends_script())
    trends = collector(http)
    unavailable = lambda source: SimpleNamespace(collect=lambda niche: CollectionResult.from_records(source, []))
    result = execute_pipeline(
        fast_mode=True, output_dir=str(tmp_path),
        niche_list=[{"name": "one", "seed_keywords": ["query one"]}, {"name": "two", "seed_keywords": ["query one"]}],
        collectors={"google_trends": trends, "amazon": unavailable("amazon"), "reddit": unavailable("reddit")},
    )
    assert len(result["request_metadata"]) == 3
    assert all(not trace["cache_reused"] for trace in result["request_metadata"].values())
    assert result["niches"]["two"]["keywords"][0]["provenance"]["from_cache"] is True
    assert result["source_health"]["google_trends"]["request_count"] == 3
    assert "Dùng lại dữ liệu live từ cache" in result["markdown_content"]


@pytest.mark.parametrize("payload", [
    {"default": {"timelineData": "invalid"}},
    {"default": {"timelineData": [{"time": "invalid", "value": [10], "isPartial": False}]}},
    {"default": {"timelineData": [{"time": "1761000000", "value": [10], "isPartial": False}] * 4}},
])
def test_invalid_timeline_is_not_retried_or_cached(payload, http_factory, response_factory, trends_script):
    script = trends_script()
    script[-1] = response_factory(text=")]}'\n" + json.dumps(payload), headers={"Content-Type": "application/json"})
    http = http_factory(script, policy=HTTPPolicy(max_attempts=3))
    result = collector(http).collect({"name": "fixture", "seed_keywords": ["query one"]})
    assert result.status == "failed" and result.records == []
    assert result.warnings[0].code == "invalid_series"
    assert http.session.request.call_count == 3  # bootstrap + explore + interest, no parse retries.


def test_explicit_null_partial_flag_and_missing_values_remain_unknown(http_factory, response_factory, trends_script):
    script = trends_script()
    rows = [{"time": str(1761000000 + index * 86400), "value": [10 + index], "isPartial": False} for index in range(6)]
    rows[-1]["isPartial"] = None
    rows[-2]["value"] = []
    script[-1] = response_factory(text=")]}'\n" + json.dumps({"default": {"timelineData": rows}}), headers={"Content-Type": "application/json"})
    http = http_factory(script)
    result = collector(http).collect({"name": "fixture", "seed_keywords": ["query one"]})
    assert result.status == "partial"
    record = result.records[0]
    assert record.time_series[-1].is_partial is None
    assert record.time_series[-2].value is None
    assert record.metrics.excluded_points == 2
    assert record.score == 13


def test_later_batch_cannot_reuse_a_stale_timeseries_widget(http_factory, response_factory):
    # A valid first batch is followed by an explore response without TIMESERIES.
    script = [response_factory(), response_factory(text=")]}'\n" + json.dumps({"widgets": [
        {"id": "TIMESERIES", "token": "private-token", "request": {}},
    ]}), headers={"Content-Type": "application/json"}),
        response_factory(text=")]}'\n" + json.dumps({"default": {"timelineData": [
            {"time": str(1761000000 + index * 86400), "value": [10] * 5, "isPartial": False} for index in range(4)
        ]}}), headers={"Content-Type": "application/json"}),
        response_factory(text=")]}'\n" + json.dumps({"widgets": []}), headers={"Content-Type": "application/json"}),
    ]
    http = http_factory(script)
    result = collector(http).collect({"name": "fixture", "seed_keywords": [f"fixture {i}" for i in range(6)]})
    assert result.status == "partial"
    assert len(result.records) == 5
    assert result.warnings[0].code == "missing_timeseries_widget"
    assert http.session.request.call_count == 4


def test_provider_can_be_replaced_without_rewriting_the_collector(http_factory, response_factory):
    from src.collectors.trends_provider import TrendObservation

    class AlternateProvider:
        cache_namespace = "fixture-provider:v1"

        def fetch(self, keywords, policy, context):
            response = context.fetch("GET", "https://example.test/series", operation="interest", query={"keywords": list(keywords)})
            return [TrendObservation(keyword, tuple(points(response.json()["values"])), (), (), response, ()) for keyword in keywords]

    http = http_factory([response_factory(payload={"values": [10, 20, 30, 40]})])
    result = collector(http, provider=AlternateProvider()).collect({"name": "fixture", "seed_keywords": ["one", "two"]})
    assert result.status == "success" and len(result.records) == 2
    assert result.records[0].metrics.recent_mean == 35
    assert validate_collection_result("google_trends", result).status == "success"
    assert http.session.request.call_count == 1


def test_cache_keys_include_provider_batch_order_geo_timeframe_and_analysis_policy(http_factory):
    instance = collector(http_factory([]))
    original = instance._cache_key(["one", "two"], instance.settings)
    others = [
        instance._cache_key(["two", "one"], instance.settings),
        instance._cache_key(["one", "two"], replace(instance.settings, geo="US")),
        instance._cache_key(["one", "two"], replace(instance.settings, timeframe="today 12-m")),
        instance._cache_key(["one", "two"], replace(instance.settings, rising_threshold_percent=25)),
    ]
    instance.provider = SimpleNamespace(cache_namespace="another-provider")
    others.append(instance._cache_key(["one", "two"], instance.settings))
    assert original not in others and len(set(others)) == len(others)


@pytest.mark.parametrize("value", [[], "", False])
def test_explicit_empty_or_invalid_keyword_input_is_not_silently_replaced(value, http_factory):
    http = http_factory([])
    result = collector(http).collect({"name": "fixture", "seed_keywords": value})
    assert result.warnings[0].code == "invalid_input"
    assert result.records == [] and result.request_metadata == []


def test_llm_receives_metrics_without_expanding_the_full_timeseries(http_factory, trends_script, monkeypatch, qualified_data_factory):
    from src.analyzers.llm_analyzer import LLMAnalyzer
    from src.models.schemas import ProductItem

    http = http_factory(trends_script())
    record = collector(http).collect({"name": "fixture", "seed_keywords": ["query one"]}).records[0]
    data = NicheData("fixture", "", keywords=[record, replace(record, keyword="query two")], products=[
        ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001"),
    ])
    prompts = []
    data = qualified_data_factory(data)
    analyzer = LLMAnalyzer()
    monkeypatch.setattr(analyzer, "_call_ollama", lambda prompt, **kwargs: prompts.append(prompt) or "")
    analyzer.analyze("fixture", data)
    assert len(prompts) == 1
    assert '"time_series":' not in prompts[0]
    context = json.loads(prompts[0])["evidence"][0]
    assert context["context"]["time_series_points"] == 4
    assert "trend.growth_percent" in context["metrics"]
    assert len(record.time_series) == 4


def test_nan_cache_ttl_cannot_create_a_nonexpiring_entry():
    with pytest.raises(ValueError):
        TrendsCache().put("fixture", TrendsSnapshot((), ()), float("nan"))


def test_bootstrap_uses_the_canonical_explore_path(http_factory, response_factory):
    http = http_factory([response_factory(429)])
    result = collector(http).collect({"name": "fixture", "seed_keywords": ["query one"]})
    assert result.status == "failed"
    assert http.session.request.call_args.args[1] == "https://trends.google.com/trends/explore"


def test_omitted_false_partial_flags_follow_pytrends_decoding_without_changing_values(http_factory, response_factory, trends_script):
    script = trends_script()
    script[-1] = response_factory(text=")]}'\n" + json.dumps({"default": {"timelineData": [
        {"time": str(1761000000 + index * 86400), "value": [value]} for index, value in enumerate([10, 20, 30, 40])
    ]}}), headers={"Content-Type": "application/json"})
    http = http_factory(script)
    result = collector(http).collect({"name": "fixture", "seed_keywords": ["query one"]})
    assert result.status == "success"
    assert [point.value for point in result.records[0].time_series] == [10, 20, 30, 40]
    assert all(point.is_partial is False for point in result.records[0].time_series)
    assert result.records[0].score == 40
