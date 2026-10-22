"""Observed commerce values; listing rank and search position are different facts."""
from dataclasses import dataclass
from typing import Optional
import re

from src.models.collection import RecordProvenance

ASIN_PATTERN = re.compile(r"[A-Z0-9]{10}\Z")
SOURCE_LABELS = {"search": "Amazon Search", "best_sellers": "Amazon Best Sellers", "movers_shakers": "Amazon Movers & Shakers"}


@dataclass(frozen=True)
class ProductListing:
    source_type: str
    listing_url: str
    listing_position: int
    search_position: Optional[int]
    listing_rank: Optional[int]
    is_sponsored: Optional[bool]
    provenance: RecordProvenance


@dataclass(frozen=True)
class ObservedPrice:
    display: str
    amount: str  # Decimal string: no floating-point money or guessed exchange rate.
    currency: str  # Observed code/symbol; '$' does not silently become 'USD'.
