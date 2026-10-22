"""Phase-6 isolated schema/gate tests. None of these fixtures are research data."""
import copy
import json
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.analyzers.llm_analyzer import LLMAnalyzer
from src.collectors.errors import CollectionError
from src.collectors.evidence_validation import is_http_url
from src.collectors.validation import MAX_CANDIDATES, MAX_WARNINGS, validate_collection_result
from src.models.collection import CollectionResult, CollectionWarning, RecordProvenance
from src.models.commerce import ProductListing
from src.models.quality import ValidationStats
from src.models.schemas import DiscussionItem, KeywordSignal, NicheData, NicheReportSection, ProductItem
from src.models.trends import TrendPoint
from src.pipeline import execute_pipeline
from src.processors.data_processor import DataProcessor
from src.processors.data_quality import assess_data_quality, has_sufficient_evidence
from src.processors.trend_metrics import calculate_trend_metrics
from src.reporters.report_generator import ReportGenerator
from src.reporters.report_repository import ReportRepository

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def keyword(name="one", score=0, **values):
    return KeywordSignal(name, score=score, **values)


def product(asin="B000000001", **values):
    return ProductItem("Fixture source product", asin=asin, url=f"https://www.amazon.com/dp/{asin}", **values)


def discussion(post_id="abc123", **values):
    return DiscussionItem("Fixture source post", post_id=post_id,
                          url=f"https://www.reddit.com/r/fixture/comments/{post_id}/post/", **values)


@pytest.fixture
def raw_sources(collection_factory):
    return {
        "google_trends": collection_factory("google_trends", [keyword(), keyword("two", 20)]),
        "amazon": collection_factory("amazon", [product(price="$12.50")]),
        "reddit": CollectionResult("reddit", status="not_configured"),
    }


def validate(sources):
    return {source: validate_collection_result(source, result, now=NOW) for source, result in sources.items()}


def prepare(sources, name="Fixture"):
    data = DataProcessor().process({"niche": name, "collected_at": NOW.isoformat(),
        "keywords_data": sources["google_trends"].records, "products_data": sources["amazon"].records,
        "discussions_data": sources["reddit"].records})
    data.quality_assessment = assess_data_quality(data, sources)
    return data


def duplicate_with_new_request(result, index=0, *, score=None):
    record = copy.deepcopy(result.records[index])
    request_id = uuid4().hex
    trace = next(trace for trace in result.request_metadata if trace.request_id == record.provenance.request_id)
    result.request_metadata.append(replace(trace, request_id=request_id, operation_id=uuid4().hex))
    record.provenance = replace(record.provenance, evidence_id=uuid4().hex, request_id=request_id, request_ids=[request_id])
    if isinstance(record, KeywordSignal) and score is not None:
        record.time_series = [replace(point, value=score) for point in record.time_series]
        record.metrics = calculate_trend_metrics(record.time_series)
        record.score, record.trend = record.metrics.latest_value, record.metrics.trend
    if isinstance(record, ProductItem):
        record.listings = [replace(listing, provenance=record.provenance) for listing in record.listings]
    result.records.append(record)
    return record


def test_full_gate_uses_real_series_and_reports_exact_counts(raw_sources):
    sources = validate(raw_sources)
    data = prepare(sources)
    quality = data.quality_assessment
    assert quality.status == "sufficient" and has_sufficient_evidence(data)
    assert quality.qualifying_keyword_count == 2 and quality.supporting_record_count == 1
    assert quality.configured_source_count == quality.observed_source_count == 2
    assert quality.source_coverage == quality.valid_ratio == 1
    assert quality.candidate_count == quality.valid_count == quality.retained_count == 3
    assert quality.rejected_count == quality.duplicate_count == 0
    assert data.keywords[0].score == 0
    assert data.to_dict()["quality_assessment"] == quality.to_dict()


