"""Isolated fixtures only: never market data or a live-network speed benchmark."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from src.collectors.collection_cache import ValidatedCollectionCache, collection_key
from src.collectors.collection_runtime import collect_sources, owned_collector
from src.collectors.concurrency import CollectionLeases
from src.collectors.errors import CollectionError
from src.collectors.http import HTTPClient
from src.collectors.http_policy import HTTPPolicy
from src.collectors.performance_settings import PerformanceSettings, SOURCES
from src.collectors.reddit_provider import OAuthRedditProvider, PublicJSONRedditProvider
from src.collectors.reddit_settings import RedditCredentials, RedditSettings
from src.collectors.validation import validate_collection_result
from src.models.collection import CollectionResult, CollectionWarning
from src.models.schemas import ProductItem
from src.pipeline import execute_pipeline
from src.reporters.collection_snapshots import CollectionSnapshotWriter, read_collection_snapshots
from src.reporters.result_codec import canonical_json

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)
NICHES = [{"name": "Fixture A", "seed_keywords": ["fixture"], "geo": "US", "timeframe": "today 3-m"},
          {"name": "Fixture B", "seed_keywords": ["fixture two"], "geo": "US", "timeframe": "today 3-m"}]


@pytest.fixture
def measured(collection_factory):
    return validate_collection_result("amazon", collection_factory("amazon", [
        ProductItem("Fixture only", url="https://www.amazon.com/dp/B000000001")]))


@pytest.fixture
def cache():
    clock = SimpleNamespace(seconds=0.0)
    cache = ValidatedCollectionCache(monotonic=lambda: clock.seconds,
        utcnow=lambda: NOW + timedelta(seconds=clock.seconds))
    return cache, clock


@pytest.mark.parametrize("values", [
    {"max_workers": 0}, {"max_workers": 4}, {"max_workers": True}, {"amazon_concurrency": 5},
    {"reddit_concurrency": 0}, {"slot_wait_seconds": 0}, {"slot_wait_seconds": float("nan")},
    {"amazon_cache_ttl": float("inf")}, {"reddit_cache_ttl": -1}, {"cache_max_entries": 513},
    {"cache_max_bytes": 100}, {"snapshot_run_max_bytes": 1024}, {"snapshot_max_bytes": True},
], ids=["workers-zero", "workers-high", "bool", "provider-high", "provider-zero", "wait-zero", "nan", "inf",
         "negative-ttl", "entries", "bytes", "run-budget", "snapshot-bool"])
def test_configuration_rejects_unbounded_values(values):
    with pytest.raises(ValueError):
        PerformanceSettings(**values)


def test_environment_and_http_caps(monkeypatch):
    monkeypatch.setenv("TREND_PERF_MAX_WORKERS", "2")
    monkeypatch.setenv("TREND_PERF_REDDIT_CACHE_TTL", "0")
    monkeypatch.setenv("TREND_HTTP_MAX_RESPONSE_BYTES", "2048")
    assert PerformanceSettings.from_env().max_workers == 2
    assert PerformanceSettings.from_env().reddit_cache_ttl == 0
    assert HTTPPolicy.from_env().max_response_bytes == 2048
    monkeypatch.setenv("TREND_PERF_MAX_WORKERS", "broken")
    with pytest.raises(ValueError, match="TREND_PERF_MAX_WORKERS"):
        PerformanceSettings.from_env()


@pytest.mark.parametrize("values", [{"connect_timeout": 121}, {"read_timeout": 301}, {"retry_wait_budget": 301},
    {"max_response_bytes": True}, {"max_response_bytes": 1023}, {"max_response_bytes": 16777217},
    {"connect_timeout": "bad"}])
def test_http_new_bounds(values):
    with pytest.raises(ValueError):
        HTTPPolicy(**values)


def test_cache_detaches_and_marks_all_listing_provenances(cache, measured):
    store, clock = cache
    assert store.put("fixture", measured, 300)
    original = asdict(measured)
    first = store.get("fixture")
    assert first.request_metadata[0].cache_reused
    assert first.records[0].provenance.from_cache
    assert first.records[0].listings[0].provenance.from_cache
    assert first.records[0].provenance.retrieved_at == measured.records[0].provenance.retrieved_at
    assert first.request_metadata[0].request_id == measured.request_metadata[0].request_id
    assert validate_collection_result("amazon", first).status == "success"
    assert first.status_dict()["live_attempted"] is False
    first.records[0].title = "Caller mutation"
    measured.records[0].title = "Other caller mutation"
    assert store.get("fixture").records[0].title == original["records"][0]["title"]
    clock.seconds = 299
    assert store.get("fixture") is not None
    clock.seconds = 300
    assert store.get("fixture") is None


def test_cache_age_not_insertion_time_and_no_renewal(cache, measured):
    store, clock = cache
    clock.seconds = 290
    assert store.put("fixture", measured, 300)
    assert not store.put("second-hand", store.get("fixture"), 300)
    clock.seconds = 301
    assert store.get("fixture") is None
    assert not store.put("old", measured, 300)


@pytest.mark.parametrize("kind", ["partial", "failed", "not_configured", "invalid", "duplicate"])
def test_cache_rejects_incomplete_or_invalid_evidence(cache, measured, kind):
    store, _ = cache
    if kind == "partial":
        measured = replace(measured, status="partial", warnings=[CollectionWarning("fixture", "Fixture warning")])
    elif kind == "failed":
        measured = CollectionResult.from_records("amazon", [])
    elif kind == "not_configured":
        measured = CollectionResult("amazon", status="not_configured")
    elif kind == "invalid":
        measured.records[0].asin = "invalid"
    else:
        duplicate = deepcopy(measured.records[0])
        duplicate.provenance = replace(duplicate.provenance, evidence_id="a" * 32)
        duplicate.listings = [replace(duplicate.listings[0], provenance=duplicate.provenance)]
        measured.records.append(duplicate)
    assert not store.put("fixture", measured, 300)
    assert store.get("fixture") is None


def test_cache_lru_and_size_limits(measured):
    size = len(canonical_json(asdict(measured)).encode("utf-8"))
    store = ValidatedCollectionCache(max_entries=2, max_bytes=size * 2 + 1, utcnow=lambda: NOW)
    assert store.put("one", measured, 300) and store.put("two", measured, 300)
    store.get("one")
    assert store.put("three", measured, 300)
    assert store.get("two") is None and store.get("one") is not None
    small = ValidatedCollectionCache(max_bytes=1024, utcnow=lambda: NOW)
    assert not small.put("too-large", measured, 300)


@pytest.mark.parametrize("field,value", [("name", "Other label"), ("seed_keywords", ["other"]),
    ("geo", "VN"), ("timeframe", "today 1-m"), ("subreddits", ["gifts"])])
def test_cache_keys_are_scoped_to_full_intent(field, value):
    niche = NICHES[0]
    original = collection_key("amazon", niche, {"provider": "fixture"})
    assert original != collection_key("amazon", {**niche, field: value}, {"provider": "fixture"})
    assert original != collection_key("reddit", niche, {"provider": "fixture"})
    assert original != collection_key("amazon", niche, {"provider": "other"})
    assert original == collection_key("amazon", dict(reversed(list(niche.items()))), {"provider": "fixture"})


def test_oauth_cache_scope_does_not_expose_credentials():
    settings = RedditSettings()
    first = OAuthRedditProvider(settings, RedditCredentials("fixture-client-id", "fixture-client-secret"))
    second = OAuthRedditProvider(settings, RedditCredentials("other-client-id", "other-client-secret"))
    serialized = canonical_json(first.cache_identity())
    assert "fixture-client" not in serialized
    assert first.cache_identity() == first.cache_identity()
    assert first.cache_identity() != second.cache_identity()
    assert first.cache_identity() != PublicJSONRedditProvider(settings).cache_identity()


def failed(source):
    return CollectionResult.from_records(source, [], [CollectionWarning("fixture", "Unit-test fixture only")])


def test_three_providers_overlap_but_each_visits_niches_in_order():
    barrier, visits, lock = threading.Barrier(3), {source: [] for source in SOURCES}, threading.Lock()
    def collect(source, niche):
        if niche["name"] == NICHES[0]["name"]:
            barrier.wait(timeout=3)
        with lock:
            visits[source].append(niche["name"])
        return failed(source)
    collectors = {source: SimpleNamespace(collect=lambda niche, s=source: collect(s, niche)) for source in SOURCES}
    result = collect_sources(NICHES, collectors=collectors)
    assert list(result) == [n["name"] for n in NICHES]
    assert all(list(sources) == list(SOURCES) for sources in result.values())
    assert all(names == list(result) for names in visits.values())


def test_serial_config_and_borrowed_resource_ownership():
    visits = []
    def collect(source, niche):
        visits.append((source, niche["name"]))
        return failed(source)
    collectors = {source: SimpleNamespace(collect=lambda niche, s=source: collect(s, niche), close=Mock()) for source in SOURCES}
    collect_sources(NICHES, settings=PerformanceSettings(max_workers=1), collectors=collectors)
    assert visits == [(source, niche["name"]) for source in SOURCES for niche in NICHES]
    assert all(not collector.close.called for collector in collectors.values())


def test_process_wide_provider_limits_apply_across_two_runs():
    entered, release = threading.Event(), threading.Event()
    active, peak = 0, 0
    lock = threading.Lock()
    def collect(source, niche):
        nonlocal active, peak
        if source == "amazon":
            with lock:
                active += 1
                peak = max(peak, active)
            entered.set()
            assert release.wait(timeout=3)
            with lock:
                active -= 1
        return failed(source)
    def run():
        return collect_sources(NICHES[:1], collectors={source: SimpleNamespace(
            collect=lambda niche, s=source: collect(s, niche)) for source in SOURCES})
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run)
        assert entered.wait(timeout=3)
        second = pool.submit(run)
        release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    assert peak == 1


def test_shared_http_instance_rejected_before_calls():
    http = object()
    collectors = {source: SimpleNamespace(http=http, collect=Mock()) for source in SOURCES}
    with pytest.raises(ValueError, match="share"):
        collect_sources(NICHES, collectors=collectors)
    assert not any(collector.collect.called for collector in collectors.values())


def test_leases_timeout_capacity_conflict_and_cleanup():
    leases = CollectionLeases()
    with leases.acquire("fixture", 1, 0.01):
        with pytest.raises(CollectionError) as error:
            with leases.acquire("fixture", 1, 0.01):
                pytest.fail("Lease cannot be acquired twice")
        assert error.value.warning.code == "provider_busy"
        with pytest.raises(CollectionError) as error:
            with leases.acquire("fixture", 2, 0.01):
                pytest.fail("Cannot change capacity while in use")
        assert error.value.warning.code == "concurrency_configuration"
    assert not leases._slots
    with leases.acquire("fixture", 2, 0.01):
        pass
    assert not leases._slots


def test_owned_factory_creates_and_closes_in_worker_and_cache_hit_reuses_origin(cache, measured):
    store, _ = cache
    threads, closed, calls = [], [], []
    class Resource:
        def __enter__(self):
            threads.append(threading.get_ident())
            return self
        def __exit__(self, *args):
            closed.append(threading.get_ident())
    def factory(source, resources, policy):
        resources.enter_context(Resource())
        def collect(niche):
            calls.append(source)
            return deepcopy(measured) if source == "amazon" else failed(source)
        return SimpleNamespace(collect=collect), {"fixture-namespace": source}
    first = collect_sources(NICHES[:1], factory=factory, cache=store)
    second = collect_sources(NICHES[:1], factory=factory, cache=store)
    assert calls.count("amazon") == 1  # Failed sources are deliberately NOT cached.
    assert calls.count("reddit") == calls.count("google_trends") == 2
    assert len(closed) == len(threads) == 6
    assert threading.get_ident() not in threads
    origin = first["Fixture A"]["amazon"]
    cached = second["Fixture A"]["amazon"]
    assert origin.records[0].provenance.evidence_id == cached.records[0].provenance.evidence_id
    assert cached.status_dict()["live_attempted"] is False


def test_expired_cache_never_falls_back_when_provider_fails(cache, measured):
    store, clock = cache
    failing = False
    def factory(source, resources, policy):
        return SimpleNamespace(collect=lambda niche: deepcopy(measured) if source == "amazon" and not failing else failed(source)), {"fixture": source}
    collect_sources(NICHES[:1], factory=factory, cache=store)
    clock.seconds = 301
    failing = True
    result = collect_sources(NICHES[:1], factory=factory, cache=store)
    assert result["Fixture A"]["amazon"].records == []
    assert result["Fixture A"]["amazon"].status == "failed"


def test_raw_snapshots_roundtrip_and_run_id_collision(tmp_path, measured):
    writer = CollectionSnapshotWriter(tmp_path, "a" * 32, ["Fixture"], PerformanceSettings())
    for source in SOURCES:
        writer.capture(0, source, measured if source == "amazon" else failed(source))
    relative = writer.commit()
    restored = read_collection_snapshots(tmp_path, "a" * 32)
    amazon = next(document for document in restored if document["source"] == "amazon")
    assert amazon["collection"] == json.loads(canonical_json(asdict(measured)))
    assert (tmp_path / relative).is_file()
    with pytest.raises(FileExistsError):
        CollectionSnapshotWriter(tmp_path, "a" * 32, ["Fixture"], PerformanceSettings())
    with pytest.raises(ValueError):
        writer.commit()


@pytest.mark.parametrize("kind", ["traversal", "duplicate", "corruption", "size", "run-id", "position", "total", "missing", "schema"])
def test_raw_snapshot_reader_rejects_tampering(tmp_path, kind):
    run_id = "b" * 32
    writer = CollectionSnapshotWriter(tmp_path, run_id, ["Fixture"], PerformanceSettings())
    for source in SOURCES:
        writer.capture(0, source, failed(source))
    path = tmp_path / writer.commit()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if kind == "corruption":
        target = path.parent / manifest["entries"][0]["filename"]
        target.write_bytes(b"{}")  # Test-only corruption, never runtime snapshot rewriting.
    else:
        if kind == "traversal": manifest["entries"][0]["filename"] = "../secret.json"
        elif kind == "duplicate": manifest["entries"][1] = manifest["entries"][0]
        elif kind == "size": manifest["entries"][0]["bytes"] = 999999999
        elif kind == "run-id": manifest["run_id"] = "c" * 32
        elif kind == "position": manifest["entries"][0]["position"] = True
        elif kind == "total": manifest["total_bytes"] += 1
        elif kind == "missing": manifest["entries"].pop()
        else: manifest["schema"] = "unknown"
        path.write_text(canonical_json(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        read_collection_snapshots(tmp_path, run_id)


def test_incomplete_manifest_and_atomic_failure_leave_latest_untouched(tmp_path, monkeypatch):
    latest = tmp_path / "latest_data.json"
    latest.write_bytes(b"previous-good-file")
    writer = CollectionSnapshotWriter(tmp_path, "d" * 32, ["Fixture"], PerformanceSettings())
    writer.capture(0, "amazon", failed("amazon"))
    with pytest.raises(ValueError, match="incomplete"):
        writer.commit()
    monkeypatch.setattr("src.reporters.collection_snapshots.os.replace", Mock(side_effect=OSError("Fixture disk full")))
    with pytest.raises(OSError):
        writer.capture(0, "reddit", failed("reddit"))
    assert latest.read_bytes() == b"previous-good-file"
    assert not (writer.directory / "manifest.json").exists()
    assert not list(writer.directory.glob("*.tmp"))


def test_snapshot_byte_limits_do_not_truncate(tmp_path, measured):
    settings = PerformanceSettings(snapshot_max_bytes=1024, snapshot_run_max_bytes=2048)
    writer = CollectionSnapshotWriter(tmp_path, "e" * 32, ["Fixture"], settings)
    with pytest.raises(ValueError, match="byte budget"):
        writer.capture(0, "amazon", measured)
    assert not list(writer.directory.glob("*.json"))


def test_pipeline_snapshot_failure_prevents_ai_and_publication(tmp_path, monkeypatch):
    collectors = {source: SimpleNamespace(collect=lambda niche, s=source: failed(s)) for source in SOURCES}
    monkeypatch.setattr("src.pipeline.CollectionSnapshotWriter.capture", Mock(side_effect=OSError("Fixture disk full")))
    analyze = Mock(side_effect=AssertionError("AI must not run after storage failure"))
    monkeypatch.setattr("src.pipeline.LLMAnalyzer.analyze", analyze)
    with pytest.raises(OSError):
        execute_pipeline(fast_mode=True, niche_list=NICHES[:1], collectors=collectors, output_dir=tmp_path)
    assert not analyze.called and not (tmp_path / "latest_data.json").exists()
    assert not list((tmp_path / "snapshots").glob("*/manifest.json"))


def test_pipeline_snapshots_before_processing_and_progress_is_serialized(tmp_path, monkeypatch, measured):
    collectors = {source: SimpleNamespace(collect=lambda niche, s=source: deepcopy(measured) if s == "amazon" else failed(s)) for source in SOURCES}
    original = __import__("src.processors.data_processor", fromlist=["DataProcessor"]).DataProcessor.process
    def process(self, data):
        assert len(list((tmp_path / "snapshots").glob("*/manifest.json"))) == 1
        return original(self, data)
    monkeypatch.setattr("src.pipeline.DataProcessor.process", process)
    callback_lock, callbacks = threading.Lock(), []
    def callback(step, total, title, detail):
        assert callback_lock.acquire(blocking=False)
        try:
            callbacks.append((step, detail))
        finally:
            callback_lock.release()
    result = execute_pipeline(fast_mode=True, niche_list=NICHES, collectors=collectors, output_dir=tmp_path, progress_callback=callback)
    run_id = result["metadata"]["run_id"]
    assert len(read_collection_snapshots(tmp_path, run_id)) == 6
    assert [step for step, _ in callbacks] == sorted(step for step, _ in callbacks)
    assert list(result["niches"]) == [n["name"] for n in NICHES]
    diagnostics = json.loads((tmp_path / result["metadata"]["diagnostics_file"]).read_text(encoding="utf-8"))
    assert diagnostics["snapshot_manifest"] == f"snapshots/{run_id}/manifest.json"


def transport_fetch(http, journal):
    return http.client.fetch("GET", "https://example.test/fixture", source="fixture", operation="search", query={}, journal=journal)


def test_streaming_response_cap_is_nonretryable_and_always_closes(http_factory, response_factory):
    raw = response_factory(text="x" * 2048, headers={"Content-Length": "1"})
    http = http_factory([raw], policy=HTTPPolicy(max_response_bytes=1024, max_attempts=3))
    journal = []
    with pytest.raises(CollectionError) as error:
        transport_fetch(http, journal)
    assert error.value.warning.code == "response_too_large"
    assert len(journal) == 1 and journal[0].status_code == 200
    assert journal[0].error_code == "response_too_large"
    assert http.session.request.call_args.kwargs["stream"] is True
    raw.close.assert_called_once()


def test_streaming_bounds_decoded_chunks_without_buffering_raw_text(http_factory, response_factory):
    raw = response_factory()
    consumed = []
    def chunks(chunk_size):
        for index in range(1000):
            consumed.append(index)
            yield b"x" * 600
    raw.iter_content = chunks
    http = http_factory([raw], policy=HTTPPolicy(max_response_bytes=1024))
    with pytest.raises(CollectionError):
        transport_fetch(http, [])
    assert consumed == [0, 1]
    raw.close.assert_called_once()


def test_owned_http_disables_ambient_credentials_but_does_not_mutate_borrowed(monkeypatch):
    session = requests.Session()
    session.trust_env = True
    borrowed = HTTPClient(session=session)
    assert session.trust_env is True
    monkeypatch.setattr("src.collectors.http.requests.Session", lambda: session)
    with HTTPClient():
        assert session.trust_env is False
    borrowed.close()


def test_owned_default_collectors_use_unified_cache_and_close_transport(monkeypatch):
    from contextlib import ExitStack
    monkeypatch.setenv("TREND_REDDIT_MODE", "public_json")
    with ExitStack() as resources:
        collector, identity = owned_collector("google_trends", resources, HTTPPolicy())
        assert collector.settings.cache_ttl_seconds == 0
        assert identity["provider"] == collector.provider.cache_namespace
        http = collector.http
        assert not http._closed
    assert http._closed
