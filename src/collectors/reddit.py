"""Deterministic, bounded Reddit collection; source failures never become fake posts."""
from datetime import datetime, timezone
from typing import Any, Callable, Dict

from src.collectors.base import BaseCollector
from src.collectors.context import CollectionContext
from src.collectors.reddit_parser import parse_reddit_listing
from src.collectors.reddit_provider import RedditProvider, create_reddit_provider
from src.collectors.reddit_settings import TIME_WINDOWS, RedditSettings, build_reddit_searches
from src.models.schemas import DiscussionItem

STOP_ERRORS = frozenset({
    "http_401", "http_403", "http_429", "source_cooldown", "retry_after_deferred",
    "retry_budget_exhausted", "connect_timeout", "read_timeout", "timeout", "connection_error",
    "tls_error", "request_error", "redirect_rejected", "invalid_oauth_response",
    "invalid_content_type", "response_too_large", "invalid_retry_after",
    "http_500", "http_502", "http_503", "http_504",
})


class RedditCollector(BaseCollector[DiscussionItem]):
    def __init__(self, http_client=None, *, settings: RedditSettings | None = None,
                 provider: RedditProvider | None = None,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        try:
            self.settings = settings if settings is not None else RedditSettings.from_env()
            self.provider = provider if provider is not None else create_reddit_provider(self.settings)
        except ValueError:
            # Bad/partial credentials affect Reddit only, not other pipeline sources.
            self.settings, self.provider = None, None
        self._utcnow = utcnow
        super().__init__("reddit", http_client)

    def _collect(self, niche: Dict[str, Any], context: CollectionContext[DiscussionItem]) -> None:
        if self.settings is None:
            context.warn("invalid_configuration", "Cấu hình Reddit/credential không hợp lệ; kiểm tra biến môi trường, chưa gửi request.")
            return
        if self.provider is None:
            context.not_configured = True
            context.warn("not_configured", "Reddit đã được tắt trong cấu hình.")
            return
        try:
            searches = build_reddit_searches(niche, self.settings)
        except ValueError:
            context.warn("invalid_configuration", "Cấu hình truy vấn Reddit sai hoặc vượt giới hạn; chưa gửi request.")
            return
        if not searches:
            context.not_configured = True
            context.warn("not_configured", "Chưa cấu hình subreddit cho niche.")
            return
        now = self._utcnow()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Reddit clock must be timezone aware")
        window_end = now.timestamp()
        seconds = TIME_WINDOWS[self.settings.time_filter]
        window_start = window_end - seconds if seconds is not None else None
        seen, limit_warned = set(), False
        for search in searches:
            query = {"provider": self.provider.name, "subreddit": search.subreddit,
                     "search_term": search.search_term, "time_filter": self.settings.time_filter,
                     "sort": self.settings.sort, "window_start_utc": window_start, "window_end_utc": window_end}
            warning_start = len(context.warnings)
            with context.capture("search"):
                response = self.provider.search(search, context, query)
                posts = parse_reddit_listing(response, search, self.settings, self.provider.name,
                                             window_start, window_end, context.warn)
                accepted = []
                for post in posts:
                    if post.post_id in seen:
                        continue
                    if len(context.records) + len(accepted) >= self.settings.max_posts:
                        if not limit_warned:
                            context.warn("record_limit", "Đã đạt giới hạn post; giữ snapshot đầu tiên theo thứ tự query, không phải ranking.",
                                         request_id=response.request_id, operation="search")
                            limit_warned = True
                        continue
                    seen.add(post.post_id)
                    accepted.append(post)
                context.add_records(accepted, response, query)
            if any(warning.code in STOP_ERRORS or warning.operation == "oauth_token"
                   for warning in context.warnings[warning_start:]):
                break
        if not context.records and not context.warnings:
            context.warn("no_discussions", "Reddit không trả post hợp lệ trong cửa sổ thời gian đã chọn.", operation="search")
