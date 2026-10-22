"""One auditable evidence gate, independent of UI, ranking and LLM clients."""
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, fields, is_dataclass

from src.models.collection import CollectionResult
from src.models.quality import QualityAssessment, QualityIssue, ValidationStats
from src.models.schemas import NicheData
from src.processors.commerce_scope import is_niche_listing

SOURCE_FIELDS = {"google_trends": "keywords", "amazon": "products", "reddit": "discussions"}
MIN_KEYWORDS = 2
MIN_SUPPORTING_RECORDS = 1


def evidence_digest(data: NicheData) -> str:
    """Detect changes after assessment; not a signature or cryptographic source proof."""
    payload = {"niche_name": data.niche_name, "collected_at": data.collected_at,
               **{source: [asdict(record) for record in getattr(data, field)] for source, field in SOURCE_FIELDS.items()}}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _qualified_product(product) -> bool:
    # A general Best Sellers hub is real commerce evidence, but not niche coverage.
    return any(is_niche_listing(listing.source_type, listing.listing_url) for listing in product.listings)


def _same_snapshot(left, right) -> bool:
    """Python considers False == 0; provenance/measurements require type equality too."""
    if left is right:
        return True
    if type(left) is not type(right):
        return False
    if is_dataclass(left):
        return all(_same_snapshot(getattr(left, item.name), getattr(right, item.name)) for item in fields(left))
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(_same_snapshot(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same_snapshot(left[key], right[key]) for key in left)
    return left == right


def assess_data_quality(data: NicheData, sources: dict[str, CollectionResult]) -> QualityAssessment:
    issues = []
    context_valid = set(sources) == set(SOURCE_FIELDS)
    if not context_valid:
        issues.append(QualityIssue("missing_validation_context", "Thiếu kết quả validation của một hoặc nhiều nguồn."))
    details, known_stats = [], []
    configured, observed = 0, 0
    for source, field in SOURCE_FIELDS.items():
        result = sources.get(source)
        actual = getattr(data, field)
        if not isinstance(result, CollectionResult) or result.source != source:
            context_valid = False
            details.append((source, "missing", None))
            configured += 1
            continue
        stats = result.validation if isinstance(result.validation, ValidationStats) else None
        details.append((source, result.status, stats))
        configured += result.status != "not_configured"
        if stats is not None:
            known_stats.append(stats)
        if not _same_snapshot(actual, result.records) or (result.records and (stats is None or stats.retained_count != len(actual))):
            context_valid = False
            issues.append(QualityIssue("evidence_context_mismatch", "Dữ liệu xử lý không khớp snapshot đã validation; không được thay số đo."))
        elif result.records:
            observed += 1
        if result.status in {"failed", "partial"}:
            issues.append(QualityIssue("source_incomplete", f"Nguồn {source} chưa hoàn thành đầy đủ; không tự tăng trọng số nguồn khác."))
    contexts = defaultdict(set)
    if context_valid:
        for keyword in data.keywords:
            contexts[(keyword.geo, keyword.timeframe)].add(keyword.keyword.strip().casefold())
    measured = max((len(values) for values in contexts.values()), default=0)
    supporting = (sum(_qualified_product(product) for product in data.products) + len(data.discussions)) if context_valid else 0
    if measured < MIN_KEYWORDS:
        issues.append(QualityIssue("insufficient_trend_series", "Cần ít nhất hai keyword khác nhau có time series hợp lệ trong cùng geo/timeframe."))
    if supporting < MIN_SUPPORTING_RECORDS:
        issues.append(QualityIssue("missing_supporting_evidence", "Cần ít nhất một sản phẩm Amazon có phạm vi cụ thể hoặc post Reddit đã validation; hub tổng không đủ evidence cho niche."))
    rejected = sum(stats.rejected_count for stats in known_stats)
    incomplete_points = any(point.value is None or point.is_partial is None for keyword in data.keywords for point in keyword.time_series) if context_valid else False
    if incomplete_points:
        issues.append(QualityIssue("incomplete_trend_points", "Series có điểm thiếu giá trị/trạng thái; giữ nguyên unknown và không nội suy."))
    if rejected:
        issues.append(QualityIssue("rejected_records", "Có candidate bị loại vì schema/provenance; xem thống kê validation theo nguồn."))
    gate_passed = context_valid and measured >= MIN_KEYWORDS and supporting >= MIN_SUPPORTING_RECORDS
    complete = (all(status in {"success", "not_configured"} and stats is not None for _, status, stats in details)
                and not rejected and not incomplete_points)
    status = ("sufficient" if complete else "partial") if gate_passed else "insufficient"
    return QualityAssessment(
        status=status, gate_passed=gate_passed, qualifying_keyword_count=measured, supporting_record_count=supporting,
        configured_source_count=configured, observed_source_count=observed,
        candidate_count=sum(stats.candidate_count for stats in known_stats), valid_count=sum(stats.valid_count for stats in known_stats),
        rejected_count=rejected, duplicate_count=sum(stats.duplicate_count for stats in known_stats),
        retained_count=sum(stats.retained_count for stats in known_stats), sources=tuple(details), issues=tuple(issues),
        data_digest=evidence_digest(data),
    )


def has_sufficient_evidence(data: NicheData) -> bool:
    assessment = data.quality_assessment
    if (not isinstance(assessment, QualityAssessment) or assessment.gate_passed is not True
            or not isinstance(assessment.status, str) or assessment.status not in {"sufficient", "partial"}):
        return False
    try:
        return assessment.data_digest == evidence_digest(data)
    except (ValueError, TypeError, AttributeError, RecursionError, UnicodeError):
        return False
