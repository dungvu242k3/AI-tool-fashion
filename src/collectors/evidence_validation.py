"""Bounded provenance primitives. Validation never fetches a user-supplied URL."""
import math
import re
from datetime import datetime
from urllib.parse import urlsplit

from src.models.collection import RecordProvenance, RequestMetadata
from src.collectors.redaction import redact_query

IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
MAX_DEPENDENCIES = 200
PROVIDER_HOSTS = {
    "google_trends": {"trends.google.com", "suggestqueries.google.com"},
    "amazon": {"www.amazon.com"},
    "reddit": {"www.reddit.com", "oauth.reddit.com"},
}


def valid_text(value, limit: int, *, empty: bool = False, multiline: bool = False) -> bool:
    return (isinstance(value, str) and len(value) <= limit and (empty or bool(value.strip()))
            and not any(0xD800 <= ord(char) <= 0xDFFF or ord(char) == 127
                        or (ord(char) < 32 and (not multiline or char not in "\n\r\t")) for char in value))


def finite_number(value, low: float, high: float) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and low <= value <= high and math.isfinite(value))


def aware_timestamp(value) -> datetime | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return None
    try:
        moment = datetime.fromisoformat(value)
        return moment if moment.utcoffset() is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def is_http_url(value) -> bool:
    if not valid_text(value, 32_768) or "\\" in value:
        return False
    try:
        parts = urlsplit(value)
        return (parts.scheme in {"http", "https"} and bool(parts.hostname) and not parts.username
                and not parts.password and parts.port in {None, 80, 443})
    except (ValueError, TypeError):
        return False


def bounded_json(value, *, depth=0, budget=None) -> bool:
    """Check before recursion/redaction/serialization; cycles exhaust the depth bound."""
    if budget is None:
        budget = [2048, 100_000]
    budget[0] -= 1
    if budget[0] < 0 or depth > 8:
        return False
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, str):
        budget[1] -= len(value)
        return budget[1] >= 0 and valid_text(value, 32_768, empty=True, multiline=True)
    if isinstance(value, (int, float)):
        return finite_number(value, -(2**53 - 1), 2**53 - 1)
    if isinstance(value, dict):
        return len(value) <= 100 and all(
            isinstance(key, str) and bounded_json(key, depth=depth + 1, budget=budget)
            and bounded_json(item, depth=depth + 1, budget=budget) for key, item in value.items())
    if isinstance(value, list):
        return len(value) <= 200 and all(bounded_json(item, depth=depth + 1, budget=budget) for item in value)
    return False


def valid_trace(trace, source: str, now: datetime) -> bool:
    if not isinstance(trace, RequestMetadata):
        return False
    start, end = aware_timestamp(trace.started_at), aware_timestamp(trace.completed_at)
    if (
        not isinstance(trace.request_id, str) or not IDENTIFIER.fullmatch(trace.request_id)
        or not isinstance(trace.operation_id, str) or not IDENTIFIER.fullmatch(trace.operation_id)
        or trace.source != source or not isinstance(trace.method, str) or trace.method not in {"GET", "HEAD", "POST"}
        or not valid_text(trace.operation, 64) or not is_http_url(trace.url)
        or not isinstance(trace.query, dict) or not bounded_json(trace.query)
        or not isinstance(trace.cache_reused, bool) or start is None or end is None or start > end
        or (end - now).total_seconds() > 60
        or not finite_number(trace.elapsed_ms, 0, 86_400_000)
        or not finite_number(trace.retry_delay_seconds, 0, 86400)
        or (trace.retry_after_seconds is not None and not finite_number(trace.retry_after_seconds, 0, 2**53 - 1))
        or isinstance(trace.attempt, bool) or not isinstance(trace.attempt, int) or not 1 <= trace.attempt <= 10
        or isinstance(trace.redirect_hop, bool) or not isinstance(trace.redirect_hop, int) or not 0 <= trace.redirect_hop <= 10
        or (trace.status_code is not None and (isinstance(trace.status_code, bool) or not isinstance(trace.status_code, int)
                                             or not 100 <= trace.status_code <= 599))
        or (trace.error_code is not None and not valid_text(trace.error_code, 64))
        or (trace.error_message is not None and not valid_text(trace.error_message, 2000, multiline=True))
    ):
        return False
    parts = urlsplit(trace.url)
    return parts.scheme == "https" and parts.netloc in PROVIDER_HOSTS[source] and not parts.fragment


def valid_provenance(provenance, source: str, public_url: str, traces: dict) -> bool:
    if not isinstance(provenance, RecordProvenance) or (
        provenance.source != source or provenance.source_url != public_url or not is_http_url(public_url)
        or provenance.is_live is not True or not isinstance(provenance.from_cache, bool)
        or not isinstance(provenance.evidence_id, str) or not IDENTIFIER.fullmatch(provenance.evidence_id)
        or not isinstance(provenance.query, dict) or not provenance.query or not bounded_json(provenance.query)
        or redact_query(provenance.query) != provenance.query
        or not isinstance(provenance.request_id, str)
        or not isinstance(provenance.request_ids, list) or not 1 <= len(provenance.request_ids) <= MAX_DEPENDENCIES
        or any(not isinstance(key, str) for key in provenance.request_ids)
        or len(set(provenance.request_ids)) != len(provenance.request_ids)
        or provenance.request_id not in provenance.request_ids
        or aware_timestamp(provenance.retrieved_at) is None
    ):
        return False
    primary = traces.get(provenance.request_id)
    return (primary is not None and provenance.retrieved_at == primary.completed_at
            and provenance.from_cache == primary.cache_reused
            and all(key in traces and traces[key].source == source and traces[key].status_code is not None
                    and 200 <= traces[key].status_code < 300 and traces[key].error_code is None
                    for key in provenance.request_ids))
