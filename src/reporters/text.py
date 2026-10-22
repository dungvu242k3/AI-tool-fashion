"""Untrusted labels remain text in Markdown and HTML-capable report viewers."""
from html import escape
import re
from urllib.parse import quote

from src.collectors.evidence_validation import is_http_url


def markdown_text(value: str) -> str:
    value = escape(" ".join(value.split()), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#!|])", r"\\\1", value)


def markdown_link(label: str, url: str) -> str:
    """Keep URL delimiters/HTML out of Markdown syntax; never fetch a link."""
    if not is_http_url(url):
        raise ValueError("Unsafe report URL")
    return f"[{markdown_text(label)}]({quote(url, safe=':/?&=%#@+-,._~')})"
