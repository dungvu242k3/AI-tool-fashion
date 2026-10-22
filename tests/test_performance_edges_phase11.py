"""Additional phase-11 boundary tests; isolated fixtures, no live source calls."""
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from src.collectors.collection_cache import ValidatedCollectionCache
from src.collectors.collection_runtime import collect_sources
from src.collectors.http_policy import HTTPPolicy
from src.collectors.performance_settings import PerformanceSettings, SOURCES
from src.collectors.validation import validate_collection_result
from src.models.collection import CollectionResult, CollectionWarning
from src.models.schemas import DiscussionItem, KeywordSignal, ProductItem
from src.reporters.collection_snapshots import CollectionSnapshotWriter, read_collection_snapshots
from src.reporters.result_codec import decode_document

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)
NICHE = [{"name": "Fixture only"}]


def empty(source):
    return CollectionResult.from_records(source, [], [CollectionWarning("fixture", "Isolated fixture")])


def test_same_key_stampede_is_single_flight_even_with_provider_capacity_two(collection_factory):
    result = collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")])
    cache = ValidatedCollectionCache(utcnow=lambda: NOW)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def factory(source, resources, policy):
        def collect(niche):
            if source == "amazon":
                calls.append(source)
                entered.set()
                assert release.wait(timeout=3)
                return deepcopy(result)
            return empty(source)
        return SimpleNamespace(collect=collect), {"isolated-fixture": source}
    def run():
        return collect_sources(NICHE, factory=factory, cache=cache, settings=PerformanceSettings(amazon_concurrency=2))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run)
        assert entered.wait(timeout=3)
        second = pool.submit(run)
        release.set()
        results = [first.result(timeout=5), second.result(timeout=5)]
    assert calls == ["amazon"]
    assert sorted(output["Fixture only"]["amazon"].status_dict()["live_attempted"] for output in results) == [False, True]


def test_provider_concurrency_two_allows_two_independent_runs():
    barrier = threading.Barrier(2)
    def run():
        def collect(source, niche):
            if source == "amazon":
                barrier.wait(timeout=3)
            return empty(source)
        return collect_sources(NICHE, settings=PerformanceSettings(amazon_concurrency=2), collectors={
            source: SimpleNamespace(collect=lambda niche, s=source: collect(s, niche)) for source in SOURCES})
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(run), pool.submit(run)
        assert first.result(timeout=5)["Fixture only"]["amazon"].warnings[0].code == "fixture"
        assert second.result(timeout=5)["Fixture only"]["amazon"].warnings[0].code == "fixture"


def test_constructor_error_is_source_local_and_owned_resources_close():
    closed = []
    class Resource:
        def __enter__(self): return self
        def __exit__(self, *args): closed.append(threading.get_ident())
    def factory(source, resources, policy):
        resources.enter_context(Resource())
        if source == "amazon":
            raise RuntimeError("Fixture private token must not leak")
        return SimpleNamespace(collect=lambda niche: empty(source)), None
    result = collect_sources(NICHE, factory=factory, cache=ValidatedCollectionCache())
    assert len(closed) == 3
    warning = result["Fixture only"]["amazon"].warnings[0]
    assert warning.code == "internal_error" and "private token" not in warning.message
    assert result["Fixture only"]["reddit"].warnings[0].code == "fixture"


def test_owned_resources_close_when_persistence_callback_fails():
    closed = []
    class Resource:
        def __enter__(self): return self
        def __exit__(self, *args): closed.append(True)
    def factory(source, resources, policy):
        resources.enter_context(Resource())
        return SimpleNamespace(collect=lambda niche: empty(source)), None
    with pytest.raises(OSError, match="Fixture storage"):
        collect_sources(NICHE, factory=factory, cache=ValidatedCollectionCache(),
                        on_result=Mock(side_effect=OSError("Fixture storage")))
    assert closed  # Every constructed resource has exited before the error returns.


