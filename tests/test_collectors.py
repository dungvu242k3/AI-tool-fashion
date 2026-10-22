"""Isolated parser fixtures and provider failures; no live data in unit tests."""
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest
import requests

from src.collectors.amazon import AmazonCollector
from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.reddit import RedditCollector
from src.collectors.reddit_settings import RedditSettings
from src.collectors.trends_cache import TrendsCache
from src.collectors.trends_settings import TrendsSettings
from src.models.trends import TrendPoint
from src.processors.trend_metrics import calculate_trend_metrics


@pytest.mark.parametrize(("values", "trend"), [
    ([10, 15, 20, 50, 75, 90], "rising"),
    ([90, 80, 70, 20, 15, 10], "declining"),
    ([50, 52, 49, 51, 50, 53], "stable"),
    ([0, 0, 0, 0], "stable"),
    ([], "unavailable"),
])
def test_determine_trend(values, trend):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    points = [TrendPoint((start + timedelta(days=index)).isoformat(), value, False) for index, value in enumerate(values)]
    metrics = calculate_trend_metrics(points)
    assert (metrics.trend if metrics else "unavailable") == trend


def test_trends_keeps_observed_interest_when_related_queries_fail(http_factory, response_factory, trends_script):
    script = trends_script([10, 20, 30, 40, 100], partials=[False, False, False, False, True], related=True)
    http = http_factory(script + [response_factory(503)])
    result = GoogleTrendsCollector(http_client=http.client, settings=TrendsSettings(suggestions_enabled=False), cache=TrendsCache()).collect({
        "name": "fixture", "seed_keywords": ["query one"],
    })
    assert result.status == "partial"
    assert len(result.records) == 1
    assert result.records[0].score == 40
    assert result.records[0].related_queries == []
    assert "date=today+3-m" in result.records[0].source_url
    assert result.records[0].provenance.request_id == result.request_metadata[2].request_id
    assert result.request_metadata[-1].status_code == 503


def test_trends_empty_series_produces_no_signals(http_factory, trends_script):
    http = http_factory(trends_script([]))
    result = GoogleTrendsCollector(http_client=http.client, settings=TrendsSettings(suggestions_enabled=False), cache=TrendsCache()).collect({"name": "fixture"})
    assert result.records == []
    assert result.status == "failed"


def test_amazon_parser_preserves_only_observed_fields():
    html = '''<div data-component-type="s-search-result" data-asin="B000000001">
    <h2><a href="/dp/B000000001"><span>Parser fixture product</span></a></h2>
    <span class="a-price"><span class="a-offscreen">$1,299.99</span></span>
    <span class="a-icon-alt">4.2 out of 5 stars</span>
    <a href="/dp/B000000001#customerReviews"><span>1,234</span></a>
    </div>'''
    product = AmazonCollector._parse_products(html)[0]
    assert product.price == "$1,299.99"
    assert product.rating == 4.2
    assert product.reviews_count == 1234
    assert product.rank is None
    assert product.search_position == 1
    assert product.source == "Amazon Search"
    assert product.url == "https://www.amazon.com/dp/B000000001"


def test_amazon_http_200_without_cards_is_failed(http_factory, response_factory):
    http = http_factory([response_factory(text="<p>No results</p>")])
    result = AmazonCollector(http_client=http.client).collect({"name": "fixture"})
    assert result.status == "failed"
    assert result.records == []


def test_amazon_partial_requests_keep_real_records(http_factory, response_factory):
    http = http_factory([
        response_factory(text='''<div data-component-type="s-search-result" data-asin="B000000001"><h2>Parser fixture product</h2></div>'''),
        requests.Timeout("test: second request failed"),
    ])
    result = AmazonCollector(http_client=http.client).collect({
        "name": "fixture", "amazon_search_terms": ["one", "two"],
    })
    assert result.status == "partial"
    assert len(result.records) == 1
    assert result.records[0].price is None
    assert result.warnings


