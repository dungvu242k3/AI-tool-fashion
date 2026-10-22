"""Typed collection contracts shared by adapters, pipeline and persistence."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Literal, Optional, Sequence, TypeVar, Union
import math

from src.models.quality import ValidationStats

T = TypeVar("T")
CollectionStatus = Literal["success", "partial", "failed", "not_configured"]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class CollectionWarning:
    code: str
    message: str
    request_id: Optional[str] = None
    operation: Optional[str] = None
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class RequestMetadata:
    """One actual HTTP attempt. Retries share operation_id, not request_id."""

    request_id: str
    operation_id: str
    source: str
    operation: str
    method: str
    url: str
    query: Dict[str, Any]
    started_at: str
    completed_at: str
    elapsed_ms: float
    attempt: int = 1
    redirect_hop: int = 0
    status_code: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retry_after_seconds: Optional[float] = None
    retry_delay_seconds: float = 0.0
    cache_reused: bool = False  # Original historical attempt, not new network I/O.

    def __post_init__(self) -> None:
        if not self.request_id or not self.operation_id or self.attempt < 1 or self.redirect_hop < 0:
            raise ValueError("Request identity/attempt is invalid")
        if self.status_code is not None and not 100 <= self.status_code <= 599:
            raise ValueError("HTTP status code is invalid")
        for value in (self.elapsed_ms, self.retry_delay_seconds, self.retry_after_seconds):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError("Request timings must be finite and non-negative")
        for timestamp in (self.started_at, self.completed_at):
            if datetime.fromisoformat(timestamp).utcoffset() is None:
                raise ValueError("Request timestamps must contain a timezone")


@dataclass(frozen=True)
class RecordProvenance:
    evidence_id: str
    source: str
    source_url: str
    query: Dict[str, Any]
    retrieved_at: str
    request_id: str
    request_ids: List[str]
    is_live: bool = True
    from_cache: bool = False


@dataclass
class CollectionResult(Generic[T]):
    source: str
    records: List[T] = field(default_factory=list)
    status: CollectionStatus = "failed"
    warnings: List[CollectionWarning] = field(default_factory=list)
    request_metadata: List[RequestMetadata] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    validation: Optional[ValidationStats] = None

    def __post_init__(self) -> None:
        if self.status not in {"success", "partial", "failed", "not_configured"}:
            raise ValueError("Invalid collection status")
        if self.status == "success" and (not self.records or self.warnings):
            raise ValueError("Successful collection requires records without warnings")
        if self.status == "partial" and (not self.records or not self.warnings):
            raise ValueError("Partial collection requires records and warnings")
        if self.status in {"failed", "not_configured"} and self.records:
            raise ValueError("Failed/unconfigured collections cannot contain records")

    @classmethod
    def from_records(
        cls,
        source: str,
        records: List[T],
        warnings: Optional[Sequence[Union[CollectionWarning, str]]] = None,
        *,
        request_metadata: Optional[Sequence[RequestMetadata]] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
        validation: Optional[ValidationStats] = None,
    ) -> "CollectionResult[T]":
        messages = [
            warning if isinstance(warning, CollectionWarning)
            else CollectionWarning("source_warning", warning)
            for warning in warnings or ()
        ]
        if not records and not messages:
            messages.append(CollectionWarning("no_records", "Nguồn không trả về bản ghi phù hợp."))
        status: CollectionStatus = "partial" if messages else "success"
        return cls(
            source, list(records), status if records else "failed", messages,
            list(request_metadata or ()), started_at, completed_at, validation,
        )

    def status_dict(self, *, include_requests: bool = False) -> Dict[str, Any]:
        result = {
            "source": self.source,
            "status": self.status,
            "record_count": len(self.records),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "fetched_at": self.request_metadata[-1].completed_at if self.request_metadata else None,
            "request_url": self.request_metadata[-1].url if self.request_metadata else None,
            "live_attempted": any(not trace.cache_reused for trace in self.request_metadata),
            "is_live": bool(self.records) and all(
                getattr(record, "provenance", None) is not None and record.provenance.is_live
                for record in self.records
            ),
            "request_count": sum(not trace.cache_reused for trace in self.request_metadata),
            "cached_request_count": sum(trace.cache_reused for trace in self.request_metadata),
            "cached_record_count": sum(
                bool(getattr(record, "provenance", None) and record.provenance.from_cache)
                for record in self.records
            ),
            "warnings": [asdict(warning) for warning in self.warnings],
            "request_ids": [request.request_id for request in self.request_metadata],
            "validation": self.validation.to_dict() if self.validation else None,
        }
        if include_requests:
            result["request_metadata"] = [asdict(request) for request in self.request_metadata]
        return result
