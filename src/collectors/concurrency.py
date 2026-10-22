"""Bounded process-wide leases; no session may be used by two workers at once."""
import threading
from contextlib import contextmanager
from dataclasses import dataclass

from src.collectors.errors import CollectionError


@dataclass(slots=True)
class _Lease:
    capacity: int
    semaphore: threading.BoundedSemaphore
    users: int = 0


class CollectionLeases:
    def __init__(self):
        self._lock = threading.Lock()
        self._slots = {}

    @contextmanager
    def acquire(self, key, capacity, timeout):
        with self._lock:
            slot = self._slots.get(key)
            if slot is None:
                slot = _Lease(capacity, threading.BoundedSemaphore(capacity))
                self._slots[key] = slot
            if slot.capacity != capacity or slot.users >= 256:
                raise CollectionError("concurrency_configuration", "Giới hạn concurrency thay đổi khi nguồn đang bận hoặc quá nhiều lượt chờ.")
            slot.users += 1
        acquired = False
        try:
            acquired = slot.semaphore.acquire(timeout=timeout)
            if not acquired:
                raise CollectionError("provider_busy", "Vượt thời gian chờ lượt thu thập; chưa gửi request.", retryable=True)
            yield
        finally:
            if acquired:
                slot.semaphore.release()
            with self._lock:
                slot.users -= 1
                if not slot.users:
                    del self._slots[key]


SHARED_LEASES = CollectionLeases()
