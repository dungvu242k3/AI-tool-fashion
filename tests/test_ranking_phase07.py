"""Isolated phase-7 fixtures, never market data. External HTTP stays blocked."""
import copy
import json
import math
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.collectors.validation import validate_collection_result
from src.models.collection import CollectionResult
from src.models.commerce import ProductListing
from src.models.schemas import DiscussionItem, KeywordSignal, NicheData, ProductItem
from src.models.trends import TrendPoint
from src.pipeline import execute_pipeline
from src.processors.data_processor import DataProcessor
from src.processors.data_quality import assess_data_quality, evidence_digest
from src.processors.trend_metrics import calculate_trend_metrics
from src.ranking.policy import COMPONENTS, MAX_NICHES, RankingPolicy
from src.ranking.service import RankingService
from src.reporters.ranking_renderer import RankingRenderer
from src.reporters.report_repository import ReportRepository

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def keyword(name, previous=20, recent=40, *, geo="", shift=0):
    points = [TrendPoint((NOW - timedelta(days=4 - index + shift)).isoformat(), value, False)
              for index, value in enumerate([previous, previous, recent, recent])]
    return KeywordSignal(name, time_series=points, metrics=calculate_trend_metrics(points), geo=geo)


def products(count=5, rating=4, reviews=100):
    return [ProductItem(f"Fixture product {index}", rating=rating, reviews_count=reviews,
                        url=f"https://www.amazon.com/dp/B{index:09d}") for index in range(1, count + 1)]


def discussions(count=3, score=20, comments=10):
    return [DiscussionItem(f"Fixture post {index}", score=score, comments=comments,
                           url=f"https://www.reddit.com/r/fixture/comments/abc{index}/post/") for index in range(count)]


def prepare(name, sources):
    validated = {source: validate_collection_result(source, result, now=NOW) for source, result in sources.items()}
    data = DataProcessor().process({
        "niche": name, "collected_at": NOW.isoformat(),
        "keywords_data": validated["google_trends"].records,
        "products_data": validated["amazon"].records, "discussions_data": validated["reddit"].records,
    })
    data.quality_assessment = assess_data_quality(data, validated)
    return data


@pytest.fixture
def build(collection_factory):
    def create(name="Fixture", *, google=None, keywords=None, amazon=None, reddit=None, omitted=()):
        raw = {
            "google_trends": google if google is not None else collection_factory("google_trends", keywords if keywords is not None else [keyword("one"), keyword("two")]),
            "amazon": collection_factory("amazon", amazon if amazon is not None else products()),
            "reddit": collection_factory("reddit", reddit if reddit is not None else discussions()),
        }
        raw.update({source: CollectionResult(source, status="not_configured") for source in omitted})
        return prepare(name, raw), raw
    return create


@pytest.fixture
def comparable_pair(build, collection_factory):
    shared = collection_factory("google_trends", [keyword("alpha one"), keyword("alpha two"),
                                                 keyword("bravo one", 20, 20), keyword("bravo two", 20, 20)])
    alpha, raw_a = build("Alpha", google=replace(shared, records=shared.records[:2]))
    bravo, raw_b = build("Bravo", google=replace(shared, records=shared.records[2:]))
    return alpha, bravo, {"Alpha": raw_a, "Bravo": raw_b}


def components(row):
    return {item.key: item for item in row.components}


def test_all_components_have_reproducible_metrics_breakdown_and_provenance(build):
    data, _ = build()
    result = RankingService().rank([data])
    row = result.ranking[0]
    items = components(row)
    assert result.status == "available" and row.rank == 1 and row.total_score == row.observed_score
    assert tuple(items) == COMPONENTS
    assert items["momentum"].score == round(100 * 40 / 60, 6)
    assert items["recent_interest"].score == 40
    assert items["commerce"].score == 40
    assert items["community"].score == round(100 * math.log1p(30) / math.log1p(100), 6)
    assert items["competition"].score == 50
    assert row.observed_score == round(sum(item.contribution for item in row.components), 6)
    assert row.confidence == 100 and row.component_coverage == 1
    assert row.score_upper_bound == row.total_score
    for item in row.components:
        assert item.formula and item.inputs and item.reason == "observed_sample_only"
        assert item.contribution == round(item.score * item.weight, 6)
        assert all(observation.evidence_id and observation.request_id and observation.retrieved_at == NOW.isoformat(timespec="milliseconds") for observation in item.inputs)


