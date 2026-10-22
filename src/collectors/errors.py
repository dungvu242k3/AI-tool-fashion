"""Sanitized operational errors; exception text never includes upstream bodies/credentials."""
from typing import Optional

from src.models.collection import CollectionWarning


class CollectionError(Exception):
    def __init__(
        self, code: str, message: str, *, request_id: Optional[str] = None,
        operation: Optional[str] = None, retryable: bool = False,
    ):
        super().__init__(message)
        self.warning = CollectionWarning(code, message, request_id, operation, retryable)


class ResponseParseError(CollectionError):
    pass
