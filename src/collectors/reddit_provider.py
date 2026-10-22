"""Read-only official OAuth/public JSON adapters on the observable HTTP transport."""
import math
import re
import time
from typing import Callable, Protocol

from requests.auth import AuthBase, HTTPBasicAuth

from src.collectors.context import CollectionContext
from src.collectors.errors import CollectionError
from src.collectors.http import HTTPResponse
from src.collectors.reddit_settings import RedditCredentials, RedditSearch, RedditSettings


def bounded_json(response: HTTPResponse, max_chars: int):
    if len(response.text) > max_chars:
        raise CollectionError("response_too_large", "JSON Reddit vượt giới hạn; không parse.",
                              request_id=response.request_id, operation=response.trace.operation)
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise CollectionError("invalid_content_type", "Reddit không trả application/json; có thể là trang chặn.",
                              request_id=response.request_id, operation=response.trace.operation)
    return response.json()


class RedditProvider(Protocol):
    name: str

    def search(self, request: RedditSearch, context: CollectionContext, query: dict) -> HTTPResponse: ...


class _RedditRequestAuth(AuthBase):
    """Prevent Requests from replacing Bearer/public access with ambient .netrc auth."""
    def __init__(self, authorization: str | None):
        self._authorization = authorization

    def __call__(self, request):
        if self._authorization:
            request.headers["Authorization"] = self._authorization
        else:
            request.headers.pop("Authorization", None)
        return request


class PublicJSONRedditProvider:
    name = "public_json"
    origin = "https://www.reddit.com"

    def __init__(self, settings: RedditSettings, *, monotonic: Callable[[], float] = time.monotonic):
        self.settings = settings
        self._monotonic = monotonic
        self._blocked_until = 0.0

    def cache_identity(self):
        return {"provider": self.name, "schema": "reddit-json-v1", "scope": "public"}

    def search(self, request: RedditSearch, context: CollectionContext, query: dict) -> HTTPResponse:
        if self._monotonic() < self._blocked_until:
            raise CollectionError("source_cooldown", "Quota Reddit đã hết; không gửi request tiếp.", operation="search", retryable=True)
        response = self._search(request, context, query, {"User-Agent": self.settings.user_agent, "Accept": "application/json"})
        self._read_quota(response)
        return response

    def _search(self, request, context, query, headers):
        suffix = ".json" if self.name == "public_json" else ""
        return context.fetch(
            "GET", f"{self.origin}/r/{request.subreddit}/search{suffix}", operation="search", query=query,
            params={"q": request.search_term, "restrict_sr": "on", "sort": self.settings.sort,
                    "t": self.settings.time_filter, "limit": self.settings.page_size, "raw_json": 1, "type": "link"},
            headers=headers, auth=_RedditRequestAuth(headers.get("Authorization")), follow_redirects=False,
        )

    def _read_quota(self, response):
        try:
            remaining = float(response.headers.get("X-Ratelimit-Remaining", "nan"))
            reset = float(response.headers.get("X-Ratelimit-Reset", "nan"))
            if math.isfinite(remaining) and remaining < 1 and math.isfinite(reset) and reset > 0:
                # Huge reset values fail closed without blocking the worker in sleep.
                self._blocked_until = self._monotonic() + min(reset, 86400)
        except (ValueError, TypeError, OverflowError):
            pass  # Malformed optional headers are not invented quota measurements.


class OAuthRedditProvider(PublicJSONRedditProvider):
    name = "oauth"
    origin = "https://oauth.reddit.com"

    def __init__(self, settings: RedditSettings, credentials: RedditCredentials, **kwargs):
        super().__init__(settings, **kwargs)
        self._credentials = credentials
        self._token = None
        self._expires_at = 0.0

    def cache_identity(self):
        from src.collectors.collection_cache import credential_scope
        return {"provider": self.name, "schema": "reddit-json-v1", "scope": credential_scope(self._credentials)}

    def _access_token(self, context):
        if self._token is not None and self._monotonic() < self._expires_at:
            return self._token
        self._token = None
        response = context.fetch(
            "POST", "https://www.reddit.com/api/v1/access_token", operation="oauth_token",
            query={"provider": self.name, "grant_type": "client_credentials"},
            headers={"User-Agent": self.settings.user_agent, "Accept": "application/json"},
            data={"grant_type": "client_credentials"},
            auth=HTTPBasicAuth(self._credentials.client_id, self._credentials.client_secret), follow_redirects=False,
        )
        payload = bounded_json(response, min(self.settings.max_json_chars, 16_384))
        token = payload.get("access_token") if isinstance(payload, dict) else None
        expires = payload.get("expires_in") if isinstance(payload, dict) else None
        if (
            not isinstance(token, str) or not 1 <= len(token) <= 4096 or not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token)
            or str(payload.get("token_type", "")).lower() != "bearer"
            or isinstance(expires, bool) or not isinstance(expires, (int, float))
            or not 0 < expires <= 86400 or not math.isfinite(expires)
        ):
            raise CollectionError("invalid_oauth_response", "Reddit không trả token/expiry hợp lệ; không chuyển sang public JSON.",
                                  request_id=response.request_id, operation="oauth_token")
        self._token = token
        self._expires_at = self._monotonic() + expires - min(30, expires / 10)
        return token

    def _search(self, request, context, query, headers):
        # At most one token refresh on 401; never downgrade to unauthenticated access.
        for attempt in range(2):
            headers = {**headers, "Authorization": f"Bearer {self._access_token(context)}"}
            try:
                return super()._search(request, context, query, headers)
            except CollectionError as exc:
                if exc.warning.code != "http_401" or attempt:
                    raise
                self._token = None
        raise AssertionError("Unreachable OAuth refresh state")


def create_reddit_provider(settings: RedditSettings) -> RedditProvider | None:
    if settings.mode == "disabled":
        return None
    if settings.mode == "public_json":
        return PublicJSONRedditProvider(settings)
    credentials = RedditCredentials.from_env()
    if settings.mode == "oauth" and credentials is None:
        raise ValueError("OAuth requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET")
    if credentials is not None:
        return OAuthRedditProvider(settings, credentials)
    return PublicJSONRedditProvider(settings)
