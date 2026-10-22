"""Phase-4 fixtures are isolated test inputs, never runtime fallback data."""
import json
from dataclasses import replace
from html import escape
from types import SimpleNamespace

import pytest

from src.collectors.amazon import AmazonCollector
from src.collectors.amazon_parser import AmazonPageParser
from src.collectors.amazon_settings import AmazonSettings, build_amazon_requests
from src.collectors.errors import ResponseParseError
from src.collectors.http_policy import HTTPPolicy
from src.collectors.validation import validate_collection_result
from src.models.collection import CollectionResult
from src.models.schemas import NicheData, ProductItem
from src.pipeline import execute_pipeline
from src.processors.amazon_values import parse_observed_price, parse_rating, parse_review_count
from src.processors.data_processor import DataProcessor
from src.reporters.evidence_renderer import EvidenceRenderer
from src.reporters.report_repository import ReportRepository

BEST_URL = "https://www.amazon.com/gp/bestsellers/toys-and-games"
MOVERS_URL = "https://www.amazon.com/gp/movers-and-shakers/toys-and-games"


def card(asin="B000000001", *, title="Parser fixture", price="$12.50", sponsored=False, href=None, extra=""):
    href = href if href is not None else f"/dp/{asin}"
    return (
        f'<div data-component-type="s-search-result" data-asin="{asin}">'
        f'<h2><a href="{escape(href, quote=True)}"><span>{escape(title)}</span></a></h2>'
        + ('<span class="puis-sponsored-label-text">Sponsored</span>' if sponsored else "")
        + (f'<span class="a-price"><span class="a-offscreen">{escape(price)}</span></span>' if price is not None else "")
        + extra + "</div>"
    )


def ranking_page(kind="best_sellers", *, rank="#7", asin="B000000001", title="Ranking fixture", price="EUR 14.99"):
    heading = "Best Sellers" if kind == "best_sellers" else "Movers &amp; Shakers"
    return (
        f'<h1>{heading}</h1><div class="zg-grid-general-faceout"><span class="zg-bdg-text">{rank}</span>'
        f'<a href="/dp/{asin}"><div class="p13n-sc-truncate-desktop-type2">{escape(title)}</div></a>'
        f'<span class="p13n-sc-price">{price}</span></div>'
    )


def parse(html, *, kind="search", settings=None):
    url = {"search": "https://www.amazon.com/s?k=fixture", "best_sellers": BEST_URL, "movers_shakers": MOVERS_URL}[kind]
    return AmazonPageParser(settings or AmazonSettings()).parse(html, source_type=kind, page_url=url)


@pytest.mark.parametrize(("display", "amount", "currency"), [
    ("$1,299.99", "1299.99", "$"), ("USD 12.50", "12.50", "USD"),
    ("254,000 VND", "254000", "VND"), ("€1.299,99", "1299.99", "€"),
    ("EUR 1 299,99", "1299.99", "EUR"), ("$0.00", "0.00", "$"), ("¥1234", "1234", "¥"),
])
def test_price_keeps_observed_currency_and_exact_decimal(display, amount, currency):
    price = parse_observed_price(display)
    assert price.amount == amount and price.currency == currency and price.display == display


@pytest.mark.parametrize("display", [None, "12.50", "$-1", "$1,23", "$12.999", "$10–$20", "$NaN", "FREE", "$1 EUR", "$" + "9" * 100])
def test_invalid_or_ambiguous_price_is_unknown(display):
    assert parse_observed_price(display) is None


@pytest.mark.parametrize(("text", "rating"), [("0 out of 5 stars", 0), ("5.0 out of 5", 5), ("6 out of 5 stars", None), ("4.5", None)])
def test_rating_requires_an_observed_valid_scale(text, rating):
    assert parse_rating(text) == rating


@pytest.mark.parametrize(("text", "count"), [("0", 0), ("1,234 ratings", 1234), ("-1", None), ("1.2K", None), ("1,2", None)])
def test_reviews_are_exact_nonnegative_counts(text, count):
    assert parse_review_count(text) == count