@pytest.mark.parametrize("changes", [
    {"score": True}, {"score": "50"}, {"score": 101}, {"score": float("nan")}, {"score": None},
    {"time_series": []}, {"time_series": [{}] * 4}, {"metrics": None}, {"metrics": {}},
    {"geo": "http://127.0.0.1/"}, {"timeframe": ""}, {"timeframe": "javascript:bad()"},
    {"comparison_keywords": ["not-in-query"]}, {"comparison_keywords": ["one", "one"]},
    {"trend": "rising"}, {"related_queries": ["unsupported"]}, {"suggestions": ["unsupported"]},
    {"keyword": "<script>bad()</script>"}, {"signal_summary": "bad\ud800"},
])
def test_bad_keyword_schema_is_filtered_without_poisoning_other_series(changes, raw_sources):
    result = raw_sources["google_trends"]
    result.records[0] = replace(result.records[0], **changes)
    valid = validate_collection_result("google_trends", result, now=NOW)
    assert [item.keyword for item in valid.records] == ["two"]
    assert valid.status == "partial"
    assert valid.validation.candidate_count == 2 and valid.validation.rejected_count == 1
    assert valid.validation.valid_ratio == 0.5


@pytest.mark.parametrize("changes", [
    {"growth_percent": 999}, {"slope": 999}, {"recent_mean": 99}, {"previous_mean": 99},
    {"volatility": float("inf")}, {"valid_points": True}, {"excluded_points": False},
    {"window_points_used": True}, {"method": "invented-method"}, {"classification_reason": "invented"},
    {"latest_value": True}, {"rising_threshold_percent": 0},
])
def test_derived_trend_metrics_must_be_reproducible(changes, raw_sources):
    result = raw_sources["google_trends"]
    result.records[0].metrics = replace(result.records[0].metrics, **changes)
    valid = validate_collection_result("google_trends", result, now=NOW)
    assert len(valid.records) == 1 and valid.validation.rejected_count == 1


@pytest.mark.parametrize("kind", ["naive", "future", "duplicate", "offset_duplicate", "unordered", "bool_value", "unknown_flag", "invalid_value"])
def test_series_points_are_typed_ordered_and_timestamped(kind, raw_sources):
    result = raw_sources["google_trends"]
    points = result.records[0].time_series
    if kind == "naive": points[0] = replace(points[0], timestamp="2026-10-17T00:00:00")
    elif kind == "future": points[0] = replace(points[0], timestamp="2026-10-22T00:00:00+00:00")
    elif kind == "duplicate": points[1] = replace(points[1], timestamp=points[0].timestamp)
    elif kind == "offset_duplicate": points[1] = replace(points[1], timestamp="2026-10-17T07:00:00+07:00")
    elif kind == "unordered": points.reverse()
    elif kind == "bool_value": points[0] = replace(points[0], value=False)
    elif kind == "unknown_flag": points[0] = replace(points[0], is_partial="false")
    else: points[0] = replace(points[0], value=-1)
    valid = validate_collection_result("google_trends", result, now=NOW)
    assert len(valid.records) == 1 and valid.validation.rejected_count == 1


@pytest.mark.parametrize("changes", [
    {"retrieved_at": None}, {"retrieved_at": "2026-10-21T00:00:00"},
    {"source_url": "https://other.test/"}, {"source_url": ""}, {"is_live": False}, {"from_cache": "false"},
    {"request_ids": []}, {"request_ids": [None]}, {"request_ids": "not-a-list"}, {"request_id": "unknown"},
    {"query": {}}, {"evidence_id": ""}, {"evidence_id": "unsafe\nheader"},
])
def test_all_record_types_require_provenance_timestamp_and_successful_request(changes, raw_sources):
    for source in ("google_trends", "amazon"):
        result = raw_sources[source]
        result.records[0].provenance = replace(result.records[0].provenance, **changes)
        valid = validate_collection_result(source, result, now=NOW)
        assert valid.validation.rejected_count == 1
        assert valid.warnings[0].code == "invalid_provenance"


