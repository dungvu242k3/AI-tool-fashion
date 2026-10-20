"""
Unit tests for data collectors (Google Trends, Amazon, Reddit).
"""
import pytest
from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.amazon import AmazonCollector
from src.collectors.reddit import RedditCollector


def test_google_trends_determine_trend():
    collector = GoogleTrendsCollector()

    # Rising trend: values increase in second half
    rising_values = [10, 15, 20, 50, 75, 90]
    assert collector._determine_trend(rising_values) == "rising"

    # Declining trend: values decrease in second half
    declining_values = [90, 80, 70, 20, 15, 10]
    assert collector._determine_trend(declining_values) == "declining"

    # Stable trend: values stay similar
    stable_values = [50, 52, 49, 51, 50, 53]
    assert collector._determine_trend(stable_values) == "stable"


def test_amazon_fallback_products():
    collector = AmazonCollector()

    christmas_prods = collector._get_fallback_products("Christmas Gift Ideas")
    assert len(christmas_prods) >= 2
    assert all(p.price.startswith("$") for p in christmas_prods)
    assert all(p.rating > 4.0 for p in christmas_prods)

    him_prods = collector._get_fallback_products("Gift for Him")
    assert len(him_prods) >= 2
    assert "Him" in him_prods[0].title or "Men" in him_prods[0].title or "Leather" in him_prods[0].title


def test_reddit_fallback_discussions():
    collector = RedditCollector()

    discussions = collector._get_fallback_discussions("Gift for Her")
    assert len(discussions) >= 2
    assert all(d.score > 100 for d in discussions)
    assert all("reddit.com" in d.url for d in discussions)
