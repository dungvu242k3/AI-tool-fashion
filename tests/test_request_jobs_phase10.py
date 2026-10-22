"""Isolated intent/job tests: no provider calls or production mock records."""
from dataclasses import FrozenInstanceError, replace
import json
import threading
from types import SimpleNamespace

import pytest

from src.models.research_request import ResearchRequest, NicheInput, decode_request
from src.web.jobs import ResearchJobs, JobBusy, IdempotencyConflict


@pytest.fixture
def intent():
    return ResearchRequest("Fixture category", tuple(NicheInput(f"Fixture {i}", ("seed alpha", "seed bravo")) for i in range(3)), "VN", "today 12-m")


@pytest.fixture
def jobs_factory():
    stores = []
    releases = []

    def create(**kwargs):
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        calls = []
        clock = SimpleNamespace(value=0.0)

        def runner(request, progress):
            calls.append(request)
            progress(1, 5, "Fixture actual callback", "fixture source started")
            entered.set()
            if not release.wait(3):
                raise RuntimeError("Fixture worker release deadline")
            progress(5, 5, "Fixture actual callback", "fixture export finished")
            done.set()
            return {"success": False, "status": "partial", "fixture_only": True}

        store = ResearchJobs(kwargs.pop("runner", runner), monotonic=lambda: clock.value, **kwargs)
        stores.append(store)
        releases.append(release)
        return SimpleNamespace(store=store, release=release, entered=entered, done=done, calls=calls, clock=clock)

    yield create
    for release in releases:
        release.set()
    for store in stores:
        store.close(timeout=3)


def finish(case, job_id):
    case.release.set()
    case.store._thread.join(timeout=3)
    job = case.store.get(job_id)
    assert job["status"] == "completed" and job["finished_at"] is not None
    return job


def test_intent_is_immutable_detached_and_routes_only_approved_queries(intent):
    raw = intent.to_dict()
    parsed = ResearchRequest.from_dict(raw)
    raw["niches"][0]["seed_keywords"].append("later mutation")
    assert parsed.niches[0].seed_keywords == ("seed alpha", "seed bravo")
    with pytest.raises(FrozenInstanceError):
        parsed.category = "changed"
    assert parsed.mode == "ollama"
    query = parsed.collector_niches()[0]
    assert query["geo"] == "VN" and query["timeframe"] == "today 12-m"
    assert query["amazon_search_terms"] == ["seed alpha", "seed bravo"]
    assert query["subreddits"] == []


@pytest.mark.parametrize("field,value", [("category", ""), ("category", "a" * 201), ("category", "\ud800"),
    ("category", "line\nbreak"), ("geo", "vn"), ("geo", "http://evil"), ("geo", None),
    ("timeframe", "today 99-m"), ("timeframe", "2026-02-30 2026-10-01"), ("timeframe", "2026-10-02 2026-01-01"),
    ("mode", True), ("mode", []), ("mode", "fast"), ("niches", []), ("niches", None)])
def test_invalid_intent_fails_before_collection(intent, field, value):
    raw = intent.to_dict()
    raw[field] = value
    with pytest.raises(ValueError):
        ResearchRequest.from_dict(raw)


@pytest.mark.parametrize("field", ["output_dir", "model_name", "base_url", "fast_mode", "collectors", "progress_callback"])
def test_web_intent_cannot_inject_execution_controls(intent, field):
    raw = intent.to_dict()
    raw[field] = "forbidden"
    with pytest.raises(ValueError):
        ResearchRequest.from_dict(raw)


@pytest.mark.parametrize("count", [0, 1, 2, 6, 100])
def test_niche_count_is_bounded(intent, count):
    with pytest.raises(ValueError):
        replace(intent, niches=tuple(NicheInput(f"Fixture {i}", ("seed",)) for i in range(count)))


@pytest.mark.parametrize("field,value", [("name", " "), ("name", "a" * 201), ("seed_keywords", []),
    ("seed_keywords", ["same", "SAME"]), ("seed_keywords", ["x"] * 9), ("seed_keywords", [None]),
    ("seed_keywords", ["a\x00b"]), ("subreddits", ["r/community"]), ("subreddits", ["https://reddit.com/r/community"]),
    ("subreddits", ["same", "SAME"]), ("subreddits", ["aa", "bb", "cc", "dd", "ee"]), ("amazon_sources", [])])
def test_bad_niche_queries_are_rejected(intent, field, value):
    raw = intent.to_dict()
    raw["niches"][0][field] = value
    with pytest.raises(ValueError):
        ResearchRequest.from_dict(raw)