@pytest.mark.parametrize("changes", [
    {"url": "http://www.amazon.com/s?k=fixture"}, {"url": "https://127.0.0.1/"},
    {"url": "https://user:password@www.amazon.com/s"}, {"url": "https://www.amazon.com/s?api_key=private"},
    {"query": {"client_secret": "private"}}, {"cache_reused": "false"}, {"method": []},
    {"status_code": True}, {"source": "reddit"}, {"operation": "bad\nheader"},
])
def test_unsafe_journal_is_rejected_before_it_can_be_persisted(changes, raw_sources):
    result = raw_sources["amazon"]
    # Frozen metadata remains mutable by hostile providers via object.__setattr__.
    trace = copy.deepcopy(result.request_metadata[0])
    for name, value in changes.items(): object.__setattr__(trace, name, value)
    result.request_metadata[0] = trace
    with pytest.raises(CollectionError) as caught:
        validate_collection_result("amazon", result, now=NOW)
    assert caught.value.warning.code == "invalid_contract"
    assert "private" not in caught.value.warning.message


@pytest.mark.parametrize("query", [{"nested": [{"x": []} for _ in range(201)]}, {"x": float("nan")}, {1: "non-string-key"}])
def test_diagnostic_json_shape_is_bounded(query, raw_sources):
    raw_sources["amazon"].request_metadata[0] = replace(raw_sources["amazon"].request_metadata[0], query=query)
    with pytest.raises(CollectionError): validate_collection_result("amazon", raw_sources["amazon"], now=NOW)


def test_cyclic_diagnostic_query_is_rejected_without_recursing_forever(raw_sources):
    cyclic = {}
    cyclic["self"] = cyclic
    raw_sources["amazon"].request_metadata[0] = replace(raw_sources["amazon"].request_metadata[0], query=cyclic)
    with pytest.raises(CollectionError): validate_collection_result("amazon", raw_sources["amazon"], now=NOW)


def test_candidate_budget_is_checked_before_record_iteration(raw_sources):
    result = raw_sources["amazon"]
    result.records = [None] * (MAX_CANDIDATES + 1)
    valid = validate_collection_result("amazon", result, now=NOW)
    assert valid.status == "failed" and valid.validation.rejected_count == MAX_CANDIDATES + 1
    assert valid.warnings[0].code == "candidate_limit"


def test_dedup_keeps_first_snapshot_and_never_boosts_or_sorts_score(raw_sources):
    duplicate_with_new_request(raw_sources["google_trends"], score=99)
    sources = validate(raw_sources)
    result = sources["google_trends"]
    assert [record.score for record in result.records] == [0, 20]
    assert result.validation.valid_count == 3 and result.validation.duplicate_count == 1
    assert result.validation.rejected_count == 0 and result.validation.valid_ratio == 1
    assert result.status == "success" and len(result.request_metadata) == 2
    data = prepare(sources)
    assert data.quality_assessment.status == "sufficient"
    assert data.quality_assessment.duplicate_count == 1


def test_same_keyword_in_different_geo_timeframe_is_not_merged_or_counted_twice_for_gate(collection_factory, raw_sources):
    batches = [collection_factory("google_trends", [keyword("same", 20, geo=geo, timeframe=frame)])
               for geo, frame in [("US", "today 3-m"), ("VN", "today 3-m"), ("US", "today 12-m")]]
    raw_sources["google_trends"] = CollectionResult.from_records("google_trends", [item for batch in batches for item in batch.records],
        request_metadata=[trace for batch in batches for trace in batch.request_metadata])
    sources = validate(raw_sources)
    assert len(sources["google_trends"].records) == 3
    quality = prepare(sources).quality_assessment
    assert not quality.gate_passed and quality.qualifying_keyword_count == 1


