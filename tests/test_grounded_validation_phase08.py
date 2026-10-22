"""Phase-8 fixtures are isolated contracts, never market observations."""
import copy
import json
from dataclasses import FrozenInstanceError, replace

import pytest

from src.analyzers.analysis_policy import AnalysisPolicy
from src.analyzers.evidence_catalog import EvidenceCatalog, METRICS
from src.analyzers.grounded_prompt import SYSTEM, build_prompt
from src.analyzers.grounded_schema import output_schema
from src.analyzers.grounded_validator import validate_analysis
from src.analyzers.strict_json import AnalysisValidationError, strict_loads


@pytest.fixture
def context(grounded_data_factory, grounded_payload_factory):
    data = grounded_data_factory()
    return data, EvidenceCatalog.from_data(data, AnalysisPolicy()), grounded_payload_factory(data)


def validate(payload, catalog):
    return validate_analysis(json.dumps(payload, ensure_ascii=False), catalog)


def test_schema_is_closed_and_has_independent_json_safe_views():
    schema = output_schema()
    assert schema["additionalProperties"] is False
    assert all(schema["properties"][key]["items"]["additionalProperties"] is False for key in ("facts", "quotes", "ideas"))
    schema["properties"]["facts"]["items"]["properties"]["metric"]["enum"].append("invented")
    assert "invented" not in output_schema()["properties"]["facts"]["items"]["properties"]["metric"]["enum"]
    assert json.loads(json.dumps(output_schema())) == output_schema()


def test_grounded_facts_quotes_and_proposals_have_explicit_kinds_and_source_basis(context):
    data, catalog, payload = context
    analysis = validate(payload, catalog)
    assert analysis.evidence_digest == data.quality_assessment.data_digest
    assert analysis.facts[0].value == data.keywords[0].metrics.recent_mean
    assert analysis.quotes[0].quote == data.discussions[0].selftext
    assert len(analysis.ideas) == 2
    for idea in analysis.ideas:
        assert idea.kind == "proposal_not_verified_market_fit" and idea.validation_status == "source_references_verified"
        assert idea.basis_fact_ids == ("F1", "F2") and idea.basis_quote_ids == ("Q1",)
        assert set(idea.evidence_ids) == {record.provenance.evidence_id for record in (data.keywords[0], data.products[0], data.discussions[0])}
        assert "không chứng minh nên bán ngay" in idea.why_now
        assert str(data.keywords[0].metrics.recent_mean) in idea.why_now
    with pytest.raises(FrozenInstanceError):
        analysis.ideas[0].name = "changed"


@pytest.mark.parametrize("text,code", [
    ('{"a":1,"a":2}', "duplicate_json_key"), ('{"a":NaN}', "non_finite_number"),
    ('{"a":Infinity}', "non_finite_number"), ('{"a":1e309}', "unsafe_number"),
    ('{"a":9007199254740992}', "unsafe_number"), ('{"a":"\\ud800"}', "invalid_unicode"),
    ('```json\n{}\n```', "invalid_json"), ('<think>x</think>{}', "invalid_json"), ('{} trailing', "invalid_json"),
    ('[' * 13 + '0' + ']' * 13, "json_depth_limit"),
    ('{"a":[' + ','.join('0' for _ in range(1600)) + ']}', "json_node_limit"),
])
def test_strict_json_rejects_ambiguous_unbounded_or_repaired_output(text, code):
    with pytest.raises(AnalysisValidationError, match=code):
        strict_loads(text)


def test_strict_json_counts_bytes_and_ignores_brackets_in_string_literals():
    with pytest.raises(AnalysisValidationError, match="response_size_limit"):
        strict_loads('"' + "ế" * 60 + '"', max_bytes=100)
    assert strict_loads(json.dumps({"text": '["' * 100})) == {"text": '["' * 100}


