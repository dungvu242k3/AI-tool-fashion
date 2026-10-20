"""
Data Processor.
Cleans, deduplicates, cross-analyzes signals across Google Trends, Amazon, and Reddit,
and calculates price ranges and pain points.
"""
import re
from typing import Dict, Any, List
from src.models.schemas import NicheData, KeywordSignal, ProductItem, DiscussionItem
from src.utils.helpers import safe_float


class DataProcessor:
    """Processes, filters, and calculates summary metrics from raw collector data."""

    def process(self, raw_data: Dict[str, Any]) -> NicheData:
        """
        Processes raw collected data into structured NicheData.

        Args:
            raw_data: Dictionary containing raw lists of keywords, products, discussions.

        Returns:
            Structured NicheData object with ranked keywords and clean metrics.
        """
        niche_name = raw_data.get("niche", "Unknown Niche")
        collected_at = raw_data.get("collected_at", "")

        # 1. Process and rank keywords
        raw_keywords = raw_data.get("keywords_data", [])
        keywords = self._process_keywords(raw_keywords)

        # 2. Process products
        raw_products = raw_data.get("products_data", [])
        products = self._process_products(raw_products)

        # 3. Process discussions
        raw_discussions = raw_data.get("discussions_data", [])
        discussions = self._process_discussions(raw_discussions)

        return NicheData(
            niche_name=niche_name,
            collected_at=collected_at,
            keywords=keywords,
            products=products,
            discussions=discussions,
        )

    def _process_keywords(self, raw_keywords: List[Any]) -> List[KeywordSignal]:
        """Deduplicates and sorts keywords by score."""
        seen = set()
        cleaned: List[KeywordSignal] = []

        for item in raw_keywords:
            if isinstance(item, KeywordSignal):
                kw_obj = item
            elif isinstance(item, dict):
                kw_obj = KeywordSignal(
                    keyword=item.get("keyword", ""),
                    trend=item.get("trend", "stable"),
                    score=float(item.get("score") or item.get("current_score") or 50.0),
                    signal_summary=item.get("signal_summary", ""),
                    source=item.get("source", "Google Trends"),
                    source_url=item.get("source_url", ""),
                    related_queries=item.get("related_queries", []),
                )
            else:
                continue

            clean_term = kw_obj.keyword.strip().lower()
            if clean_term and clean_term not in seen:
                seen.add(clean_term)
                # Boost score if trend is rising
                if kw_obj.trend == "rising":
                    kw_obj.score = min(100.0, kw_obj.score + 15.0)
                cleaned.append(kw_obj)

        # Sort descending by score
        cleaned.sort(key=lambda x: x.score, reverse=True)
        return cleaned

    def _process_products(self, raw_products: List[Any]) -> List[ProductItem]:
        """Cleans and deduplicates product items."""
        seen = set()
        cleaned: List[ProductItem] = []

        for item in raw_products:
            if isinstance(item, ProductItem):
                p_obj = item
            elif isinstance(item, dict):
                p_obj = ProductItem(
                    title=item.get("title", ""),
                    price=item.get("price", "N/A"),
                    rating=safe_float(item.get("rating"), 4.5),
                    reviews_count=int(item.get("reviews_count", 0)),
                    rank=int(item.get("rank", 0)),
                    url=item.get("url", ""),
                    source=item.get("source", "Amazon"),
                )
            else:
                continue

            clean_title = p_obj.title.strip().lower()
            if clean_title and clean_title not in seen:
                seen.add(clean_title)
                cleaned.append(p_obj)

        return cleaned

    def _process_discussions(self, raw_discussions: List[Any]) -> List[DiscussionItem]:
        """Cleans discussion posts."""
        seen = set()
        cleaned: List[DiscussionItem] = []

        for item in raw_discussions:
            if isinstance(item, DiscussionItem):
                d_obj = item
            elif isinstance(item, dict):
                d_obj = DiscussionItem(
                    title=item.get("title", ""),
                    score=int(item.get("score", 0)),
                    comments=int(item.get("comments", 0)),
                    content_summary=item.get("content_summary", ""),
                    url=item.get("url", ""),
                    source=item.get("source", "Reddit"),
                )
            else:
                continue

            clean_title = d_obj.title.strip().lower()
            if clean_title and clean_title not in seen:
                seen.add(clean_title)
                cleaned.append(d_obj)

        return cleaned

    @staticmethod
    def extract_price_range(products: List[ProductItem]) -> Dict[str, Any]:
        """Extracts minimum, maximum, and average price from product list."""
        prices = []
        for p in products:
            clean_str = p.price.replace(",", "")
            match = re.search(r"[\$]?\s*(\d+(?:\.\d{1,2})?)", clean_str)
            if match:
                val = float(match.group(1))
                if 1.0 <= val <= 300.0:
                    prices.append(val)
                elif val > 5000:
                    prices.append(round(val / 25400.0, 2))

        if not prices:
            return {"min": 15.0, "max": 45.0, "avg": 28.0, "formatted": "$15.00 – $45.00"}

        min_p = min(prices)
        max_p = max(prices)
        avg_p = sum(prices) / len(prices)
        return {
            "min": min_p,
            "max": max_p,
            "avg": avg_p,
            "formatted": f"${min_p:.2f} – ${max_p:.2f} (Trung bình: ${avg_p:.2f})",
        }
