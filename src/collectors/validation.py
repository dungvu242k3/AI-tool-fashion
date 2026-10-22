"""Validate, count and deduplicate evidence before normalization, analysis or output."""
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from typing import Protocol

from src.collectors.errors import CollectionError
from src.collectors.amazon_validation import valid_amazon_product
from src.collectors.reddit_validation import valid_reddit_discussion
from src.collectors.trends_validation import valid_keyword_signal
from src.collectors.evidence_validation import IDENTIFIER, aware_timestamp, valid_provenance, valid_text, valid_trace
from src.collectors.redaction import redact_query, redact_url
from src.models.collection import CollectionResult, CollectionWarning
from src.models.identities import record_identity
from src.models.quality import ValidationStats
from src.models.schemas import DiscussionItem, KeywordSignal, ProductItem

RECORD_TYPES = {"google_trends": KeywordSignal, "amazon": ProductItem, "reddit": DiscussionItem}
MAX_CANDIDATES = 1000
MAX_REQUESTS = 5000
MAX_WARNINGS = 10000
VALIDATORS = {"google_trends": valid_keyword_signal, "amazon": valid_amazon_product, "reddit": valid_reddit_discussion}
SCHEMA_ERRORS = {"google_trends": "invalid_keyword_evidence", "amazon": "invalid_product_evidence", "reddit": "invalid_discussion_evidence"}


class Collector(Protocol):
    def collect(self, niche: dict) -> CollectionResult: ...


def _record_error(record, source, traces, evidence_ids):
    if not isinstance(record, RECORD_TYPES[source]):
        return "invalid_schema"
    public_url = getattr(record, "source_url", None) or getattr(record, "url", None)
    if not valid_provenance(record.provenance, source, public_url, traces):
        return "invalid_provenance"
    if record.provenance.evidence_id in evidence_ids:
        return "invalid_provenance"
    title = record.keyword if source == "google_trends" else record.title
    if not valid_text(title, 200 if source == "google_trends" else 2000):
        return "invalid_schema"
    if source == "amazon" and (not isinstance(record.listings, list) or len(record.listings) > 200):
        return "invalid_product_evidence"
    if not VALIDATORS[source](record, traces):
        return SCHEMA_ERRORS[source]
    if source == "amazon":
        for listing in record.listings:
            if (listing.provenance.evidence_id in evidence_ids
                    or not valid_provenance(listing.provenance, source, public_url, traces)):
                return "invalid_provenance"
    return None


def validate_collection_result(source: str, result: CollectionResult, *, now: datetime | None = None) -> CollectionResult:
    if not isinstance(source, str) or source not in RECORD_TYPES or not isinstance(result, CollectionResult) or result.source != source:
        raise CollectionError("invalid_contract", "Collector trả contract hoặc source ID không hợp lệ.")
    if (not isinstance(result.records, list) or not isinstance(result.warnings, list) or len(result.warnings) > MAX_WARNINGS
            or not isinstance(result.request_metadata, list) or len(result.request_metadata) > MAX_REQUESTS
            or not isinstance(result.status, str) or result.status not in {"success", "partial", "failed", "not_configured"}):
        raise CollectionError("invalid_contract", "Container/status hoặc giới hạn nhật ký collector không hợp lệ.")
    if not all(isinstance(warning, CollectionWarning) and valid_text(warning.code, 64)
               and valid_text(warning.message, 2000, multiline=True) and isinstance(warning.retryable, bool)
               and (warning.operation is None or valid_text(warning.operation, 64))
               and (warning.request_id is None or (isinstance(warning.request_id, str) and IDENTIFIER.fullmatch(warning.request_id)))
               for warning in result.warnings):
        raise CollectionError("invalid_contract", "Collector phải trả warning có cấu trúc.")
    clock = now if now is not None else datetime.now(timezone.utc)
    if clock.utcoffset() is None:
        raise ValueError("Validation clock must contain a timezone")
    started, completed = aware_timestamp(result.started_at), aware_timestamp(result.completed_at)
    if ((result.started_at is not None and started is None) or (result.completed_at is not None and completed is None)
            or (started is not None and completed is not None and started > completed)
            or (completed is not None and (completed - clock).total_seconds() > 60)):
        raise CollectionError("invalid_contract", "Timestamp cấp collection không hợp lệ; không lưu metadata sai schema.")
    try:
        journal_valid = all(valid_trace(trace, source, clock) and redact_url(trace.url) == trace.url
                            and redact_query(trace.query) == trace.query for trace in result.request_metadata)
    except (ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        journal_valid = False
    if not journal_valid:
        raise CollectionError("invalid_contract", "Metadata request sai schema, timestamp, origin hoặc chưa che credential; không lưu nhật ký không an toàn.")
    traces = {trace.request_id: trace for trace in result.request_metadata}
    if len(traces) != len(result.request_metadata):
        raise CollectionError("invalid_contract", "Nhật ký request có ID trùng hoặc sai nguồn.")
    if result.status == "not_configured":
        if result.records or result.request_metadata:
            raise CollectionError("invalid_contract", "Nguồn chưa cấu hình không được có request hoặc bản ghi.")
        return replace(result, validation=ValidationStats(0, 0, 0, 0, 0))
    if len(result.records) > MAX_CANDIDATES:
        stats = ValidationStats(len(result.records), 0, len(result.records), 0, 0, (("candidate_limit", len(result.records)),))
        return CollectionResult.from_records(source, [], [CollectionWarning("candidate_limit", "Collector vượt giới hạn candidate; từ chối trước khi duyệt record.")],
                                             request_metadata=result.request_metadata, started_at=result.started_at,
                                             completed_at=result.completed_at, validation=stats)
    records, warnings = [], list(result.warnings)
    evidence_ids, identities = set(), {}
    rejected, duplicates = Counter(), 0
    for record in result.records:
        try:
            error = _record_error(record, source, traces, evidence_ids)
            if error is None and source == "amazon":
                key = record_identity(source, record)
                if key in identities and len(records[identities[key]].listings) + len(record.listings) > 200:
                    error = "listing_limit"
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            error = "invalid_schema"
        if error:
            rejected[error] += 1
            warnings.append(CollectionWarning(error, "Bỏ record sai schema, dữ kiện hoặc không truy ngược được về request thành công."))
            continue
        key = record_identity(source, record)
        evidence_ids.add(record.provenance.evidence_id)
        if source == "amazon":
            evidence_ids.update(listing.provenance.evidence_id for listing in record.listings)
        if key in identities:
            duplicates += 1
            if source == "amazon":
                position = identities[key]
                records[position] = replace(records[position], listings=[*records[position].listings, *record.listings])
            continue
        identities[key] = len(records)
        records.append(record)
    stats = ValidationStats(len(result.records), len(result.records) - sum(rejected.values()), sum(rejected.values()),
                            duplicates, len(records), tuple(sorted(rejected.items())))
    return CollectionResult.from_records(
        source, records, warnings, request_metadata=result.request_metadata,
        started_at=result.started_at, completed_at=result.completed_at, validation=stats,
    )
