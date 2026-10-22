"""Bounded context/output policy; no provider data or market defaults."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AnalysisPolicy:
    max_prompt_bytes: int = 24000
    max_response_bytes: int = 65536
    max_evidence_records: int = 100
    max_context_keywords: int = 5
    max_context_products: int = 6
    max_context_posts: int = 4
    max_quote_context_chars: int = 800
    max_output_tokens: int = 4096
    context_tokens: int = 32768

    def __post_init__(self):
        bounds = (
            (self.max_prompt_bytes, 2048, 1000000), (self.max_response_bytes, 1024, 262144),
            (self.max_evidence_records, 3, 1000), (self.max_quote_context_chars, 100, 4000),
            (self.max_context_keywords, 2, 100), (self.max_context_products, 1, 100), (self.max_context_posts, 1, 100),
            (self.max_output_tokens, 256, 16384), (self.context_tokens, 4096, 131072),
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high
               for value, low, high in bounds):
            raise ValueError("Analysis budgets must be bounded integers")
        if self.max_prompt_bytes + self.max_output_tokens + 1024 > self.context_tokens:
            raise ValueError("Conservative prompt byte budget exceeds the configured context reserve")

    def to_dict(self):
        return asdict(self)