def test_canonical_ranking_is_order_independent_and_explains_differences(comparable_pair):
    alpha, bravo, _ = comparable_pair
    first = RankingService().rank([bravo, alpha]).to_dict()
    second = RankingService().rank([alpha, bravo]).to_dict()
    assert first == second
    assert [(row["niche"], row["rank"]) for row in first["ranking"]] == [("Alpha", 1), ("Bravo", 2)]
    assert "Alpha" in first["ranking"][1]["explanation"]
    assert "điểm đóng góp quan sát" in first["ranking"][1]["explanation"]
    assert first["ranking"][0]["components"][0]["score"] > first["ranking"][1]["components"][0]["score"]


def test_missing_source_does_not_reweight_or_impute_observations(build):
    complete, _ = build()
    missing, _ = build(omitted=("reddit",))
    service = RankingService()
    complete_row = service.rank([complete]).ranking[0]
    result = service.rank([missing])
    row = result.ranking[0]
    item = components(row)["community"]
    assert result.status == "partial" and row.total_score is None
    assert item.score is item.contribution is None and item.weight == 0.2
    assert row.observed_score == round(complete_row.observed_score - components(complete_row)["community"].contribution, 6)
    assert row.score_upper_bound == round(row.observed_score + 20, 6)
    assert row.confidence == 80 and row.component_coverage == 0.8
    assert "không reweight" in row.explanation
    for key in ("momentum", "recent_interest", "commerce", "competition"):
        assert components(row)[key].contribution == components(complete_row)[key].contribution


def test_different_trends_requests_remove_interest_for_entire_comparison(build):
    alpha, _ = build("Alpha", keywords=[keyword("one", 20, 40), keyword("two", 20, 40)])
    bravo, _ = build("Bravo", keywords=[keyword("one", 20, 20), keyword("two", 20, 20)])
    result = RankingService().rank([alpha, bravo])
    assert result.status == "partial" and len(result.ranking) == 2
    for row in result.ranking:
        item = components(row)["recent_interest"]
        assert item.score is None and item.reason == "different_google_normalisation_requests"
        assert item.inputs[0].measurements and row.component_coverage == 0.8
        assert row.total_score is None and row.confidence == 80


@pytest.mark.parametrize("difference", ["geo", "window", "mixed_windows"])
def test_incomparable_trend_context_fails_closed_without_selecting_favourable_cohort(build, difference):
    alpha, _ = build("Alpha")
    options = {"geo": "US"} if difference == "geo" else {"shift": 1}
    keywords = [keyword("bravo one", **options), keyword("bravo two", **options)]
    if difference == "mixed_windows":
        keywords[1] = keyword("bravo two")
    bravo, _ = build("Bravo", keywords=keywords)
    result = RankingService().rank([alpha, bravo])
    assert result.status == "unavailable" and not result.ranking and len(result.unranked) == 2
    for row in result.unranked:
        assert "incomparable_trend_windows_or_geography" in row.reasons
        assert components(row)["momentum"].score is None


def test_two_batches_within_one_niche_are_not_one_interest_scale(build, collection_factory):
    first = collection_factory("google_trends", [keyword("one")])
    second = collection_factory("google_trends", [keyword("two")])
    google = CollectionResult.from_records("google_trends", first.records + second.records,
                                          request_metadata=first.request_metadata + second.request_metadata)
    data, _ = build(google=google)
    row = RankingService().rank([data]).ranking[0]
    assert components(row)["recent_interest"].score is None and row.total_score is None


@pytest.mark.parametrize("previous,recent,expected", [(0, 50, 100), (50, 0, 0), (20, 20, 50), (10, 100, 90.909091)])
def test_momentum_has_no_growth_boost_and_handles_zero_baseline(build, previous, recent, expected):
    data, _ = build(keywords=[keyword("one", previous, recent), keyword("two", previous, recent)])
    row = RankingService().rank([data]).ranking[0]
    assert components(row)["momentum"].score == expected
    if previous == 0:
        assert dict(components(row)["momentum"].inputs[0].measurements)["growth_percent"] is None


