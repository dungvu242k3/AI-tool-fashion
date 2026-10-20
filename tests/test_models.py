"""
Unit tests for data models and schemas.
"""
import pytest
from src.models.schemas import (
    KeywordSignal,
    ProductItem,
    DiscussionItem,
    NicheData,
    ProductIdea,
    NicheReportSection,
)


def test_keyword_signal_serialization():
    kw = KeywordSignal(
        keyword="christmas gift ideas 2026",
        trend="rising",
        score=92.5,
        signal_summary="Score 92/100",
        source="Google Trends",
        source_url="https://trends.google.com",
        related_queries=["gifts for family", "cheap gifts"],
    )
    d = kw.to_dict()
    assert d["keyword"] == "christmas gift ideas 2026"
    assert d["trend"] == "rising"
    assert d["score"] == 92.5
    assert len(d["related_queries"]) == 2


def test_product_item_serialization():
    prod = ProductItem(
        title="Personalized Wallet",
        price="$29.99",
        rating=4.8,
        reviews_count=1500,
        rank=1,
        url="https://amazon.com/dp/123",
        source="Amazon Best Sellers",
    )
    d = prod.to_dict()
    assert d["title"] == "Personalized Wallet"
    assert d["price"] == "$29.99"
    assert d["rating"] == 4.8
    assert d["rank"] == 1


def test_niche_data_structure():
    niche = NicheData(
        niche_name="Gift for Him",
        collected_at="2026-10-20T10:00:00",
        keywords=[KeywordSignal(keyword="edc gear", score=80.0)],
        products=[ProductItem(title="Multi-tool Pen", price="$15.00")],
        discussions=[DiscussionItem(title="Best gifts for men", score=500)],
    )
    serialized = niche.to_dict()
    assert serialized["niche_name"] == "Gift for Him"
    assert len(serialized["keywords"]) == 1
    assert len(serialized["products"]) == 1
    assert len(serialized["discussions"]) == 1