def test_amazon_asin_dedup_keeps_all_listing_evidence_not_a_mixed_price(raw_sources):
    duplicate = duplicate_with_new_request(raw_sources["amazon"])
    duplicate.title, duplicate.price, duplicate.price_amount = "Later snapshot", "$99.99", "99.99"
    valid = validate_collection_result("amazon", raw_sources["amazon"], now=NOW)
    assert len(valid.records) == 1 and len(valid.records[0].listings) == 2
    assert valid.records[0].price == "$12.50" and valid.records[0].title == "Fixture source product"
    assert valid.validation.duplicate_count == 1
    assert len(raw_sources["amazon"].records[0].listings) == 1


def test_equal_titles_with_distinct_asin_and_post_ids_are_retained(collection_factory):
    amazon = validate_collection_result("amazon", collection_factory("amazon", [product(), product("B000000002")]), now=NOW)
    reddit = validate_collection_result("reddit", collection_factory("reddit", [discussion(), discussion("def456")]), now=NOW)
    assert len(amazon.records) == len(reddit.records) == 2
    assert len(DataProcessor()._process_products(amazon.records)) == len(DataProcessor()._process_discussions(reddit.records)) == 2


def test_duplicate_evidence_ids_are_invalid_not_neutral_duplicates(raw_sources):
    raw_sources["amazon"].records.append(raw_sources["amazon"].records[0])
    valid = validate_collection_result("amazon", raw_sources["amazon"], now=NOW)
    assert valid.validation.rejected_count == 1 and valid.validation.duplicate_count == 0
    assert valid.validation.valid_ratio == 0.5


def test_bad_record_type_is_counted_and_does_not_discard_valid_records(raw_sources):
    raw_sources["amazon"].records += [None, {"title": "untyped"}]
    valid = validate_collection_result("amazon", raw_sources["amazon"], now=NOW)
    assert valid.validation.to_dict()["rejection_counts"] == {"invalid_schema": 2}
    assert len(valid.records) == 1


def test_processor_uses_stable_keys_and_owns_deep_copies(raw_sources):
    sources = validate(raw_sources)
    data = prepare(sources)
    data.keywords[0].provenance.query["keywords"].append("changed")
    data.keywords[0].time_series.clear()
    assert len(sources["google_trends"].records[0].time_series) == 4
    assert sources["google_trends"].records[0].provenance.query["keywords"] == ["one", "two"]
    assert DataProcessor()._process_products([ProductItem("No ASIN")]) == []
    assert DataProcessor()._process_discussions([DiscussionItem("No post ID")]) == []


def test_raw_and_derived_metric_views_are_independent_and_truthful(raw_sources):
    data = prepare(validate(raw_sources))
    serialized = data.to_dict()
    observed = serialized["keywords"][0]
    assert observed["raw_metric"] == {"score": 0}
    assert observed["derived_metric"]["growth_percent"] == 0
    assert serialized["products"][0]["raw_metric"]["price_currency"] == "$"
    assert serialized["products"][0]["derived_metric"] == {}
    observed["raw_metric"]["score"] = 99
    observed["derived_metric"]["recent_mean"] = 99
    assert data.keywords[0].score == data.keywords[0].metrics.recent_mean == 0
    assert has_sufficient_evidence(data)


@pytest.mark.parametrize("field", ["keywords", "products"])
def test_assessment_cannot_be_reused_after_source_values_change(field, raw_sources, monkeypatch):
    data = prepare(validate(raw_sources))
    if field == "keywords": data.keywords[0].score = 99
    else: data.products[0].price = "$999.99"
    assert not has_sufficient_evidence(data)
    analyzer = LLMAnalyzer()
    monkeypatch.setattr(analyzer, "_call_ollama", lambda *a, **kw: pytest.fail("No AI after evidence changed"))
    assert analyzer.analyze("Fixture", data).analysis_status == "insufficient_data"


def test_processor_changes_invalidate_the_source_context(raw_sources):
    sources = validate(raw_sources)
    data = prepare(sources)
    data.keywords[0].score = 99
    quality = assess_data_quality(data, sources)
    assert quality.status == "insufficient"
    assert "evidence_context_mismatch" in {issue.code for issue in quality.issues}


