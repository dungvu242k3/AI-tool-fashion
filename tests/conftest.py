"""Unit tests must explicitly replace HTTP I/O; real collection is tested separately."""
import pytest
import requests
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
from urllib.parse import urlencode, urlsplit

from src.collectors.http import HTTPClient
from src.collectors.http_policy import HTTPPolicy
from src.models.collection import CollectionResult, RecordProvenance, RequestMetadata
from src.models.commerce import ProductListing
from src.processors.amazon_values import parse_observed_price
from src.models.trends import TrendPoint
from src.processors.trend_metrics import calculate_trend_metrics
from src.utils.helpers import truncate_text


@pytest.fixture(autouse=True)
def block_accidental_external_http(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("External HTTP is disabled in unit tests; inject an explicit transport fixture.")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)


@pytest.fixture
def response_factory():
    def create(status=200, text="", *, payload=None, headers=None):
        response = requests.Response()
        response.status_code = status
        response.encoding = "utf-8"
        response._content = (json.dumps(payload) if payload is not None else text).encode("utf-8")
        response._content_consumed = True
        response.headers.update({"Content-Type": "application/json" if payload is not None else "text/html"})
        response.headers.update(headers or {})
        response.close = Mock(wraps=response.close)
        return response
    return create


@pytest.fixture
def http_factory():
    clients = []

    def create(script, *, policy=None):
        clock = SimpleNamespace(seconds=0.0, sleeps=[])

        def sleep(delay):
            clock.sleeps.append(delay)
            clock.seconds += delay

        session = SimpleNamespace(request=Mock(side_effect=script), close=Mock())
        client = HTTPClient(
            session=session, policy=policy if policy is not None else HTTPPolicy(max_attempts=1),
            sleep=sleep, monotonic=lambda: clock.seconds,
            utcnow=lambda: datetime(2026, 10, 21, tzinfo=timezone.utc) + timedelta(seconds=clock.seconds),
            random_value=lambda: 0.0,
        )
        clients.append(client)
        return SimpleNamespace(client=client, session=session, clock=clock)

    yield create
    for client in clients:
        client.close()


@pytest.fixture
def collection_factory():
    """Construct a traced result fixture; never used by runtime code."""
    def create(source, records):
        request_id = uuid4().hex
        timestamp = "2026-10-21T00:00:00.000+00:00"
        query = {"fixture": True, **({"source_type": "search"} if source == "amazon" else {})}
        trace_url = "https://www.amazon.com/s?k=fixture" if source == "amazon" else "https://example.test/fixture"
        if source == "google_trends":
            query = {"keywords": [record.keyword for record in records], "geo": records[0].geo if records else "",
                     "timeframe": (records[0].timeframe or "today 3-m") if records else "today 3-m"}
            trace_url = "https://trends.google.com/trends/api/widgetdata/multiline"
        if source == "reddit":
            end = datetime.fromisoformat(timestamp).timestamp()
            query = {"provider": "public_json", "subreddit": "fixture", "search_term": "fixture",
                     "sort": "top", "time_filter": "month", "window_start_utc": end - 30 * 86400, "window_end_utc": end}
            trace_url = "https://www.reddit.com/r/fixture/search.json?" + urlencode({
                "q": "fixture", "restrict_sr": "on", "sort": "top", "t": "month", "type": "link"})
        trace = RequestMetadata(
            request_id=request_id, operation_id=uuid4().hex, source=source,
            operation="interest" if source == "google_trends" else "search" if source in {"amazon", "reddit"} else "fixture", method="GET",
            url=trace_url,
            query=query, started_at=timestamp, completed_at=timestamp,
            elapsed_ms=1, status_code=200,
        )
        with_provenance = [replace(record, provenance=RecordProvenance(
            evidence_id=uuid4().hex, source=source,
            source_url=getattr(record, "source_url", None) or getattr(record, "url", ""),
            query=trace.query, retrieved_at=timestamp,
            request_id=request_id, request_ids=[request_id],
        )) for record in records]
        if source == "google_trends":
            modern = []
            for record in with_provenance:
                points = record.time_series or [TrendPoint(
                    (datetime.fromisoformat(timestamp) - timedelta(days=4 - index)).isoformat(), record.score, False,
                ) for index in range(4)]
                metrics = record.metrics if record.time_series else calculate_trend_metrics(points)
                url = "https://trends.google.com/trends/explore?" + urlencode({"q": record.keyword, "date": query["timeframe"], "geo": query["geo"]})
                modern.append(replace(record, time_series=points, metrics=metrics,
                    score=metrics.latest_value if metrics else record.score, trend=metrics.trend if metrics else "unavailable",
                    geo=query["geo"], timeframe=query["timeframe"], source_url=url, comparison_keywords=query["keywords"],
                    provenance=replace(record.provenance, source_url=url, query={**query, "keyword": record.keyword})))
            with_provenance = modern
        if source == "amazon":
            modern = []
            for position, record in enumerate(with_provenance, 1):
                price = parse_observed_price(record.price)
                modern.append(replace(
                    record, asin=record.url.rsplit("/", 1)[-1], source="Amazon Search", source_type="search",
                    listing_url=trace.url, listing_position=position, search_position=position, rank=None, listing_rank=None,
                    is_sponsored=False, price_amount=price.amount if price else None, price_currency=price.currency if price else None,
                    listings=[ProductListing("search", trace.url, position, position, None, False, record.provenance)],
                ))
            with_provenance = modern
        if source == "reddit":
            with_provenance = [replace(
                record, post_id=urlsplit(record.url).path.split("/")[4], subreddit="fixture",
                permalink=urlsplit(record.url).path, created_utc=end - 3600,
                source="Reddit r/fixture", provider="public_json",
                selftext=record.selftext if record.selftext is not None else record.content_summary or None,
                content_summary=truncate_text(record.selftext if record.selftext is not None else record.content_summary, 200),
            ) for record in with_provenance]
        return CollectionResult.from_records(
            source, with_provenance, request_metadata=[trace], started_at=timestamp, completed_at=timestamp,
        )
    return create


