"""Small, independent validators for observed Amazon fields and currency-preserving prices."""
import re
from decimal import Decimal, InvalidOperation

from src.models.commerce import ObservedPrice
from src.utils.helpers import optional_float

_CURRENCY = r"(?:USD|VND|EUR|GBP|JPY|CNY|CAD|AUD|INR|US\$|CA\$|A\$|[$€£¥₫₹])"
_PRICE = re.compile(rf"\s*(?:(?P<before>{_CURRENCY})\s*(?P<number1>[\d.,\s]+)|(?P<number2>[\d.,\s]+)\s*(?P<after>{_CURRENCY}))\s*\Z")


def parse_observed_price(text: str | None) -> ObservedPrice | None:
    if not isinstance(text, str) or len(text) > 100:
        return None
    match = _PRICE.fullmatch(text.replace("\xa0", " "))
    if not match:
        return None
    number = (match["number1"] or match["number2"]).strip()
    currency = match["before"] or match["after"]
    # Accept strict grouped English numbers, or unambiguous decimal-comma numbers.
    if re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?", number):
        normalized = number.replace(",", "")
    elif currency in {"EUR", "€"} and re.fullmatch(r"(?:\d+|\d{1,3}(?:\.\d{3})+),\d{1,2}", number):
        normalized = number.replace(".", "").replace(",", ".")
    elif ("," not in number or currency in {"EUR", "€"}) and re.fullmatch(r"\d{1,3}(?: \d{3})+(?:[.,]\d{1,2})?", number):
        normalized = number.replace(" ", "").replace(",", ".")
    else:
        return None
    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return ObservedPrice(" ".join(text.split()), format(amount, "f"), currency)


def parse_rating(text: str) -> float | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s+out of\s+5(?:\s+stars?)?\s*", text, re.I)
    value = optional_float(match[1]) if match else None
    return value if value is not None and 0 <= value <= 5 else None


def parse_review_count(text: str) -> int | None:
    match = re.fullmatch(r"\s*(\d+|\d{1,3}(?:,\d{3})+)(?:\s+(?:(?:global\s+)?ratings?|reviews?))?\s*", text, re.I)
    value = int(match[1].replace(",", "")) if match and len(match[1]) <= 20 else None
    return value if value is not None and value <= 2 ** 53 - 1 else None
