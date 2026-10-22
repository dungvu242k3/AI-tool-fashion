"""Validate bounded Amazon requests before I/O; only fixed marketplace routes are allowed."""
import os
import re
from dataclasses import dataclass, fields
from urllib.parse import urlsplit, urlunsplit

from src.config import AMAZON_BASE_URL, AMAZON_MAX_PRODUCTS
from src.models.commerce import ASIN_PATTERN, SOURCE_LABELS
_RANKING_PATHS = {
    "best_sellers": re.compile(r"/(?:gp/bestsellers|(?:[A-Za-z0-9-]+/)?zgbs)(?:/[A-Za-z0-9-]+)*/?\Z"),
    "movers_shakers": re.compile(r"/gp/movers-and-shakers(?:/[A-Za-z0-9-]+)*/?\Z"),
}


def amazon_source_type(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        if (
            parts.scheme != "https" or parts.hostname not in {"www.amazon.com", "amazon.com"}
            or parts.username or parts.password or parts.port not in {None, 443}
            or "\\" in url or any(ord(char) < 32 or ord(char) == 127 for char in url)
        ):
            return None
        if parts.path in {"/s", "/s/"}:
            return "search"
        for kind, pattern in _RANKING_PATHS.items():
            if pattern.fullmatch(parts.path):
                return kind
    except (ValueError, TypeError):
        return None
    return None


@dataclass(frozen=True)
class AmazonSettings:
    max_requests: int = 4
    max_products: int = AMAZON_MAX_PRODUCTS
    max_cards_per_page: int = 100
    max_html_chars: int = 2_000_000
    include_sponsored: bool = False

    def __post_init__(self):
        for name, upper in {"max_requests": 8, "max_products": 100, "max_cards_per_page": 200, "max_html_chars": 5_000_000}.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper:
                raise ValueError(f"Invalid Amazon setting: {name}")
        if not isinstance(self.include_sponsored, bool):
            raise ValueError("include_sponsored must be boolean")

    @classmethod
    def from_env(cls):
        values = {}
        for item in fields(cls):
            raw = os.getenv(f"TREND_AMAZON_{item.name.upper()}")
            if raw is None:
                continue
            if item.name == "include_sponsored":
                if raw.lower() not in {"true", "false"}:
                    raise ValueError("TREND_AMAZON_INCLUDE_SPONSORED must be true or false")
                values[item.name] = raw.lower() == "true"
            else:
                try:
                    values[item.name] = int(raw)
                except ValueError:
                    raise ValueError(f"Invalid setting: TREND_AMAZON_{item.name.upper()}") from None
        return cls(**values)


@dataclass(frozen=True)
class AmazonRequest:
    source_type: str
    url: str
    search_term: str | None = None

    @property
    def params(self) -> dict | None:
        return {"k": self.search_term} if self.source_type == "search" else None


def build_amazon_requests(niche: dict, settings: AmazonSettings) -> list[AmazonRequest]:
    sources = niche.get("amazon_sources")
    if sources is None:
        terms = niche.get("amazon_search_terms")
        if terms is None:
            terms = [niche["name"]]
        if not isinstance(terms, (list, tuple)):
            raise ValueError("Amazon search terms must be a list")
        sources = [{"type": "search", "query": term} for term in terms]
    if not isinstance(sources, list) or not 1 <= len(sources) <= settings.max_requests:
        raise ValueError("Amazon source count exceeds the configured request budget")
    requests, seen = [], set()
    for item in sources:
        if not isinstance(item, dict) or item.get("type") not in SOURCE_LABELS:
            raise ValueError("Invalid Amazon source type")
        kind = item["type"]
        if kind == "search":
            term = item.get("query")
            if (
                set(item) - {"type", "query"} or not isinstance(term, str) or not term.strip() or len(term) > 200
                or any(ord(char) < 32 or ord(char) == 127 for char in term)
            ):
                raise ValueError("Invalid Amazon search term")
            request = AmazonRequest(kind, f"{AMAZON_BASE_URL}/s", term.strip())
        else:
            url = item.get("url")
            if not isinstance(url, str) or len(url) > 1000 or set(item) - {"type", "url"} or amazon_source_type(url) != kind:
                raise ValueError("Invalid Amazon ranking URL")
            parts = urlsplit(url)
            if parts.query or parts.fragment:
                raise ValueError("Amazon ranking URLs must not contain query parameters or fragments")
            request = AmazonRequest(kind, urlunsplit(("https", "www.amazon.com", parts.path.rstrip("/"), "", "")))
        identity = (request.source_type, request.url, request.search_term)
        if identity not in seen:
            seen.add(identity)
            requests.append(request)
    return requests
