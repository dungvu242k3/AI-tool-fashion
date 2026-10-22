"""Parse only live post fields; never manufacture IDs, counts or community summaries."""
import math
import re

from src.collectors.errors import CollectionError
from src.collectors.http import HTTPResponse
from src.collectors.reddit_provider import bounded_json
from src.collectors.reddit_settings import SUBREDDIT_PATTERN, RedditSearch, RedditSettings, plain_text
from src.models.schemas import DiscussionItem
from src.utils.helpers import truncate_text

POST_ID_PATTERN = re.compile(r"[a-z0-9]{3,16}\Z")
PERMALINK_PATTERN = re.compile(r"/r/([A-Za-z0-9_]{2,21})/comments/([a-z0-9]{3,16})(?:/[^/?#\\\s]{1,300})?/?\Z")
JSON_SAFE_INTEGER = 2**53 - 1


def reddit_permalink(value, post_id: str, subreddit: str) -> str | None:
    if not isinstance(value, str) or len(value) > 512 or not plain_text(value, 512):
        return None
    match = PERMALINK_PATTERN.fullmatch(value)
    if not match or match[1].casefold() != subreddit.casefold() or match[2] != post_id:
        return None
    if value.rstrip("/").rsplit("/", 1)[-1] in {".", ".."}:
        return None
    # Reject encoded separators/control characters rather than decoding ambiguous paths.
    if "%" in value or any(char in value for char in "<>\"'`[]()"):
        return None
    return value


def observed_integer(value, *, nonnegative: bool = False) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) > JSON_SAFE_INTEGER:
        return None
    return value if not nonnegative or value >= 0 else None


def valid_created_utc(value, window_start: float | None, window_end: float) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and 0 < value <= window_end and math.isfinite(value) and (window_start is None or value >= window_start))


def parse_reddit_listing(response: HTTPResponse, request: RedditSearch, settings: RedditSettings,
                         provider: str, window_start: float | None, window_end: float, warn) -> list[DiscussionItem]:
    payload = bounded_json(response, settings.max_json_chars)
    data = payload.get("data") if isinstance(payload, dict) else None
    children = data.get("children") if isinstance(data, dict) else None
    if not isinstance(children, list) or len(children) > settings.page_size:
        raise CollectionError("invalid_payload", "Reddit listing không hợp lệ hoặc vượt page_size.",
                              request_id=response.request_id, operation="search")
    records = []
    for child in children:
        post = child.get("data") if isinstance(child, dict) and child.get("kind", "t3") == "t3" else None
        if not isinstance(post, dict):
            warn("invalid_record", "Bỏ phần tử Reddit không phải post.", request_id=response.request_id, operation="search")
            continue
        post_id, subreddit, title = post.get("id"), post.get("subreddit"), post.get("title")
        if (
            not isinstance(post_id, str) or not POST_ID_PATTERN.fullmatch(post_id)
            or not isinstance(subreddit, str) or not SUBREDDIT_PATTERN.fullmatch(subreddit)
            or subreddit.casefold() != request.subreddit.casefold() or not plain_text(title, 500)
            or reddit_permalink(post.get("permalink"), post_id, subreddit) is None
            or (post.get("name") is not None and post["name"] != f"t3_{post_id}")
        ):
            warn("invalid_record", "Bỏ post Reddit thiếu/xung đột ID, subreddit, title hoặc permalink.",
                 request_id=response.request_id, operation="search")
            continue
        created = post.get("created_utc")
        if not valid_created_utc(created, None, window_end):
            warn("invalid_created_utc", "Bỏ post Reddit thiếu/sai thời điểm hoặc nằm trong tương lai.",
                 request_id=response.request_id, operation="search")
            continue
        if window_start is not None and created < window_start:
            continue
        text = post.get("selftext")
        if text is not None and (not isinstance(text, str) or len(text) > 40_000
                                 or any(0xD800 <= ord(char) <= 0xDFFF for char in text)):
            warn("invalid_selftext", "Bỏ post Reddit có selftext sai kiểu/vượt giới hạn; không cắt dữ liệu gốc.",
                 request_id=response.request_id, operation="search")
            continue
        if (text or "").strip() in {"[deleted]", "[removed]"} or post.get("removed_by_category") is not None:
            continue  # Do not republish source content that has been removed.
        permalink = post["permalink"]
        records.append(DiscussionItem(
            title=title, post_id=post_id, subreddit=subreddit, created_utc=created,
            permalink=permalink, selftext=text, content_summary=truncate_text(text, 200) if text else "",
            score=observed_integer(post.get("score")), comments=observed_integer(post.get("num_comments"), nonnegative=True),
            url=f"https://www.reddit.com{permalink}", source=f"Reddit r/{subreddit}", provider=provider,
        ))
    return records
