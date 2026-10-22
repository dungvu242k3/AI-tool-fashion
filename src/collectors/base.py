"""Collector boundary with per-call context, explicit transport ownership and diagnostics."""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, Optional, TypeVar

from src.collectors.context import CollectionContext
from src.collectors.errors import CollectionError
from src.collectors.http import HTTPClient
from src.models.collection import CollectionResult

T = TypeVar("T")


class BaseCollector(ABC, Generic[T]):
    def __init__(self, name: str, http_client: Optional[HTTPClient] = None):
        self.name = name
        self.http = http_client if http_client is not None else HTTPClient()
        self._owns_http = http_client is None
        self.logger = logging.getLogger(f"collector.{name}")

    def collect(self, niche: Dict[str, Any]) -> CollectionResult[T]:
        context: CollectionContext[T] = CollectionContext(self.name, self.http)
        try:
            self._collect(niche, context)
        except CollectionError as exc:
            context.warnings.append(exc.warning)
        except Exception as exc:
            # Last-resort isolation. Do not leak exception strings/response bodies.
            last_request = context.request_metadata[-1] if context.request_metadata else None
            self.logger.error("collector_internal_error", extra={
                "source": self.name, "error_type": type(exc).__name__,
                "request_id": last_request.request_id if last_request else None,
            })
            context.warn(
                "internal_error", f"Lỗi xử lý collector ({type(exc).__name__}).",
                request_id=last_request.request_id if last_request else None,
            )
        return context.finish()

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @abstractmethod
    def _collect(self, niche: Dict[str, Any], context: CollectionContext[T]) -> None:
        """Append only observed records to context, capturing partial operations."""
        raise NotImplementedError