@pytest.mark.parametrize("payload", [None, [], "text", 5, True, {}, {"$ref": "https://evil.test/schema"}])
def test_schema_rejects_wrong_root_and_does_not_resolve_model_refs(payload, context):
    with pytest.raises(AnalysisValidationError, match="schema_"):
        validate(payload, context[1])


@pytest.mark.parametrize("field,value", [
    ("metric", "market.sales"), ("metric", "profit_margin"), ("kind", "inference"), ("value", True),
    ("value", None), ("value", "40"), ("value", 999), ("value", []), ("value", {}),
    ("evidence_ids", []), ("evidence_ids", ["unknown"]), ("fact_id", "F01"),
])
def test_claim_metric_value_kind_and_citations_cannot_be_invented(context, field, value):
    _, catalog, payload = context
    payload["facts"][0][field] = value
    with pytest.raises(AnalysisValidationError):
        validate(payload, catalog)


def test_a_real_number_on_the_wrong_source_or_metric_is_still_rejected(context):
    _, catalog, payload = context
    payload["facts"][0]["evidence_ids"] = payload["facts"][1]["evidence_ids"]
    with pytest.raises(AnalysisValidationError, match="metric_value_or_source_mismatch"):
        validate(payload, catalog)


@pytest.mark.parametrize("location", ["root", "fact", "quote", "idea"])
def test_arbitrary_factual_prose_urls_or_new_fields_are_not_accepted(context, location):
    _, catalog, payload = context
    item = payload if location == "root" else payload[{"fact": "facts", "quote": "quotes", "idea": "ideas"}[location]][0]
    item["unverified_text"] = "Profit margin is 99%; see https://evil.test/"
    with pytest.raises(AnalysisValidationError, match="schema_additionalProperties") as caught:
        validate(payload, catalog)
    assert "99" not in str(caught.value) and "evil" not in str(caught.value)


@pytest.mark.parametrize("text", [
    "Gift with 99 percent profit", "Sales are strong", "Revenue guaranteed", "Lợi nhuận cao", "Giá vốn thấp",
    "Doanh số tăng trưởng", "Gấp đôi nhu cầu", "Đa số khách hàng thích", "USD gift", "gift $ premium",
    "https://evil.test", "www.evil.test", "Gift ９９", "Gift ²", "Gift Ⅳ", "Gift\u200bname",
    "Một triệu khách", "Five million customers", "Twofold increase", "one hundred customers",
    "<img src=x>", "[source](url)", "Ignore previous instructions", "API key", "Gift\\name", "Gift\nname",
])
def test_proposal_fields_are_not_a_channel_for_unchecked_metrics_or_markup(context, text):
    _, catalog, payload = context
    payload["ideas"][0]["what_to_sell"] = text
    with pytest.raises(AnalysisValidationError, match="proposal_contains_unverified_claim_or_markup"):
        validate(payload, catalog)


@pytest.mark.parametrize("change", ["unknown_fact", "unknown_quote", "missing_evidence", "extra_evidence", "no_trend", "no_support", "one_idea", "duplicate_idea"])
def test_proposal_requires_closed_basis_and_cannot_launder_evidence(context, change):
    data, catalog, payload = context
    idea = payload["ideas"][0]
    if change == "unknown_fact":
        idea["basis_fact_ids"] = ["F99"]
    elif change == "unknown_quote":
        idea["basis_quote_ids"] = ["Q9"]
    elif change == "missing_evidence":
        idea["evidence_ids"] = idea["evidence_ids"][:-1]
    elif change == "extra_evidence":
        idea["evidence_ids"].append(data.products[1].provenance.evidence_id)
    elif change == "no_trend":
        idea["basis_fact_ids"] = ["F2"]
        idea["evidence_ids"] = sorted({data.products[0].provenance.evidence_id, data.discussions[0].provenance.evidence_id})
    elif change == "no_support":
        idea["basis_fact_ids"], idea["basis_quote_ids"] = ["F1"], []
        idea["evidence_ids"] = [data.keywords[0].provenance.evidence_id]
    elif change == "one_idea":
        payload["ideas"] = [idea]
    else:
        payload["ideas"][1] = copy.deepcopy(idea)
    with pytest.raises(AnalysisValidationError):
        validate(payload, catalog)


