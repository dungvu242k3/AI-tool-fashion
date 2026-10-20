"""
Collectors package exports.
"""
from src.collectors.base import BaseCollector
from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.amazon import AmazonCollector
from src.collectors.reddit import RedditCollector

__all__ = [
    "BaseCollector",
    "GoogleTrendsCollector",
    "AmazonCollector",
    "RedditCollector",
]