def test_all_zero_interest_is_observed_zero_but_zero_over_zero_momentum_is_unknown(build):
    data, _ = build(keywords=[keyword("one", 0, 0), keyword("two", 0, 0)])
    row = RankingService().rank([data]).ranking[0]
    assert components(row)["recent_interest"].score == 0
    assert components(row)["momentum"].score is None
    assert row.total_score is None and row.confidence == 70


@pytest.mark.parametrize("score,comments,expected", [(-50, 0, 0), (0, 0, 0), (100, 0, 100), (2**53 - 1, 2**53 - 1, 100)])
def test_community_clips_only_derived_negative_score_and_caps_log_transform(build, score, comments, expected):
    data, _ = build(reddit=discussions(score=score, comments=comments))
    row = RankingService().rank([data]).ranking[0]
    item = components(row)["community"]
    assert item.score == expected
    assert dict(item.inputs[0].measurements)["score"] == score
    assert data.discussions[0].score == score
    json.dumps(row.to_dict(), allow_nan=False)


@pytest.mark.parametrize("count,expected", [(4, None), (5, 100)])
def test_competition_requires_sample_and_is_not_a_total_competitor_count(build, count, expected):
    data, _ = build(amazon=products(count=count, reviews=0))
    row = RankingService().rank([data]).ranking[0]
    item = components(row)["competition"]
    assert item.score == expected and item.sample_size == count
    assert "not total competitors" in item.formula
    assert components(row)["commerce"].score == 0


def test_missing_scalar_is_not_filled_and_reduces_input_completeness(build):
    records = products()
    records[0].rating = records[1].rating = None
    data, _ = build(amazon=records)
    row = RankingService().rank([data]).ranking[0]
    item = components(row)["commerce"]
    assert item.status == "partial" and item.sample_size == 3 and item.candidate_count == 5
    assert row.confidence == 92
    assert dict(item.inputs[0].measurements)["rating"] is None
    assert row.component_coverage == 1


def test_rejected_record_lowers_confidence_using_real_validation_denominator(build):
    records = products(6)
    records[-1].rating = 6
    data, _ = build(amazon=records)
    row = RankingService().rank([data]).ranking[0]
    assert data.quality_assessment.candidate_count == 11 and data.quality_assessment.valid_count == 10
    assert row.confidence == round(100 * 10 / 11, 6)
    assert row.quality_status == "partial"


def test_no_measured_supporting_sample_is_unranked_even_when_quality_gate_passes(build):
    data, _ = build(amazon=products(1, rating=None, reviews=None), reddit=discussions(1, score=None, comments=None))
    assert data.quality_assessment.gate_passed
    result = RankingService().rank([data])
    assert not result.ranking and result.unranked[0].rank is None
    assert result.unranked[0].reasons == ("insufficient_measured_supporting_sample",)


@pytest.mark.parametrize("change", ["rating", "score_nan", "url", "missing_gate"])
def test_changed_or_unassessed_evidence_cannot_produce_scores(build, change):
    data, _ = build()
    if change == "rating":
        data.products[0].rating = True
    elif change == "score_nan":
        data.keywords[0].score = float("nan")
    elif change == "url":
        data.discussions[0].url = "javascript:bad()"
    else:
        data.quality_assessment = None
    result = RankingService().rank([data])
    assert result.status == "unavailable" and not result.ranking
    assert all(item.score is None and not item.inputs for item in result.unranked[0].components)
    assert result.unranked[0].confidence is None
    json.dumps(result.to_dict(), allow_nan=False)


def test_ranking_does_not_mutate_or_retain_mutable_source_aliases(build):
    data, _ = build()
    original = copy.deepcopy(data)
    result = RankingService().rank([data])
    exported = result.to_dict()
    assert data == original and evidence_digest(data) == data.quality_assessment.data_digest
    assert json.loads(json.dumps(exported, allow_nan=False)) == exported
    exported["ranking"][0]["components"][0]["inputs"][0]["measurements"]["comparison_keywords"].append("bad")
    assert "bad" not in result.to_dict()["ranking"][0]["components"][0]["inputs"][0]["measurements"]["comparison_keywords"]
    data.keywords[0].comparison_keywords.append("changed")
    assert "changed" not in result.to_dict()["ranking"][0]["components"][0]["inputs"][0]["measurements"]["comparison_keywords"]
    with pytest.raises(FrozenInstanceError):
        result.ranking[0].rank = 99