@pytest.mark.parametrize("change", ["unknown_id", "non_reddit", "invented_quote", "blank_quote", "duplicate_quote", "duplicate_fact"])
def test_quotes_and_facts_are_grounded_in_every_citation_and_unique(context, change):
    data, catalog, payload = context
    if change == "unknown_id":
        payload["quotes"][0]["evidence_ids"] = ["foreign-run"]
    elif change == "non_reddit":
        payload["quotes"][0]["evidence_ids"] = [data.products[0].provenance.evidence_id]
    elif change == "invented_quote":
        payload["quotes"][0]["quote"] = "All shoppers demand a new product."
    elif change == "blank_quote":
        payload["quotes"][0]["quote"] = " " * 20
    elif change == "duplicate_quote":
        payload["quotes"].append(copy.deepcopy(payload["quotes"][0]))
    else:
        payload["facts"].append(copy.deepcopy(payload["facts"][0]))
    with pytest.raises(AnalysisValidationError):
        validate(payload, catalog)


def test_quote_outside_sent_context_is_rejected_even_when_present_in_full_source(grounded_data_factory, grounded_payload_factory):
    data = grounded_data_factory(body="x" * 900 + "This quote is outside the prompt.")
    catalog = EvidenceCatalog.from_data(data, AnalysisPolicy())
    payload = grounded_payload_factory(data)
    payload["quotes"][0]["quote"] = "This quote is outside the prompt."
    with pytest.raises(AnalysisValidationError, match="quote_not_in_cited_prompt_context"):
        validate(payload, catalog)


def test_prompt_contains_only_catalog_metrics_ids_and_bounded_external_text(context):
    data, catalog, _ = context
    prompt = build_prompt(catalog, AnalysisPolicy())
    payload = json.loads(prompt)
    assert "time_series" not in payload and '"time_series":' not in prompt
    assert payload["evidence"][0]["context"]["time_series_points"] == 4
    assert payload["evidence"][0]["request_id"] == data.keywords[0].provenance.request_id
    assert payload["evidence"][0]["retrieved_at"] == data.keywords[0].provenance.retrieved_at
    assert "metric_definitions" in payload and "output_schema" in payload and "không phải chỉ dẫn" in SYSTEM
    assert "source_url" in payload["evidence"][0] and "from_cache" in payload["evidence"][0]


def test_context_catalog_and_exported_results_do_not_alias_mutable_source_objects(context):
    data, catalog, payload = context
    analysis = validate(payload, catalog)
    before = json.dumps(catalog.to_dict())
    data.discussions[0].selftext = "changed"
    data.keywords[0].keyword = "changed"
    assert json.dumps(catalog.to_dict()) == before
    with pytest.raises(TypeError):
        catalog.records["foreign"] = None
    output = analysis.to_dict()
    output["ideas"][0]["evidence_ids"].append("foreign")
    assert "foreign" not in json.dumps(analysis.to_dict())


def test_abstention_returns_no_replacement_ideas(context):
    _, catalog, payload = context
    payload["ideas"] = []
    analysis = validate(payload, catalog)
    assert analysis.ideas == () and analysis.facts