def test_score_and_url_only_can_never_open_the_new_gate(raw_sources, monkeypatch):
    for record in raw_sources["google_trends"].records: record.time_series = []
    data = prepare(validate(raw_sources))
    assert not has_sufficient_evidence(data)
    analyzer = LLMAnalyzer()
    monkeypatch.setattr(analyzer, "_call_ollama", lambda *a, **kw: pytest.fail("No AI without measured series"))
    section = analyzer.analyze("Fixture", data)
    assert not section.ideas and section.analysis_status == "insufficient_data"


def test_unvalidated_collections_and_client_flags_cannot_open_gate(raw_sources):
    data = prepare(raw_sources)
    assert not has_sufficient_evidence(data)
    naked = NicheData("Fixture", "", keywords=raw_sources["google_trends"].records, products=raw_sources["amazon"].records)
    assert not has_sufficient_evidence(naked)


def test_record_rejection_changes_ratio_not_observed_scores(raw_sources):
    raw_sources["amazon"].records.append(ProductItem("No provenance"))
    data = prepare(validate(raw_sources))
    assessment = data.quality_assessment
    assert assessment.gate_passed and assessment.status == "partial"
    assert assessment.valid_ratio == 0.75 and assessment.rejected_count == 1
    assert [item.score for item in data.keywords] == [0, 20]


def test_partial_source_does_not_reweight_or_invent_missing_source_evidence(raw_sources):
    raw_sources["reddit"] = CollectionResult.from_records("reddit", [], ["Fixture blocked"])
    quality = prepare(validate(raw_sources)).quality_assessment
    assert quality.gate_passed and quality.status == "partial"
    assert quality.source_coverage == 2 / 3 and quality.valid_ratio == 1


def test_reddit_alone_is_sufficient_support_when_amazon_is_unconfigured(raw_sources, collection_factory):
    raw_sources["amazon"] = CollectionResult("amazon", status="not_configured")
    raw_sources["reddit"] = collection_factory("reddit", [discussion(score=0, comments=0)])
    quality = prepare(validate(raw_sources)).quality_assessment
    assert quality.status == "sufficient" and quality.supporting_record_count == 1


@pytest.mark.parametrize("all_disabled", [False, True])
def test_empty_denominators_are_unknown_not_fabricated_confidence(all_disabled):
    sources = {source: CollectionResult(source, status="not_configured") if all_disabled else CollectionResult.from_records(source, [])
               for source in ("google_trends", "amazon", "reddit")}
    quality = prepare(validate(sources)).quality_assessment
    assert quality.status == "insufficient" and quality.valid_ratio is None
    assert quality.source_coverage == (None if all_disabled else 0)
    json.dumps(quality.to_dict(), allow_nan=False)


def test_missing_context_or_unavailable_candidate_counts_are_explicit(raw_sources):
    sources = validate(raw_sources)
    data = prepare(sources)
    missing = assess_data_quality(data, {"google_trends": sources["google_trends"]})
    assert not missing.gate_passed and missing.valid_ratio is None
    sources["reddit"] = CollectionResult.from_records("reddit", [], ["Fixture collector error"])
    partial = assess_data_quality(data, sources)
    assert partial.gate_passed and partial.valid_ratio is None
    assert partial.to_dict()["validation_counts_complete"] is False