def test_cache_handles_wall_clock_jump_and_monotonic_expiry(collection_factory):
    wall, mono = [NOW], [0.0]
    cache = ValidatedCollectionCache(utcnow=lambda: wall[0], monotonic=lambda: mono[0])
    result = collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")])
    assert cache.put("wall", result, 300)
    wall[0] = NOW + timedelta(seconds=301)
    assert cache.get("wall") is None
    wall[0] = NOW
    assert cache.put("mono", result, 300)
    wall[0] = NOW - timedelta(seconds=100)
    mono[0] = 301
    assert cache.get("mono") is None


def test_cache_entry_expiring_during_copy_is_not_returned(collection_factory, monkeypatch):
    clock = [0.0]
    cache = ValidatedCollectionCache(utcnow=lambda: NOW, monotonic=lambda: clock[0])
    result = collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")])
    assert cache.put("fixture", result, 1)
    original = deepcopy
    def copy_then_expire(value):
        copied = original(value)
        clock[0] = 2
        return copied
    monkeypatch.setattr("src.collectors.collection_cache.deepcopy", copy_then_expire)
    assert cache.get("fixture") is None


def test_full_trends_series_is_preserved_in_snapshot_and_cache(tmp_path, collection_factory):
    result = validate_collection_result("google_trends", collection_factory("google_trends", [KeywordSignal("fixture", score=30)]))
    cache = ValidatedCollectionCache(utcnow=lambda: NOW)
    assert cache.put("series", result, 300)
    cached = cache.get("series")
    assert cached.records[0].time_series == result.records[0].time_series
    assert cached.records[0].metrics == result.records[0].metrics
    writer = CollectionSnapshotWriter(tmp_path, "f" * 32, ["Fixture"], PerformanceSettings())
    for source in SOURCES:
        writer.capture(0, source, cached if source == "google_trends" else empty(source))
    writer.commit()
    document = next(item for item in read_collection_snapshots(tmp_path, "f" * 32) if item["source"] == "google_trends")
    assert len(document["collection"]["records"][0]["time_series"]) == 4
    assert document["collection"]["records"][0]["provenance"]["from_cache"] is True


def test_run_byte_limit_keeps_partial_artifacts_without_manifest(tmp_path):
    settings = PerformanceSettings(snapshot_max_bytes=1024, snapshot_run_max_bytes=1024)
    writer = CollectionSnapshotWriter(tmp_path, "a" * 32, ["Fixture"], settings)
    with pytest.raises(ValueError, match="Run snapshots"):
        for source in SOURCES:
            writer.capture(0, source, empty(source))
    assert not (writer.directory / "manifest.json").exists()
    assert list(writer.directory.glob("*.json"))


@pytest.mark.parametrize("body", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'[]', b'{} trailing'])
def test_new_snapshot_decoder_rejects_noncanonical_json(body):
    with pytest.raises(ValueError):
        decode_document(body)


def test_streaming_preserves_json_and_handles_unknown_encoding(http_factory, response_factory):
    raw = response_factory(payload={"observed": "dữ liệu fixture"})
    raw.encoding = "invalid-fixture-encoding"
    http = http_factory([raw])
    journal = []
    response = http.client.fetch("GET", "https://example.test/fixture", source="fixture", operation="search", query={}, journal=journal)
    assert response.json() == {"observed": "dữ liệu fixture"}
    assert len(journal) == 1 and journal[0].error_code is None
    raw.close.assert_called_once()


def test_streaming_read_failure_closes_and_journals_without_private_body(http_factory, response_factory):
    raw = response_factory()
    raw.iter_content = Mock(side_effect=requests.ReadTimeout("Fixture private body"))
    http = http_factory([raw], policy=HTTPPolicy(max_attempts=1))
    journal = []
    from src.collectors.errors import CollectionError
    with pytest.raises(CollectionError):
        http.client.fetch("GET", "https://example.test/fixture", source="fixture", operation="search", query={}, journal=journal)
    assert journal[0].error_code == "read_timeout"
    assert "private body" not in journal[0].error_message
    raw.close.assert_called_once()


def test_snapshot_directory_cannot_escape_output_root_through_symlink(tmp_path):
    root, outside = tmp_path / "reports", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        (root / "snapshots").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("OS does not allow creating symlinks; no fake symlink fallback")
    with pytest.raises(ValueError, match="escapes"):
        CollectionSnapshotWriter(root, "b" * 32, ["Fixture"], PerformanceSettings())
    with pytest.raises(ValueError, match="escapes"):
        read_collection_snapshots(root, "b" * 32)


