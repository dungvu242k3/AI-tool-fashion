"""New verification integration paths. All responses/data here are fixtures only."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from src.collectors.amazon import AmazonCollector
from src.collectors.amazon_settings import AmazonSettings
from src.collectors.http_policy import HTTPPolicy
from src.collectors.performance_settings import SOURCES
from src.collectors.reddit import RedditCollector
from src.collectors.reddit_settings import RedditSettings
from src.models.schemas import ProductItem
from src.pipeline import execute_pipeline
from src.reporters.result_codec import read_document
from src.verification.live_probe import PROBE_HTTP_POLICY, _collector, probe_provider
from src.verification.publication_audit import audit_publication


def sources_from(research, collection_factory):
    from src.verification.collection_codec import restore_record
    fields = {"google_trends": "keywords", "amazon": "products", "reddit": "discussions"}
    niche = next(iter(research.niches.values()))
    from src.models.research_result import thaw_json
    return {source: SimpleNamespace(collect=lambda query, s=source, f=field:
        collection_factory(s, [restore_record(s, {key: raw[key] for key in raw if key not in {"raw_metric", "derived_metric"}})
                               for raw in thaw_json(niche[f])])) for source, field in fields.items()}


@pytest.mark.parametrize("case", ["rate-limited", "timeout", "selector-changed", "json-field-missing"])
def test_failure_to_pipeline_to_snapshot_to_audit_is_consistent(
        case, tmp_path, research_result_factory, collection_factory, http_factory, response_factory):
    research = research_result_factory()
    sources = sources_from(research, collection_factory)
    if case == "json-field-missing":
        transport = http_factory([response_factory(payload={"data": {}})])
        sources["reddit"] = RedditCollector(transport.client, settings=RedditSettings(
            mode="public_json", max_queries=1, max_keywords=1, max_subreddits=1))
        failed = "reddit"
    else:
        response = (response_factory(429) if case == "rate-limited" else
                    requests.ReadTimeout("Fixture private timeout details") if case == "timeout" else
                    response_factory(text="<html><div class='changed-layout'>No identifiable product cards</div></html>"))
        transport = http_factory([response], policy=HTTPPolicy(max_attempts=1))
        sources["amazon"] = AmazonCollector(transport.client, settings=AmazonSettings(max_requests=1))
        failed = "amazon"
    result = execute_pipeline(fast_mode=True, collectors=sources, output_dir=tmp_path,
        niche_list=[{"name": "Fixture", "seed_keywords": ["fixture"], "amazon_search_terms": ["fixture"], "subreddits": ["fixture"]}])
    state = result["source_statuses"]["Fixture"][failed]
    assert state["status"] == "failed" and state["record_count"] == 0
    assert state["warnings"] and transport.session.request.call_count == 1
    assert result["status"] != "success" and result["top_ideas"] == []
    report = audit_publication(tmp_path / "latest_data.json", tmp_path, result["metadata"]["run_id"])
    assert report["status"] == "consistent_with_collector_snapshots"
    assert report["research_status"] == result["status"]


def test_ollama_offline_pipeline_is_auditable_without_fictional_ideas(
        tmp_path, research_result_factory, monkeypatch):
    from src.analyzers.llm_analyzer import LLMAnalyzer
    from src.analyzers.ollama_client import GenerationError
    client = SimpleNamespace(generate=Mock(side_effect=GenerationError("ollama_connection_error")), close=Mock())
    monkeypatch.setattr("src.pipeline.LLMAnalyzer", lambda **options: LLMAnalyzer(generation_client=client, **options))
    research = research_result_factory(fast_mode=False)
    assert research.metadata["status"] == "partial" and not research.analysis_summary["top_ideas"]
    report = audit_publication(tmp_path / "latest_data.json", tmp_path, research.metadata["run_id"])
    assert report["status"] == "consistent_with_collector_snapshots" and client.generate.call_count == 1


@pytest.mark.parametrize("source", SOURCES)
def test_probe_constructor_has_small_explicit_budgets_and_borrowed_transport(source):
    from src.collectors.http import HTTPClient
    with HTTPClient(policy=PROBE_HTTP_POLICY) as http:
        collector = _collector(source, http)
        assert collector.http is http and not collector._owns_http
        if source == "google_trends":
            assert collector.settings.cache_ttl_seconds == 0 and not collector.settings.suggestions_enabled
        elif source == "amazon":
            assert collector.settings.max_requests == 1 and collector.settings.max_products == 5
        else:
            assert collector.settings.max_queries == 1 and collector.settings.page_size == 5
    assert PROBE_HTTP_POLICY.max_attempts == 1


def test_unknown_probe_cannot_start_a_transport_or_choose_arbitrary_url(tmp_path, monkeypatch):
    constructor = Mock(side_effect=AssertionError("Transport should not be created"))
    monkeypatch.setattr("src.verification.live_probe.HTTPClient", constructor)
    with pytest.raises(ValueError, match="Unknown"):
        probe_provider("https://127.0.0.1/private", tmp_path)
    assert not constructor.called and not list(tmp_path.iterdir())


@pytest.mark.parametrize("kind", ["records", "empty", "exception"])
def test_probe_diagnostics_are_unique_honest_and_do_not_publish_latest(
        tmp_path, monkeypatch, collection_factory, kind):
    class FixtureCollector:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def collect(self, query):
            if kind == "exception":
                raise RuntimeError("Fixture private secret must not be persisted")
            return collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")] if kind == "records" else [])
    monkeypatch.setattr("src.verification.live_probe._collector", lambda source, http: FixtureCollector())
    first, second = probe_provider("amazon", tmp_path), probe_provider("amazon", tmp_path)
    assert first["diagnostics"] != second["diagnostics"]
    saved = read_document(tmp_path / first["diagnostics"])
    assert saved["status"] == ("observed" if kind == "records" else "failed")
    assert saved["cache_enabled"] is False and saved["model_calls"] == 0
    assert "private secret" not in json.dumps(saved)
    assert not (tmp_path / "latest_data.json").exists()
    assert not list(tmp_path.glob("report_trend_*.md"))
    if kind == "exception":
        assert saved["network_attempts"] is None  # Never invent zero after unknown I/O.


def test_custom_ranking_policy_and_escaped_niche_names_are_reproducible(tmp_path, research_result_factory):
    from src.ranking.policy import RankingPolicy
    from src.ranking.service import RankingService
    policy = RankingPolicy(review_reference=150, community_reference=50, min_commerce_products=2)
    research = research_result_factory(names=("A/B~C",), ranking_service=RankingService(policy))
    report = audit_publication(tmp_path / "latest_data.json", tmp_path, research.metadata["run_id"])
    assert any(item["json_pointer"].startswith("/niches/A~1B~0C/") for item in report["sources"])


def test_offline_audit_can_pair_another_manifest_only_for_exact_same_archived_evidence(
        tmp_path, research_result_factory):
    from src.reporters.collection_snapshots import CollectionSnapshotWriter, read_collection_snapshots
    from src.collectors.performance_settings import PerformanceSettings
    from src.verification.collection_codec import restore_collection
    from src.reporters.report_repository import ReportRepository
    from src.models.research_result import ResearchResult
    research = research_result_factory()
    original = read_collection_snapshots(tmp_path, research.metadata["run_id"])
    alternate = "d" * 32
    writer = CollectionSnapshotWriter(tmp_path, alternate, ["Fixture"], PerformanceSettings())
    for document in original:
        writer.capture(0, document["source"], restore_collection(document["collection"]))
    writer.commit()
    publication = research.to_dict()
    publication["metadata"]["execution_kind"] = "offline_publication_audit"
    ReportRepository(tmp_path).publish(ResearchResult.from_dict(publication))
    assert audit_publication(tmp_path / "latest_data.json", tmp_path, alternate)["status"] == "consistent_with_collector_snapshots"
