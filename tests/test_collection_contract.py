from dataclasses import asdict, replace
from datetime import datetime, timezone
import json

import pytest

from src.collectors.amazon import AmazonCollector
from src.collectors.base import BaseCollector
from src.collectors.errors import CollectionError
from src.collectors.reddit import RedditCollector
from src.collectors.reddit_settings import RedditSettings
from src.collectors.validation import validate_collection_result
from src.models.collection import CollectionResult, CollectionWarning
from src.models.schemas import ProductItem
from src.processors.source_health import aggregate_source_health


def test_contract_serializes_structured_warnings_and_request_references(collection_factory):
    result = collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")])
    result = CollectionResult.from_records(
        result.source, result.records, [CollectionWarning("fixture_warning", "Fixture warning")],
        request_metadata=result.request_metadata,
    )
    status = result.status_dict()
    assert status["status"] == "partial"
    assert status["warnings"][0]["code"] == "fixture_warning"
    assert status["request_ids"] == [result.request_metadata[0].request_id]
    assert status["is_live"] is True
    assert "request_metadata" not in status
    assert len(result.status_dict(include_requests=True)["request_metadata"]) == 1


@pytest.mark.parametrize("changes", [
    {"source": "other"}, {"is_live": False}, {"query": {}}, {"evidence_id": ""},
    {"request_id": "unknown"}, {"request_ids": ["unknown"]},
    {"source_url": "https://other.test/"}, {"retrieved_at": "unrelated timestamp"},
])
def test_untraceable_records_are_rejected(changes, collection_factory):
    result = collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")])
    result.records[0] = replace(result.records[0], provenance=replace(result.records[0].provenance, **changes))
    validated = validate_collection_result("amazon", result)
    assert validated.status == "failed"
    assert validated.records == []
    assert validated.warnings[0].code == "invalid_provenance"
    assert validated.request_metadata == result.request_metadata


def test_record_cannot_reference_a_failed_attempt(collection_factory):
    result = collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")])
    result.request_metadata[0] = replace(result.request_metadata[0], status_code=503, error_code="http_503")
    assert validate_collection_result("amazon", result).records == []


def test_invalid_source_contract_is_not_silently_accepted(collection_factory):
    result = collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")])
    with pytest.raises(CollectionError):
        validate_collection_result("reddit", result)


def test_duplicate_evidence_ids_are_rejected(collection_factory):
    result = collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")])
    result.records.append(result.records[0])
    validated = validate_collection_result("amazon", result)
    assert len(validated.records) == 1
    assert validated.status == "partial"


def test_source_health_includes_every_niche_and_retains_partial_evidence(collection_factory):
    good = collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")])
    failed = CollectionResult.from_records("amazon", [], [CollectionWarning("http_403", "Fixture blocked")])
    unconfigured = CollectionResult("reddit", status="not_configured")
    health = aggregate_source_health({
        "one": {"amazon": good, "reddit": unconfigured},
        "two": {"amazon": failed, "reddit": unconfigured},
    })
    assert health["amazon"]["status"] == "partial"
    assert health["amazon"]["record_count"] == 1
    assert health["amazon"]["status_counts"]["failed"] == 1
    assert health["amazon"]["warning_counts"] == {"http_403": 1}
    assert health["reddit"]["status"] == "not_configured"
    assert health["reddit"]["request_count"] == 0


def test_collector_context_does_not_leak_requests_or_failures_between_calls(http_factory, response_factory):
    http = http_factory([
        response_factory(403),
        response_factory(text='<div data-component-type="s-search-result" data-asin="B000000001"><h2>Fixture product</h2></div>'),
    ])
    collector = AmazonCollector(http_client=http.client)
    first, second = collector.collect({"name": "first"}), collector.collect({"name": "second"})
    assert first.status == "failed"
    assert second.status == "success"
    assert second.warnings == []
    assert len(first.request_metadata) == len(second.request_metadata) == 1
    assert first.request_metadata[0].request_id != second.request_metadata[0].request_id
    assert second.records[0].provenance.request_id == second.request_metadata[0].request_id


