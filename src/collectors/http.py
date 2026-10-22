"""One observable HTTP attempt per send, with bounded retries and pooled connections."""
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Tuple
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import requests
from requests.adapters import HTTPAdapter

from src.collectors.errors import CollectionError, ResponseParseError
from src.collectors.http_policy import HTTPPolicy
from src.collectors.redaction import redact_query, redact_url
from src.models.collection import RequestMetadata

logger = logging.getLogger(__name__)
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class HTTPSession(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class HTTPResponse:
    trace: RequestMetadata
    text: str = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)
    cookies: Mapping[str, str] = field(repr=False)

    @property
    def request_id(self) -> str:
        return self.trace.request_id

    def json(self, trim_chars: int = 0) -> Any:
        try:
            return json.loads(self.text[trim_chars:])
        except (ValueError, TypeError) as exc:
            raise ResponseParseError(
                "invalid_json", "Nguồn trả JSON không hợp lệ; không retry lỗi parse.",
                request_id=self.request_id, operation=self.trace.operation,
            ) from exc


def retry_after_seconds(value: Optional[str], now: datetime) -> Optional[float]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if re.fullmatch(r"\d+", value):
        # An unreasonable header must not cause a premature retry or unbounded conversion.
        if len(value) > 128:
            raise ValueError("Retry-After exceeds supported length")
        return float(value)
    try:
        deadline = parsedate_to_datetime(value)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return max(0.0, (deadline - now).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def _network_error(exc: requests.RequestException) -> tuple[str, bool]:
    if isinstance(exc, requests.exceptions.SSLError):
        return "tls_error", False
    if isinstance(exc, requests.ConnectTimeout):
        return "connect_timeout", True
    if isinstance(exc, requests.ReadTimeout):
        return "read_timeout", True
    if isinstance(exc, requests.Timeout):
        return "timeout", True
    if isinstance(exc, (requests.ConnectionError, requests.exceptions.ChunkedEncodingError)):
        return "connection_error", True
    return "request_error", False


class HTTPClient:
    """Provider-scoped client. Inject clocks/session for deterministic tests.

    Sessions are not shared between providers/workers. Only this class retries;
    requests adapter retries and automatic redirects are disabled.
    """

    def __init__(
        self, session: Optional[HTTPSession] = None, policy: Optional[HTTPPolicy] = None,
        *, sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        random_value: Callable[[], float] = random.random,
    ):
        self.policy = policy if policy is not None else HTTPPolicy.from_env()
        self._owns_session = session is None
        self._session = session if session is not None else requests.Session()
        if self._owns_session:
            # No implicit proxy/.netrc credentials. Explicit provider auth remains supported.
            self._session.trust_env = False
            for prefix in ("https://", "http://"):
                self._session.mount(prefix, HTTPAdapter(max_retries=0, pool_connections=4, pool_maxsize=4))
        self._sleep = sleep
        self._monotonic = monotonic
        self._utcnow = utcnow
        self._random = random_value
        self._cooldowns: Dict[str, float] = {}
        self._closed = False

    def close(self) -> None:
        if not self._closed and self._owns_session:
            self._session.close()
        self._closed = True

    def __enter__(self) -> "HTTPClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def fetch(
        self, method: str, url: str, *, source: str, operation: str,
        query: Mapping[str, Any], journal: List[RequestMetadata],
        params: Optional[dict] = None, headers: Optional[dict] = None,
        cookies: Optional[dict] = None, retry_safe: bool = False,
        data: Optional[dict] = None, auth: Optional[Any] = None,
        follow_redirects: bool = True,
    ) -> HTTPResponse:
        if self._closed:
            raise RuntimeError("HTTP client is closed")
        method = method.upper()
        origin = urlsplit(url)
        if origin.scheme not in {"http", "https"} or not origin.hostname or origin.username or origin.password:
            raise ValueError("Only HTTP URLs without embedded credentials are supported")
        operation_id = uuid4().hex
        safe_query = redact_query(dict(query))
        may_retry = method in {"GET", "HEAD"} or retry_safe
        waited = 0.0
        hop = 0
        attempt = 1
        current_url = url
        while True:
            host = urlsplit(current_url).netloc.lower()
            pending = max(0.0, self._cooldowns.get(host, 0.0) - self._monotonic())
            if pending:
                if waited + pending > self.policy.retry_wait_budget:
                    raise CollectionError(
                        "source_cooldown", "Nguồn đang yêu cầu chờ; vượt ngân sách retry của request.",
                        operation=operation, retryable=True,
                    )
                self._sleep(pending)
                waited += pending

            response, trace, retryable = self._send(
                method, current_url, params=params, headers=headers, cookies=cookies,
                source=source, operation=operation, query=safe_query,
                operation_id=operation_id, attempt=attempt, hop=hop,
                data=data, auth=auth,
            )
            after = None
            if response is not None:
                try:
                    after = retry_after_seconds(response.headers.get("Retry-After"), self._utcnow())
                except ValueError as exc:
                    self._record(trace, journal)
                    raise CollectionError(
                        "invalid_retry_after", "Retry-After vượt độ dài hỗ trợ; dừng request.",
                        request_id=trace.request_id, operation=operation,
                    ) from exc
            trace = replace(trace, retry_after_seconds=after)
            status = trace.status_code
            is_redirect = status in REDIRECT_STATUSES
            if after is not None and (retryable or is_redirect):
                self._cooldowns[host] = max(self._cooldowns.get(host, 0), self._monotonic() + after)

            if response is not None and status is not None and 200 <= status < 300 and trace.error_code is None:
                self._record(trace, journal)
                return replace(response, trace=trace)

            if is_redirect and response is not None:
                target = urljoin(current_url, response.headers.get("Location", ""))
                target_parts = urlsplit(target)
                if (
                    not follow_redirects or auth is not None or data is not None
                    or hop >= self.policy.max_redirects or not response.headers.get("Location")
                    or target_parts.netloc.lower() != origin.netloc.lower()
                    or target_parts.scheme != origin.scheme
                    or target_parts.username or target_parts.password
                ):
                    self._record(replace(trace, error_code="redirect_rejected", error_message="Redirect không được chấp nhận."), journal)
                    raise CollectionError(
                        "redirect_rejected", "Redirect vượt giới hạn hoặc đổi origin; chưa lấy được dữ liệu.",
                        request_id=trace.request_id, operation=operation,
                    )
                if after is not None and waited + after > self.policy.retry_wait_budget:
                    self._record(trace, journal)
                    raise CollectionError(
                        "retry_after_deferred", "Retry-After vượt ngân sách chờ; dừng request.",
                        request_id=trace.request_id, operation=operation, retryable=True,
                    )
                self._record(trace, journal)
                if status == 303 or (status in {301, 302} and method == "POST"):
                    method = "GET"
                    may_retry = True
                current_url, params = target, None
                hop += 1
                attempt = 1
                continue

            can_retry = may_retry and retryable and attempt < self.policy.max_attempts
            delay = 0.0
            if can_retry:
                cap = min(self.policy.backoff_cap, self.policy.backoff_base * 2 ** (attempt - 1))
                delay = max(after or 0.0, cap * (0.5 + 0.5 * self._random()))
                if waited + delay > self.policy.retry_wait_budget:
                    self._record(trace, journal)
                    raise CollectionError(
                        "retry_after_deferred" if after is not None else "retry_budget_exhausted",
                        "Thời gian retry vượt ngân sách; dừng request và giữ lỗi nguồn.",
                        request_id=trace.request_id, operation=operation, retryable=retryable,
                    )
            self._record(replace(trace, retry_delay_seconds=delay), journal)
            if not can_retry:
                raise CollectionError(
                    trace.error_code or "http_error",
                    f"Nguồn không khả dụng ({trace.error_code}); đã thử {attempt} lần.",
                    request_id=trace.request_id, operation=operation, retryable=retryable,
                )
            self._sleep(delay)
            waited += delay
            attempt += 1

    def _send(
        self, method: str, url: str, *, params: Optional[dict], headers: Optional[dict],
        cookies: Optional[dict], source: str, operation: str, query: Dict[str, Any],
        operation_id: str, attempt: int, hop: int,
        data: Optional[dict] = None, auth: Optional[Any] = None,
    ) -> Tuple[Optional[HTTPResponse], RequestMetadata, bool]:
        request_id = uuid4().hex
        prepared_url = requests.Request(method, url, params=params).prepare().url
        effective_url = prepared_url
        started_at = self._utcnow().isoformat(timespec="milliseconds")
        started = self._monotonic()
        raw = None
        body, response_headers, response_cookies = "", {}, {}
        status, error_code, message, retryable = None, None, None, False
        try:
            # OAuth form bodies and credentials are transport-only: never in a trace.
            private_options = {}
            if data is not None:
                private_options["data"] = data
            if auth is not None:
                private_options["auth"] = auth
            raw = self._session.request(
                method, url, params=params, headers=headers, cookies=cookies,
                timeout=self.policy.timeout, allow_redirects=False, stream=True,
                **private_options,
            )
            if raw.request is not None and raw.request.url:
                effective_url = raw.request.url
            status = raw.status_code
            response_headers = requests.structures.CaseInsensitiveDict(raw.headers)
            if 200 <= status < 300:
                body = self._bounded_text(raw)
                response_cookies = dict(raw.cookies.items())
            elif status not in REDIRECT_STATUSES:
                error_code, message = f"http_{status}", f"HTTP {status} từ nguồn dữ liệu."
                retryable = status in self.policy.RETRY_STATUSES
        except CollectionError as exc:
            error_code, message = exc.warning.code, exc.warning.message
        except requests.RequestException as exc:
            if exc.request is not None and exc.request.url:
                effective_url = exc.request.url
            error_code, retryable = _network_error(exc)
            message = f"Lỗi kết nối nguồn: {error_code}."
        finally:
            if raw is not None:
                raw.close()
        trace = RequestMetadata(
            request_id=request_id, operation_id=operation_id, source=source, operation=operation,
            method=method, url=redact_url(effective_url), query=dict(query),
            started_at=started_at, completed_at=self._utcnow().isoformat(timespec="milliseconds"),
            elapsed_ms=round(max(0, self._monotonic() - started) * 1000, 3),
            attempt=attempt, redirect_hop=hop, status_code=status,
            error_code=error_code, error_message=message,
        )
        response = HTTPResponse(trace, body, response_headers, response_cookies) if raw is not None else None
        return response, trace, retryable

    def _bounded_text(self, response):
        # iter_content bounds decompressed bytes as well as chunked bodies. Never use
        # .text/.content first: both would allocate an unbounded response per worker.
        body = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if len(body) + len(chunk) > self.policy.max_response_bytes:
                raise CollectionError("response_too_large", "Response vượt giới hạn byte; không parse hoặc retry.")
            body.extend(chunk)
        try:
            return body.decode(response.encoding or "utf-8", errors="replace")
        except LookupError:
            return body.decode("utf-8", errors="replace")

    @staticmethod
    def _record(trace: RequestMetadata, journal: List[RequestMetadata]) -> None:
        journal.append(trace)
        logger.info("collector_http_attempt", extra={
            "source": trace.source, "request_id": trace.request_id,
            "operation_id": trace.operation_id, "operation": trace.operation,
            "status_code": trace.status_code, "error_code": trace.error_code,
            "attempt": trace.attempt, "elapsed_ms": trace.elapsed_ms,
            "url": trace.url,
        })
