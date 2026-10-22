"""Cross-view record integrity without re-running collection, scoring or analysis."""
from dataclasses import fields
import hashlib
import json

from src.models.schemas import KeywordSignal, ProductItem, DiscussionItem

RECORD_MODELS = {"google_trends": ("keywords", KeywordSignal), "amazon": ("products", ProductItem),
                 "reddit": ("discussions", DiscussionItem)}


def encoded(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def validate_record_views(niche: dict) -> None:
    """Match phase-6 digest with actual serialized records; don't guess missing fields."""
    payload = {key: niche[key] for key in ("niche_name", "collected_at")}
    for source, (field, model) in RECORD_MODELS.items():
        values = []
        for record in niche[field]:
            raw = {item.name: record[item.name] for item in fields(model)}
            values.append(raw)
            # raw_metric properties only read scalars; nested dicts aren't used as models.
            expected_raw = model(**raw).raw_metric
            expected_derived = (record["metrics"] or {}) if source == "google_trends" else {}
            if encoded(record["raw_metric"]) != encoded(expected_raw) or encoded(record["derived_metric"]) != encoded(expected_derived):
                raise ValueError("Raw/derived metric views disagree")
        payload[source] = values
    digest = hashlib.sha256(encoded(payload).encode("utf-8")).hexdigest()
    if niche["quality_assessment"]["data_digest"] != digest:
        raise ValueError("Evidence changed after quality assessment")