def test_fields_are_independent_and_search_badge_is_not_a_rank():
    html = card(price=None, title="Pen", extra='<span class="a-icon-alt">4.2 out of 5 stars</span><span class="zg-bdg-text">#1</span>')
    product = parse(html).products[0]
    assert product.title == "Pen" and product.asin == "B000000001"
    assert product.rating == 4.2 and product.price is None and product.price_amount is None
    assert product.reviews_count is None and product.rank is None and product.listing_rank is None
    assert product.search_position == 1 and product.source_type == "search"


def test_split_price_parts_never_cross_price_containers_or_invent_cents():
    malformed = '<span class="a-price"><span class="a-price-symbol">$</span><span class="a-price-whole">12.</span></span><span class="a-price-fraction">99</span>'
    assert parse(card(price=None, extra=malformed)).products[0].price is None
    valid = '<span class="a-price"><span class="a-price-symbol">$</span><span class="a-price-whole">12.</span><span class="a-price-fraction">99</span></span>'
    assert parse(card(price=None, extra=valid)).products[0].price_amount == "12.99"


def test_sponsored_filter_keeps_original_search_positions():
    html = card(sponsored=True) + card("B000000002")
    page = parse(html)
    assert page.sponsored_filtered == 1
    assert page.products[0].asin == "B000000002" and page.products[0].search_position == 2
    included = parse(html, settings=AmazonSettings(include_sponsored=True))
    assert included.products[0].is_sponsored is True


@pytest.mark.parametrize("kind", ["best_sellers", "movers_shakers"])
def test_ranked_sources_require_explicit_badges_and_have_separate_rank_semantics(kind):
    product = parse(ranking_page(kind), kind=kind).products[0]
    assert product.source_type == kind and product.listing_rank == 7
    assert product.rank == (7 if kind == "best_sellers" else None)
    assert product.search_position is None
    missing = parse(ranking_page(kind, rank=""), kind=kind).products[0]
    assert missing.listing_rank is None and missing.rank is None


def test_source_url_and_heading_must_both_match():
    with pytest.raises(ResponseParseError, match="tiêu đề"):
        parse(ranking_page("movers_shakers"), kind="best_sellers")
    with pytest.raises(ResponseParseError):
        AmazonPageParser(AmazonSettings()).parse(ranking_page(), source_type="best_sellers", page_url="https://www.amazon.com/s")


@pytest.mark.parametrize("html", ['<title>Robot Check</title>', '<form action="/errors/validateCaptcha"><input id="captchacharacters"></form>'])
def test_http_200_challenge_is_blocked_not_market_data(html, http_factory, response_factory):
    http = http_factory([response_factory(text=html)], policy=HTTPPolicy(max_attempts=3))
    result = AmazonCollector(http.client).collect({"name": "fixture"})
    assert result.status == "failed" and result.records == []
    assert result.warnings[0].code == "source_blocked"
    assert result.warnings[0].request_id == result.request_metadata[0].request_id
    assert http.session.request.call_count == 1


@pytest.mark.parametrize("href", [
    "https://www.amazon.com.attacker.test/dp/B000000001", "//127.0.0.1/dp/B000000001",
    "javascript:alert(1)", "https://user:password@www.amazon.com/dp/B000000001", "/dp/B000000002",
])
def test_unsafe_links_and_conflicting_asins_are_not_accepted(href):
    page = parse(card(href=href))
    assert page.products == () and page.discarded_cards == 1


def test_asin_can_be_observed_in_product_url_without_data_attribute():
    html = card(asin="", href="/gp/product/B000000001?ref=fixture")
    product = parse(html).products[0]
    assert product.asin == "B000000001" and product.url == "https://www.amazon.com/dp/B000000001"


