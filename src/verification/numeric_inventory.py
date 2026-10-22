"""Inventory EVERY Unicode numeric occurrence, with source-bound section context.

This is not a value whitelist: section text must first have been reconstructed
from validated snapshots. A number elsewhere in the document cannot justify a
new claim. Source quotes/labels, warnings, IDs and template constants are not
independent market measurements; the ledger explicitly keeps that distinction.
"""
import unicodedata
from collections import Counter

from src.verification.contracts import check

MAX_TOKENS = 100_000
MAX_NUMERIC_FIELDS = 200_000
MAX_BLOCK_MATCHES = 100_000
# Include Unicode digits, superscripts/fractions and signs/separators. Group only
# adjacent numeric characters, preserving exact spelling instead of float coercion.
_SEPARATORS = frozenset(".,+-−/%:–")
_TRAILING = _SEPARATORS - {"%"}


def pointer(*parts):
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def numeric_spans(text):
    start = None
    for index, char in enumerate(text):
        numeric = unicodedata.category(char).startswith("N")
        if numeric and start is None:
            start = index - 1 if index and text[index - 1] in "+-−" else index
        elif start is not None and not numeric and char not in _SEPARATORS:
            end = index
            while end > start and text[end - 1] in _TRAILING:
                end -= 1
            yield start, end, text[start:end]
            start = None
    if start is not None:
        end = len(text)
        while end > start and text[end - 1] in _TRAILING:
            end -= 1
        yield start, end, text[start:end]


def structured_numbers(document):
    result = []
    def visit(value, parts):
        if type(value) in (int, float):
            check(len(result) < MAX_NUMERIC_FIELDS, "numeric_field_budget")
            if parts[0] == "niches" and len(parts) > 2 and parts[2] in {"keywords", "products", "discussions"}:
                category = "snapshot_record_or_recomputed_metric"
            elif parts[0] == "request_metadata":
                category = "snapshot_request_metadata_not_market_metric"
            elif parts[0] in {"ranking", "ranking_assessment", "source_health", "source_statuses", "top_ideas", "analysis_summary"}:
                category = "recomputed_derived_or_validated_view"
            else:
                category = "metadata_or_nested_view_not_independent_measurement"
            result.append({"json_pointer": pointer(*parts), "value": value, "classification": category})
        elif isinstance(value, dict):
            for key, item in value.items():
                visit(item, (*parts, key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, (*parts, index))
    visit(document, ())
    return result


def markdown_numbers(markdown, blocks):
    """Blocks are exact rebuilt text, not arbitrary regexes from a publication."""
    intervals = []
    for block in blocks:
        text = block["text"].strip()
        if not text:
            continue
        start = markdown.find(text)
        while start >= 0:
            check(len(intervals) < MAX_BLOCK_MATCHES, "numeric_block_match_budget")
            intervals.append((start, start + len(text), block))
            start = markdown.find(text, start + len(text))
    intervals.sort(key=lambda item: item[0])
    # A sweep over intervals avoids O(numbers × report sections) on large reports.
    ledger, active, cursor = [], [], 0
    line, line_start, previous = 1, 0, 0
    for start, end, token in numeric_spans(markdown):
        check(len(ledger) < MAX_TOKENS, "numeric_token_budget")
        line += markdown.count("\n", previous, start)
        last_newline = markdown.rfind("\n", previous, start)
        if last_newline >= 0:
            line_start = last_newline + 1
        previous = start
        while cursor < len(intervals) and intervals[cursor][0] <= start:
            active.append(intervals[cursor])
            cursor += 1
        active = [item for item in active if item[1] > start]
        matches = [item[2] for item in active if end <= item[1]]
        ledger.append({
            "line": line, "column": start - line_start + 1, "token": token,
            "classification": "source_bound_section" if matches else "metadata_input_warning_identifier_or_template",
            "section_references": sorted({block["reference"] for block in matches}),
        })
    return {"occurrences": ledger, "counts": dict(Counter(item["classification"] for item in ledger)),
            "scope": "all_Unicode_numeric_characters_including_URLs_IDs_dates_source_text_and_template_constants",
            "not_all_occurrences_are_market_claims": True}
