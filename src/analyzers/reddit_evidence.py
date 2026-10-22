"""Extractive community observations, not generated market-wide pain-point claims."""
import json

from src.models.community import RedditPainPoint
from src.models.schemas import DiscussionItem

REDDIT_SECTION = "### 4. Reddit evidence"


def parse_reddit_pain_points(text: str, discussions: list[DiscussionItem]) -> list[RedditPainPoint]:
    """Fail closed on invented citations/quotes; accept no free-text interpretation."""
    if len(text) > 10_000:
        raise ValueError("Reddit analysis exceeds size limit")
    payload = json.loads(text)
    if not isinstance(payload, dict) or set(payload) != {"pain_points"}:
        raise ValueError("Invalid Reddit evidence schema")
    items = payload["pain_points"]
    if not isinstance(items, list) or len(items) > 5:
        raise ValueError("Too many Reddit pain points")
    evidence = {post.provenance.evidence_id: post for post in discussions
                if post.provenance is not None and post.provenance.source == "reddit" and post.provenance.is_live}
    points, seen = [], set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"quote", "evidence_ids"}:
            raise ValueError("Unsupported Reddit claim fields")
        quote, ids = item["quote"], item["evidence_ids"]
        if (
            not isinstance(quote, str) or not 8 <= len(quote) <= 500 or not quote.strip()
            or not isinstance(ids, list) or not 1 <= len(ids) <= 5
            or any(not isinstance(key, str) or key not in evidence for key in ids)
            or len(set(ids)) != len(ids)
            or any(quote not in (evidence[key].selftext or "") and quote not in evidence[key].title for key in ids)
        ):
            raise ValueError("Reddit quote must exist verbatim in every cited post")
        identity = (quote, tuple(ids))
        if identity not in seen:
            seen.add(identity)
            points.append(RedditPainPoint(quote, tuple(ids)))
    return points
