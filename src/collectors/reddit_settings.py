"""Bounded, deterministic Reddit input; credentials are never part of evidence."""
import os
import re
from dataclasses import dataclass, field, fields

from src.config import REDDIT_MAX_POSTS, REDDIT_TIME_FILTER

SUBREDDIT_PATTERN = re.compile(r"[A-Za-z0-9_]{2,21}\Z")
TIME_WINDOWS = {"hour": 3600, "day": 86400, "week": 7 * 86400,
                "month": 30 * 86400, "year": 365 * 86400, "all": None}


def plain_text(value, limit: int, *, empty: bool = False) -> bool:
    return (isinstance(value, str) and len(value) <= limit and (empty or bool(value.strip()))
            and not any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF for char in value))


@dataclass(frozen=True)
class RedditCredentials:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)

    def __post_init__(self):
        if not plain_text(self.client_id, 256) or not plain_text(self.client_secret, 1024):
            raise ValueError("Invalid Reddit credentials; values are not logged")
        if ":" in self.client_id:
            raise ValueError("Reddit client ID must not contain ':'")

    @classmethod
    def from_env(cls):
        client_id, secret = os.getenv("REDDIT_CLIENT_ID"), os.getenv("REDDIT_CLIENT_SECRET")
        if client_id is None and secret is None:
            return None
        if not client_id or not secret:
            raise ValueError("Set both REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET")
        return cls(client_id, secret)


@dataclass(frozen=True)
class RedditSettings:
    mode: str = "auto"
    time_filter: str = REDDIT_TIME_FILTER
    sort: str = "top"
    max_queries: int = 32
    max_subreddits: int = 8
    max_keywords: int = 8
    max_posts: int = REDDIT_MAX_POSTS
    page_size: int = 25
    max_json_chars: int = 2_000_000
    user_agent: str = "python:ai-tool-fashion:v1.0 (read-only community evidence)"

    def __post_init__(self):
        if self.mode not in {"auto", "oauth", "public_json", "disabled"}:
            raise ValueError("Invalid Reddit mode")
        if self.time_filter not in TIME_WINDOWS or self.sort not in {"top", "new", "relevance", "comments"}:
            raise ValueError("Invalid Reddit search filter")
        for name, upper in {"max_queries": 64, "max_subreddits": 16, "max_keywords": 16,
                            "max_posts": 100, "page_size": 100, "max_json_chars": 5_000_000}.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper:
                raise ValueError(f"Invalid Reddit setting: {name}")
        if not plain_text(self.user_agent, 256) or not self.user_agent.isascii():
            raise ValueError("Reddit User-Agent must be printable ASCII, at most 256 characters")

    @classmethod
    def from_env(cls):
        values = {}
        numeric = {"max_queries", "max_subreddits", "max_keywords", "max_posts", "page_size", "max_json_chars"}
        for item in fields(cls):
            env_name = "REDDIT_USER_AGENT" if item.name == "user_agent" else f"TREND_REDDIT_{item.name.upper()}"
            raw = os.getenv(env_name)
            if raw is None:
                continue
            try:
                values[item.name] = int(raw) if item.name in numeric else raw
            except ValueError:
                raise ValueError(f"Invalid setting: {env_name}") from None
        return cls(**values)


@dataclass(frozen=True)
class RedditSearch:
    subreddit: str
    search_term: str


def build_reddit_searches(niche: dict, settings: RedditSettings) -> list[RedditSearch]:
    subreddits = niche.get("subreddits", [])
    terms = niche.get("seed_keywords")
    if terms is None:
        terms = [niche.get("name")]
    if not isinstance(subreddits, (list, tuple)) or len(subreddits) > settings.max_subreddits:
        raise ValueError("Invalid subreddit list or subreddit budget exceeded")
    if not isinstance(terms, (list, tuple)) or not terms or len(terms) > settings.max_keywords:
        raise ValueError("Invalid Reddit seed keywords or keyword budget exceeded")
    if any(not isinstance(sub, str) or not SUBREDDIT_PATTERN.fullmatch(sub) for sub in subreddits):
        raise ValueError("Only individual subreddit names are allowed")
    if any(not plain_text(term, 200) for term in terms):
        raise ValueError("Invalid Reddit seed keyword")
    # Keep display spelling, deduplicate subreddit names case-insensitively.
    unique_subs, seen = [], set()
    for sub in subreddits:
        if sub.casefold() not in seen:
            unique_subs.append(sub)
            seen.add(sub.casefold())
    unique_terms = list(dict.fromkeys(term.strip() for term in terms))
    if len(unique_subs) * len(unique_terms) > settings.max_queries:
        raise ValueError("Reddit query budget exceeded; reduce input or configure max_queries")
    return [RedditSearch(sub, term) for sub in unique_subs for term in unique_terms]