def test_provider_busy_timeout_does_not_call_collector_then_recovers():
    entered, release = threading.Event(), threading.Event()
    second_calls = []
    settings = PerformanceSettings(slot_wait_seconds=0.02)
    def run(holding=False):
        def collect(source, niche):
            if source == "amazon":
                if holding:
                    entered.set()
                    assert release.wait(timeout=3)
                else:
                    second_calls.append(source)
            return empty(source)
        return collect_sources(NICHE, settings=settings, collectors={
            source: SimpleNamespace(collect=lambda niche, s=source: collect(s, niche)) for source in SOURCES})
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(run, True)
        assert entered.wait(timeout=3)
        second = run()
        assert not second_calls
        assert second["Fixture only"]["amazon"].warnings[0].code == "provider_busy"
        release.set()
        first.result(timeout=5)
    assert run()["Fixture only"]["amazon"].warnings[0].code == "fixture"
    assert second_calls == ["amazon"]


def test_concurrent_cache_readers_own_results_and_lru_accounting(collection_factory):
    result = collection_factory("amazon", [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")])
    cache = ValidatedCollectionCache(max_entries=2, utcnow=lambda: NOW)
    assert cache.put("initial", result, 300)
    barrier = threading.Barrier(3)
    def read_and_change(index):
        snapshot = cache.get("initial")
        barrier.wait(timeout=3)
        snapshot.records[0].title = f"Caller {index}"
        return snapshot.records[0].title
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert list(pool.map(read_and_change, range(3))) == ["Caller 0", "Caller 1", "Caller 2"]
    assert cache.get("initial").records[0].title == "Fixture"
    assert cache.put("next", result, 300)
    assert cache.put("third", result, 300)
    assert cache.get("initial") is None
    assert cache._bytes == sum(entry.serialized_bytes for entry in cache._entries.values())


def test_cached_run_publishes_consistent_real_origin_flags_without_new_attempts(tmp_path, monkeypatch, collection_factory):
    """End-to-end publication contract, explicitly using isolated fixture evidence."""
    from src.pipeline import execute_pipeline
    from src.reporters.report_repository import ReportRepository
    cache = ValidatedCollectionCache(utcnow=lambda: NOW)
    calls = []
    def factory(source, resources, policy):
        def collect(niche):
            calls.append(source)
            records = {
                "google_trends": [KeywordSignal("fixture one", score=40), KeywordSignal("fixture two", score=60)],
                "amazon": [ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")],
                "reddit": [DiscussionItem("Fixture", url="https://www.reddit.com/r/fixture/comments/abc123/post/")],
            }
            return collection_factory(source, records[source])
        return SimpleNamespace(collect=collect), {"isolated-fixture": source}
    def isolated_sources(niches, **options):
        return collect_sources(niches, **options, cache=cache, factory=factory)
    monkeypatch.setattr("src.pipeline.collect_sources", isolated_sources)
    first = execute_pipeline(fast_mode=True, niche_list=NICHE, output_dir=tmp_path)
    second = execute_pipeline(fast_mode=True, niche_list=NICHE, output_dir=tmp_path)
    assert len(calls) == 3 and set(calls) == set(SOURCES)
    assert first["metadata"]["run_id"] != second["metadata"]["run_id"]
    assert second["metadata"]["status"] == first["metadata"]["status"] == "success"
    assert ReportRepository(tmp_path).load_latest() == second
    assert set(first["request_metadata"]) == set(second["request_metadata"])
    assert all(trace["cache_reused"] for trace in second["request_metadata"].values())
    assert not any(trace["cache_reused"] for trace in first["request_metadata"].values())
    assert all(status["request_count"] == 0 and status["cached_record_count"] > 0
               for status in second["source_statuses"]["Fixture only"].values())
    assert all(item["from_cache"] for item in second["evidence"])
    documents = read_collection_snapshots(tmp_path, second["metadata"]["run_id"])
    assert all(trace["cache_reused"] for document in documents for trace in document["collection"]["request_metadata"])
