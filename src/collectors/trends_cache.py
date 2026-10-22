"""Bounded in-memory TTL cache of normalized live observations, never cookies/tokens."""
import copy
import json
import math
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Callable

from src.models.collection import RequestMetadata
from src.models.schemas import KeywordSignal


@dataclass(frozen=True)
class TrendsSnapshot:
    records: tuple[KeywordSignal, ...]
    requests: tuple[RequestMetadata, ...]


class TrendsCache:
    def __init__(self, *, max_entries=64, max_bytes=8 * 1024 * 1024, clock: Callable[[], float] = time.monotonic):
        if max_entries < 1 or max_bytes < 1:
            raise ValueError("Cache limits must be positive")
        self._max_entries, self._max_bytes = max_entries, max_bytes
        self._clock = clock
        self._entries = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def _expire(self):
        for key, (deadline, size, _) in list(self._entries.items()):
            if deadline <= self._clock():
                del self._entries[key]
                self._bytes -= size

    def get(self, key: str) -> TrendsSnapshot | None:
        with self._lock:
            self._expire()
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return copy.deepcopy(entry[2])

    def put(self, key: str, snapshot: TrendsSnapshot, ttl_seconds: float) -> bool:
        if not math.isfinite(ttl_seconds) or not 0 <= ttl_seconds <= 3600:
            raise ValueError("Cache TTL must be finite and between 0 and 3600 seconds")
        if ttl_seconds <= 0 or not snapshot.records:
            return False
        stored = copy.deepcopy(snapshot)
        size = len(json.dumps(asdict(stored), ensure_ascii=False, allow_nan=False).encode("utf-8"))
        if size > self._max_bytes:
            return False
        with self._lock:
            self._expire()
            previous = self._entries.pop(key, None)
            if previous:
                self._bytes -= previous[1]
            while self._entries and (len(self._entries) >= self._max_entries or self._bytes + size > self._max_bytes):
                _, (_, old_size, _) = self._entries.popitem(last=False)
                self._bytes -= old_size
            self._entries[key] = (self._clock() + ttl_seconds, size, stored)
            self._bytes += size
        return True


SHARED_TRENDS_CACHE = TrendsCache()
