"""Bounded research intent, not evidence. No endpoints, credentials or output paths."""
from dataclasses import dataclass
import json
import math

from src.collectors.evidence_validation import valid_text
from src.collectors.reddit_settings import SUBREDDIT_PATTERN
from src.collectors.trends_settings import TrendsSettings
from src.config import CATEGORY, NICHES, GOOGLE_TRENDS_GEO, GOOGLE_TRENDS_TIMEFRAME

MIN_NICHES, MAX_NICHES = 3, 5
MAX_KEYWORDS, MAX_SUBREDDITS = 8, 4
MAX_BODY_BYTES = 32 * 1024


def _text(value, label, limit=200, *, empty=False):
    if not valid_text(value, limit, empty=empty):
        raise ValueError(f"{label} không hợp lệ hoặc vượt {limit} ký tự.")
    return value.strip()


def _unique(values, label, maximum, *, minimum=0):
    if not isinstance(values, (list, tuple)) or not minimum <= len(values) <= maximum:
        raise ValueError(f"{label}: cần {minimum}–{maximum} mục.")
    normalized = tuple(_text(value, label) for value in values)
    if len({value.casefold() for value in normalized}) != len(normalized):
        raise ValueError(f"{label} không được trùng nhau.")
    return normalized


@dataclass(frozen=True, slots=True)
class NicheInput:
    name: str
    seed_keywords: tuple[str, ...]
    subreddits: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "name", _text(self.name, "Tên niche"))
        object.__setattr__(self, "seed_keywords", _unique(self.seed_keywords, "Seed keyword", MAX_KEYWORDS, minimum=1))
        subs = _unique(self.subreddits, "Subreddit", MAX_SUBREDDITS)
        if any(not SUBREDDIT_PATTERN.fullmatch(sub) for sub in subs):
            raise ValueError("Subreddit chỉ nhận tên cộng đồng, không nhận URL hoặc r/.")
        object.__setattr__(self, "subreddits", subs)

    def to_dict(self):
        return {"name": self.name, "seed_keywords": list(self.seed_keywords), "subreddits": list(self.subreddits)}


@dataclass(frozen=True, slots=True)
class ResearchRequest:
    category: str
    niches: tuple[NicheInput, ...]
    geo: str
    timeframe: str
    mode: str = "ollama"

    def __post_init__(self):
        object.__setattr__(self, "category", _text(self.category, "Danh mục"))
        if not isinstance(self.niches, (list, tuple)) or not MIN_NICHES <= len(self.niches) <= MAX_NICHES:
            raise ValueError("Cần từ 3 đến 5 niche.")
        if any(not isinstance(niche, NicheInput) for niche in self.niches):
            raise ValueError("Niche phải có tên và seed keywords.")
        object.__setattr__(self, "niches", tuple(self.niches))
        if len({niche.name.casefold() for niche in self.niches}) != len(self.niches):
            raise ValueError("Tên niche không được trùng nhau.")
        if not isinstance(self.mode, str) or self.mode not in {"ollama", "deterministic"}:
            raise ValueError("Chế độ chỉ nhận ollama hoặc deterministic.")
        geo = _text(self.geo, "Geo", 9, empty=True)
        timeframe = _text(self.timeframe, "Timeframe", 64)
        try:
            TrendsSettings(geo=geo, timeframe=timeframe)
        except ValueError:
            raise ValueError("Geo/timeframe không được Google Trends hỗ trợ; dùng mã quốc gia viết hoa và khoảng thời gian hợp lệ.") from None
        object.__setattr__(self, "geo", geo)
        object.__setattr__(self, "timeframe", timeframe)

    @classmethod
    def from_dict(cls, data):
        required = {"category", "niches", "geo", "timeframe"}
        if not isinstance(data, dict) or set(data) - required - {"mode"} or not required <= set(data):
            raise ValueError("Payload cần category, niches, geo, timeframe; chỉ mode là tùy chọn.")
        if not isinstance(data["niches"], list) or not MIN_NICHES <= len(data["niches"]) <= MAX_NICHES:
            raise ValueError("Cần từ 3 đến 5 niche.")
        niches = []
        for niche in data["niches"]:
            if not isinstance(niche, dict) or set(niche) - {"name", "seed_keywords", "subreddits"} or not {"name", "seed_keywords"} <= set(niche):
                raise ValueError("Mỗi niche cần name, seed_keywords và subreddits tùy chọn; không nhận field khác.")
            niches.append(NicheInput(niche["name"], niche["seed_keywords"], niche.get("subreddits", ())))
        return cls(data["category"], tuple(niches), data["geo"], data["timeframe"], data.get("mode", "ollama"))

    @classmethod
    def defaults(cls):
        return cls.from_dict({"category": CATEGORY, "geo": GOOGLE_TRENDS_GEO, "timeframe": GOOGLE_TRENDS_TIMEFRAME,
                              "niches": [{key: niche[key] for key in ("name", "seed_keywords", "subreddits") if key in niche} for niche in NICHES]})

    def to_dict(self):
        return {"category": self.category, "geo": self.geo, "timeframe": self.timeframe, "mode": self.mode,
                "niches": [niche.to_dict() for niche in self.niches]}

    def collector_niches(self):
        # Explicit query policy, not synthetic products: first two seeds query Amazon.
        return [{**niche.to_dict(), "geo": self.geo, "timeframe": self.timeframe,
                 "amazon_search_terms": list(niche.seed_keywords[:2])} for niche in self.niches]


def decode_request(body: bytes) -> ResearchRequest:
    if len(body) > MAX_BODY_BYTES:
        raise ValueError("Payload vượt giới hạn 32 KiB.")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("JSON có field trùng lặp.")
            result[key] = value
        return result

    def number(value):
        if not math.isfinite(float(value)):
            raise ValueError("JSON không nhận số không hữu hạn.")
        return float(value)

    try:
        data = json.loads(body.decode("utf-8"), object_pairs_hook=unique, parse_constant=number, parse_float=number)
        return ResearchRequest.from_dict(data)
    except (UnicodeError, RecursionError, TypeError, KeyError, OverflowError) as exc:
        raise ValueError("JSON input không hợp lệ.") from exc
