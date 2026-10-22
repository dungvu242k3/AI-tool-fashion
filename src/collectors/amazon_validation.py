"""Validate modern Amazon records, including every retained listing's provenance."""
import math

from src.collectors.amazon_settings import ASIN_PATTERN, SOURCE_LABELS, amazon_source_type
from src.config import AMAZON_BASE_URL
from src.models.collection import RecordProvenance
from src.models.commerce import ProductListing
from src.processors.amazon_values import parse_observed_price


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 2**53 - 1


def _valid_listing(listing, product_url, traces):
    if not isinstance(listing, ProductListing) or not isinstance(listing.source_type, str) or listing.source_type not in SOURCE_LABELS:
        return False
    if amazon_source_type(listing.listing_url) != listing.source_type or not _positive_int(listing.listing_position):
        return False
    if listing.source_type == "search":
        if not _positive_int(listing.search_position) or listing.search_position != listing.listing_position or listing.listing_rank is not None or not isinstance(listing.is_sponsored, bool):
            return False
    elif listing.search_position is not None or (listing.is_sponsored is not None and listing.is_sponsored is not True) or (listing.listing_rank is not None and not _positive_int(listing.listing_rank)):
        return False
    provenance = listing.provenance
    if not isinstance(provenance, RecordProvenance) or (
        provenance.source != "amazon" or provenance.is_live is not True or provenance.source_url != product_url
        or not isinstance(provenance.query, dict) or provenance.query.get("source_type") != listing.source_type
        or not isinstance(provenance.request_id, str) or not isinstance(provenance.request_ids, list)
        or any(not isinstance(key, str) for key in provenance.request_ids)
        or provenance.request_id not in provenance.request_ids or not isinstance(provenance.evidence_id, str) or not provenance.evidence_id
    ):
        return False
    primary = traces.get(provenance.request_id)
    return (
        primary is not None and primary.url == listing.listing_url and primary.operation == listing.source_type
        and provenance.retrieved_at == primary.completed_at
        and all(key in traces and traces[key].source == "amazon" and traces[key].status_code is not None
                and 200 <= traces[key].status_code < 300 and traces[key].error_code is None for key in provenance.request_ids)
    )


def valid_amazon_product(product, traces) -> bool:
    if (
        not isinstance(product.asin, str) or not ASIN_PATTERN.fullmatch(product.asin)
        or product.url != f"{AMAZON_BASE_URL}/dp/{product.asin}"
        or not isinstance(product.source_type, str) or product.source_type not in SOURCE_LABELS or product.source != SOURCE_LABELS[product.source_type]
        or not isinstance(product.listings, list) or not product.listings
    ):
        return False
    if product.price is None:
        if product.price_amount is not None or product.price_currency is not None:
            return False
    else:
        price = parse_observed_price(product.price)
        if price is None or product.price_amount != price.amount or product.price_currency != price.currency:
            return False
    if product.rating is not None and (
        isinstance(product.rating, bool) or not isinstance(product.rating, (int, float))
        or not math.isfinite(product.rating) or not 0 <= product.rating <= 5
    ):
        return False
    if product.reviews_count is not None and (isinstance(product.reviews_count, bool) or not isinstance(product.reviews_count, int) or not 0 <= product.reviews_count <= 2 ** 53 - 1):
        return False
    if not all(_valid_listing(listing, product.url, traces) for listing in product.listings):
        return False
    primary_listing = ProductListing(
        product.source_type, product.listing_url, product.listing_position, product.search_position,
        product.listing_rank, product.is_sponsored, product.provenance,
    )
    if not _valid_listing(primary_listing, product.url, traces) or (product.rank is not None and not _positive_int(product.rank)):
        return False
    first = product.listings[0]
    identities = [listing.provenance.evidence_id for listing in product.listings]
    return (
        len(set(identities)) == len(identities) and first.provenance == product.provenance
        and first == primary_listing
        and product.rank == (first.listing_rank if first.source_type == "best_sellers" else None)
    )
