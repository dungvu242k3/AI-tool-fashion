"""Immutable, source-checked AI selections; no free-form factual claims."""
from dataclasses import dataclass
from typing import ClassVar


ANALYSIS_VERSION = "grounded-analysis-v1"


@dataclass(frozen=True)
class GroundedFact:
    fact_id: str
    metric: str
    value: str | int | float
    evidence_ids: tuple[str, ...]
    text: str  # Server template populated from verified metric values only.
    kind: ClassVar[str] = "fact"

    def to_dict(self):
        return {"fact_id": self.fact_id, "kind": self.kind, "metric": self.metric, "value": self.value,
                "evidence_ids": list(self.evidence_ids), "text": self.text}


@dataclass(frozen=True)
class GroundedQuote:
    quote_id: str
    quote: str
    evidence_ids: tuple[str, ...]
    kind: ClassVar[str] = "source_quote_not_verified_market_fact"

    def to_dict(self):
        return {"quote_id": self.quote_id, "kind": self.kind, "quote": self.quote, "evidence_ids": list(self.evidence_ids)}


@dataclass(frozen=True)
class GroundedIdea:
    idea_id: str  # Content-derived by the server, not a model-created score/rank.
    name: str
    rationale: str
    target_audience: str
    why_now: str  # Server renders cited facts; model cannot insert market prose.
    evidence_ids: tuple[str, ...]
    basis_fact_ids: tuple[str, ...]
    basis_quote_ids: tuple[str, ...]
    kind: ClassVar[str] = "proposal_not_verified_market_fit"
    validation_status: ClassVar[str] = "source_references_verified"

    def to_dict(self):
        return {"idea_id": self.idea_id, "kind": self.kind, "validation_status": self.validation_status,
                "name": self.name, "rationale": self.rationale, "target_audience": self.target_audience,
                "why_now": self.why_now, "evidence_ids": list(self.evidence_ids),
                "basis_fact_ids": list(self.basis_fact_ids), "basis_quote_ids": list(self.basis_quote_ids)}


@dataclass(frozen=True)
class GroundedAnalysis:
    niche_name: str
    evidence_digest: str
    facts: tuple[GroundedFact, ...]
    quotes: tuple[GroundedQuote, ...]
    ideas: tuple[GroundedIdea, ...]
    limitations: tuple[str, ...]
    schema_version: ClassVar[str] = ANALYSIS_VERSION

    def to_dict(self):
        return {"schema_version": self.schema_version, "niche_name": self.niche_name,
                "evidence_digest": self.evidence_digest, "facts": [item.to_dict() for item in self.facts],
                "quotes": [item.to_dict() for item in self.quotes], "ideas": [item.to_dict() for item in self.ideas],
                "limitations": list(self.limitations)}
