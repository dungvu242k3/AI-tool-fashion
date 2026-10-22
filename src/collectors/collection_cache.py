"""Process-local, owned LRU snapshots; no stale/error fallback or timestamp renewal."""
import hashlib
import hmac
import secrets
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone

from src.collectors.validation import validate_collection_result
from src.config import DATA_POLICY_VERSION
from src.models.collection import CollectionResult
from src.reporters.result_codec import canonical_json

_SCOPE_SECRET = secrets.token_bytes(32)


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    deadline: float
    result: CollectionResult
    serialized_bytes: int
    expires_at: datetime


def credential_scope(credentials) -> str:
    """An opaque, process-local namespace; never persist credentials or token values."""
    return hmac.new(_SCOPE_SECRET, canonical_json(asdict(credentials)).encode(), hashlib.sha256).hexdigest()


def collection_key(source: str, niche: dict, identity: dict) -> str:
    # Preserve array order: Trends batches and first-N source queries are order-sensitive.
    payload = {"schema": "validated-collection-v1", "policy": DATA_POLICY_VERSION,
               "source": source, "query": niche, "provider": identity}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class ValidatedCollectionCache:
    def __init__(self, *, max_entries=64, max_bytes=32 * 1024 * 1024,
                 monotonic=time.monotonic, utcnow=lambda: datetime.now(timezone.utc)):
        if type(max_entries) is not int or not 1 <= max_entries <= 512:
            raise ValueError("Invalid cache entry budget")
        if type(max_bytes) is not int or not 1024 <= max_bytes <= 128 * 1024 * 1024:
            raise ValueError("Invalid cache byte budget")
        self._max_entries, self._max_bytes = max_entries, max_bytes
        self._monotonic, self._utcnow = monotonic, utcnow
        self._entries, self._bytes = OrderedDict(), 0
        self._lock = threading.Lock()

    def _remove(self, key):
        entry = self._entries.pop(key)
        self._bytes -= entry.serialized_bytes

    def get(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._monotonic() >= entry.deadline or self._utcnow() >= entry.expires_at:
                self._remove(key)
                return None
            self._entries.move_to_end(key)
            stored = entry.result
        # Stored entries are private and never mutated; eviction cannot invalidate
        # this reference. Large copy operations must not block other providers.
        result = deepcopy(stored)
        result.request_metadata = [replace(trace, cache_reused=True) for trace in result.request_metadata]
        for record in result.records:
            record.provenance = replace(record.provenance, from_cache=True)
            if hasattr(record, "listings"):
                record.listings = [replace(listing, provenance=replace(listing.provenance, from_cache=True))
                                   for listing in record.listings]
        if self._monotonic() >= entry.deadline or self._utcnow() >= entry.expires_at:
            return None  # Copying a large entry must not turn an expired entry into a hit.
        return result

    def put(self, key, result, ttl_seconds) -> bool:
        if (isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float))
                or not 0 < ttl_seconds <= 3600):
            return False
        now = self._utcnow()
        owned = validate_collection_result(result.source, deepcopy(result), now=now)
        stats = owned.validation
        # Never launder a prior partial/invalid result through a second validation pass.
        original_stats = result.validation
        if (result.status != "success" or owned.status != "success" or owned.warnings
                or not owned.records or stats.rejected_count or stats.duplicate_count
                or (original_stats is not None and (original_stats.rejected_count or original_stats.duplicate_count))
                or any(trace.cache_reused for trace in owned.request_metadata)
                or any(record.provenance.from_cache for record in owned.records)):
            return False
        provenances = [p for record in owned.records for p in (
            record.provenance, *(listing.provenance for listing in getattr(record, "listings", [])))]
        if any(p.from_cache for p in provenances):
            return False
        age = max((now - datetime.fromisoformat(p.retrieved_at)).total_seconds() for p in provenances)
        remaining = ttl_seconds - max(0.0, age)
        if remaining <= 0:
            return False
        size = len(canonical_json(asdict(owned)).encode("utf-8"))
        if size > self._max_bytes:
            return False
        with self._lock:
            if key in self._entries:
                self._remove(key)
            while self._entries and (len(self._entries) >= self._max_entries or self._bytes + size > self._max_bytes):
                self._remove(next(iter(self._entries)))
            self._entries[key] = _CacheEntry(self._monotonic() + remaining, owned, size,
                                             now + timedelta(seconds=remaining))
            self._bytes += size
        return True


_CACHES = {}
_CACHE_LOCK = threading.Lock()


def shared_cache(settings):
    """One configured cache per process; changing its budget requires restart."""
    budget = (settings.cache_max_entries, settings.cache_max_bytes)
    with _CACHE_LOCK:
        if budget not in _CACHES:
            if _CACHES:
                raise ValueError("Restart required to change shared collection cache budgets")
            _CACHES[budget] = ValidatedCollectionCache(max_entries=budget[0], max_bytes=budget[1])
        return _CACHES[budget]
