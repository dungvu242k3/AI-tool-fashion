"""Parse one verified Amazon listing page; no I/O, synthetic metrics or JS execution."""
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from src.collectors.amazon_settings import ASIN_PATTERN, SOURCE_LABELS, AmazonSettings, amazon_source_type
from src.collectors.errors import ResponseParseError
from src.config import AMAZON_BASE_URL
from src.models.schemas import ProductItem
from src.processors.amazon_values import parse_observed_price, parse_rating, parse_review_count


@dataclass(frozen=True)
class AmazonPage:
    products: tuple[ProductItem, ...]
    discarded_cards: int
    sponsored_filtered: int


class AmazonPageParser:
    def __init__(self, settings: AmazonSettings):
        self.settings = settings

    def parse(self, html: str, *, source_type: str, page_url: str, request_id=None) -> AmazonPage:
        def fail(code, message):
            raise ResponseParseError(code, message, request_id=request_id, operation=source_type)

        if len(html) > self.settings.max_html_chars:
            fail("payload_too_large", "Trang Amazon vượt giới hạn xử lý HTML.")
        if amazon_source_type(page_url) != source_type:
            fail("source_mismatch", "URL trang Amazon thực tế không khớp loại nguồn yêu cầu.")
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        if (
            soup.select_one('form[action*="validateCaptcha"], #captchacharacters, #challenge-container')
            or re.search(r"robot check|access denied|captcha", title, re.I)
            or "automated access to amazon data" in html.lower()
        ):
            fail("source_blocked", "Amazon yêu cầu xác minh hoặc từ chối truy cập; không vượt captcha.")
        if source_type != "search":
            heading = " ".join(node.get_text(" ", strip=True) for node in soup.select("h1, #zg_banner_text, #zg_banner_subtext"))
            expected = r"best\s*sellers" if source_type == "best_sellers" else r"movers\s*(?:&|and)\s*shakers"
            if not re.search(expected, heading, re.I):
                fail("source_mismatch", "Trang Amazon không xác nhận tiêu đề loại bảng xếp hạng.")
        selector = 'div[data-component-type="s-search-result"]' if source_type == "search" else (
            ".zg-grid-general-faceout, .p13n-sc-uncoverable-faceout, .zg-item-immersion"
        )
        candidates = soup.select(selector)
        candidate_ids = {id(card) for card in candidates}
        cards = [card for card in candidates if not any(id(parent) in candidate_ids for parent in card.parents)]
        products, discarded, sponsored_filtered = [], 0, 0
        for position, card in enumerate(cards[:self.settings.max_cards_per_page], 1):
            detected_ad = self._sponsored(card)
            sponsored = detected_ad if source_type == "search" or detected_ad else None
            if sponsored and not self.settings.include_sponsored:
                sponsored_filtered += 1
                continue
            asin = self._asin(card)
            title = self._title(card)
            if asin is None or title is None:
                discarded += 1
                continue
            price = self._price(card)
            rank = self._rank(card) if source_type != "search" else None
            products.append(ProductItem(
                title=title, asin=asin, url=f"{AMAZON_BASE_URL}/dp/{asin}",
                price=price.display if price else None, price_amount=price.amount if price else None,
                price_currency=price.currency if price else None,
                rating=self._rating(card), reviews_count=self._reviews(card, asin),
                source=SOURCE_LABELS[source_type], source_type=source_type, listing_url=page_url,
                listing_position=position, search_position=position if source_type == "search" else None,
                listing_rank=rank, rank=rank if source_type == "best_sellers" else None,
                is_sponsored=sponsored,
            ))
        return AmazonPage(tuple(products), discarded, sponsored_filtered)

    @staticmethod
    def _asin(card):
        declared = str(card.get("data-asin", "")).upper()
        if declared and not ASIN_PATTERN.fullmatch(declared):
            return None
        link = card.select_one("h2 a[href], a[href*='/dp/'], a[href*='/gp/product/']")
        linked = None
        if link:
            href = link.get("href", "")
            try:
                parts = urlsplit(urljoin(AMAZON_BASE_URL, href))
                if (
                    parts.scheme != "https" or parts.hostname not in {"www.amazon.com", "amazon.com"}
                    or parts.username or parts.password or parts.port not in {None, 443}
                    or "\\" in href or any(ord(char) < 32 or ord(char) == 127 for char in href)
                ):
                    return None
                match = re.search(r"/(?:dp|gp/product)/([A-Za-z0-9]{10})(?:[/?]|$)", parts.path)
                linked = match[1].upper() if match else None
            except (ValueError, TypeError):
                return None
        if declared and linked and declared != linked:
            return None
        return declared or linked

    @staticmethod
    def _title(card):
        for selector in ("h2 a span, h2 span, h2", "[class*='p13n-sc-css-line-clamp']", ".p13n-sc-truncate-desktop-type2", "a[href*='/dp/'] img[alt]"):
            node = card.select_one(selector)
            if node is None:
                continue
            text = node.get("alt", "") if node.name == "img" else node.get_text(" ", strip=True)
            if 1 <= len(text) <= 1000 and text.casefold() not in {"results", "sponsored"}:
                return text
        return None

    @staticmethod
    def _sponsored(card):
        return bool(card.get("data-ad-id") or "AdHolder" in card.get("class", []) or card.select_one(
            '[data-component-type="s-sponsored-label-marker"], .puis-sponsored-label-text, '
            '.s-sponsored-label-text, .s-sponsored-label-info-icon, [aria-label="Sponsored"]'
        ))

    @staticmethod
    def _price(card):
        price_node = card.select_one(".a-price:not(.a-text-price)")
        if price_node:
            offscreen = price_node.select_one(".a-offscreen")
            if offscreen:
                return parse_observed_price(offscreen.get_text(" ", strip=True))
            symbol, whole, fraction = (price_node.select_one(selector) for selector in (".a-price-symbol", ".a-price-whole", ".a-price-fraction"))
            if symbol and whole and fraction:
                cents = fraction.get_text(strip=True)
                if re.fullmatch(r"\d{2}", cents):
                    return parse_observed_price(f"{symbol.get_text(strip=True)}{whole.get_text(strip=True).rstrip('.,')}.{cents}")
        node = card.select_one(".p13n-sc-price")
        return parse_observed_price(node.get_text(" ", strip=True)) if node else None

    @staticmethod
    def _rating(card):
        for node in card.select(".a-icon-alt, [aria-label*='out of 5']"):
            for text in (node.get("aria-label", ""), node.get_text(" ", strip=True)):
                value = parse_rating(text)
                if value is not None:
                    return value
        return None

    @staticmethod
    def _reviews(card, asin):
        for node in card.select('a[href*="customerReviews"] span, a[href*="#customerReviews"], a[href*="/product-reviews/"] span, a[href*="/product-reviews/"], span[aria-label$="ratings"], span[aria-label$="reviews"]'):
            link = node if node.name == "a" else node.find_parent("a")
            identity = re.search(r"/product-reviews/([A-Za-z0-9]{10})(?:[/?#]|$)", link.get("href", "")) if link else None
            if identity and identity[1].upper() != asin:
                continue
            for text in (node.get("aria-label", ""), node.get_text(" ", strip=True)):
                value = parse_review_count(text)
                if value is not None:
                    return value
        return None

    @staticmethod
    def _rank(card):
        badge = card.select_one(".zg-bdg-text")
        text = badge.get_text(strip=True) if badge else ""
        value = parse_review_count(text[1:]) if text.startswith("#") else None
        return value if value is not None and value > 0 else None
