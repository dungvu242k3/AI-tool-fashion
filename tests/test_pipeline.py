"""Pipeline contract tests. All evidence here is an isolated test fixture."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from src.models.schemas import CollectionResult, DiscussionItem, KeywordSignal, ProductItem
from src.pipeline import execute_pipeline


@pytest.fixture
def sources(collection_factory):
    records = {
        "google_trends": [
            KeywordSignal("fixture one", score=0, trend="stable", source_url="https://trends.google.com/trends/explore?q=one"),
            KeywordSignal("fixture two", score=20, trend="declining", source_url="https://trends.google.com/trends/explore?q=two"),
        ],
        "amazon": [ProductItem("Fixture product", url="https://www.amazon.com/dp/B000000001")],
        "reddit": [DiscussionItem("Fixture discussion", url="https://www.reddit.com/r/fixture/comments/abc123/post/")],
    }
    return {
        source: SimpleNamespace(collect=lambda niche, s=source, r=items: collection_factory(s, r))
        for source, items in records.items()
    }


def run(tmp_path, sources, **kwargs):
    return execute_pipeline(
        niche_list=[{"name": "Fixture niche"}], output_dir=str(tmp_path), collectors=sources, **kwargs,
    )


def test_complete_deterministic_run_uses_actual_measurements(tmp_path, sources):
    result = run(tmp_path, sources, fast_mode=True)
    assert result["success"] is True
    assert result["status"] == "success"
    assert result["metadata"]["mode"] == "deterministic"
    assert result["metadata"]["model_name"] is None
    assert result["metadata"]["model_attempted"] is None
    assert result["metadata"]["total_keywords"] == 2
    assert result["metadata"]["total_products"] == 1
    assert result["ranking"] == []
    assert result["top_ideas"] == []
    details = result["niches"]["Fixture niche"]
    assert details["keywords"][0]["score"] == 0  # Source order is preserved, not sorted/boosted.
    assert details["products"][0]["price"] is None
    assert details["ideas"] == []
    assert Path(result["report_filepath"]).read_text(encoding="utf-8") == result["markdown_content"]
    cached = json.loads((tmp_path / "latest_data.json").read_text(encoding="utf-8"))
    assert cached == result
    diagnostics = json.loads((tmp_path / result["metadata"]["diagnostics_file"]).read_text(encoding="utf-8"))
    assert diagnostics["request_metadata"] == result["request_metadata"]
    assert diagnostics["source_health"]["amazon"]["request_count"] == 1
    for record in [*details["keywords"], *details["products"], *details["discussions"]]:
        provenance = record["provenance"]
        primary = diagnostics["request_metadata"][provenance["request_id"]]
        assert primary["status_code"] == 200
        assert provenance["retrieved_at"] == primary["completed_at"]


def test_partial_run_keeps_good_source_records(tmp_path, sources):
    sources["reddit"] = SimpleNamespace(collect=lambda niche: CollectionResult.from_records("reddit", [], ["Fixture unavailable"]))
    result = run(tmp_path, sources, fast_mode=True)
    assert result["success"] is False
    assert result["status"] == "partial"
    assert result["metadata"]["data_quality"] == "partial"
    assert result["metadata"]["total_products"] == 1
    assert result["source_statuses"]["Fixture niche"]["reddit"]["status"] == "failed"
    assert "Fixture unavailable" in result["markdown_content"]
    assert "| reddit | failed | 0 |" in result["markdown_content"]


def test_missing_trends_blocks_ideas_and_ai_call(tmp_path, sources, monkeypatch):
    sources["google_trends"] = SimpleNamespace(collect=lambda niche: CollectionResult.from_records("google_trends", []))
    monkeypatch.setattr(requests, "post", lambda *a, **kw: pytest.fail("LLM must not run without evidence"))
    result = run(tmp_path, sources)
    assert result["success"] is False
    assert result["metadata"]["data_quality"] == "insufficient"
    assert result["metadata"]["model_attempted"] is None
    assert result["niches"]["Fixture niche"]["ideas"] == []


def test_ollama_unavailable_is_not_reported_as_success(tmp_path, sources, monkeypatch):
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("Fixture Ollama offline")

    monkeypatch.setattr("src.analyzers.ollama_client.requests.Session.post", unavailable)
    result = run(tmp_path, sources, model_name="fixture-model")
    assert result["success"] is False
    assert result["status"] == "partial"
    assert result["metadata"]["model_attempted"] == "fixture-model"
    assert result["metadata"]["model_name"] is None
    assert result["niches"]["Fixture niche"]["analysis_status"] == "failed"
    assert result["niches"]["Fixture niche"]["ideas"] == []


def test_unexpected_provider_error_is_visible(tmp_path, sources):
    def broken(niche):
        raise RuntimeError("Fixture parser bug")

    sources["amazon"] = SimpleNamespace(collect=broken)
    result = run(tmp_path, sources, fast_mode=True)
    assert result["source_statuses"]["Fixture niche"]["amazon"]["status"] == "failed"
    assert result["metadata"]["total_products"] == 0
    assert result["success"] is False


def test_pipeline_excludes_untraceable_records(tmp_path, sources):
    sources["amazon"] = SimpleNamespace(collect=lambda niche: CollectionResult.from_records(
        "amazon", [ProductItem("Untraceable fixture", price="$10.00", url="https://www.amazon.com/dp/B000000001")],
    ))
    result = run(tmp_path, sources, fast_mode=True)
    assert result["metadata"]["total_products"] == 0
    assert result["source_statuses"]["Fixture niche"]["amazon"]["warnings"][0]["code"] == "invalid_provenance"
    assert "Untraceable fixture" not in result["markdown_content"]


def test_collection_diagnostics_survive_a_later_analysis_failure(tmp_path, sources, monkeypatch):
    def broken_analysis(*args, **kwargs):
        raise RuntimeError("Fixture analysis failure")

    monkeypatch.setattr("src.pipeline.LLMAnalyzer.analyze", broken_analysis)
    with pytest.raises(RuntimeError, match="Fixture analysis failure"):
        run(tmp_path, sources, fast_mode=True)
    paths = list((tmp_path / "diagnostics").glob("*.json"))
    assert len(paths) == 1
    diagnostics = json.loads(paths[0].read_text(encoding="utf-8"))
    assert len(diagnostics["request_metadata"]) == 3
    assert len(diagnostics["evidence"]) == 4
    assert {item["niche"] for item in diagnostics["evidence"]} == {"Fixture niche"}
    assert all(item["request_id"] in diagnostics["request_metadata"] for item in diagnostics["evidence"])
    assert not (tmp_path / "latest_data.json").exists()


@pytest.mark.parametrize("niches", [[], [{"name": ""}], [{"name": "one"}, {"name": "ONE"}]])
def test_empty_and_duplicate_niches_are_rejected(tmp_path, niches):
    with pytest.raises(ValueError):
        execute_pipeline(niche_list=niches, output_dir=str(tmp_path))
