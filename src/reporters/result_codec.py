"""Versioned wire envelope and bounded strict cache decoding.

The checksum detects accidental edits/truncation, NOT a malicious local writer.
It does not authenticate provider responses or replace evidence validation.
"""
import hashlib
import hmac
import json
import math
from pathlib import Path

from src.models.research_result import MAX_DOCUMENT_BYTES, ResearchResult, require

ARTIFACT_FIELDS = {"report_filepath", "report_filename", "markdown_content", "document_sha256"}


def report_filename(result: ResearchResult) -> str:
    return f"report_trend_{result.metadata['run_id']}.md"


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def document_digest(data: dict) -> str:
    return hashlib.sha256(canonical_json({k: v for k, v in data.items() if k != "document_sha256"}).encode("utf-8")).hexdigest()


def publication(result: ResearchResult, report_path: Path, markdown: str) -> dict:
    data = result.to_dict()
    data.update(report_filepath=str(report_path.resolve()), report_filename=report_path.name, markdown_content=markdown)
    data["document_sha256"] = document_digest(data)
    return data


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate cache JSON key")
        result[key] = value
    return result


def _invalid_number(value):
    raise ValueError("Non-finite cache number")


def _finite_float(value):
    parsed = float(value)
    require(math.isfinite(parsed), "Non-finite cache float")
    return parsed


def decode_document(body: bytes, *, max_bytes: int = MAX_DOCUMENT_BYTES) -> dict:
    require(len(body) <= max_bytes, "Cache exceeds byte budget")
    result = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                        parse_constant=_invalid_number, parse_float=_finite_float)
    require(isinstance(result, dict), "Cache must be an object")
    return result


def read_document(path: Path, *, max_bytes: int = MAX_DOCUMENT_BYTES) -> dict:
    with path.open("rb") as stream:
        return decode_document(stream.read(max_bytes + 1), max_bytes=max_bytes)


def validate_publication(data: dict, directory: Path) -> ResearchResult:
    result = ResearchResult.from_dict(data)
    # Compare exact JSON types (False must not compare equal to measured zero).
    canonical = result.to_dict()
    require(canonical_json({k: v for k, v in data.items() if k not in ARTIFACT_FIELDS}) == canonical_json(canonical),
            "Cached views disagree with canonical result")
    filename = report_filename(result)
    require(data["report_filename"] == filename and data["report_filepath"] == str((directory / filename).resolve()),
            "Invalid report artifact path")
    require(isinstance(data["markdown_content"], str) and isinstance(data["document_sha256"], str)
            and hmac.compare_digest(data["document_sha256"], document_digest(data)), "Cache checksum mismatch")
    # A checksum alone would not catch a caller hashing inconsistent Markdown.
    from src.reporters.report_generator import ReportGenerator
    require(data["markdown_content"] == ReportGenerator().render(result), "Markdown and JSON disagree")
    return result
