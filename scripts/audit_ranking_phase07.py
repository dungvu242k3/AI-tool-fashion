"""Audit ranking against archived real evidence; no network or fixture imports.

Run from the repository root: python -B -m scripts.audit_ranking_phase07
This is not a collector, cache loader or a new market research run. Phase-6
accepted records/counts are reused, not re-fetched or replaced with sample data.
"""
import argparse
from dataclasses import fields
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from src.config import DATA_POLICY_VERSION
from src.models.collection import CollectionResult, CollectionWarning, RecordProvenance
from src.models.commerce import ProductListing
from src.models.quality import ValidationStats
from src.models.schemas import DiscussionItem, KeywordSignal, ProductItem
from src.models.trends import TrendMetrics, TrendPoint
from src.processors.data_processor import DataProcessor
from src.processors.data_quality import assess_data_quality
from src.ranking.service import RankingService
from src.reporters.report_repository import ReportRepository


def _restore(raw, model):
    values = {item.name: raw[item.name] for item in fields(model) if item.name in raw}
    values["provenance"] = RecordProvenance(**values["provenance"])
    if model is KeywordSignal:
        values["time_series"] = [TrendPoint(**point) for point in values["time_series"]]
        values["metrics"] = TrendMetrics(**values["metrics"])
    if model is ProductItem:
        values["listings"] = [ProductListing(**{**listing, "provenance": RecordProvenance(**listing["provenance"])})
                              for listing in values["listings"]]
    return model(**values)


def load_validated_evidence(input_path: Path):
    """Restore archived accepted observations; never re-fetch a provider."""
    if input_path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Audit input exceeds its size budget")
    previous = json.loads(input_path.read_text(encoding="utf-8"))
    if (previous.get("audit_kind") != "offline_validation_of_prior_live_snapshots"
            or previous.get("data_policy") != "live-only-v6"):
        raise ValueError("Expected the archived phase-6 validated live-evidence audit")
    models = {"google_trends": KeywordSignal, "amazon": ProductItem, "reddit": DiscussionItem}
    sources = {}
    for source, model in models.items():
        status = previous["source_validation"][source]
        counts = status["validation"]
        validation = ValidationStats(**{
            **{item.name: counts[item.name] for item in fields(ValidationStats) if item.name != "rejection_counts"},
            "rejection_counts": tuple(sorted(counts["rejection_counts"].items())),
        })
        sources[source] = CollectionResult(
            source, [_restore(raw, model) for raw in previous["records"][source]], status["status"],
            [CollectionWarning(**warning) for warning in status["warnings"]],
            started_at=status["started_at"], completed_at=status["completed_at"], validation=validation,
        )
    data = DataProcessor().process({
        "niche": "Christmas Gift Ideas", "collected_at": previous["audited_at"],
        "keywords_data": sources["google_trends"].records,
        "products_data": sources["amazon"].records, "discussions_data": sources["reddit"].records,
    })
    data.quality_assessment = assess_data_quality(data, sources)
    return previous, data, sources


def audit(input_path: Path, output_path: Path) -> dict:
    previous, data, sources = load_validated_evidence(input_path)
    ranking = RankingService().rank([data]).to_dict()
    run_id = uuid4().hex
    output = {
        "run_id": run_id, "data_policy": DATA_POLICY_VERSION,
        "audit_kind": "offline_ranking_of_previously_validated_live_snapshots",
        "audited_at": datetime.now(timezone.utc).isoformat(), "network_requests_during_audit": 0,
        "provider_rechecks": False, "record_validation_reused_from_phase06": True,
        "not_a_new_live_collection_or_market_recommendation": True,
        "previous_audit": {"snapshot": input_path.as_posix(), "run_id": previous["run_id"]},
        "origin_snapshots": previous["origin_snapshots"],
        "record_counts": {source: len(result.records) for source, result in sources.items()},
        "original_evidence": [
            {"source": source, "evidence_id": record.provenance.evidence_id,
             "source_url": record.provenance.source_url, "retrieved_at": record.provenance.retrieved_at,
             "request_id": record.provenance.request_id, "from_cache": record.provenance.from_cache}
            for source, result in sources.items() for record in result.records
        ],
        "quality_assessment": data.quality_assessment.to_dict(), "ranking_assessment": ranking,
        "top_ideas": [],
    }
    relative = ReportRepository(output_path).save_diagnostics(run_id, output)
    return {"audit_file": str((output_path / relative).resolve()), "ranking_status": ranking["status"],
            "ranked_niches": len(ranking["ranking"]), "quality": data.quality_assessment.status,
            "record_counts": output["record_counts"], "network_requests": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("reports/verification_phase06/diagnostics/ba0da4abf898429b9f4816722e73dd0a.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/verification_phase07"))
    args = parser.parse_args()
    print(json.dumps(audit(args.input, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
