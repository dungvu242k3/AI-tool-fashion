"""Aggregate source availability without conflating recovery with terminal failure."""
from collections import Counter
from typing import Dict

from src.models.collection import CollectionResult


def aggregate_source_health(collections: Dict[str, Dict[str, CollectionResult]]) -> dict:
    grouped = {}
    for sources in collections.values():
        for source, result in sources.items():
            grouped.setdefault(source, []).append(result)
    health = {}
    for source, results in grouped.items():
        counts = Counter(result.status for result in results)
        records = sum(len(result.records) for result in results)
        all_requests = [trace for result in results for trace in result.request_metadata]
        requests = [trace for trace in all_requests if not trace.cache_reused]
        if counts["not_configured"] == len(results):
            status = "not_configured"
        elif counts["success"] == len(results):
            status = "success"
        else:
            status = "partial" if records else "failed"
        health[source] = {
            "source": source, "status": status, "niche_count": len(results),
            "status_counts": {key: counts[key] for key in ("success", "partial", "failed", "not_configured")},
            "record_count": records, "request_count": len(requests),
            "cached_request_count": sum(trace.cache_reused for trace in all_requests),
            "cached_record_count": sum(
                bool(getattr(record, "provenance", None) and record.provenance.from_cache)
                for result in results for record in result.records
            ),
            "retry_count": sum(trace.attempt > 1 for trace in requests),
            "request_error_counts": dict(Counter(trace.error_code for trace in requests if trace.error_code)),
            "warning_counts": dict(Counter(warning.code for result in results for warning in result.warnings)),
        }
    return health