@pytest.mark.parametrize("source", [
    {"type": "best_sellers", "url": "http://www.amazon.com/gp/bestsellers"},
    {"type": "best_sellers", "url": "https://127.0.0.1/gp/bestsellers"},
    {"type": "best_sellers", "url": "https://www.amazon.com:444/gp/bestsellers"},
    {"type": "best_sellers", "url": "https://www.amazon.com/gp/bestsellers?redirect=http://localhost"},
    {"type": "best_sellers", "url": "https://www.amazon.com/gp/movers-and-shakers"},
    {"type": "movers_shakers", "url": "https://www.amazon.com/gp/movers-and-shakers/../s"},
    {"type": "search", "query": "x\nheader"}, {"type": "search", "query": "x" * 201},
    {"type": "search", "query": "fixture", "url": "https://example.test"},
])
def test_invalid_input_is_rejected_before_network(source, http_factory):
    http = http_factory([])
    result = AmazonCollector(http.client).collect({"name": "fixture", "amazon_sources": [source]})
    assert result.warnings[0].code == "invalid_input" and result.records == []
    http.session.request.assert_not_called()


def test_input_budget_and_request_deduplication_are_explicit():
    source = {"type": "search", "query": "fixture"}
    assert len(build_amazon_requests({"amazon_sources": [source, source]}, AmazonSettings())) == 1
    with pytest.raises(ValueError):
        build_amazon_requests({"amazon_sources": [source] * 5}, AmazonSettings())
    with pytest.raises(ValueError):
        AmazonSettings(max_products=1000)


def test_asin_dedup_preserves_per_source_evidence_without_merging_prices(http_factory, response_factory):
    http = http_factory([response_factory(text=card(price="$12.50")), response_factory(text=ranking_page(price="EUR 99.99"))])
    result = AmazonCollector(http.client).collect({"name": "fixture", "amazon_sources": [
        {"type": "search", "query": "fixture"}, {"type": "best_sellers", "url": BEST_URL},
    ]})
    assert result.status == "success" and len(result.records) == 1
    product = result.records[0]
    assert product.price == "$12.50" and product.price_currency == "$" and product.rank is None
    assert [listing.source_type for listing in product.listings] == ["search", "best_sellers"]
    assert product.listings[1].listing_rank == 7
    assert len({listing.provenance.request_id for listing in product.listings}) == 2
    assert validate_collection_result("amazon", result).status == "success"


def test_processor_uses_asin_not_title_and_groups_currency_without_conversion():
    raw = [
        ProductItem("Same title", asin="B000000001", price="$12.50"),
        ProductItem("Same title", asin="B000000002", price="254,000 VND"),
        ProductItem("Other title", asin="B000000001", price="USD 99.99"),
    ]
    result = DataProcessor()._process_products(raw)
    assert len(result) == 2
    ranges = DataProcessor.extract_price_ranges(result)
    assert {item["currency"]: item["min"] for item in ranges} == {"$": "12.50", "VND": "254000"}
    assert raw[0].price_amount is None  # Normalization did not mutate source records.


def test_invalid_nested_listing_is_rejected_without_losing_other_products(http_factory, response_factory):
    http = http_factory([response_factory(text=card() + card("B000000002"))])
    result = AmazonCollector(http.client).collect({"name": "fixture"})
    product = result.records[0]
    listing = product.listings[0]
    result.records[0] = replace(product, listings=[replace(listing, source_type="best_sellers")])
    validated = validate_collection_result("amazon", result)
    assert validated.status == "partial"
    assert [record.asin for record in validated.records] == ["B000000002"]
    assert validated.warnings[0].code == "invalid_product_evidence"


def test_request_and_product_limits_are_independent(http_factory, response_factory):
    http = http_factory([response_factory(text=card() + card("B000000002")), response_factory(text=card("B000000003"))])
    result = AmazonCollector(http.client, settings=AmazonSettings(max_products=1)).collect({"name": "fixture", "amazon_search_terms": ["one", "two"]})
    assert len(result.records) == 1 and len(result.request_metadata) == 2


def test_oversized_html_is_rejected_before_parsing(http_factory, response_factory):
    http = http_factory([response_factory(text="<p>" + "x" * 200)])
    result = AmazonCollector(http.client, settings=AmazonSettings(max_html_chars=100)).collect({"name": "fixture"})
    assert result.records == [] and result.warnings[0].code == "payload_too_large"