@pytest.fixture
def qualified_data_factory(collection_factory):
    """Migrate isolated analyzer fixtures to the phase-6 validated-series gate."""
    from src.collectors.validation import validate_collection_result
    from src.processors.data_processor import DataProcessor
    from src.processors.data_quality import assess_data_quality

    def create(data):
        fields = {"google_trends": ("keywords", "keywords_data"), "amazon": ("products", "products_data"), "reddit": ("discussions", "discussions_data")}
        sources = {source: validate_collection_result(source, collection_factory(source, getattr(data, field)))
                   for source, (field, _) in fields.items()}
        processed = DataProcessor().process({"niche": data.niche_name, "collected_at": data.collected_at,
            **{raw: sources[source].records for source, (_, raw) in fields.items()}})
        processed.quality_assessment = assess_data_quality(processed, sources)
        return processed

    return create


@pytest.fixture
def trends_script(response_factory):
    def create(values=None, *, partials=None, related=False):
        values = values if values is not None else [10, 20, 30, 40]
        widgets = [{"id": "TIMESERIES", "token": "fixture-private-token", "request": {"time": "fixture"}}]
        if related:
            widgets.append({
                "id": "RELATED_QUERIES", "token": "fixture-related-token",
                "request": {"restriction": {"complexKeywordsRestriction": {"keyword": [{"value": "query one"}]}}},
            })
        return [
            response_factory(),
            response_factory(text=")]}'\n" + json.dumps({"widgets": widgets}), headers={"Content-Type": "application/json"}),
            response_factory(text=")]}'\n" + json.dumps({"default": {"timelineData": [
                {"time": str(1761000000 + 86400 * index), "value": [value], "isPartial": partials[index] if partials else False}
                for index, value in enumerate(values)
            ]}}), headers={"Content-Type": "application/json"}),
        ]
    return create


