"""
Unit tests for DataProcessor and statistical calculations.
"""
import pytest
from src.processors.data_processor import DataProcessor
from src.models.schemas import KeywordSignal, ProductItem, DiscussionItem


def test_process_deduplication():
    processor = DataProcessor()
    raw = {
        "niche": "Christmas Gift Ideas",
        "collected_at": "2026-10-20T10:00:00",
        "keywords_data": [
            {"keyword": "cozy gifts", "score": 70, "trend": "rising"},
            {"keyword": "cozy gifts", "score": 60, "trend": "stable"},  # duplicate
            {"keyword": "family ornaments", "score": 85, "trend": "rising"},
        ],
        "products_data": [
            {"title": "Cozy Blanket Set", "price": "$35.00", "asin": "B000000001"},
            {"title": "Cozy Blanket Set", "price": "$35.00", "asin": "B000000001"},  # duplicate
        ],
        "discussions_data": [
            {"title": "Best Christmas gifts?", "score": 300, "post_id": "abc123"},
            {"title": "Best Christmas gifts?", "score": 250, "post_id": "abc123"},  # duplicate
        ],
    }

    niche_obj = processor.process(raw)
    assert len(niche_obj.keywords) == 2
    assert len(niche_obj.products) == 1
    assert len(niche_obj.discussions) == 1


def test_rising_score_is_preserved():
    processor = DataProcessor()
    raw_kw = [{"keyword": "rising gift item", "score": 50, "trend": "rising"}]
    processed_kws = processor._process_keywords(raw_kw)
    assert processed_kws[0].score == 50.0


def test_extract_price_range():
    products = [
        ProductItem(title="Item 1", price="$10.00"),
        ProductItem(title="Item 2", price="$20.00"),
        ProductItem(title="Item 3", price="$30.00"),
    ]
    price_info = DataProcessor.extract_price_range(products)
    assert price_info["min"] == 10.0
    assert price_info["max"] == 30.0
    assert price_info["avg"] == 20.0
    assert "$10.00 – $30.00" in price_info["formatted"]


def test_extract_price_range_empty():
    price_info = DataProcessor.extract_price_range([])
    assert "min" in price_info
    assert "max" in price_info
    assert price_info["min"] is None
    assert price_info["max"] is None
    assert price_info["avg"] is None
    assert price_info["sample_size"] == 0


def test_prices_are_not_converted_or_discarded_by_arbitrary_threshold():
    info = DataProcessor.extract_price_range([
        ProductItem("VND fixture", price="254,000 VND"),
        ProductItem("USD fixture", price="$1,299.99"),
        ProductItem("Missing fixture"),
    ])
    assert info["sample_size"] == 1
    assert info["min"] == 1299.99
