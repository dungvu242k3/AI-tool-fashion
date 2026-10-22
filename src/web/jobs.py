"""Bounded single-flight research jobs. Source collection itself stays sequential."""
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
import threading
import time
from uuid import uuid4

from src.models.research_request import ResearchRequest
from src.models.research_result import MAX_DOCUMENT_BYTES

logger = logging.getLogger(__name__)
JOB_ID = re.compile(r"[a-f0-9]{32}\Z")
IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9-]{16,64}\Z")


class JobBusy(ValueError):
    pass


class IdempotencyConflict(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class _Job:
    job_id: str
    key: str
    fingerprint: str
    submitted_at: str
    touched: float
    status: str = "queued"
    started_at: str | None = None
    finished_at: str | None = None
    progress: dict | None = None
    result: bytes | None = None
    error: str | None = None

    def snapshot(self):
        return {"job_id": self.job_id, "status": self.status, "submitted_at": self.submitted_at,
                "started_at": self.started_at, "finished_at": self.finished_at,
                "progress": dict(self.progress) if self.progress else None,
                "result_available": self.result is not None, "error": self.error}


class ResearchJobs:
    def __init__(self, runner, *, max_jobs=8, ttl_seconds=3600, max_result_bytes=MAX_DOCUMENT_BYTES,
                 max_total_bytes=64 * 1024 * 1024, monotonic=time.monotonic):
        if not 1 <= max_jobs <= 32 or not 1 <= ttl_seconds <= 86400 or not 1 <= max_result_bytes <= max_total_bytes:
            raise ValueError("Invalid research job budgets")
        self._runner, self._clock = runner, monotonic
        self._max_jobs, self._ttl = max_jobs, ttl_seconds
        self._max_result_bytes, self._max_total_bytes = max_result_bytes, max_total_bytes
        self._jobs = OrderedDict()
        self._lock = threading.Lock()
        self._active = None
        self._thread = None
        self._closed = False

    def _prune(self, *, reserve=False):
        now = self._clock()
        for key, job in list(self._jobs.items()):
            if key != self._active and now - job.touched >= self._ttl:
                del self._jobs[key]
        limit = self._max_jobs - int(reserve)
        while len(self._jobs) > limit or sum(len(job.result or b"") for job in self._jobs.values()) > self._max_total_bytes:
            key = next((key for key in self._jobs if key != self._active), None)
            if key is None:
                break
            del self._jobs[key]

    def submit(self, request: ResearchRequest, key: str):
        if not isinstance(request, ResearchRequest) or not isinstance(key, str) or not IDEMPOTENCY_KEY.fullmatch(key):
            raise ValueError("Idempotency-Key cần 16–64 ký tự chữ, số hoặc dấu gạch nối.")
        fingerprint = hashlib.sha256(json.dumps(request.to_dict(), sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        with self._lock:
            if self._closed:
                raise JobBusy("Dịch vụ job đang đóng.")
            self._prune()
            previous = next((job for job in self._jobs.values() if job.key == key), None)
            if previous:
                if previous.fingerprint != fingerprint:
                    raise IdempotencyConflict("Idempotency-Key đã dùng với input khác.")
                return previous.snapshot()
            if self._active:
                raise JobBusy("Đã có một job đang chạy; hãy theo dõi job hiện tại.")
            self._prune(reserve=True)
            job = _Job(uuid4().hex, key, fingerprint, _now(), self._clock())
            self._jobs[job.job_id] = job
            self._active = job.job_id
            thread = threading.Thread(target=self._run, args=(job, request), daemon=True, name=f"research-{job.job_id[:8]}")
            self._thread = thread
            try:
                thread.start()
            except RuntimeError:
                del self._jobs[job.job_id]
                self._active = None
                self._thread = None
                raise
            return job.snapshot()

    def _run(self, job, request):
        with self._lock:
            job.status, job.started_at = "running", _now()
        body, error = None, None
        try:
            result = self._runner(request, lambda *args: self._progress(job, *args))
            body = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
            if len(body) > self._max_result_bytes:
                raise ValueError("Job result exceeds byte budget")
        except Exception:
            logger.exception("research_job_failed job_id=%s", job.job_id, extra={"job_id": job.job_id})
            error = "Job thực thi thất bại. Xem log server theo job ID; không có kết quả thay thế."
        finally:
            with self._lock:
                job.status, job.result, job.error = ("failed" if error else "completed"), (None if error else body), error
                job.finished_at, job.touched = _now(), self._clock()
                self._active = None
                self._prune()

    def _progress(self, job, step, total, title, detail=""):
        if type(step) is not int or type(total) is not int or not 1 <= step <= total <= 20:
            raise ValueError("Invalid pipeline progress")
        if not isinstance(title, str) or not isinstance(detail, str) or len(title) > 500 or len(detail) > 1000:
            raise ValueError("Invalid pipeline progress text")
        with self._lock:
            if job.status != "running":
                return  # Ignore a late callback after the worker committed its result.
            sequence = job.progress["sequence"] + 1 if job.progress else 1
            job.progress = {"step": step, "total_steps": total, "title": title, "detail": detail,
                            "sequence": sequence, "updated_at": _now()}

    def get(self, job_id):
        if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
            return None
        with self._lock:
            self._prune()
            job = self._jobs.get(job_id)
            return job.snapshot() if job else None

    def active(self):
        with self._lock:
            job = self._jobs.get(self._active)
            return job.snapshot() if job else None

    def result(self, job_id):
        with self._lock:
            self._prune()
            job = self._jobs.get(job_id)
            return job.result if job else None

    def close(self, timeout=1):
        with self._lock:
            self._closed = True
            thread = self._thread
        if thread:
            thread.join(timeout=timeout)