def test_duplicate_normalized_niche_names_rejected(intent):
    with pytest.raises(ValueError):
        replace(intent, niches=(intent.niches[0], NicheInput(" fixture 0 ", ("seed",)), intent.niches[2]))


@pytest.mark.parametrize("body", [b'{"category":"first","category":"second"}', b'[]', b'null', b'{invalid',
    b'{"number":NaN}', b'{"number":Infinity}', b'{"number":1e9999}', b'\xff', b'[' * 2000 + b']' * 2000, b' ' * 32769],
    ids=["duplicate", "array", "null", "malformed", "nan", "infinity", "overflow", "unicode", "deep", "oversize"])
def test_input_json_is_strict_and_bounded(body):
    with pytest.raises(ValueError):
        decode_request(body)


def test_missing_mode_explicitly_defaults_to_ollama_not_fast(intent):
    raw = intent.to_dict()
    del raw["mode"]
    assert decode_request(json.dumps(raw).encode()).mode == "ollama"


def test_single_flight_progress_and_idempotent_submission(intent, jobs_factory):
    case = jobs_factory()
    job = case.store.submit(intent, "fixture-idempotency-1")
    assert case.entered.wait(2)
    pending = case.store.get(job["job_id"])
    assert pending["status"] == "running" and pending["progress"]["step"] == 1
    assert pending["progress"]["sequence"] == 1 and pending["result_available"] is False
    pending["progress"]["detail"] = "mutated"
    assert case.store.get(job["job_id"])["progress"]["detail"] != "mutated"
    assert case.store.submit(intent, "fixture-idempotency-1")["job_id"] == job["job_id"]
    with pytest.raises(JobBusy):
        case.store.submit(intent, "fixture-idempotency-2")
    with pytest.raises(IdempotencyConflict):
        case.store.submit(replace(intent, category="different"), "fixture-idempotency-1")
    finish(case, job["job_id"])
    assert len(case.calls) == 1 and case.store.active() is None
    assert json.loads(case.store.result(job["job_id"]))["status"] == "partial"
    assert case.store.submit(intent, "fixture-idempotency-1")["status"] == "completed"  # Dedup after completion, too.


@pytest.mark.parametrize("key", ["", "a", "x" * 65, "../outside", "x" * 16 + "\n", "x" * 16 + "é"])
def test_invalid_idempotency_keys_never_start_worker(intent, jobs_factory, key):
    case = jobs_factory()
    with pytest.raises(ValueError):
        case.store.submit(intent, key)
    assert not case.calls


def test_failures_are_correlated_in_server_logs_without_raw_client_exception(intent, jobs_factory, caplog):
    def broken(request, progress):
        raise RuntimeError("fixture private transport diagnostics")
    case = jobs_factory(runner=broken)
    job = case.store.submit(intent, "fixture-failure-key")
    case.store.close(timeout=3)
    snapshot = case.store.get(job["job_id"])
    assert snapshot["status"] == "failed" and snapshot["finished_at"]
    assert "private transport" not in snapshot["error"] and case.store.result(job["job_id"]) is None
    assert any(record.job_id == job["job_id"] for record in caplog.records if hasattr(record, "job_id"))


def test_result_memory_and_job_ttl_are_bounded(intent, jobs_factory):
    case = jobs_factory(runner=lambda request, progress: {"fixture": "x" * 64}, ttl_seconds=1, max_result_bytes=256, max_total_bytes=256)
    first = case.store.submit(intent, "fixture-memory-key1")
    # join, not close: the store must remain available for the next intentional job.
    case.store._thread.join(2)
    second = case.store.submit(intent, "fixture-memory-key2")
    case.store._thread.join(2)
    third = case.store.submit(intent, "fixture-memory-key3")
    case.store._thread.join(2)
    fourth = case.store.submit(intent, "fixture-memory-key4")
    case.store._thread.join(2)
    assert case.store.get(first["job_id"]) is None
    assert case.store.get(fourth["job_id"])["status"] == "completed"
    case.clock.value = 2
    assert case.store.get(fourth["job_id"]) is None


def test_retention_never_expires_active_job(intent, jobs_factory):
    case = jobs_factory(ttl_seconds=1)
    job = case.store.submit(intent, "fixture-active-key")
    assert case.entered.wait(2)
    case.clock.value = 999
    assert case.store.get(job["job_id"])["status"] == "running"
    finish(case, job["job_id"])


def test_oversize_result_fails_without_result_fallback(intent, jobs_factory):
    case = jobs_factory(runner=lambda request, progress: {"fixture": "x" * 100}, max_result_bytes=32, max_total_bytes=64)
    job = case.store.submit(intent, "fixture-oversize-key")
    case.store.close(3)
    assert case.store.get(job["job_id"])["status"] == "failed"
    assert case.store.result(job["job_id"]) is None