@pytest.mark.parametrize("path", ["/gp/bestsellers", "/Best-Sellers/zgbs", "/Any-Prefix/zgbs"])
def test_general_amazon_hubs_do_not_qualify_as_niche_support(path, raw_sources):
    result = raw_sources["amazon"]
    url = "https://www.amazon.com" + path
    query = {"source_type": "best_sellers", "niche": "Fixture", "search_term": None}
    result.request_metadata[0] = replace(result.request_metadata[0], url=url, operation="best_sellers", query=query)
    record = result.records[0]
    provenance = replace(record.provenance, query=query)
    listing = ProductListing("best_sellers", url, 1, None, None, None, provenance)
    result.records[0] = replace(record, source="Amazon Best Sellers", source_type="best_sellers", listing_url=url,
        listing_position=1, search_position=None, listing_rank=None, rank=None, is_sponsored=None, provenance=provenance, listings=[listing])
    sources = validate(raw_sources)
    assert len(sources["amazon"].records) == 1
    quality = prepare(sources).quality_assessment
    assert not quality.gate_passed and quality.supporting_record_count == 0


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://user:secret@example.test/", "https://example.test/\nheader", "https://example.test:invalid/", "https://example.test/\\evil"])
def test_evidence_url_checks_reject_unsafe_representations(url):
    assert not is_http_url(url)


def test_pipeline_exports_the_same_gate_in_json_markdown_and_diagnostics(tmp_path, raw_sources):
    collectors = {source: SimpleNamespace(collect=lambda niche, result=result: result) for source, result in raw_sources.items()}
    output = execute_pipeline(fast_mode=True, niche_list=[{"name": "Fixture"}], output_dir=str(tmp_path), collectors=collectors)
    assert output["success"] and output["metadata"]["data_quality"] == "sufficient"
    assessment = output["niches"]["Fixture"]["quality_assessment"]
    assert assessment == output["metadata"]["quality_assessments"]["Fixture"]
    diagnostics = json.loads((tmp_path / output["metadata"]["diagnostics_file"]).read_text(encoding="utf-8"))
    assert diagnostics["quality_assessments"]["Fixture"] == assessment
    assert "Validation và điều kiện dữ liệu" in output["markdown_content"]
    assert output["niches"]["Fixture"]["keywords"][0]["raw_metric"]["score"] == 0
    assert json.loads((tmp_path / "latest_data.json").read_text(encoding="utf-8")) == output


def llm_text():
    body = "### 1. Keyword\nFixture\n### 2. Phân tích\nObserved\n### 3. Idea sản phẩm\n"
    return body + "".join(f"{i}. **Fixture idea {i}**\n- **Bán cái gì**: Fixture\n- **Cho ai**: Cần kiểm chứng\n- **Vì sao nên bán bây giờ**: Suy luận cần kiểm chứng\n- **Dựa trên**: https://www.amazon.com/dp/B000000001\n" for i in (1, 2))


def test_insufficient_niche_is_separate_and_never_calls_ai(tmp_path, collection_factory, monkeypatch, grounded_payload_factory):
    calls = []
    def generated(self, prompt, **kwargs):
        self.attempted = True
        calls.append(prompt)
        return json.dumps(grounded_payload_factory(prompt=prompt))
    monkeypatch.setattr(LLMAnalyzer, "_call_ollama", generated)
    collectors = {
        "google_trends": SimpleNamespace(collect=lambda niche: collection_factory("google_trends", [keyword(), keyword("two", 20)] if niche["name"] == "Enough" else [keyword()])),
        "amazon": SimpleNamespace(collect=lambda niche: collection_factory("amazon", [product()])),
        "reddit": SimpleNamespace(collect=lambda niche: CollectionResult("reddit", status="not_configured")),
    }
    result = execute_pipeline(niche_list=[{"name": "Enough"}, {"name": "Insufficient"}], output_dir=str(tmp_path), collectors=collectors)
    assert len(calls) == 1 and json.loads(calls[0])["niche_name"] == "Enough"
    details = result["niches"]["Insufficient"]
    assert details["data_quality"] == "insufficient" and details["ideas"] == []
    assert details["analysis_status"] == "insufficient_data"
    diagnostic_section = result["markdown_content"].split("## Dữ liệu chưa đủ", 1)[1]
    assert "Insufficient" in diagnostic_section and "Fixture idea" not in diagnostic_section
    assert result["status"] == "partial" and result["metadata"]["data_quality"] == "partial"


