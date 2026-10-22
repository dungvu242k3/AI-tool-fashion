"""One closed JSON schema for both Ollama's format and local validation."""
from copy import deepcopy

from jsonschema import Draft202012Validator

from src.analyzers.evidence_catalog import METRICS
from src.models.analysis import ANALYSIS_VERSION


LIMITATIONS = (
    "proposals_require_market_validation", "source_samples_not_market_representative",
    "causality_not_established", "customer_profile_not_verified", "insufficient_grounded_basis",
)


def _object(properties):
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


def _ids(pattern, minimum=1, maximum=5):
    return {"type": "array", "minItems": minimum, "maxItems": maximum, "uniqueItems": True,
            "items": {"type": "string", "pattern": pattern, "maxLength": 128}}


FACT_ID = r"^F[1-9][0-9]?$"
QUOTE_ID = r"^Q[1-9]$"
EVIDENCE_ID = r"^[A-Za-z0-9_.:-]{1,128}$"
_SCHEMA = _object({
    "schema_version": {"const": ANALYSIS_VERSION},
    "facts": {"type": "array", "maxItems": 16, "items": _object({
        "fact_id": {"type": "string", "pattern": FACT_ID}, "kind": {"const": "fact"},
        "metric": {"enum": list(METRICS)}, "value": {"type": ["number", "string"], "maxLength": 500},
        "evidence_ids": _ids(EVIDENCE_ID),
    })},
    "quotes": {"type": "array", "maxItems": 5, "items": _object({
        "quote_id": {"type": "string", "pattern": QUOTE_ID},
        "quote": {"type": "string", "minLength": 8, "maxLength": 500}, "evidence_ids": _ids(EVIDENCE_ID),
    })},
    "ideas": {"type": "array", "maxItems": 3, "items": _object({
        "kind": {"const": "proposal"}, "name": {"type": "string", "minLength": 3, "maxLength": 120},
        "what_to_sell": {"type": "string", "minLength": 3, "maxLength": 400},
        "target_audience": {"type": "string", "minLength": 3, "maxLength": 200},
        "basis_fact_ids": _ids(FACT_ID, maximum=8), "basis_quote_ids": _ids(QUOTE_ID, minimum=0),
        "evidence_ids": _ids(EVIDENCE_ID, maximum=12),
    })},
    "limitations": {"type": "array", "minItems": 1, "maxItems": len(LIMITATIONS), "uniqueItems": True,
                    "items": {"enum": list(LIMITATIONS)}},
})
Draft202012Validator.check_schema(_SCHEMA)
VALIDATOR = Draft202012Validator(_SCHEMA)  # No remote refs/format fetchers, compile once.


def output_schema():
    return deepcopy(_SCHEMA)