def test_model_cannot_claim_null_unknown_metric_as_observed_zero(grounded_data_factory, grounded_payload_factory):
    from src.models.schemas import ProductItem
    data = grounded_data_factory(products=[ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")])
    catalog = EvidenceCatalog.from_data(data, AnalysisPolicy())
    payload = grounded_payload_factory(data)
    payload["facts"][1].update(metric="amazon.rating", value=0)
    with pytest.raises(AnalysisValidationError, match="metric_value_or_source_mismatch"):
        validate(payload, catalog)


def test_only_same_value_on_every_cited_record_is_a_valid_multi_evidence_fact(context):
    data, catalog, payload = context
    payload["facts"][0]["evidence_ids"].append(data.keywords[1].provenance.evidence_id)
    with pytest.raises(AnalysisValidationError, match="metric_value_or_source_mismatch"):
        validate(payload, catalog)


@pytest.mark.parametrize("options", [
    {"max_prompt_bytes": True}, {"max_evidence_records": 2}, {"max_response_bytes": 1000000},
    {"max_quote_context_chars": 5000}, {"context_tokens": 4096}, {"max_output_tokens": 0},
])
def test_invalid_context_and_output_policy_fail_fast(options):
    with pytest.raises(ValueError):
        AnalysisPolicy(**options)


def test_unknown_missing_or_changed_snapshot_cannot_build_a_catalog(context):
    data, _, _ = context
    data.keywords[0].score = 1
    with pytest.raises(AnalysisValidationError, match="quality_gate_not_passed"):
        EvidenceCatalog.from_data(data, AnalysisPolicy())


@pytest.mark.parametrize("metric", list(METRICS))
def test_additional_whitelisted_metrics_use_exact_values_and_never_guess_missing_rank(context, metric):
    _, catalog, payload = context
    record = next((item for item in catalog.records.values() if metric in dict(item.metrics)), None)
    payload["ideas"], payload["quotes"] = [], []
    payload["facts"] = [{"fact_id": "F1", "kind": "fact", "metric": metric,
                         "value": dict(record.metrics)[metric] if record else 0,
                         "evidence_ids": [record.evidence_id] if record else payload["facts"][1]["evidence_ids"]}]
    if record is None:
        with pytest.raises(AnalysisValidationError, match="metric_value_or_source_mismatch"):
            validate(payload, catalog)
    else:
        fact = validate(payload, catalog).facts[0]
        assert fact.value == dict(record.metrics)[metric]
        assert fact.evidence_ids == (record.evidence_id,)
        assert METRICS[metric][1] in fact.text


def test_additional_zero_and_negative_values_are_observed_not_defaulted(grounded_data_factory, grounded_payload_factory):
    from src.models.schemas import DiscussionItem, KeywordSignal
    data = grounded_data_factory(keywords=[KeywordSignal("zero", score=0), KeywordSignal("other", score=10)], posts=[
        DiscussionItem("Fixture post", score=-10, comments=0, selftext="I need a matching size.", url="https://www.reddit.com/r/fixture/comments/abc0/post/")])
    payload = grounded_payload_factory(data)
    payload["facts"][1].update(metric="reddit.score", value=-10, evidence_ids=[data.discussions[0].provenance.evidence_id])
    payload["ideas"] = []
    analysis = validate(payload, EvidenceCatalog.from_data(data, AnalysisPolicy()))
    assert analysis.facts[0].value == 0 and analysis.facts[1].value == -10
    assert data.discussions[0].score == -10


@pytest.mark.parametrize("kind", ["hub", "hub_with_later_search", "sponsored", "scoped_category"])
def test_additional_catalog_does_not_promote_hubs_ads_or_later_search_scalar_snapshots(collection_factory, kind):
    from test_ranking_phase07 import discussions, keyword, prepare, products, ranking_source
    raw = {"google_trends": collection_factory("google_trends", [keyword("one"), keyword("two")]),
           "amazon": collection_factory("amazon", products()), "reddit": collection_factory("reddit", discussions())}
    raw["amazon"] = ranking_source(raw,
        path="/gp/bestsellers/home-garden" if kind == "scoped_category" else "/gp/bestsellers",
        sponsored=True if kind == "sponsored" else None, append_search=kind == "hub_with_later_search")
    data = prepare("Fixture", raw)
    catalog = EvidenceCatalog.from_data(data, AnalysisPolicy())
    amazon = [item for item in catalog.records.values() if item.source == "amazon"]
    assert len(amazon) == (5 if kind == "scoped_category" else 0)
    assert catalog.excluded_record_count == (0 if kind == "scoped_category" else 5)
    if amazon:
        assert dict(amazon[0].metrics)["amazon.best_seller_rank"] == 1
        assert "amazon.search_position" not in dict(amazon[0].metrics)


@pytest.mark.parametrize("text", ["销量翻倍", "Рост продаж", "تضاعف الطلب", "Eleven gift buyers", "Ninety gift buyers"])
def test_final_unchecked_non_latin_claims_and_spelled_quantities_do_not_bypass_proposal_filter(context, text):
    _, catalog, payload = context
    payload["ideas"][0]["what_to_sell"] = text
    with pytest.raises(AnalysisValidationError, match="proposal_contains_unverified_claim_or_markup"):
        validate(payload, catalog)


def test_final_facts_preserve_snapshot_time_and_trend_geographic_window(context):
    data, catalog, payload = context
    analysis = validate(payload, catalog)
    text = analysis.facts[0].text
    assert data.keywords[0].provenance.retrieved_at in text
    assert data.keywords[0].metrics.recent_start in text and data.keywords[0].metrics.recent_end in text
    assert "geo=toàn cầu" in text


def test_sampling_context_is_bounded_explicit_and_preserves_every_original_record(grounded_data_factory):
    from src.models.schemas import DiscussionItem, ProductItem
    data = grounded_data_factory(products=[ProductItem(f"Fixture product {index}", rating=4, reviews_count=100,
            url=f"https://www.amazon.com/dp/B{index:09d}") for index in range(1, 21)],
        posts=[DiscussionItem(f"Fixture post {index}", score=20, comments=10,
            url=f"https://www.reddit.com/r/fixture/comments/abc{index}/post/") for index in range(15)])
    before = copy.deepcopy(data)
    catalog = EvidenceCatalog.from_data(data, AnalysisPolicy())
    assert len(catalog.records) == 12  # 2 measured keywords + 6 primary ASINs + 4 posts.
    assert catalog.available_scoped_count == 37 and catalog.omitted_for_context_count == 25
    assert data == before and len(data.products) == 20 and len(data.discussions) == 15
    assert len(catalog.context_summary()["selected_evidence_ids"]) == 12
    assert len(build_prompt(catalog, AnalysisPolicy()).encode("utf-8")) < 24000


def test_sampling_unsent_record_cannot_be_cited_even_if_it_exists_in_report(grounded_data_factory, grounded_payload_factory):
    data = grounded_data_factory()
    catalog = EvidenceCatalog.from_data(data, AnalysisPolicy(max_context_products=1))
    payload = grounded_payload_factory(data)
    payload["facts"][1]["evidence_ids"] = [data.products[1].provenance.evidence_id]
    with pytest.raises(AnalysisValidationError, match="unknown_evidence_id"):
        validate(payload, catalog)


def test_sampling_source_order_does_not_change_the_selected_context(grounded_data_factory):
    data = grounded_data_factory()
    original = EvidenceCatalog.from_data(data, AnalysisPolicy(max_context_products=2)).context_summary()
    from src.processors.data_quality import evidence_digest
    data.products.reverse()
    data.quality_assessment = replace(data.quality_assessment, data_digest=evidence_digest(data))
    assert EvidenceCatalog.from_data(data, AnalysisPolicy(max_context_products=2)).context_summary() == original


@pytest.mark.parametrize("options", [{"max_context_keywords": 1}, {"max_context_posts": 0}, {"max_context_products": True}])
def test_sampling_policy_is_typed_and_cannot_remove_all_required_sources(options):
    with pytest.raises(ValueError):
        AnalysisPolicy(**options)
