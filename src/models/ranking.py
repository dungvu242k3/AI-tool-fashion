"""Immutable scoring outputs. Renderers consume these values, never recalculate."""
from dataclasses import dataclass, fields
from typing import Any

from src.ranking.policy import METHOD, RankingPolicy


def _scalars(instance, *excluded):
    # Do not recursively deepcopy every component/input only to serialize it
    # again below. Nested containers have their own explicit JSON-safe view.
    return {item.name: getattr(instance, item.name) for item in fields(instance) if item.name not in excluded}


@dataclass(frozen=True)
class RankingInput:
    evidence_id: str
    source: str
    source_url: str
    retrieved_at: str
    request_id: str
    from_cache: bool
    identity: str
    measurements: tuple[tuple[str, Any], ...]

    def to_dict(self) -> dict:
        return {**_scalars(self, "measurements"), "measurements": {
            key: list(value) if isinstance(value, tuple) else value for key, value in self.measurements
        }}


@dataclass(frozen=True)
class RankingComponent:
    key: str
    label: str
    source: str
    weight: float
    score: float | None
    contribution: float | None
    status: str
    reason: str
    formula: str
    sample_size: int
    candidate_count: int
    inputs: tuple[RankingInput, ...]
    context: tuple[tuple[str, Any], ...] = ()
    # Actual metric used only after an equal total, not configuration order.
    tie_break_value: float | None = None

    def to_dict(self) -> dict:
        return {**_scalars(self, "context", "inputs"), "context": dict(self.context),
                "inputs": [item.to_dict() for item in self.inputs]}


@dataclass(frozen=True)
class NicheRanking:
    niche: str
    rank: int | None
    status: str
    observed_score: float | None
    total_score: float | None
    score_upper_bound: float | None
    component_coverage: float
    confidence: float | None
    quality_status: str
    evidence_digest: str | None
    components: tuple[RankingComponent, ...]
    reasons: tuple[str, ...]
    explanation: str

    def to_dict(self) -> dict:
        return {**_scalars(self, "components", "reasons"), "components": [item.to_dict() for item in self.components],
                "reasons": list(self.reasons)}


@dataclass(frozen=True)
class RankingResult:
    status: str
    policy: RankingPolicy
    ranking: tuple[NicheRanking, ...]
    unranked: tuple[NicheRanking, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "method": METHOD, "policy_id": self.policy.policy_id, "policy": self.policy.to_dict(),
            "status": self.status, "ranking": [row.to_dict() for row in self.ranking],
            "unranked": [row.to_dict() for row in self.unranked], "warnings": list(self.warnings),
            "score_basis": "conservative_observed_contribution_not_business_probability",
            "confidence_basis": "weighted_input_completeness_times_validation_ratio_not_success_probability",
            "tie_break_order": ["observed_score", "momentum_symmetric_change", "comparable_recent_mean",
                                "median_amazon_rating", "median_reddit_comments", "lower_median_search_reviews"],
            "tie_policy": "equal_measured_keys_share_rank_names_only_stabilise_display",
            "top_ideas_status": "not_evaluated_by_ranking_service",
        }