def test_rank_and_sponsored_metadata_are_rendered_as_text(http_factory, response_factory):
    http = http_factory([response_factory(text=card(title="<img src=x onerror=bad()>", sponsored=True))])
    result = AmazonCollector(http.client, settings=AmazonSettings(include_sponsored=True)).collect({"name": "fixture"})
    text = EvidenceRenderer.section(NicheData("fixture", "", products=result.records), "not_requested").analysis_content
    assert "<img" not in text and "Sponsored" in text
    assert "vị trí tìm kiếm 1" in text
    assert "Best Sellers" not in text


def test_pipeline_diagnostics_include_each_retained_listing(tmp_path, http_factory, response_factory):
    http = http_factory([response_factory(text=card()), response_factory(text=ranking_page())])
    amazon = AmazonCollector(http.client)
    unavailable = lambda source: SimpleNamespace(collect=lambda niche: CollectionResult.from_records(source, []))
    result = execute_pipeline(fast_mode=True, output_dir=str(tmp_path), niche_list=[{
        "name": "fixture", "amazon_sources": [{"type": "search", "query": "fixture"}, {"type": "best_sellers", "url": BEST_URL}],
    }], collectors={"amazon": amazon, "google_trends": unavailable("google_trends"), "reddit": unavailable("reddit")})
    assert result["metadata"]["total_products"] == 1
    assert len(result["niches"]["fixture"]["products"][0]["listings"]) == 2
    diagnostics = json.loads((tmp_path / result["metadata"]["diagnostics_file"]).read_text(encoding="utf-8"))
    assert len(diagnostics["evidence"]) == 2
    assert all(item["request_id"] in diagnostics["request_metadata"] for item in diagnostics["evidence"])
    assert "Amazon Best Sellers" in result["markdown_content"]


def test_old_cache_without_amazon_listing_contract_is_rejected(tmp_path):
    repository = ReportRepository(tmp_path)
    repository.save_latest({"metadata": {"data_policy": "live-only-v3"}, "markdown_content": "Fixture historical", "niches": {}})
    assert repository.load_latest()["status"] == "legacy"


def test_blocked_source_stops_other_pages_instead_of_working_around_the_challenge(http_factory, response_factory):
    http = http_factory([response_factory(text="<title>Robot Check</title>")])
    result = AmazonCollector(http.client).collect({"name": "fixture", "amazon_sources": [
        {"type": "search", "query": "fixture"}, {"type": "best_sellers", "url": BEST_URL},
    ]})
    assert result.status == "failed" and result.records == []
    assert http.session.request.call_count == 1
    assert [warning.code for warning in result.warnings] == ["source_blocked"]


def test_exhausted_rate_limit_retains_earlier_evidence_and_stops_new_queries(http_factory, response_factory):
    http = http_factory([response_factory(text=card()), *[response_factory(429) for _ in range(3)]], policy=HTTPPolicy(max_attempts=3))
    result = AmazonCollector(http.client).collect({"name": "fixture", "amazon_search_terms": ["one", "two", "three"]})
    assert result.status == "partial" and len(result.records) == 1
    assert result.warnings[0].code == "http_429"
    assert len(result.request_metadata) == http.session.request.call_count == 4
    assert result.records[0].provenance.request_id == result.request_metadata[0].request_id
    assert validate_collection_result("amazon", result).status == "partial"


def test_non_html_response_cannot_be_parsed_as_product_data(http_factory, response_factory):
    http = http_factory([response_factory(payload={"message": "Fixture maintenance"})])
    result = AmazonCollector(http.client).collect({"name": "fixture"})
    assert result.status == "failed" and result.records == []
    assert result.warnings[0].code == "invalid_content_type"
    assert http.session.request.call_count == 1


