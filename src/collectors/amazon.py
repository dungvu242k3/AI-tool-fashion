"""Collect verified Amazon source pages with per-ASIN, per-listing provenance."""
from dataclasses import replace

from src.collectors.base import BaseCollector
from src.collectors.context import CollectionContext
from src.collectors.amazon_parser import AmazonPageParser
from src.collectors.amazon_settings import AmazonSettings, build_amazon_requests
from src.collectors.errors import CollectionError, ResponseParseError
from src.config import AMAZON_BASE_URL
from src.models.commerce import ProductListing
from src.models.schemas import ProductItem


class AmazonCollector(BaseCollector[ProductItem]):
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, http_client=None, *, settings: AmazonSettings | None = None):
        self.settings = settings if settings is not None else AmazonSettings.from_env()
        self.parser = AmazonPageParser(self.settings)
        super().__init__("amazon", http_client)

    def _collect(self, niche: dict, context: CollectionContext[ProductItem]) -> None:
        try:
            requests = build_amazon_requests(niche, self.settings)
        except (ValueError, TypeError, KeyError) as exc:
            raise CollectionError("invalid_input", "Cấu hình nguồn Amazon không hợp lệ hoặc vượt giới hạn.") from exc
        for request in requests:
            warning_start = len(context.warnings)
            with context.capture(request.source_type):
                query = {"source_type": request.source_type, "search_term": request.search_term, "niche": niche["name"]}
                response = context.fetch(
                    "GET", request.url, params=request.params, headers=self.HEADERS,
                    operation=request.source_type, query=query,
                )
                mime = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if mime not in {"text/html", "application/xhtml+xml"}:
                    raise ResponseParseError("invalid_content_type", "Amazon không trả HTML.", request_id=response.request_id)
                page = self.parser.parse(
                    response.text, source_type=request.source_type,
                    page_url=response.trace.url, request_id=response.request_id,
                )
                if page.discarded_cards:
                    context.warn("invalid_product_cards", f"Bỏ {page.discarded_cards} card thiếu định danh hoặc tiêu đề hợp lệ.", request_id=response.request_id)
                if not page.products:
                    context.warn(
                        "no_eligible_products" if page.sponsored_filtered else "no_product_cards",
                        "Amazon không trả card sản phẩm đủ điều kiện.",
                        request_id=response.request_id, operation=request.source_type,
                    )
                context.add_records(page.products, response, query)
                context.records = self._merge_listings(context.records)
            if any(warning.code in {"http_429", "http_403", "source_blocked", "source_cooldown", "retry_after_deferred"} for warning in context.warnings[warning_start:]):
                break

    @staticmethod
    def _parse_products(html: str):
        """Parser-only compatibility entry point; these records have no live provenance."""
        return list(AmazonPageParser(AmazonSettings()).parse(html, source_type="search", page_url=f"{AMAZON_BASE_URL}/s").products)

    def _merge_listings(self, records):
        products = {}
        for product in records:
            listings = product.listings or [ProductListing(
                product.source_type, product.listing_url, product.listing_position,
                product.search_position, product.listing_rank, product.is_sponsored, product.provenance,
            )]
            if product.asin in products:
                products[product.asin].listings.extend(listings)
            elif len(products) < self.settings.max_products:
                products[product.asin] = replace(product, listings=list(listings))
        return list(products.values())
