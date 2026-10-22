"""Normalize records without changing observed measurements."""
import re
from decimal import Decimal, localcontext
from dataclasses import fields
from copy import deepcopy
from typing import Any, Dict, List

from src.models.schemas import DiscussionItem, KeywordSignal, NicheData, ProductItem
from src.models.identities import keyword_identity, record_identity
from src.processors.amazon_values import parse_observed_price
from src.utils.helpers import optional_float  # Legacy USD helper only; no coercion in the evidence pipeline.


class DataProcessor:
    def process(self, raw_data: Dict[str, Any]) -> NicheData:
        return NicheData(
            niche_name=raw_data.get("niche", ""),
            collected_at=raw_data.get("collected_at", ""),
            keywords=self._process_keywords(raw_data.get("keywords_data", [])),
            products=self._process_products(raw_data.get("products_data", [])),
            discussions=self._process_discussions(raw_data.get("discussions_data", [])),
        )

    @staticmethod
    def _records(items, model, title_field, identity):
        """Own independent copies; identity normalization never changes source values."""
        seen = set()
        accepted = {item.name for item in fields(model)}
        for item in items:
            if isinstance(item, model):
                record = item
            elif isinstance(item, dict):
                values = {key: value for key, value in item.items() if key in accepted}
                if title_field not in values:
                    continue
                record = model(**values)
            else:
                continue
            title = getattr(record, title_field)
            if not isinstance(title, str) or not title.strip():
                continue
            try:
                key = identity(record)
                if any(value is None for value in key):
                    continue
                hash(key)
            except (AttributeError, TypeError):
                continue
            if key not in seen:
                seen.add(key)
                yield deepcopy(record)

    def _process_keywords(self, raw_keywords: List[Any]) -> List[KeywordSignal]:
        return list(self._records(raw_keywords, KeywordSignal, "keyword", identity=keyword_identity))

    def _process_products(self, raw_products: List[Any]) -> List[ProductItem]:
        return list(self._records(raw_products, ProductItem, "title", identity=lambda record: record_identity("amazon", record)))

    @staticmethod
    def extract_price_ranges(products: List[ProductItem]) -> List[Dict[str, Any]]:
        """Summarize each observed currency separately, never guessing '$' is USD."""
        groups = {}
        for product in products:
            price = parse_observed_price(product.price)
            if price:
                groups.setdefault(price.currency, []).append(Decimal(price.amount))
        ranges = []
        for currency, amounts in sorted(groups.items()):
            with localcontext() as context:
                context.prec = 128  # Price strings are capped at 100 characters.
                low, high, average = min(amounts), max(amounts), sum(amounts) / len(amounts)
            ranges.append({
                "currency": currency, "min": format(low, "f"), "max": format(high, "f"),
                "avg": format(average, ".2f"), "sample_size": len(amounts),
                "formatted": f"{currency} {low:f} – {high:f} (trung bình mẫu: {average:.2f}; n={len(amounts)})",
            })
        return ranges

    @staticmethod
    def format_price_ranges(products: List[ProductItem]) -> str:
        return "; ".join(item["formatted"] for item in DataProcessor.extract_price_ranges(products)) or "Chưa có mẫu giá kèm currency hợp lệ."

    def _process_discussions(self, raw_discussions: List[Any]) -> List[DiscussionItem]:
        return list(self._records(raw_discussions, DiscussionItem, "title", identity=lambda record: record_identity("reddit", record)))

    @staticmethod
    def extract_price_range(products: List[ProductItem]) -> Dict[str, Any]:
        """Summarize explicit USD prices only; do not guess currencies or rates."""
        prices = []
        for product in products:
            if product.price_currency not in {None, "USD", "US$"}:
                continue
            if not isinstance(product.price, str):
                continue
            match = re.fullmatch(
                r"\s*(?:US\s*)?\$\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?)\s*",
                product.price,
            )
            if match:
                value = optional_float(match.group(1).replace(",", ""))
                if value is not None and value >= 0:
                    prices.append(value)
        if not prices:
            return {
                "min": None, "max": None, "avg": None, "sample_size": 0,
                "formatted": "Chưa có mẫu giá USD hợp lệ.",
            }
        low, high, average = min(prices), max(prices), sum(prices) / len(prices)
        return {
            "min": low, "max": high, "avg": average, "sample_size": len(prices),
            "formatted": "$" + f"{low:.2f} – $" + f"{high:.2f} (Trung bình mẫu: $" + f"{average:.2f})",
        }
