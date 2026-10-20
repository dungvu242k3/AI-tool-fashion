"""
Helper utility functions for data sanitization, formatting, and text processing.
"""
import re
from typing import Any


def strip_thinking_tags(text: str) -> str:
    """
    Strips deep thinking / reasoning tokens output by models like Qwen 3.5 / DeepSeek.
    Handles <think>...</think> XML blocks and 'Thinking Process:' prefixes.
    """
    if not text:
        return ""

    # Remove <think>...</think>
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)

    # Remove markdown/plain 'Thinking Process: ... \n\n' if present at start
    cleaned = re.sub(
        r"^(?:\*\*|\#\#)?\s*Thinking Process:?[\s\S]*?\n\s*\n",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    return cleaned.strip()


def sanitize_text(text: str) -> str:
    """Removes irregular control characters and normalizes whitespace."""
    if not text:
        return ""
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def truncate_text(text: str, max_chars: int = 300) -> str:
    """Truncates long text neatly at word boundary with ellipsis."""
    if not text or len(text) <= max_chars:
        return text
    truncated = text[:max_chars].rsplit(" ", 1)[0]
    return f"{truncated}..."


def safe_float(val: Any, default: float = 0.0) -> float:
    """Safely converts value to float without raising exceptions."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_int(val: Any, default: int = 0) -> int:
    """Safely converts value to int without raising exceptions."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default