def test_equal_measured_metrics_share_rank_names_do_not_choose_a_winner(build):
    alpha, raw = build("Alpha")
    bravo = prepare("Bravo", raw)
    result = RankingService().rank([bravo, alpha])
    assert [(item.niche, item.rank) for item in result.ranking] == [("Alpha", 1), ("Bravo", 1)]
    assert "Đồng hạng" in result.ranking[1].explanation


def test_competition_ranking_uses_standard_gaps_after_a_tied_position(build):
    alpha, raw = build("Alpha")
    bravo = prepare("Bravo", raw)
    third = prepare("Third", {**raw, "amazon": replace(raw["amazon"], records=[replace(item, rating=3) for item in raw["amazon"].records])})
    result = RankingService().rank([third, bravo, alpha])
    assert [item.rank for item in result.ranking] == [1, 1, 3]


@pytest.mark.parametrize("value", [None, True, "0.3", float("nan"), float("inf"), -0.1, 0, 2])
def test_invalid_weights_are_rejected_not_normalised(value):
    weights = (("momentum", value), *RankingPolicy().weights[1:])
    with pytest.raises(ValueError):
        RankingPolicy(weights=weights)


@pytest.mark.parametrize("values", [
    {"weights": tuple(reversed(RankingPolicy().weights))}, {"weights": RankingPolicy().weights[:-1]},
    {"weights": list(RankingPolicy().weights)}, {"weights": (("momentum", 0.4), *RankingPolicy().weights[1:])},
    {"review_reference": True}, {"review_reference": float("nan")}, {"community_reference": 0},
    {"min_trend_keywords": 1}, {"min_competition_products": True}, {"min_commerce_products": 1001},
])
def test_invalid_ranking_policy_fails_fast(values):
    with pytest.raises(ValueError):
        RankingPolicy(**values)


def test_custom_policy_is_persisted_and_versioned_without_market_defaults(build):
    policy = RankingPolicy(review_reference=200)
    data, _ = build()
    result = RankingService(policy).rank([data]).to_dict()
    assert result["policy"]["review_reference"] == 200
    assert result["policy_id"] == policy.policy_id != RankingPolicy().policy_id
    assert result["policy"]["weights"] == dict(RankingPolicy().weights)


@pytest.mark.parametrize("inputs", [
    [None], [NicheData("", "")], [NicheData("Same", ""), NicheData("SAME", "")],
    [NicheData("Oversized", "", products=products(1) * 1001)],
    [NicheData("bad\ud800", "")], [NicheData("bad\nname", "")],
])
def test_invalid_or_unbounded_ranking_input_is_rejected(inputs):
    with pytest.raises(ValueError):
        RankingService().rank(inputs)


def test_generator_niche_limit_and_empty_run_are_bounded():
    with pytest.raises(ValueError, match="Too many niches"):
        RankingService().rank(NicheData(f"Fixture {index}", "") for index in range(MAX_NICHES + 1))
    assert RankingService().rank([]).to_dict()["ranking"] == []


def test_unknown_validation_ratio_does_not_become_confidence_100(build):
    data, _ = build()
    assessment = data.quality_assessment
    data.quality_assessment = replace(assessment, sources=tuple((source, status, None) for source, status, _ in assessment.sources))
    assert RankingService().rank([data]).ranking[0].confidence is None


