"""Regression tests for phase 0: runtime must never manufacture market data.

HTTP doubles in this file are isolated parser/failure fixtures, not report data.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from src.collectors.amazon import AmazonCollector
from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.reddit import RedditCollector
from src.models.schemas import KeywordSignal, NicheData, ProductItem
from src.processors.data_processor import DataProcessor
from src.analyzers.llm_analyzer import LLMAnalyzer
from src.reporters.report_generator import ReportGenerator
from src.pipeline import execute_pipeline


NICHE = {"name": "Test niche", "seed_keywords": ["test query"], "subreddits": ["fixture"]}


def records(result):
    """Allow the regression tests to run against the pre-migration list API."""
    return result if isinstance(result, list) else result.records


@pytest.mark.parametrize("collector_type", [AmazonCollector, RedditCollector])
@pytest.mark.parametrize("niche_name", ["Christmas Gift Ideas", "Gift for Him", "Gift for Her", "Unconfigured niche"])
def test_http_failure_returns_no_invented_records(http_factory, collector_type, niche_name):
    http = http_factory([requests.ConnectionError("test: offline")])
    result = collector_type(http_client=http.client).collect({**NICHE, "name": niche_name})
    assert records(result) == []
    assert result.status == "failed"
    assert result.warnings


def test_trends_failure_does_not_fabricate_interest(http_factory, response_factory):
    http = http_factory([response_factory(429)])
    collector = GoogleTrendsCollector(http_client=http.client)
    result = collector.collect(NICHE)
    assert records(result) == []
    assert result.status == "failed"


def test_amazon_missing_fields_remain_unknown(http_factory, response_factory):
    html = '''<div data-component-type="s-search-result" data-asin="B000000001">
    <h2><a href="/dp/B000000001"><span>Parser fixture product</span></a></h2>
    </div>'''
    http = http_factory([response_factory(text=html)])
    product = records(AmazonCollector(http_client=http.client).collect(NICHE))[0]
    assert product.price is None
    assert product.rating is None
    assert product.reviews_count is None


def test_empty_price_sample_has_no_fabricated_range():
    price_info = DataProcessor.extract_price_range([])
    assert price_info["min"] is None
    assert price_info["max"] is None
    assert price_info["avg"] is None
    assert "$" not in price_info["formatted"]


def test_processor_preserves_zero_and_does_not_boost_raw_score():
    processor = DataProcessor()
    zero = processor._process_keywords([{"keyword": "no interest", "score": 0}])[0]
    assert zero.score == 0
    raw = KeywordSignal(keyword="measured", score=50, trend="rising")
    assert processor._process_keywords([raw])[0].score == 50
    assert raw.score == 50


def test_processor_missing_product_values_stay_null():
    product = DataProcessor()._process_products([{"title": "fixture", "asin": "B000000001"}])[0]
    assert product.price is None
    assert product.rating is None
    assert product.reviews_count is None


def test_analyzer_failure_does_not_invent_ideas(monkeypatch):
    analyzer = LLMAnalyzer()
    monkeypatch.setattr(analyzer, "_call_ollama", lambda *a, **kw: "")
    section = analyzer.analyze("Unconfigured niche", NicheData("Unconfigured niche", ""))
    assert section.ideas == []
    assert "180%" not in section.ideas_content
    assert "tăng trưởng mạnh" not in section.analysis_content


def test_summary_does_not_inject_unrequested_niches():
    summary = LLMAnalyzer(fast_mode=True).summarize({})
    assert "Christmas Gift Ideas" not in summary
    assert "Gift for Him" not in summary
    assert "9.5/10" not in summary


def test_deterministic_report_never_claims_ollama_usage(tmp_path):
    reporter = ReportGenerator(str(tmp_path))
    path = reporter.generate(
        category="Test category", niches=[], analysis_results={},
        summary="Không đủ dữ liệu.", model_name=None,
    )
    text = Path(path).read_text(encoding="utf-8")
    assert "Chạy Local qua Ollama" not in text
    assert "`None`" not in text
    assert "Amazon Best Sellers" not in text


def test_offline_pipeline_is_not_successful(tmp_path, http_factory):
    collectors = {
        source: kind(http_client=http_factory([requests.ConnectionError("test: offline")]).client)
        for source, kind in (("google_trends", GoogleTrendsCollector), ("amazon", AmazonCollector), ("reddit", RedditCollector))
    }
    result = execute_pipeline(fast_mode=True, niche_list=[NICHE], output_dir=str(tmp_path), collectors=collectors)
    assert result["success"] is False
    assert result["ranking"] == []
    assert result["top_ideas"] == []
    assert result["metadata"]["model_name"] is None
    assert result["metadata"]["total_products"] == 0
    assert result["metadata"]["total_discussions"] == 0


def test_unknown_metrics_are_null_by_default():
    product = ProductItem("fixture")
    keyword = KeywordSignal("fixture")
    assert (product.price, product.rating, product.reviews_count, product.rank) == (None,) * 4
    assert keyword.score is None
    assert keyword.trend == "unavailable"