def test_closed_job_store_rejects_new_research(intent, jobs_factory):
    case = jobs_factory()
    case.store.close()
    with pytest.raises(JobBusy):
        case.store.submit(intent, "fixture-closed-key")


def test_pipeline_preserves_custom_intent_and_real_source_callbacks(tmp_path, intent, collection_factory):
    from src.models.schemas import KeywordSignal, ProductItem, DiscussionItem
    from src.pipeline import execute_pipeline
    from src.reporters.report_repository import ReportRepository
    observed, progress = [], []

    def collect(source, niche):
        observed.append((source, niche))
        records = {
            "google_trends": [KeywordSignal(seed, score=40, geo=niche["geo"], timeframe=niche["timeframe"]) for seed in niche["seed_keywords"]],
            "amazon": [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")],
            "reddit": [DiscussionItem("Fixture", url="https://www.reddit.com/r/fixture/comments/abc123/post/")],
        }
        return collection_factory(source, records[source])

    request = replace(intent, mode="deterministic")
    collectors = {source: SimpleNamespace(collect=lambda niche, s=source: collect(s, niche)) for source in ("google_trends", "amazon", "reddit")}
    result = execute_pipeline(request=request, collectors=collectors, output_dir=str(tmp_path), progress_callback=lambda *args: progress.append(args))
    assert result["metadata"]["research_input"] == request.to_dict()
    assert result["metadata"]["category"] == "Fixture category" and result["metadata"]["mode"] == "deterministic"
    assert result["metadata"]["model_attempted"] is None
    assert len(observed) == 9 and all(niche["geo"] == "VN" and niche["timeframe"] == "today 12-m" for _, niche in observed)
    assert sum("bắt đầu" in event[3] for event in progress) == 9
    assert sum("bản ghi" in event[3] for event in progress) == 9
    assert ReportRepository(tmp_path).load_latest() == result
    assert result["ranking"] == [] and result["top_ideas"] == []


def test_late_progress_cannot_mutate_completed_job(intent, jobs_factory):
    callbacks = []
    def runner(request, progress):
        callbacks.append(progress)
        progress(5, 5, "Fixture export", "done")
        return {"fixture_only": True}
    case = jobs_factory(runner=runner)
    job = case.store.submit(intent, "fixture-late-progress")
    case.store._thread.join(2)
    before = case.store.get(job["job_id"])
    callbacks[0](1, 5, "Fixture late callback", "must be ignored")
    assert case.store.get(job["job_id"]) == before


def test_thread_start_failure_releases_single_flight_and_closes_safely(intent, jobs_factory, monkeypatch):
    case = jobs_factory()
    def failed_start(self):
        raise RuntimeError("Fixture thread startup failure")
    monkeypatch.setattr(threading.Thread, "start", failed_start)
    with pytest.raises(RuntimeError):
        case.store.submit(intent, "fixture-thread-failure")
    assert case.store.active() is None
    case.store.close()


def test_each_job_keeps_its_own_result_after_a_later_job_finishes(intent, jobs_factory):
    case = jobs_factory(runner=lambda request, progress: {"category": request.category, "fixture_only": True})
    first = case.store.submit(intent, "fixture-original-result")
    case.store._thread.join(2)
    second = case.store.submit(replace(intent, category="Later fixture"), "fixture-later-result")
    case.store._thread.join(2)
    assert json.loads(case.store.result(first["job_id"]))["category"] == intent.category
    assert json.loads(case.store.result(second["job_id"]))["category"] == "Later fixture"


@pytest.mark.parametrize("field,value", [("category", "Different"), ("mode", "ollama"), ("geo", "VN"), ("seeds", ["different", "keywords"])])
def test_published_input_cannot_disagree_with_actual_keyword_context(research_result_factory, field, value):
    from src.models.research_result import thaw_json
    result = research_result_factory(names=("Fixture 0", "Fixture 1", "Fixture 2"))
    request = ResearchRequest(result.metadata["category"], tuple(NicheInput(name, ("fixture alpha", "fixture bravo")) for name in result.niches), "", "today 3-m", "deterministic")
    metadata = thaw_json(result.metadata)
    metadata["research_input"] = request.to_dict()
    assert replace(result, metadata=metadata).metadata["research_input"]["mode"] == "deterministic"
    if field == "seeds":
        metadata["research_input"]["niches"][0]["seed_keywords"] = value
    else:
        metadata["research_input"][field] = value
    with pytest.raises(ValueError):
        replace(result, metadata=metadata)