def test_unconfigured_reddit_makes_no_http_requests(http_factory):
    http = http_factory([])
    result = RedditCollector(http_client=http.client).collect({"name": "fixture"})
    assert result.status == "not_configured"
    assert result.request_metadata == []
    assert result.warnings[0].code == "not_configured"
    http.session.request.assert_not_called()


def test_last_resort_error_preserves_prior_records_and_journal(http_factory, response_factory, caplog):
    class BrokenCollector(BaseCollector):
        def _collect(self, niche, context):
            response = context.fetch("GET", "https://example.test/", operation="fixture", query={"fixture": True})
            context.add_records([ProductItem("Fixture", url="https://example.test/")], response, {"fixture": True})
            raise RuntimeError("private body or credential")

    http = http_factory([response_factory()])
    result = BrokenCollector("fixture", http.client).collect({"name": "fixture"})
    assert result.status == "partial"
    assert len(result.records) == len(result.request_metadata) == 1
    assert result.warnings[0].code == "internal_error"
    assert "private body" not in json.dumps(result.status_dict(include_requests=True))
    assert "private body" not in caplog.text


def test_result_invariants_cannot_claim_success_without_data():
    with pytest.raises(ValueError):
        CollectionResult("fixture", status="success")
    with pytest.raises(ValueError):
        CollectionResult("fixture", status="partial")
    with pytest.raises(ValueError):
        CollectionResult("fixture", records=[ProductItem("Fixture")], status="failed")


def test_malformed_provenance_does_not_discard_other_valid_records(collection_factory):
    result = collection_factory("amazon", [
        ProductItem("Valid fixture", url="https://www.amazon.com/dp/B000000001"),
        ProductItem("Malformed fixture", url="https://www.amazon.com/dp/B000000002"),
        ProductItem("Missing URL fixture", url="https://www.amazon.com/dp/B000000003"),
    ])
    malformed = result.records[1]
    result.records[1] = replace(malformed, provenance=replace(malformed.provenance, request_ids=None))
    missing = result.records[2]
    result.records[2] = replace(missing, url="", provenance=replace(missing.provenance, source_url=""))
    validated = validate_collection_result("amazon", result)
    assert [record.title for record in validated.records] == ["Valid fixture"]
    assert validated.status == "partial"
    assert [warning.code for warning in validated.warnings] == ["invalid_provenance", "invalid_provenance"]
    assert validated.request_metadata == result.request_metadata


def test_records_do_not_share_mutable_provenance_references(http_factory, response_factory):
    class FixtureCollector(BaseCollector):
        def _collect(self, niche, context):
            response = context.fetch("GET", "https://example.test/", operation="fixture", query={"fixture": True})
            context.add_records([
                ProductItem("First fixture", url="https://example.test/one"),
                ProductItem("Second fixture", url="https://example.test/two"),
            ], response, {"fixture": True})

    http = http_factory([response_factory()])
    result = FixtureCollector("fixture", http.client).collect({"name": "fixture"})
    result.records[0].provenance.request_ids.clear()
    assert result.records[1].provenance.request_ids == [result.request_metadata[0].request_id]


def test_reddit_keeps_valid_posts_when_another_record_is_malformed(http_factory, response_factory):
    http = http_factory([response_factory(payload={"data": {"children": [
        None,
        {"data": {"id": "abc", "subreddit": "fixture", "created_utc": 1792454400, "title": "Observed fixture", "permalink": "/r/fixture/comments/abc/post/", "score": 0}},
    ]}})])
    result = RedditCollector(http.client, settings=RedditSettings(mode="public_json"),
                             utcnow=lambda: datetime(2026, 10, 21, tzinfo=timezone.utc)).collect({"name": "fixture", "subreddits": ["fixture"]})
    assert result.status == "partial"
    assert [record.title for record in result.records] == ["Observed fixture"]
    assert result.warnings[0].code == "invalid_record"
    assert result.warnings[0].request_id == result.records[0].provenance.request_id
    assert len(result.request_metadata) == http.session.request.call_count == 1
