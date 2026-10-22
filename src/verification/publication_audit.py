"""Read-only audit: archived collector input -> calculations -> all report views.

Recomputation is verification-only, never part of the publication/read-cache path.
There is no provider/model request, score repair, fresh timestamp or fallback.
"""
from dataclasses import asdict, fields
from pathlib import Path

from src.analyzers.grounded_summary import GroundedSummaryService
from src.collectors.performance_settings import SOURCES
from src.models.research_result import MAX_DOCUMENT_BYTES
from src.processors.data_processor import DataProcessor
from src.processors.data_quality import assess_data_quality
from src.processors.source_health import aggregate_source_health
from src.ranking.policy import COMPONENTS, RankingPolicy
from src.ranking.service import RankingService
from src.reporters.collection_snapshots import read_collection_snapshots
from src.reporters.ranking_renderer import RankingRenderer
from src.reporters.report_generator import ReportGenerator
from src.reporters.result_codec import canonical_json, read_document, validate_publication
from src.verification.collection_codec import restore_collection
from src.verification.contracts import AuditFailure, check
from src.verification.numeric_inventory import markdown_numbers, pointer, structured_numbers
from src.verification.section_audit import rebuild_section

SOURCE_FIELDS = {"google_trends": "keywords", "amazon": "products", "reddit": "discussions"}


def _same(left, right, code, path="$"):
    check(canonical_json(left) == canonical_json(right), code, path)


def _ranking_policy(raw):
    keys = {item.name for item in fields(RankingPolicy)}
    check(isinstance(raw, dict) and set(raw) == keys | {"method", "precision"}, "ranking_policy_fields")
    check(isinstance(raw["weights"], dict) and set(raw["weights"]) == set(COMPONENTS), "ranking_weights")
    values = {key: raw[key] for key in keys}
    values["weights"] = tuple((key, raw["weights"][key]) for key in COMPONENTS)
    policy = RankingPolicy(**values)
    _same(policy.to_dict(), raw, "ranking_policy_mismatch")
    return policy


