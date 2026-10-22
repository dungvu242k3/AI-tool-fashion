"""Versioned heuristic policy, never market observations or learned coefficients."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import ClassVar


COMPONENTS = ("momentum", "recent_interest", "commerce", "community", "competition")
METHOD = "fixed_weight_observed_evidence_v1"
PRECISION = 6
MAX_NICHES = 100
MAX_RECORDS_PER_SOURCE = 1000


@dataclass(frozen=True)
class RankingPolicy:
    """Knobs must be explicit, bounded and persisted with every result.

    Defaults express a research preference, not empirical business performance.
    Changing knobs produces a different policy_id; no run-relative normalisation.
    """

    weights: tuple[tuple[str, float], ...] = (
        ("momentum", 0.30), ("recent_interest", 0.20), ("commerce", 0.20),
        ("community", 0.20), ("competition", 0.10),
    )
    review_reference: float = 100.0
    community_reference: float = 100.0
    min_trend_keywords: int = 2
    min_commerce_products: int = 3
    min_community_posts: int = 3
    min_competition_products: int = 5
    method: ClassVar[str] = METHOD

    def __post_init__(self):
        if (not isinstance(self.weights, tuple) or len(self.weights) != len(COMPONENTS)
                or any(not isinstance(pair, tuple) or len(pair) != 2 for pair in self.weights)
                or tuple(key for key, _ in self.weights) != COMPONENTS):
            raise ValueError("Ranking weights must contain the five components in canonical order")
        numbers = [value for _, value in self.weights]
        if (any(isinstance(value, bool) or not isinstance(value, (int, float))
                or not 0 < value <= 1 for value in numbers)
                or not math.isclose(math.fsum(numbers), 1.0, rel_tol=0, abs_tol=1e-12)):
            raise ValueError("Positive finite ranking weights must sum to one; never auto-reweight")
        if any(round(value, PRECISION) != value for value in numbers):
            raise ValueError("Explicit ranking weights support at most six decimal places")
        for value in (self.review_reference, self.community_reference):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1 <= value <= 1_000_000:
                raise ValueError("Ranking reference constants must be finite and within 1..1000000")
        for value, minimum in ((self.min_trend_keywords, 2), (self.min_commerce_products, 1),
                               (self.min_community_posts, 1), (self.min_competition_products, 2)):
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= MAX_RECORDS_PER_SOURCE:
                raise ValueError("Ranking sample thresholds must be bounded positive integers")

    def to_dict(self) -> dict:
        return {**asdict(self), "weights": dict(self.weights), "method": self.method, "precision": PRECISION}

    @property
    def policy_id(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, allow_nan=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
