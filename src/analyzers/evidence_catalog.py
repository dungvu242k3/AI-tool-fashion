"""Immutable whitelist of measured fields and quote context sent to the model."""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from src.models.schemas import NicheData
from src.processors.commerce_scope import is_niche_listing
from src.processors.data_quality import has_sufficient_evidence
from src.analyzers.analysis_policy import AnalysisPolicy
from src.analyzers.strict_json import AnalysisValidationError


# (source, Vietnamese label, unit). No unconstrained metric/JSON-path evaluation.
METRICS = MappingProxyType({
    "trend.latest_value": ("google_trends", "Interest cuối kỳ hoàn tất", " điểm chỉ số"),
    "trend.recent_mean": ("google_trends", "Interest trung bình kỳ gần đây", " điểm chỉ số"),
    "trend.previous_mean": ("google_trends", "Interest trung bình kỳ trước", " điểm chỉ số"),
    "trend.growth_percent": ("google_trends", "Thay đổi interest giữa hai cửa sổ", "%"),
    "trend.slope": ("google_trends", "Slope interest", " điểm/ngày"),
    "trend.volatility": ("google_trends", "Độ lệch chuẩn interest trong mẫu", " điểm"),
    "trend.trend": ("google_trends", "Nhãn xu hướng theo ngưỡng cấu hình", ""),
    "amazon.title": ("amazon", "Tiêu đề listing", ""),
    "amazon.price": ("amazon", "Giá hiển thị trong snapshot", ""),
    "amazon.rating": ("amazon", "Rating trong snapshot", "/5"),
    "amazon.reviews_count": ("amazon", "Số review trong snapshot", ""),
    "amazon.best_seller_rank": ("amazon", "Best Sellers rank được công bố", ""),
    "amazon.search_position": ("amazon", "Vị trí trong kết quả Search, không phải bestseller", ""),
    "reddit.title": ("reddit", "Tiêu đề post được quan sát, chưa kiểm chứng nội dung", ""),
    "reddit.score": ("reddit", "Điểm Reddit của post, không phải số upvote thô", ""),
    "reddit.comments": ("reddit", "Số bình luận của post trong snapshot", ""),
})


@dataclass(frozen=True)
class AnalysisEvidence:
    evidence_id: str
    source: str
    identity: str
    source_url: str
    retrieved_at: str
    request_id: str
    from_cache: bool
    metrics: tuple[tuple[str, str | int | float], ...]
    quote_context: tuple[str, ...]
    context: tuple[tuple[str, str | int | float | bool | None], ...]

    def to_dict(self):
        return {"evidence_id": self.evidence_id, "source": self.source, "identity": self.identity,
                "source_url": self.source_url, "retrieved_at": self.retrieved_at, "request_id": self.request_id,
                "from_cache": self.from_cache,
                "metrics": dict(self.metrics), "quote_context": list(self.quote_context), "context": dict(self.context)}


@dataclass(frozen=True)
class EvidenceCatalog:
    niche_name: str
    evidence_digest: str
    records: Mapping[str, AnalysisEvidence]
    excluded_record_count: int
    omitted_for_context_count: int
    available_scoped_count: int

    @classmethod
    def from_data(cls, data: NicheData, policy: AnalysisPolicy):
        if not has_sufficient_evidence(data):
            raise AnalysisValidationError("quality_gate_not_passed")
        records = {}
        omitted = 0
        def add(record, identity, metrics, quote_context=(), context=()):
            provenance = record.provenance
            if provenance.evidence_id in records:
                raise AnalysisValidationError("ambiguous_evidence_id")
            if len(records) >= policy.max_evidence_records:
                raise AnalysisValidationError("evidence_record_limit")
            records[provenance.evidence_id] = AnalysisEvidence(
                provenance.evidence_id, provenance.source, identity, provenance.source_url,
                provenance.retrieved_at, provenance.request_id, provenance.from_cache,
                tuple((key, value) for key, value in metrics.items() if value is not None),
                tuple(quote_context), tuple(context),
            )
        keyword_items = sorted(data.keywords, key=lambda item: (item.keyword.casefold(), item.geo, item.timeframe))
        omitted += max(0, len(keyword_items) - policy.max_context_keywords)
        for item in keyword_items[:policy.max_context_keywords]:
            metric = item.metrics
            add(item, item.keyword, {"trend." + name: getattr(metric, name) for name in (
                "latest_value", "recent_mean", "previous_mean", "growth_percent", "slope", "volatility", "trend")},
                context=(("geo", item.geo), ("timeframe", item.timeframe), ("time_series_points", len(item.time_series)),
                         ("previous_start", metric.previous_start), ("previous_end", metric.previous_end),
                         ("recent_start", metric.recent_start), ("recent_end", metric.recent_end)))
        scoped_products = sorted((item for item in data.products if item.is_sponsored is not True
                                  and is_niche_listing(item.source_type, item.listing_url)), key=lambda item: item.asin)
        excluded = len(data.products) - len(scoped_products)
        omitted += max(0, len(scoped_products) - policy.max_context_products)
        for item in scoped_products[:policy.max_context_products]:
            add(item, item.asin, {"amazon.title": item.title, "amazon.price": item.price,
                "amazon.rating": item.rating, "amazon.reviews_count": item.reviews_count,
                "amazon.best_seller_rank": item.rank if item.source_type == "best_sellers" else None,
                "amazon.search_position": item.search_position if item.source_type == "search" else None},
                context=(("source_type", item.source_type), ("is_sponsored", item.is_sponsored),
                         ("price_currency", item.price_currency)))
        posts = sorted(data.discussions, key=lambda item: (-item.created_utc, item.post_id))
        omitted += max(0, len(posts) - policy.max_context_posts)
        for item in posts[:policy.max_context_posts]:
            add(item, item.post_id, {"reddit.title": item.title, "reddit.score": item.score, "reddit.comments": item.comments},
                quote_context=(item.title, (item.selftext or "")[:policy.max_quote_context_chars]),
                context=(("subreddit", item.subreddit), ("created_utc", item.created_utc),
                         ("time_filter", item.provenance.query["time_filter"]),
                         ("body_truncated", len(item.selftext or "") > policy.max_quote_context_chars)))
        available = len(data.keywords) + len(scoped_products) + len(data.discussions)
        return cls(data.niche_name, data.quality_assessment.data_digest, MappingProxyType(records), excluded, omitted, available)

    def context_summary(self):
        return {"selection_policy": "bounded_keyword_identity_asin_then_recent_post_identity_v1",
                "available_scoped_records": self.available_scoped_count, "selected_records": len(self.records),
                "omitted_for_context": self.omitted_for_context_count,
                "excluded_unscoped_or_sponsored": self.excluded_record_count,
                "selected_evidence_ids": list(self.records)}

    def to_dict(self):
        return {"niche_name": self.niche_name, "evidence_digest": self.evidence_digest,
                "excluded_unscoped_or_sponsored_records": self.excluded_record_count,
                "context_selection": self.context_summary(),
                "evidence": [record.to_dict() for record in self.records.values()]}
