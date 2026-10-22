"""One URL-scope rule for the quality gate and ranking; not semantic relevance."""
import re
from urllib.parse import urlsplit


_SCOPED_RANKING_PATH = re.compile(r"/(?:gp/bestsellers|(?:[^/]+/)?zgbs|gp/movers-and-shakers)/[^/]+(?:/[^/]+)*/?\Z")


def is_niche_listing(source_type: str, listing_url: str) -> bool:
    """A general ranking hub cannot support claims about a configured niche."""
    return source_type == "search" or _SCOPED_RANKING_PATH.fullmatch(urlsplit(listing_url).path) is not None