def _audit(publication_path, snapshot_dir, snapshot_run_id):
    path = Path(publication_path).resolve()
    root = path.parent
    publication = read_document(path)
    research = validate_publication(publication, root)
    report_path = (root / publication["report_filename"]).resolve()
    check(report_path.parent == root, "markdown_path_escape")
    with report_path.open("rb") as stream:
        markdown_body = stream.read(MAX_DOCUMENT_BYTES + 1)
    check(len(markdown_body) <= MAX_DOCUMENT_BYTES, "markdown_byte_budget")
    check(markdown_body.decode("utf-8") == publication["markdown_content"], "markdown_file_mismatch")
    if publication["metadata"]["execution_kind"] == "live_collection":
        check(snapshot_run_id == publication["metadata"]["run_id"], "snapshot_run_mismatch")
    snapshots = read_collection_snapshots(snapshot_dir, snapshot_run_id)
    sources = {}
    for document in snapshots:
        check(set(document) == {"schema", "data_policy", "run_id", "position", "niche", "source", "collection"},
              "unknown_snapshot_envelope_field")
        name, source = document["niche"], document["source"]
        sources.setdefault(name, {})[source] = restore_collection(document["collection"])
    check(list(sources) == list(publication["niches"]), "snapshot_niche_order_mismatch")
    processor, processed, sections, blocks, source_checks = DataProcessor(), {}, {}, [], []
    request_metadata = {}
    for name, niche in publication["niches"].items():
        check(set(sources[name]) == set(SOURCES), "snapshot_source_set")
        raw = {"niche": name, "collected_at": niche["collected_at"]}
        for source, field in SOURCE_FIELDS.items():
            result = sources[name][source]
            raw[f"{field}_data"] = result.records
            _same([record.to_dict() for record in result.records], niche[field], "record_snapshot_mismatch", pointer("niches", name, field))
            _same(result.status_dict(), publication["source_statuses"][name][source], "source_status_mismatch")
            source_checks.append({"niche": name, "source": source, "record_count": len(result.records),
                                  "json_pointer": pointer("niches", name, field),
                                  "evidence_ids": [record.provenance.evidence_id for record in result.records]})
            for trace in result.request_metadata:
                previous = request_metadata.get(trace.request_id)
                if previous is None or (previous["cache_reused"] and not trace.cache_reused):
                    request_metadata[trace.request_id] = asdict(trace)
        data = processor.process(raw)
        quality = assess_data_quality(data, sources[name])
        _same(quality.to_dict(), niche["quality_assessment"], "quality_recompute_mismatch")
        data.quality_assessment = quality
        _same(processor.extract_price_ranges(data.products), niche["price_ranges"], "price_range_mismatch")
        expected_price = "; ".join(item["formatted"] for item in niche["price_ranges"]) or "Chưa có mẫu giá kèm currency hợp lệ."
        check(niche["price_range"] == expected_price, "price_range_text_mismatch")
        section = rebuild_section(data, niche)
        for field in ("keywords_content", "analysis_text", "ideas_content"):
            blocks.append({"text": niche[field], "reference": pointer("niches", name, field)})
        # Restore only the audit metadata needed by the deterministic summary.
        section.ai_validation = niche["ai_validation"]
        processed[name], sections[name] = data, section
    _same(request_metadata, publication["request_metadata"], "request_journal_mismatch")
    _same(aggregate_source_health(sources), publication["source_health"], "health_recompute_mismatch")
    ranking = RankingService(_ranking_policy(publication["ranking_assessment"]["policy"])).rank(processed.values()).to_dict()
    _same(ranking, publication["ranking_assessment"], "ranking_recompute_mismatch")
    summary = GroundedSummaryService().build(processed, sections, ranking)
    _same(summary, publication["analysis_summary"], "summary_recompute_mismatch")
    blocks.append({"text": RankingRenderer.summary(ranking, publication["niches"], summary),
                   "reference": "/ranking_assessment+analysis_summary"})
    for lines, reference in ((ReportGenerator._sources(research), "/source_statuses+source_health"),
                             (ReportGenerator._quality(research), "/metadata/quality_assessments"),
                             (ReportGenerator._evidence(research), "/evidence")):
        blocks.append({"text": "\n".join(lines), "reference": reference})
    inventory = markdown_numbers(publication["markdown_content"], blocks)
    return {
        "schema": "publication-data-audit-v1", "status": "consistent_with_collector_snapshots",
        "research_run_id": research.metadata["run_id"], "snapshot_run_id": snapshot_run_id,
        "research_status": research.metadata["status"], "research_quality": research.metadata["data_quality"],
        "network_requests": 0, "model_calls": 0, "publication_sha256": publication["document_sha256"],
        "checks": ["strict_publication_checksum_aliases_and_actual_markdown_file", "closed_snapshot_schema_and_provenance_validation",
                   "exact_raw_records_and_request_journal", "recomputed_trend_metrics_via_collection_validation",
                   "recomputed_quality_health_currency_ranges", "recomputed_stored_policy_ranking_and_summary",
                   "source_revalidated_AI_facts_quotes_proposals_and_rebuilt_sections", "all_numeric_occurrences_inventoried"],
        "sources": source_checks, "structured_numeric_fields": structured_numbers(publication),
        "markdown_numeric_inventory": inventory,
        "limitations": ["Consistency with saved observations, not current provider truth/authentication/market fit",
                        "Uses production pure calculators; cannot detect a mathematical bug common to calculator and auditor",
                        "Rejected candidate counts reconcile but excluded raw candidates cannot be re-parsed",
                        "Metadata/input/warnings/IDs/dates/constants and source text numbers are not independent market measurements",
                        "Ledger references verified sections, not a semantic proof of every natural-language statement"],
    }


def audit_publication(publication_path, snapshot_dir, snapshot_run_id):
    try:
        return _audit(publication_path, snapshot_dir, snapshot_run_id)
    except AuditFailure:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError, UnicodeError,
            OverflowError, RecursionError) as exc:
        raise AuditFailure("invalid_or_unreadable_audit_input") from exc