def test_pipeline_uses_one_ranking_for_json_markdown_cache_and_pre_ai_diagnostics(comparable_pair, tmp_path, monkeypatch):
    _, _, raw = comparable_pair
    service = RankingService()
    service.rank = Mock(wraps=service.rank)
    monkeypatch.setattr("src.pipeline.LLMAnalyzer.summarize", lambda *args: pytest.fail("Analyzer must not rank"))
    collectors = {source: SimpleNamespace(collect=lambda niche, s=source: raw[niche["name"]][s]) for source in raw["Alpha"]}
    result = execute_pipeline(fast_mode=True, niche_list=[{"name": "Bravo"}, {"name": "Alpha"}],
                              output_dir=str(tmp_path), collectors=collectors, ranking_service=service)
    assert service.rank.call_count == 1
    assert result["ranking"] is result["ranking_assessment"]["ranking"]
    assert [item["niche"] for item in result["ranking"]] == ["Alpha", "Bravo"]
    assert result["metadata"]["ranking_status"] == "available"
    assert result["metadata"]["ranking_policy_id"] == result["ranking_assessment"]["policy_id"]
    assert result["top_ideas"] == [] and result["metadata"]["top_ideas_status"] == "unavailable_no_grounded_ranked_ideas"
    cached = ReportRepository(tmp_path).load_latest()
    assert cached == result
    diagnostics = json.loads((tmp_path / result["metadata"]["diagnostics_file"]).read_text(encoding="utf-8"))
    assert diagnostics["ranking_assessment"] == result["ranking_assessment"]
    summary = result["markdown_content"].split("## TỔNG KẾT\n")[1]
    assert summary.index("| 1 | Alpha |") < summary.index("| 2 | Bravo |")
    for row in result["ranking"]:
        assert f"{row['observed_score']:.6f}" in summary and row["explanation"] in summary
        for item in row["components"]:
            assert f"{item['score']:.6f}" in summary
            assert all(observation["evidence_id"] in summary for observation in item["inputs"])


def test_ranking_diagnostics_survive_later_ai_failure(build, tmp_path, monkeypatch):
    _, raw = build()
    collectors = {source: SimpleNamespace(collect=lambda niche, s=source: raw[s]) for source in raw}
    def broken(*args):
        raise RuntimeError("Fixture AI failure after ranking")
    monkeypatch.setattr("src.pipeline.LLMAnalyzer.analyze", broken)
    with pytest.raises(RuntimeError, match="after ranking"):
        execute_pipeline(niche_list=[{"name": "Fixture"}], output_dir=str(tmp_path), collectors=collectors)
    diagnostics = json.loads(next((tmp_path / "diagnostics").glob("*.json")).read_text(encoding="utf-8"))
    assert diagnostics["ranking_assessment"]["ranking"][0]["rank"] == 1
    assert not (tmp_path / "latest_data.json").exists()


def test_insufficient_niche_cannot_change_valid_peer_scores_or_interest_scale(build):
    alpha, _ = build("Alpha")
    blocked, _ = build("Blocked", keywords=[keyword("only keyword")], amazon=[], reddit=[])
    alone = RankingService().rank([alpha]).ranking[0].to_dict()
    result = RankingService().rank([blocked, alpha])
    assert result.ranking[0].to_dict() == alone
    assert result.unranked[0].niche == "Blocked" and result.unranked[0].confidence is None


def test_renderer_escapes_source_strings_and_never_recalculates_scores(build):
    data, _ = build("<script>bad()</script> | niche")
    payload = RankingService().rank([data]).to_dict()
    payload["ranking"][0]["observed_score"] = 12.345678
    text = RankingRenderer.summary(payload)
    assert "12.345678" in text
    assert "<script>" not in text and "&lt;script&gt;" in text
    assert "\\| niche" in text
    assert "Top 3" in text and "không tự tạo Top 3" in text


def test_phase6_cache_is_rejected_after_ranking_contract_upgrade(tmp_path):
    repository = ReportRepository(tmp_path)
    repository.save_latest({"metadata": {"data_policy": "live-only-v6"}, "markdown_content": "Old fixture", "niches": {}})
    assert repository.load_latest()["status"] == "legacy"


def ranking_source(raw, *, path="/gp/bestsellers", sponsored=None, append_search=False):
    """A fully traced alternative listing fixture, not a runtime market record."""
    original = raw["amazon"]
    old_trace = original.request_metadata[0]
    trace = replace(old_trace, request_id="fixture-ranking-request", operation_id="fixture-ranking-operation",
                    operation="best_sellers", url="https://www.amazon.com" + path,
                    query={"fixture": True, "source_type": "best_sellers"})
    records = []
    for index, item in enumerate(original.records, 1):
        provenance = replace(item.provenance, query=trace.query, request_id=trace.request_id,
                             request_ids=[trace.request_id], evidence_id=f"fixture-ranking-{index}")
        listing = ProductListing("best_sellers", trace.url, index, None, index, sponsored, provenance)
        records.append(replace(item, source="Amazon Best Sellers", source_type="best_sellers", listing_url=trace.url,
                               listing_position=index, search_position=None, rank=index, listing_rank=index,
                               is_sponsored=sponsored, provenance=provenance,
                               listings=[listing, *item.listings] if append_search else [listing]))
    return CollectionResult.from_records("amazon", records,
        request_metadata=[trace, old_trace] if append_search else [trace],
        started_at=original.started_at, completed_at=original.completed_at)