def test_parser_card_budget_replaces_the_old_fixed_eight_card_cutoff():
    html = "".join(card(f"B{index:09d}") for index in range(12))
    assert len(parse(html).products) == 12
    limited = parse(html, settings=AmazonSettings(max_cards_per_page=2))
    assert [product.search_position for product in limited.products] == [1, 2]


def test_amazon_settings_validate_environment_without_echoing_values(monkeypatch):
    monkeypatch.setenv("TREND_AMAZON_INCLUDE_SPONSORED", "true")
    monkeypatch.setenv("TREND_AMAZON_MAX_PRODUCTS", "2")
    settings = AmazonSettings.from_env()
    assert settings.include_sponsored is True and settings.max_products == 2
    monkeypatch.setenv("TREND_AMAZON_MAX_PRODUCTS", "private-unparseable-value")
    with pytest.raises(ValueError) as failure:
        AmazonSettings.from_env()
    assert "private-unparseable-value" not in str(failure.value)


@pytest.mark.parametrize("changes", [{"rank": 1}, {"reviews_count": -1}, {"price_amount": "99.99"}])
def test_invalid_observed_product_values_are_rejected_before_processing(changes, http_factory, response_factory):
    http = http_factory([response_factory(text=card())])
    result = AmazonCollector(http.client).collect({"name": "fixture"})
    result.records[0] = replace(result.records[0], **changes)
    validated = validate_collection_result("amazon", result)
    assert validated.status == "failed" and validated.records == []
    assert validated.warnings[0].code == "invalid_product_evidence"


def test_missing_asin_or_listing_contract_cannot_use_legacy_validation_bypass(collection_factory):
    result = collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")])
    result.records[0] = replace(result.records[0], asin=None, source_type=None, listings=[])
    assert validate_collection_result("amazon", result).records == []


def test_migrated_fixture_factory_obeys_the_new_amazon_contract(collection_factory):
    result = collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001", price="$12.50")])
    assert validate_collection_result("amazon", result).status == "success"
    assert result.records[0].listings[0].provenance == result.records[0].provenance


@pytest.mark.parametrize("changes", [{"listing_position": True}, {"search_position": True}, {"rank": True}, {"is_sponsored": 1}])
def test_boolean_positions_or_ranks_cannot_pass_as_numeric_facts(changes, http_factory, response_factory):
    http = http_factory([response_factory(text=card())])
    result = AmazonCollector(http.client).collect({"name": "fixture"})
    result.records[0] = replace(result.records[0], **changes)
    assert validate_collection_result("amazon", result).records == []


def test_modern_review_link_preserves_exact_global_rating_count():
    product = parse(card(extra='<a href="/product-reviews/B000000001"><span>1,234 global ratings</span></a>')).products[0]
    assert product.reviews_count == 1234


def test_review_link_for_another_asin_is_not_attached_to_the_product():
    product = parse(card(extra='<a href="/product-reviews/B000000002"><span>1,234 ratings</span></a>')).products[0]
    assert product.reviews_count is None


def test_counts_beyond_json_integer_precision_are_unknown_not_rounded(http_factory, response_factory):
    assert parse_review_count(str(2 ** 53)) is None
    http = http_factory([response_factory(text=card())])
    result = AmazonCollector(http.client).collect({"name": "fixture"})
    result.records[0] = replace(result.records[0], reviews_count=2 ** 53)
    assert validate_collection_result("amazon", result).records == []


def test_sponsored_ranked_card_is_filtered_or_explicitly_tagged(http_factory, response_factory):
    html = ranking_page().replace('<span class="zg-bdg-text">', '<span class="puis-sponsored-label-text">Sponsored</span><span class="zg-bdg-text">')
    excluded = parse(html, kind="best_sellers")
    assert excluded.products == () and excluded.sponsored_filtered == 1
    http = http_factory([response_factory(text=html)])
    result = AmazonCollector(http.client, settings=AmazonSettings(include_sponsored=True)).collect({
        "name": "fixture", "amazon_sources": [{"type": "best_sellers", "url": BEST_URL}],
    })
    assert result.records[0].is_sponsored is True
    assert validate_collection_result("amazon", result).status == "success"
