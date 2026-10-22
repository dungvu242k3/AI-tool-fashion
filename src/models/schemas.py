"""
Domain records. Missing measurements are unknown, never synthetic defaults.
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from src.models.collection import CollectionResult, RecordProvenance
from src.models.trends import TrendMetrics, TrendPoint
from src.models.commerce import ProductListing
from src.models.community import RedditPainPoint
from src.models.quality import QualityAssessment
from src.models.analysis import GroundedAnalysis, GroundedIdea


@dataclass
class KeywordSignal:
    """Keyword trending signal with verification source and metrics."""
    keyword: str
    trend: str = "unavailable"
    score: Optional[float] = None
    signal_summary: str = ""
    source: str = "Google Trends"
    source_url: str = ""
    related_queries: List[str] = field(default_factory=list)
    provenance: Optional[RecordProvenance] = None
    time_series: List[TrendPoint] = field(default_factory=list)
    metrics: Optional[TrendMetrics] = None
    suggestions: List[str] = field(default_factory=list)
    geo: str = ""
    timeframe: str = ""
    comparison_keywords: List[str] = field(default_factory=list)

    @property
    def raw_metric(self) -> Dict[str, Any]:
        return {"score": self.score}

    @property
    def derived_metric(self) -> Dict[str, Any]:
        return asdict(self.metrics) if self.metrics is not None else {}

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "raw_metric": self.raw_metric, "derived_metric": self.derived_metric}


@dataclass
class ProductItem:
    """Product competitor / best-seller item from Amazon or other e-commerce."""
    title: str
    price: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    rank: Optional[int] = None  # Actual bestseller rank, never search position.
    url: str = ""
    source: str = "Amazon"
    search_position: Optional[int] = None
    provenance: Optional[RecordProvenance] = None
    asin: Optional[str] = None
    source_type: Optional[str] = None
    listing_url: Optional[str] = None
    listing_position: Optional[int] = None
    listing_rank: Optional[int] = None  # Movers list rank is not a bestseller rank.
    is_sponsored: Optional[bool] = None
    price_amount: Optional[str] = None
    price_currency: Optional[str] = None
    listings: List[ProductListing] = field(default_factory=list)

    @property
    def raw_metric(self) -> Dict[str, Any]:
        return {key: getattr(self, key) for key in ("price", "price_amount", "price_currency", "rating", "reviews_count",
                                                  "rank", "search_position", "listing_position", "listing_rank")}

    @property
    def derived_metric(self) -> Dict[str, Any]:
        return {}

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "raw_metric": self.raw_metric, "derived_metric": self.derived_metric}


@dataclass
class DiscussionItem:
    """Community discussion item from Reddit or social forums."""
    title: str
    score: Optional[int] = None
    comments: Optional[int] = None
    content_summary: str = ""
    url: str = ""
    source: str = "Reddit"
    provenance: Optional[RecordProvenance] = None
    post_id: Optional[str] = None
    subreddit: Optional[str] = None
    created_utc: Optional[float] = None
    permalink: str = ""
    selftext: Optional[str] = None
    provider: Optional[str] = None

    @property
    def raw_metric(self) -> Dict[str, Any]:
        return {"score": self.score, "comments": self.comments, "created_utc": self.created_utc}

    @property
    def derived_metric(self) -> Dict[str, Any]:
        return {}

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "raw_metric": self.raw_metric, "derived_metric": self.derived_metric}


@dataclass
class NicheData:
    """Aggregated raw and processed signals for a specific niche."""
    niche_name: str
    collected_at: str
    keywords: List[KeywordSignal] = field(default_factory=list)
    products: List[ProductItem] = field(default_factory=list)
    discussions: List[DiscussionItem] = field(default_factory=list)
    quality_assessment: Optional[QualityAssessment] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "niche_name": self.niche_name,
            "collected_at": self.collected_at,
            "keywords": [k.to_dict() for k in self.keywords],
            "products": [p.to_dict() for p in self.products],
            "discussions": [d.to_dict() for d in self.discussions],
            "quality_assessment": self.quality_assessment.to_dict() if self.quality_assessment else None,
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
    ideas: List[ProductIdea | GroundedIdea] = field(default_factory=list)
    generation_mode: str = "deterministic"
    analysis_status: str = "not_requested"
    warnings: List[str] = field(default_factory=list)
    reddit_pain_points: List[RedditPainPoint] = field(default_factory=list)
    grounded_analysis: Optional[GroundedAnalysis] = None
    ai_validation: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "niche_name": self.niche_name,
            "keywords_content": self.keywords_content,
            "analysis_content": self.analysis_content,
            "ideas_content": self.ideas_content,
            "ideas": [i.to_dict() for i in self.ideas],
            "generation_mode": self.generation_mode,
            "analysis_status": self.analysis_status,
            "warnings": list(self.warnings),
            "reddit_pain_points": [point.to_dict() for point in self.reddit_pain_points],
            "grounded_analysis": self.grounded_analysis.to_dict() if self.grounded_analysis else None,
            "ai_validation": dict(self.ai_validation),
        }
