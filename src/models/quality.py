"""Auditable counts and gate decisions; not a synthetic market/confidence score."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ValidationStats:
    candidate_count: int
    valid_count: int
    rejected_count: int
    duplicate_count: int
    retained_count: int
    rejection_counts: tuple[tuple[str, int], ...] = ()

    def __post_init__(self):
        counts = (self.candidate_count, self.valid_count, self.rejected_count, self.duplicate_count, self.retained_count)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
            raise ValueError("Validation counts must be non-negative integers")
        if self.candidate_count != self.valid_count + self.rejected_count or self.valid_count != self.retained_count + self.duplicate_count:
            raise ValueError("Validation counts do not reconcile")

    @property
    def valid_ratio(self) -> float | None:
        return self.valid_count / self.candidate_count if self.candidate_count else None

    def to_dict(self) -> dict:
        return {**asdict(self), "valid_ratio": self.valid_ratio, "rejection_counts": dict(self.rejection_counts)}


@dataclass(frozen=True)
class QualityIssue:
    code: str
    message: str


@dataclass(frozen=True)
class QualityAssessment:
    status: str
    gate_passed: bool
    qualifying_keyword_count: int
    supporting_record_count: int
    configured_source_count: int
    observed_source_count: int
    candidate_count: int
    valid_count: int
    rejected_count: int
    duplicate_count: int
    retained_count: int
    sources: tuple[tuple[str, str, ValidationStats | None], ...]
    issues: tuple[QualityIssue, ...]
    data_digest: str
    method: str = "validated_series_and_support_v1"

    @property
    def valid_ratio(self) -> float | None:
        complete = all(stats is not None for _, _, stats in self.sources)
        return self.valid_count / self.candidate_count if self.candidate_count and complete else None

    @property
    def source_coverage(self) -> float | None:
        return self.observed_source_count / self.configured_source_count if self.configured_source_count else None

    def to_dict(self) -> dict:
        return {
            "status": self.status, "gate_passed": self.gate_passed, "method": self.method,
            "qualifying_keyword_count": self.qualifying_keyword_count,
            "supporting_record_count": self.supporting_record_count,
            "configured_source_count": self.configured_source_count, "observed_source_count": self.observed_source_count,
            "source_coverage": self.source_coverage,
            "candidate_count": self.candidate_count, "valid_count": self.valid_count,
            "rejected_count": self.rejected_count, "duplicate_count": self.duplicate_count,
            "retained_count": self.retained_count, "valid_ratio": self.valid_ratio,
            "validation_counts_complete": all(stats is not None for _, _, stats in self.sources),
            "sources": {source: {"status": status, "validation": stats.to_dict() if stats else None}
                        for source, status, stats in self.sources},
            "issues": [asdict(issue) for issue in self.issues], "data_digest": self.data_digest,
        }
