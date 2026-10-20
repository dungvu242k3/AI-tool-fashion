"""
Data models and schemas for the AI fashion trend research tool.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class KeywordSignal:
    """Keyword trending signal with verification source and metrics."""
    keyword: str
    trend: str = "stable"  # rising, stable, declining
    score: float = 0.0
    signal_summary: str = ""
    source: str = "Google Trends"
    source_url: str = ""
    related_queries: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProductItem:
    """Product competitor / best-seller item from Amazon or other e-commerce."""
    title: str
    price: str = "N/A"
    rating: float = 0.0
    reviews_count: int = 0
    rank: int = 0
    url: str = ""
    source: str = "Amazon"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiscussionItem:
    """Community discussion item from Reddit or social forums."""
    title: str
    score: int = 0
    comments: int = 0
    content_summary: str = ""
    url: str = ""
    source: str = "Reddit"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NicheData:
    """Aggregated raw and processed signals for a specific niche."""
    niche_name: str
    collected_at: str
    keywords: List[KeywordSignal] = field(default_factory=list)
    products: List[ProductItem] = field(default_factory=list)
    discussions: List[DiscussionItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "niche_name": self.niche_name,
            "collected_at": self.collected_at,
            "keywords": [k.to_dict() for k in self.keywords],
            "products": [p.to_dict() for p in self.products],
            "discussions": [d.to_dict() for d in self.discussions],
        }


@dataclass
class ProductIdea:
    """Product opportunity suggestion matching required structure."""
    name: str
    target_audience: str
    why_now: str
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NicheReportSection:
    """Structured report output for a single niche."""
    niche_name: str
    keywords_content: str
    analysis_content: str
    ideas_content: str
    ideas: List[ProductIdea] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "niche_name": self.niche_name,
            "keywords_content": self.keywords_content,
            "analysis_content": self.analysis_content,
            "ideas_content": self.ideas_content,
            "ideas": [i.to_dict() for i in self.ideas],
        }
