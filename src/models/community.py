"""Source-backed, extractive community observations; not generated market claims."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RedditPainPoint:
    quote: str
    evidence_ids: tuple[str, ...]

    def to_dict(self):
        return {"quote": self.quote, "evidence_ids": list(self.evidence_ids)}
