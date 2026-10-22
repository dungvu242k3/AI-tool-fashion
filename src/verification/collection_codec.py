"""Closed, typed restoration of collector snapshots; no pickle or dynamic imports."""
from dataclasses import asdict, fields
from copy import deepcopy

from src.collectors.errors import CollectionError
from src.collectors.validation import RECORD_TYPES, validate_collection_result
from src.models.collection import CollectionResult, CollectionWarning, RecordProvenance, RequestMetadata
from src.models.commerce import ProductListing
from src.models.quality import ValidationStats
from src.models.research_result import freeze_json
from src.models.schemas import KeywordSignal, ProductItem
from src.models.trends import TrendMetrics, TrendPoint
from src.reporters.result_codec import canonical_json
from src.verification.contracts import AuditFailure, check


def _values(model, raw):
    check(isinstance(raw, dict) and set(raw) == {item.name for item in fields(model)}, "snapshot_fields")
    return dict(raw)


def restore_record(source, raw):
    check(source in RECORD_TYPES, "snapshot_source")
    model = RECORD_TYPES[source]
    values = _values(model, raw)
    values["provenance"] = RecordProvenance(**_values(RecordProvenance, values["provenance"]))
    if model is KeywordSignal:
        check(isinstance(values["time_series"], list), "snapshot_series")
        values["time_series"] = [TrendPoint(**_values(TrendPoint, point)) for point in values["time_series"]]
        values["metrics"] = TrendMetrics(**_values(TrendMetrics, values["metrics"]))
    if model is ProductItem:
        check(isinstance(values["listings"], list), "snapshot_listings")
        listings = []
        for listing in values["listings"]:
            item = _values(ProductListing, listing)
            item["provenance"] = RecordProvenance(**_values(RecordProvenance, item["provenance"]))
            listings.append(ProductListing(**item))
        values["listings"] = listings
    return model(**values)


def restore_collection(raw: dict) -> CollectionResult:
    """Revalidate retained evidence, preserving honest historical rejection counts.

    Rejected candidates are deliberately absent from phase-11 snapshots. Their
    counts reconcile, but cannot be independently re-parsed from these artifacts.
    """
    try:
        freeze_json(raw)  # Shared node/depth/text/finite-number budget.
        raw = deepcopy(raw)
        values = _values(CollectionResult, raw)
        source = values["source"]
        check(isinstance(source, str) and source in RECORD_TYPES, "snapshot_source")
        for name, maximum in (("records", 1000), ("request_metadata", 5000), ("warnings", 10000)):
            check(isinstance(values[name], list) and len(values[name]) <= maximum, "snapshot_container", name)
        values["records"] = [restore_record(source, record) for record in values["records"]]
        values["request_metadata"] = [RequestMetadata(**_values(RequestMetadata, trace)) for trace in values["request_metadata"]]
        values["warnings"] = [CollectionWarning(**_values(CollectionWarning, item)) for item in values["warnings"]]
        if values["validation"] is not None:
            stats = _values(ValidationStats, values["validation"])
            pairs = stats["rejection_counts"]
            check(isinstance(pairs, list) and all(isinstance(pair, list) and len(pair) == 2
                  and isinstance(pair[0], str) and type(pair[1]) is int and pair[1] > 0 for pair in pairs), "rejection_counts")
            check(len({pair[0] for pair in pairs}) == len(pairs)
                  and sum(pair[1] for pair in pairs) == stats["rejected_count"], "rejection_counts")
            stats["rejection_counts"] = tuple(tuple(pair) for pair in pairs)
            values["validation"] = ValidationStats(**stats)
        result = CollectionResult(**values)
        check((result.validation is not None and result.validation.retained_count == len(result.records))
              or (not result.records and result.validation is None), "snapshot_retained_counts")
        validated = validate_collection_result(source, result)
        check(canonical_json([asdict(item) for item in validated.records]) == canonical_json(raw["records"])
              and validated.status == result.status and validated.warnings == result.warnings,
              "snapshot_evidence_rejected")
        return result
    except AuditFailure:
        raise
    except (CollectionError, ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as exc:
        raise AuditFailure("invalid_collector_snapshot") from exc