@pytest.fixture
def grounded_payload_factory():
    """Synthetic AI selections for tests only, grounded in each test's catalog."""
    def create(data=None, *, prompt=None, include_quotes=True, proposals=True):
        if prompt is None:
            from src.analyzers.analysis_policy import AnalysisPolicy
            from src.analyzers.evidence_catalog import EvidenceCatalog
            evidence = EvidenceCatalog.from_data(data, AnalysisPolicy()).to_dict()["evidence"]
        else:
            evidence = json.loads(prompt)["evidence"]
        trend = next(item for item in evidence if item["source"] == "google_trends")
        support = next(item for item in evidence if item["source"] in {"amazon", "reddit"})
        support_metric = "amazon.title" if support["source"] == "amazon" else "reddit.title"
        facts = [
            {"fact_id": "F1", "kind": "fact", "metric": "trend.recent_mean", "value": trend["metrics"]["trend.recent_mean"], "evidence_ids": [trend["evidence_id"]]},
            {"fact_id": "F2", "kind": "fact", "metric": support_metric, "value": support["metrics"][support_metric], "evidence_ids": [support["evidence_id"]]},
        ]
        quotes, ids = [], {trend["evidence_id"], support["evidence_id"]}
        post = next((item for item in evidence if item["source"] == "reddit"), None)
        if include_quotes and post:
            context = post["quote_context"][1] if len(post["quote_context"][1]) >= 8 else post["quote_context"][0]
            quotes = [{"quote_id": "Q1", "quote": context[:160], "evidence_ids": [post["evidence_id"]]}]
            ids.add(post["evidence_id"])
        ideas = [{"kind": "proposal", "name": name, "what_to_sell": design, "target_audience": "Gift recipients",
                  "basis_fact_ids": ["F1", "F2"], "basis_quote_ids": ["Q1"] if quotes else [], "evidence_ids": sorted(ids)}
                 for name, design in (("Gift pouch Alpha", "Fabric pouch with a gift tag"),
                                      ("Gift sleeve Bravo", "Reusable sleeve with a personal motif"))] if proposals else []
        return {"schema_version": "grounded-analysis-v1", "facts": facts, "quotes": quotes, "ideas": ideas,
                "limitations": ["proposals_require_market_validation", "source_samples_not_market_representative"]}
    return create


@pytest.fixture
def grounded_data_factory(qualified_data_factory):
    """Phase-8 isolated input models, never loaded by production modules."""
    from src.models.schemas import DiscussionItem, KeywordSignal, NicheData, ProductItem
    def create(name="Fixture", *, keywords=None, products=None, posts=None, body="I cannot find the right size."):
        return qualified_data_factory(NicheData(name, "2026-10-21T00:00:00+00:00",
            keywords=keywords if keywords is not None else [KeywordSignal("fixture alpha", score=40), KeywordSignal("fixture bravo", score=60)],
            products=products if products is not None else [ProductItem(f"Fixture product {index}", rating=4, reviews_count=100,
                price="USD 18.00", url=f"https://www.amazon.com/dp/B{index:09d}") for index in range(1, 6)],
            discussions=posts if posts is not None else [DiscussionItem(f"Fixture discussion {index}", score=20, comments=10,
                selftext=body, url=f"https://www.reddit.com/r/fixture/comments/abc{index}/post/") for index in range(3)]))
    return create


@pytest.fixture
def research_result_factory(tmp_path, collection_factory):
    """Phase-9 output scenarios from isolated test collectors, never production data."""
    from src.models.research_result import ResearchResult
    from src.models.schemas import KeywordSignal, ProductItem, DiscussionItem
    from src.pipeline import execute_pipeline

    def create(*, state="complete", names=("Fixture",), fast_mode=True, cached=False, **kwargs):
        records = {
            "google_trends": [KeywordSignal("fixture alpha", score=0), KeywordSignal("fixture bravo", score=60)],
            "amazon": [ProductItem(f"Fixture product {index}", rating=4, reviews_count=100, price=None,
                                   url=f"https://www.amazon.com/dp/B{index:09d}") for index in range(1, 6)],
            "reddit": [DiscussionItem(f"Fixture discussion {index}", score=0, comments=10,
                        selftext="I cannot find the right size.",
                        url=f"https://www.reddit.com/r/fixture/comments/abc{index}/post/") for index in range(3)],
        }
        if state == "insufficient":
            records["google_trends"] = []
        if state in {"partial", "failed"}:
            records["reddit"] = []
        if state == "failed":
            records = {source: [] for source in records}
        sources = {source: collection_factory(source, items) for source, items in records.items()}
        if cached:
            trends = sources["google_trends"]
            trends.records = [replace(record, provenance=replace(record.provenance, from_cache=True)) for record in trends.records]
            trends.request_metadata = [replace(trace, cache_reused=True) for trace in trends.request_metadata]
        collectors = {source: SimpleNamespace(collect=lambda niche, s=source: sources[s]) for source in sources}
        document = execute_pipeline(fast_mode=fast_mode, niche_list=[{"name": name} for name in names],
                                    output_dir=str(tmp_path), collectors=collectors, **kwargs)
        return ResearchResult.from_dict(document)
    return create