def test_gate_decision_is_persisted_before_a_later_analysis_crash(tmp_path, raw_sources, monkeypatch):
    def crash(*a, **kw): raise RuntimeError("Fixture analysis crash")
    monkeypatch.setattr(LLMAnalyzer, "analyze", crash)
    collectors = {source: SimpleNamespace(collect=lambda niche, result=result: result) for source, result in raw_sources.items()}
    with pytest.raises(RuntimeError):
        execute_pipeline(niche_list=[{"name": "Fixture"}], output_dir=str(tmp_path), collectors=collectors)
    diagnostics = json.loads(next((tmp_path / "diagnostics").glob("*.json")).read_text(encoding="utf-8"))
    assert diagnostics["quality_assessments"]["Fixture"]["gate_passed"] is True
    assert not (tmp_path / "latest_data.json").exists()


def test_reporter_fails_closed_on_gate_and_analysis_disagreement(research_result_factory):
    from dataclasses import replace
    from src.models.research_result import thaw_json
    result = research_result_factory(state="insufficient")
    niches = thaw_json(result.niches)
    niches["Fixture"].update(keywords_content="UNSUPPORTED", analysis_text="UNSUPPORTED", ideas_content="UNSUPPORTED", analysis_status="success")
    metadata = thaw_json(result.metadata)
    metadata.update(category="<script>bad()</script>", warnings=["<img src=x>"])
    text = ReportGenerator().render(replace(result, metadata=metadata, niches=niches))
    assert "## Dữ liệu chưa đủ" in text and "UNSUPPORTED" not in text
    assert "<script>" not in text and "<img" not in text


def test_cache_before_quality_gate_v6_is_legacy(tmp_path):
    repository = ReportRepository(tmp_path)
    repository.save_latest({"metadata": {"data_policy": "live-only-v5"}, "markdown_content": "Historical", "niches": {}})
    assert repository.load_latest()["status"] == "legacy"


@pytest.mark.parametrize("values", [(1, 1, 1, 0, 1), (1, 1, 0, 1, 1), (True, 1, 0, 0, 1), (-1, 0, 0, 0, 0)])
def test_validation_statistics_cannot_claim_impossible_counts(values):
    with pytest.raises(ValueError): ValidationStats(*values)


def test_partial_unknown_points_are_retained_not_interpolated_or_used_as_latest_score(raw_sources):
    record = raw_sources["google_trends"].records[0]
    record.time_series += [TrendPoint("2026-10-20T01:00:00+00:00", None, False), TrendPoint("2026-10-20T02:00:00+00:00", 99, True)]
    record.metrics = calculate_trend_metrics(record.time_series)
    sources = validate(raw_sources)
    data = prepare(sources)
    assert data.quality_assessment.status == "partial" and data.quality_assessment.gate_passed
    assert data.keywords[0].score == 0 and data.keywords[0].time_series[-2].value is None
    assert data.keywords[0].metrics.valid_points == 4 and data.keywords[0].metrics.excluded_points == 2


def test_casefold_keyword_dedup_keeps_separate_request_journal(raw_sources, collection_factory):
    extra = collection_factory("google_trends", [keyword("ONE", 99)])
    raw_sources["google_trends"].records += extra.records
    raw_sources["google_trends"].request_metadata += extra.request_metadata
    result = validate_collection_result("google_trends", raw_sources["google_trends"], now=NOW)
    assert [record.keyword for record in result.records] == ["one", "two"]
    assert result.records[0].score == 0 and len(result.request_metadata) == 2
    assert result.validation.duplicate_count == 1


@pytest.mark.parametrize("kind", ["naive", "future", "reversed"])
def test_bad_request_clock_cannot_stamp_records_as_live(kind, raw_sources):
    trace = copy.deepcopy(raw_sources["amazon"].request_metadata[0])
    if kind == "naive": object.__setattr__(trace, "completed_at", "2026-10-21T00:00:00")
    elif kind == "future": object.__setattr__(trace, "completed_at", "2026-10-22T00:00:00+00:00")
    else: object.__setattr__(trace, "started_at", "2026-10-21T01:00:00+00:00")
    raw_sources["amazon"].request_metadata[0] = trace
    with pytest.raises(CollectionError): validate_collection_result("amazon", raw_sources["amazon"], now=NOW)