def test_reddit_missing_counts_and_body_remain_unknown(http_factory, response_factory):
    posts = [
        {"data": {"id": "abc123", "subreddit": "fixture", "created_utc": 1792454400, "title": "Fixture one", "permalink": "/r/fixture/comments/abc123/one/"}},
        {"data": {"id": "def456", "subreddit": "fixture", "created_utc": 1792454400, "title": "Fixture two", "permalink": "/r/fixture/comments/def456/two/", "score": 0, "num_comments": 0}},
    ]
    http = http_factory([response_factory(payload={"data": {"children": posts}})])
    result = RedditCollector(http_client=http.client, settings=RedditSettings(mode="public_json"),
                             utcnow=lambda: datetime(2026, 10, 21, tzinfo=timezone.utc)).collect({"name": "fixture", "subreddits": ["fixture"]})
    assert result.status == "success"
    assert result.records[0].score is None
    assert result.records[0].comments is None
    assert result.records[0].content_summary == ""
    assert result.records[1].score == 0
    assert result.records[1].comments == 0


@pytest.mark.parametrize("status", [403, 429, 503])
def test_reddit_http_errors_are_visible(status, http_factory, response_factory):
    http = http_factory([response_factory(status)])
    result = RedditCollector(http_client=http.client).collect({"name": "fixture", "subreddits": ["fixture"]})
    assert result.status == "failed"
    assert result.records == []
    assert result.warnings


def test_trends_all_network_operations_use_observable_retry_layer(http_factory, response_factory, trends_script):
    from dataclasses import asdict
    from src.collectors.http_policy import HTTPPolicy
    import json

    script = trends_script(related=True)
    script.insert(1, response_factory(429, headers={"Retry-After": "2"}))
    script.append(response_factory(text=")]}'\n" + json.dumps({"default": {"rankedList": [
        {"rankedKeyword": [{"query": "related top fixture", "value": 80}]},
        {"rankedKeyword": [{"query": "related rising fixture", "value": 20}]},
    ]}}), headers={"Content-Type": "application/json"}))
    http = http_factory(script, policy=HTTPPolicy(max_attempts=3))
    result = GoogleTrendsCollector(http_client=http.client, settings=TrendsSettings(suggestions_enabled=False), cache=TrendsCache()).collect({"name": "fixture", "seed_keywords": ["query one"]})
    assert result.status == "success"
    assert [trace.operation for trace in result.request_metadata] == ["bootstrap", "explore", "explore", "interest", "related_queries"]
    assert http.clock.sleeps == [2]
    assert result.records[0].related_queries
    ids = result.records[0].provenance.request_ids
    assert result.request_metadata[1].request_id not in ids  # Failed exploration is not evidence.
    assert len(ids) == 4
    audit = json.dumps([asdict(trace) for trace in result.request_metadata])
    assert "fixture-private-token" not in audit
    assert "fixture-related-token" not in audit


def test_reddit_invalid_json_is_not_retried(http_factory, response_factory):
    from src.collectors.http_policy import HTTPPolicy

    http = http_factory([response_factory(text="{broken", headers={"Content-Type": "application/json"})], policy=HTTPPolicy(max_attempts=3))
    result = RedditCollector(http_client=http.client).collect({"name": "fixture", "subreddits": ["fixture"]})
    assert result.status == "failed"
    assert result.warnings[0].code == "invalid_json"
    assert result.warnings[0].request_id == result.request_metadata[0].request_id
    assert http.session.request.call_count == 1


def test_missing_html_selectors_do_not_trigger_retries(http_factory, response_factory):
    from src.collectors.http_policy import HTTPPolicy

    http = http_factory([response_factory(text="<html>changed markup</html>")], policy=HTTPPolicy(max_attempts=3))
    result = AmazonCollector(http_client=http.client).collect({"name": "fixture"})
    assert result.status == "failed"
    assert result.warnings[0].code == "no_product_cards"
    assert http.session.request.call_count == 1
