"""Explicit, bounded real-provider smoke probes. No cache, mock or report fallback."""
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from src.collectors.amazon import AmazonCollector
from src.collectors.amazon_settings import AmazonSettings
from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.http import HTTPClient
from src.collectors.http_policy import HTTPPolicy
from src.collectors.performance_settings import SOURCES
from src.collectors.reddit import RedditCollector
from src.collectors.reddit_settings import RedditSettings
from src.collectors.trends_settings import TrendsSettings
from src.collectors.validation import validate_collection_result
from src.config import NICHES
from src.reporters.report_repository import ReportRepository

# At most one HTTP attempt/operation. These are probe budgets, not production
# defaults or fabricated market measurements. Provider parsers/validation are real.
PROBE_HTTP_POLICY = HTTPPolicy(connect_timeout=3, read_timeout=8, max_attempts=1,
                               max_redirects=2, retry_wait_budget=1, max_response_bytes=2 * 1024 * 1024)


def _collector(source, http):
    if source == "google_trends":
        return GoogleTrendsCollector(http, settings=TrendsSettings(
            geo="US", cache_ttl_seconds=0, batch_delay_seconds=0, suggestions_enabled=False))
    if source == "amazon":
        return AmazonCollector(http, settings=AmazonSettings(max_requests=1, max_products=5))
    return RedditCollector(http, settings=RedditSettings(
        mode="auto", max_queries=1, max_subreddits=1, max_keywords=1, max_posts=3, page_size=5))


def probe_provider(source: str, output_dir) -> dict:
    """Only configured query input, never arbitrary provider URLs or sample records."""
    if not isinstance(source, str) or source not in SOURCES:
        raise ValueError("Unknown live provider")
    configured = NICHES[0]
    niche = {"name": configured["name"], "seed_keywords": list(configured["seed_keywords"][:2 if source == "google_trends" else 1]),
             "subreddits": list(configured.get("subreddits", [])[:1]),
             "amazon_search_terms": list(configured.get("amazon_search_terms", configured["seed_keywords"])[:1])}
    run_id = uuid4().hex
    report = {"run_id": run_id, "audit_kind": "explicit_real_provider_probe", "source": source,
              "started_at": datetime.now(timezone.utc).isoformat(), "query_input": niche,
              "transport_policy": asdict(PROBE_HTTP_POLICY), "cache_enabled": False, "model_calls": 0,
              "not_a_complete_market_report": True}
    result = None
    try:
        with ExitStack() as resources:
            http = resources.enter_context(HTTPClient(policy=PROBE_HTTP_POLICY))
            collector = resources.enter_context(_collector(source, http))
            report["provider"] = getattr(getattr(collector, "provider", None), "name", source)
            result = validate_collection_result(source, collector.collect(niche))
        observed = bool(result.records) and any(not trace.cache_reused for trace in result.request_metadata)
        accepted = observed and result.status in {"success", "partial"}
        report.update(status="observed" if accepted else "failed", collection=asdict(result),
                      warning_codes=[warning.code for warning in result.warnings],
                      record_count=len(result.records), network_attempts=len(result.request_metadata),
                      scope="accepted_real_records_present_not_complete_provider_accuracy")
    except Exception as exc:
        # Do not log raw exception strings, auth state or response bodies.
        report.update(status="failed", error_type=type(exc).__name__, warning_codes=["probe_internal_failure"],
                      record_count=0, network_attempts=None,
                      scope="unknown_attempt_count_when_transport_contract_failed")
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    relative = ReportRepository(output_dir).save_diagnostics(run_id, report)
    return {"status": report["status"], "source": source, "record_count": report["record_count"],
            "network_attempts": report["network_attempts"], "warning_codes": report["warning_codes"],
            "diagnostics": relative}