@pytest.mark.parametrize("kind", ["sponsored_search", "general_hub", "hub_with_later_search", "scoped_ranking", "sponsored_ranking"])
def test_additional_primary_snapshot_scope_and_sponsored_rules(build, kind):
    _, raw = build()
    if kind == "sponsored_search":
        raw["amazon"].records = [replace(item, is_sponsored=True, listings=[replace(item.listings[0], is_sponsored=True)])
                                 for item in raw["amazon"].records]
    else:
        raw["amazon"] = ranking_source(raw, path="/gp/bestsellers/home-garden" if kind == "scoped_ranking" else "/gp/bestsellers",
                                        sponsored=True if kind == "sponsored_ranking" else None,
                                        append_search=kind == "hub_with_later_search")
    data = prepare("Fixture", raw)
    assert data.quality_assessment.gate_passed and len(data.products) == 5
    row = RankingService().rank([data]).ranking[0]  # Reddit remains measurable.
    items = components(row)
    assert items["competition"].score is None  # No organic Search primary snapshot.
    if kind == "scoped_ranking":
        assert items["commerce"].score == 40 and len(items["commerce"].inputs) == 5
    else:
        assert items["commerce"].score is None and not items["commerce"].inputs


def with_reddit_window(result, window):
    query = {**result.request_metadata[0].query, "time_filter": window}
    duration = {"week": 7 * 86400, "all": None}[window]
    query["window_start_utc"] = query["window_end_utc"] - duration if duration else None
    trace = replace(result.request_metadata[0], query=query,
                    url=result.request_metadata[0].url.replace("t=month", "t=" + window))
    return replace(result, request_metadata=[trace], records=[
        replace(item, provenance=replace(item.provenance, query=query)) for item in result.records])


@pytest.mark.parametrize("window", ["week", "all"])
def test_additional_reddit_window_mismatch_is_not_comparable(build, window):
    alpha, _ = build("Alpha")
    _, raw = build("Bravo")
    raw["reddit"] = with_reddit_window(raw["reddit"], window)
    bravo = prepare("Bravo", raw)
    assert len(bravo.discussions) == 3
    result = RankingService().rank([alpha, bravo])
    for row in result.ranking:
        assert components(row)["community"].score is None
        assert components(row)["community"].reason == "different_reddit_collection_windows"


def test_additional_unbounded_reddit_window_remains_explicit_not_subtracted_from_none(build):
    _, raw = build()
    raw["reddit"] = with_reddit_window(raw["reddit"], "all")
    data = prepare("Fixture", raw)
    row = RankingService().rank([data]).ranking[0]
    assert dict(components(row)["community"].inputs[0].measurements)["window_start_utc"] is None


def test_additional_equal_totals_tie_break_on_measured_momentum_not_config(build, collection_factory):
    shared = collection_factory("google_trends", [keyword("alpha one", 0, 10), keyword("alpha two", 0, 10),
                                                 keyword("bravo one", 10, 40), keyword("bravo two", 10, 40)])
    alpha, _ = build("Alpha", google=replace(shared, records=shared.records[:2]))
    bravo, _ = build("Bravo", google=replace(shared, records=shared.records[2:]))
    result = RankingService().rank([bravo, alpha])
    assert result.ranking[0].observed_score == result.ranking[1].observed_score
    assert [row.niche for row in result.ranking] == ["Alpha", "Bravo"]
    assert [row.rank for row in result.ranking] == [1, 2]
    assert "metric thật" in result.ranking[1].explanation and "momentum" in result.ranking[1].explanation


def test_additional_partial_score_intervals_warn_when_they_overlap(build):
    alpha, _ = build("Alpha")
    bravo, _ = build("Bravo", keywords=[keyword("one", 20, 39), keyword("two", 20, 39)])
    result = RankingService().rank([alpha, bravo])
    assert "chồng lấp" in result.ranking[1].explanation


