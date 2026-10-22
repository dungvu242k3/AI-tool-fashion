"""Parallelize independent providers, never a provider's mutable session/state.

Only three tasks are submitted, irrespective of niche count. A source worker owns
its transport and visits niches in input order. Borrowed collectors stay borrowed.
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack, nullcontext
from copy import deepcopy
from dataclasses import asdict, replace

from src.collectors.amazon import AmazonCollector
from src.collectors.collection_cache import collection_key, shared_cache
from src.collectors.concurrency import SHARED_LEASES
from src.collectors.errors import CollectionError
from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.http import HTTPClient
from src.collectors.http_policy import HTTPPolicy
from src.collectors.performance_settings import PerformanceSettings, SOURCES
from src.collectors.reddit import RedditCollector
from src.collectors.trends_settings import TrendsSettings
from src.collectors.validation import validate_collection_result
from src.models.collection import CollectionResult, CollectionWarning

logger = logging.getLogger(__name__)


def _failure(source, exc):
    if isinstance(exc, CollectionError):
        return CollectionResult.from_records(source, [], [exc.warning])
    logger.error("collector_contract_failed", extra={"source": source, "error_type": type(exc).__name__})
    return CollectionResult.from_records(source, [], [CollectionWarning(
        "internal_error", f"Thu thập thất bại ({type(exc).__name__}).")])


def collect_validated(collector, source, niche):
    try:
        return validate_collection_result(source, collector.collect(deepcopy(niche)))
    except Exception as exc:
        return _failure(source, exc)


def owned_collector(source, resources, http_policy):
    http = resources.enter_context(HTTPClient(policy=http_policy))
    if source == "google_trends":
        # One cache policy at the validated boundary. Standalone batch cache is unchanged.
        collector = GoogleTrendsCollector(http, settings=replace(TrendsSettings.from_env(), cache_ttl_seconds=0))
        provider = collector.provider.cache_namespace
    elif source == "amazon":
        collector, provider = AmazonCollector(http), "amazon-html-v1"
    else:
        collector = RedditCollector(http)
        provider = collector.provider.cache_identity() if collector.provider is not None else None
    resources.enter_context(collector)
    identity = ({"provider": provider, "settings": asdict(collector.settings), "transport": asdict(http_policy)}
                if collector.settings is not None else None)
    return collector, identity


def collect_sources(niches, *, settings=None, http_policy=None, collectors=None,
                    progress=None, on_result=None, cache=None, factory=owned_collector):
    settings = settings if settings is not None else PerformanceSettings.from_env()
    http_policy = http_policy if http_policy is not None else HTTPPolicy.from_env()
    if collectors is not None:
        if set(collectors) != set(SOURCES):
            raise ValueError("Exactly three source collectors required")
        resources = [getattr(collector, "http", collector) for collector in collectors.values()]
        if len({id(resource) for resource in resources}) != len(SOURCES):
            raise ValueError("Independent providers cannot share collector/HTTP state")
    # Runtime injection never enters the shared cache: no fixture/custom provider leakage.
    cache = (cache if cache is not None else shared_cache(settings)) if collectors is None else None
    stop = threading.Event()

    def worker(source):
        results = {}
        with ExitStack() as resources:
            try:
                collector, identity = (factory(source, resources, http_policy) if collectors is None
                                       else (collectors[source], None))
                setup_error = None
            except Exception as exc:
                collector, identity, setup_error = None, None, _failure(source, exc)
            for index, niche in enumerate(niches):
                if stop.is_set():
                    break
                name = niche["name"]
                if progress:
                    progress(name, source, None)
                if setup_error is not None:
                    result = deepcopy(setup_error)
                else:
                    ttl = getattr(settings, f"{source}_cache_ttl")
                    key = (collection_key(source, niche, {**identity, "ttl_seconds": ttl})
                           if identity is not None and ttl > 0 else None)
                    try:
                        # Key lease suppresses stampedes even when provider capacity > 1.
                        with ExitStack() as leases:
                            leases.enter_context(SHARED_LEASES.acquire(("cache", key), 1, settings.slot_wait_seconds)
                                                 if key else nullcontext())
                            result = cache.get(key) if key else None
                            if result is None:
                                # Mutable transport/provider must stay single-threaded even across runs.
                                resource = getattr(collector, "http", collector)
                                leases.enter_context(SHARED_LEASES.acquire(
                                    ("instance", id(resource)), 1, settings.slot_wait_seconds))
                                leases.enter_context(SHARED_LEASES.acquire(
                                    ("provider", source), getattr(settings, f"{source}_concurrency"), settings.slot_wait_seconds))
                                result = collect_validated(collector, source, niche)
                                if key:
                                    cache.put(key, result, ttl)
                    except CollectionError as exc:
                        result = _failure(source, exc)
                # Persistence errors are fatal, not disguised as upstream no-data results.
                if on_result:
                    on_result(index, source, result)
                results[name] = result
                if progress:
                    progress(name, source, result)
        return results

    outputs = {}
    with ThreadPoolExecutor(max_workers=settings.max_workers, thread_name_prefix="collection") as pool:
        futures = {pool.submit(worker, source): source for source in SOURCES}
        try:
            for future in as_completed(futures):
                outputs[futures[future]] = future.result()
        except BaseException:
            stop.set()
            for future in futures:
                future.cancel()
            raise
    # Completion timing must not reorder scoring inputs, warning order or publication.
    return {niche["name"]: {source: outputs[source][niche["name"]] for source in SOURCES} for niche in niches}
