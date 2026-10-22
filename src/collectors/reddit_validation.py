"""Reject ungrounded Reddit records before normalization or reporting (no legacy bypass)."""
import math
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

from src.collectors.reddit_parser import POST_ID_PATTERN, observed_integer, reddit_permalink, valid_created_utc
from src.collectors.reddit_settings import SUBREDDIT_PATTERN, TIME_WINDOWS, plain_text
from src.utils.helpers import truncate_text


def valid_reddit_discussion(record, traces: dict) -> bool:
    if (
        not plain_text(record.title, 500) or not isinstance(record.post_id, str)
        or not POST_ID_PATTERN.fullmatch(record.post_id) or not isinstance(record.subreddit, str)
        or not SUBREDDIT_PATTERN.fullmatch(record.subreddit)
        or reddit_permalink(record.permalink, record.post_id, record.subreddit) is None
        or record.url != f"https://www.reddit.com{record.permalink}"
        or record.source != f"Reddit r/{record.subreddit}"
        or (record.selftext is not None and (not isinstance(record.selftext, str) or len(record.selftext) > 40_000
                                            or any(0xD800 <= ord(char) <= 0xDFFF for char in record.selftext)))
        or (record.selftext or "").strip() in {"[removed]", "[deleted]"}
        or record.content_summary != (truncate_text(record.selftext, 200) if record.selftext else "")
        or (record.score is not None and observed_integer(record.score) is None)
        or (record.comments is not None and observed_integer(record.comments, nonnegative=True) is None)
        or not isinstance(record.provider, str) or record.provider not in {"oauth", "public_json"}
    ):
        return False
    provenance = record.provenance
    primary = traces[provenance.request_id]
    query = provenance.query
    if (
        query != primary.query or query.get("provider") != record.provider
        or not isinstance(query.get("subreddit"), str)
        or query.get("subreddit", "").casefold() != record.subreddit.casefold()
        or not plain_text(query.get("search_term"), 200)
        or not isinstance(query.get("time_filter"), str) or query.get("time_filter") not in TIME_WINDOWS
        or not isinstance(query.get("sort"), str) or query.get("sort") not in {"top", "new", "relevance", "comments"}
        or primary.method != "GET" or primary.operation != "search"
    ):
        return False
    start, end = query.get("window_start_utc"), query.get("window_end_utc")
    if isinstance(end, bool) or not isinstance(end, (int, float)) or not 0 < end < 253402300800 or not math.isfinite(end):
        return False
    seconds = TIME_WINDOWS[query["time_filter"]]
    if seconds is None:
        if start is not None:
            return False
    elif isinstance(start, bool) or not isinstance(start, (int, float)) or start != end - seconds:
        return False
    if not valid_created_utc(record.created_utc, start, end):
        return False
    try:
        parts = urlsplit(primary.url)
        params = parse_qs(parts.query)
        host = "oauth.reddit.com" if record.provider == "oauth" else "www.reddit.com"
        suffix = "" if record.provider == "oauth" else ".json"
        return (
            end <= datetime.fromisoformat(primary.completed_at).timestamp() + 1
            and parts.scheme == "https" and parts.netloc == host and not parts.fragment
            and parts.path == f"/r/{query['subreddit']}/search{suffix}"
            and params.get("q") == [query["search_term"]] and params.get("restrict_sr") == ["on"]
            and params.get("t") == [query["time_filter"]] and params.get("sort") == [query["sort"]]
            and params.get("type") == ["link"]
        )
    except (ValueError, TypeError):
        return False