def test_additional_interest_comparability_is_recomputed_per_run_not_stored_in_service(build):
    alpha, _ = build("Alpha")
    bravo, _ = build("Bravo")
    service = RankingService()
    assert components(service.rank([alpha]).ranking[0])["recent_interest"].score == 40
    assert components(service.rank([alpha, bravo]).ranking[0])["recent_interest"].score is None
    assert components(service.rank([alpha]).ranking[0])["recent_interest"].score == 40


def test_additional_rankings_are_not_boosted_by_prices_titles_or_suggestions(build):
    data, raw = build()
    raw["amazon"].records = [replace(item, title="New fixture title", price="USD 999.99", price_amount="999.99", price_currency="USD")
                             for item in raw["amazon"].records]
    changed = prepare("Changed", raw)
    row = RankingService().rank([data]).ranking[0]
    other = RankingService().rank([changed]).ranking[0]
    assert row.observed_score == other.observed_score
    assert [item.score for item in row.components] == [item.score for item in other.components]


def test_additional_pipeline_niche_limit_rejects_before_network(tmp_path):
    with pytest.raises(ValueError):
        execute_pipeline(niche_list=[{"name": f"Fixture {index}"} for index in range(MAX_NICHES + 1)], output_dir=str(tmp_path))
    assert not list(tmp_path.iterdir())


def test_final_explicit_weight_precision_rejects_instead_of_silently_rounding():
    with pytest.raises(ValueError, match="six decimal"):
        RankingPolicy(weights=(("momentum", 0.30000001), ("recent_interest", 0.19999999),
                               ("commerce", 0.2), ("community", 0.2), ("competition", 0.1)))


def test_final_serialized_views_are_independent_and_preserve_every_frozen_field(build):
    data, _ = build()
    result = RankingService().rank([data])
    exported = result.to_dict()
    assert json.loads(json.dumps(exported, allow_nan=False)) == exported
    row = exported["ranking"][0]
    assert row["rank"] == 1 and row["observed_score"] == result.ranking[0].observed_score
    assert row["components"][0]["context"]["minimum_sample_size"] == 2
    row["components"][0]["inputs"][0]["measurements"]["comparison_keywords"].append("injected")
    row["components"][0]["context"]["geo"] = "injected"
    row["reasons"].append("injected")
    assert "injected" not in json.dumps(result.to_dict())
    assert "injected" not in json.dumps(data.to_dict())


def test_final_extreme_measured_scores_and_small_weights_stay_within_100(build):
    _, raw = build(keywords=[keyword("one", 0, 100), keyword("two", 0, 100)],
                   amazon=products(20, rating=5, reviews=2**53 - 1), reddit=discussions(score=100, comments=0))
    for item in raw["amazon"].records[:5]:
        item.reviews_count = 0
    category = ranking_source(raw, path="/gp/bestsellers/home-garden")
    raw["amazon"] = CollectionResult.from_records("amazon", raw["amazon"].records[:5] + category.records[5:],
        request_metadata=raw["amazon"].request_metadata + category.request_metadata)
    data = prepare("Fixture", raw)
    policy = RankingPolicy(weights=(("momentum", 0.333333), ("recent_interest", 0.333333),
                                    ("commerce", 0.333332), ("community", 0.000001), ("competition", 0.000001)))
    row = RankingService(policy).rank([data]).ranking[0]
    assert all(item.score == 100 for item in row.components)
    assert row.observed_score == row.total_score == row.score_upper_bound == 100
    # Competition uses 5 organic Search primaries out of 20 observed products;
    # the 15 category primaries are not silently counted as Search coverage.
    assert row.confidence == 99.999925
    assert round(sum(item.contribution for item in row.components), 6) == 100


def test_final_old_policy_message_does_not_claim_phase6_provenance_is_fake(tmp_path):
    repository = ReportRepository(tmp_path)
    repository.save_latest({"metadata": {"data_policy": "live-only-v6"}, "markdown_content": "Fixture", "niches": {}})
    result = repository.load_latest()
    assert result["status"] == "legacy" and "ranking" in result["message"]
    assert "chưa có dấu vết nguồn" not in result["message"]