@pytest.mark.parametrize("changes", [{"gate_passed": 1}, {"status": "insufficient"}])
def test_inconsistent_gate_flags_are_not_authority(changes, raw_sources):
    data = prepare(validate(raw_sources))
    data.quality_assessment = replace(data.quality_assessment, **changes)
    assert not has_sufficient_evidence(data)


def test_untyped_quality_status_is_rejected_without_crashing(raw_sources):
    data = prepare(validate(raw_sources))
    data.quality_assessment = replace(data.quality_assessment, status=[])
    assert not has_sufficient_evidence(data)


def test_free_text_signal_cannot_override_measured_metrics(raw_sources):
    raw_sources["google_trends"].records[0].signal_summary = "Market demand grew 999 percent."
    result = validate_collection_result("google_trends", raw_sources["google_trends"], now=NOW)
    assert result.validation.rejected_count == 1 and result.records[0].keyword == "two"


def test_warning_container_budget_is_checked_before_iteration(raw_sources):
    raw_sources["amazon"].warnings = [None] * (MAX_WARNINGS + 1)
    with pytest.raises(CollectionError): validate_collection_result("amazon", raw_sources["amazon"], now=NOW)


@pytest.mark.parametrize("source", [None, [], "unknown"])
def test_source_contract_rejects_unknown_or_untyped_identifiers(source, raw_sources):
    with pytest.raises(CollectionError): validate_collection_result(source, raw_sources["amazon"], now=NOW)


@pytest.mark.parametrize("field", ["score", "point", "query"])
def test_python_boolean_numeric_equality_cannot_hide_snapshot_changes(field, raw_sources):
    sources = validate(raw_sources)
    data = prepare(sources)
    if field == "score": data.keywords[0].score = False
    elif field == "point": data.keywords[0].time_series[0] = replace(data.keywords[0].time_series[0], value=False)
    else: data.products[0].provenance.query["fixture"] = 1
    assessment = assess_data_quality(data, sources)
    assert not assessment.gate_passed
    assert "evidence_context_mismatch" in {issue.code for issue in assessment.issues}


def test_record_query_cannot_leak_secrets_not_present_in_request_journal(raw_sources):
    result = raw_sources["amazon"]
    record = result.records[0]
    provenance = replace(record.provenance, query={**record.provenance.query, "client_secret": "fixture-private-secret"})
    result.records[0] = replace(record, provenance=provenance, listings=[replace(record.listings[0], provenance=provenance)])
    validated = validate_collection_result("amazon", result, now=NOW)
    assert validated.records == [] and validated.warnings[0].code == "invalid_provenance"
    assert "fixture-private-secret" not in json.dumps(validated.status_dict(include_requests=True))


@pytest.mark.parametrize("changes", [{"request_id": {}}, {"operation": []}, {"retryable": 1}])
def test_invalid_warning_metadata_is_not_allowed_into_diagnostics(changes, raw_sources):
    result = raw_sources["amazon"]
    result.warnings = [replace(CollectionWarning("fixture", "Fixture warning"), **changes)]
    with pytest.raises(CollectionError): validate_collection_result("amazon", result, now=NOW)


@pytest.mark.parametrize("changes", [{"started_at": []}, {"completed_at": "not-a-timestamp"},
    {"completed_at": "2026-10-20T00:00:00+00:00"}, {"completed_at": "2026-10-22T00:00:00+00:00"}])
def test_invalid_collection_timing_cannot_break_persistence(changes, raw_sources):
    result = raw_sources["amazon"]
    for name, value in changes.items(): setattr(result, name, value)
    with pytest.raises(CollectionError): validate_collection_result("amazon", result, now=NOW)
