"""Per-call journal and result builder, isolated from reusable collector instances."""
import logging
from contextlib import contextmanager
from dataclasses import replace
from typing import Any, Dict, Generic, Iterable, List, Optional, TypeVar
from urllib.parse import urlsplit
from uuid import uuid4

from src.collectors.errors import CollectionError
from src.collectors.http import HTTPClient, HTTPResponse
from src.collectors.redaction import redact_query
from src.models.collection import (
    CollectionResult, CollectionWarning, RecordProvenance, RequestMetadata, utc_timestamp,
)

T = TypeVar("T")
logger = logging.getLogger(__name__)


class CollectionContext(Generic[T]):
    def __init__(self, source: str, http: HTTPClient):
        self.source = source
        self.http = http
        self.started_at = utc_timestamp()
        self.records: List[T] = []
        self.warnings: List[CollectionWarning] = []
        self.request_metadata: List[RequestMetadata] = []
        self.not_configured = False

    def fetch(self, method: str, url: str, *, operation: str, query: dict, **kwargs: Any) -> HTTPResponse:
        return self.http.fetch(
            method, url, source=self.source, operation=operation,
            query=query, journal=self.request_metadata, **kwargs,
        )

    def warn(self, code: str, message: str, *, request_id=None, operation=None) -> None:
        self.warnings.append(CollectionWarning(code, message, request_id, operation))

    @contextmanager
    def capture(self, operation: str):
        """Catch a single provider operation, keeping earlier successful records."""
        start = len(self.request_metadata)
        warning_start = len(self.warnings)
        try:
            yield
        except CollectionError as exc:
            self.warnings.append(replace(exc.warning, operation=exc.warning.operation or operation))
        except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
            request_id = self.request_metadata[-1].request_id if len(self.request_metadata) > start else None
            self.warn(
                "parse_error", f"Không đọc được cấu trúc dữ liệu nguồn ({type(exc).__name__}); không retry lỗi parse.",
                request_id=request_id, operation=operation,
            )
        if len(self.warnings) > warning_start:
            logger.debug("collector_operation_finished", extra={"source": self.source, "operation": operation})

    def add_records(
        self, records: Iterable[T], response: HTTPResponse, query: Dict[str, Any],
        *, dependencies: Optional[Iterable[str]] = None,
    ) -> None:
        traces = {trace.request_id: trace for trace in self.request_metadata}
        primary = traces.get(response.request_id)
        ids = list(dict.fromkeys([response.request_id, *(dependencies or ())]))
        if primary is None or any(
            key not in traces or traces[key].source != self.source
            or traces[key].status_code is None or not 200 <= traces[key].status_code < 300
            or traces[key].error_code is not None
            for key in ids
        ):
            raise CollectionError("invalid_provenance", "Không có response thành công để xác minh nguồn gốc bản ghi.")
        for record in records:
            url = getattr(record, "source_url", None) or getattr(record, "url", "")
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                self.warn("invalid_source_url", "Bỏ bản ghi không có URL nguồn hợp lệ.", request_id=response.request_id)
                continue
            provenance = RecordProvenance(
                evidence_id=uuid4().hex, source=self.source, source_url=url,
                query=redact_query(query), retrieved_at=primary.completed_at,
                request_id=response.request_id, request_ids=list(ids),
            )
            self.records.append(replace(record, provenance=provenance))

    def finish(self) -> CollectionResult[T]:
        completed_at = utc_timestamp()
        if self.not_configured:
            return CollectionResult(
                self.source, [], "not_configured", self.warnings, self.request_metadata,
                self.started_at, completed_at,
            )
        return CollectionResult.from_records(
            self.source, self.records, self.warnings, request_metadata=self.request_metadata,
            started_at=self.started_at, completed_at=completed_at,
        )
