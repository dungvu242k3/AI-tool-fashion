"""
Unit tests for helper utility functions.
"""
import pytest
from src.utils.helpers import (
    strip_thinking_tags,
    sanitize_text,
    truncate_text,
    safe_float,
    safe_int,
)


def test_strip_thinking_tags_xml():
    raw_response = "<think>Here is some internal reasoning\nthat should be hidden.</think>Actual visible output"
    cleaned = strip_thinking_tags(raw_response)
    assert cleaned == "Actual visible output"


def test_strip_thinking_tags_prefix():
    raw_response = "Thinking Process:\n1. Analyze user request\n2. Formulate answer\n\nĐây là câu trả lời chính."
    cleaned = strip_thinking_tags(raw_response)
    assert "Thinking Process" not in cleaned
    assert "Đây là câu trả lời chính." in cleaned


def test_strip_thinking_tags_clean_text():
    raw = "Báo cáo xu hướng sản phẩm 2026."
    assert strip_thinking_tags(raw) == raw


def test_sanitize_text():
    dirty = "  Hello   \n\n\t World!   "
    clean = sanitize_text(dirty)
    assert clean == "Hello World!"


def test_truncate_text():
    long_text = "This is a very detailed string containing a lot of characters that need to be shortened."
    truncated = truncate_text(long_text, max_chars=30)
    assert len(truncated) <= 35
    assert truncated.endswith("...")


def test_safe_conversions():
    assert safe_float("12.50") == 12.50
    assert safe_float("invalid", 4.5) == 4.5
    assert safe_int("1200") == 1200
    assert safe_int("bad_int", 10) == 10
