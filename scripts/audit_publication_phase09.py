"""Publish archived real evidence through phase-9 views, without collecting again.

This is an offline publication audit, not a fresh live market report. Archived
phase-6 validation is reused; original record/request identities are preserved.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from scripts.audit_ranking_phase07 import load_validated_evidence
from src.analyzers.grounded_summary import GroundedSummaryService
from src.analyzers.llm_analyzer import LLMAnalyzer
from src.config import CATEGORY, OLLAMA_MODEL
from src.models.collection import RequestMetadata
from src.processors.data_quality import has_sufficient_evidence
from src.processors.research_result_builder import RunContext, build_research_result
from src.processors.source_health import aggregate_source_health
from src.ranking.service import RankingService
from src.reporters.report_repository import ReportRepository
from src.reporters.result_codec import read_document


def audit(input_path: Path, output_path: Path) -> dict:
    started = time.monotonic()
    previous, data, sources = load_validated_evidence(input_path)
    if has_sufficient_evidence(data):
        raise ValueError("Offline insufficient-evidence audit must never request model generation")
    requests = {}
    for source, origin in previous["origin_snapshots"].items():
        snapshot = read_document(Path(origin["snapshot"]))
        source_requests = snapshot["request_metadata"]
        if isinstance(source_requests, list):
            source_requests = {trace["request_id"]: trace for trace in source_requests}
        sources[source].request_metadata = [RequestMetadata(**source_requests[key]) for key in origin["original_request_ids"]]
        requests.update({trace.request_id: asdict(trace) for trace in sources[source].request_metadata})
    with LLMAnalyzer() as analyzer:
        section = analyzer.analyze(data.niche_name, data)
        if analyzer.attempted:
            raise RuntimeError("Unexpected model call in offline publication audit")
    processed, sections = {data.niche_name: data}, {data.niche_name: section}
    ranking = RankingService().rank([data]).to_dict()
    summary = GroundedSummaryService().build(processed, sections, ranking)
    run_id = uuid4().hex
    repository = ReportRepository(output_path)
    notes = ["KIỂM TRA OFFLINE TRÊN SNAPSHOT THẬT ĐÃ LƯU — KHÔNG PHẢI LẦN THU THẬP LIVE MỚI.",
             "Giữ nguyên thời điểm/request gốc; không xác minh lại provider hoặc positive Ollama end-to-end."]
    context = RunContext(run_id=run_id, category=CATEGORY, timestamp=datetime.now(timezone.utc).isoformat(),
                         requested_mode="ollama", requested_model=OLLAMA_MODEL, model_attempted=analyzer.attempted,
                         elapsed_seconds=round(time.monotonic() - started, 2), diagnostics_file=f"diagnostics/{run_id}.json",
                         execution_kind="offline_publication_audit")
    research = build_research_result(context=context, processed=processed, sections=sections,
        source_statuses={data.niche_name: {source: result.status_dict() for source, result in sources.items()}},
        source_health=aggregate_source_health({data.niche_name: sources}), request_metadata=requests,
        ranking_assessment=ranking, analysis_summary=summary, warnings=notes)
    diagnostic = {"run_id": run_id, "audit_kind": "offline_canonical_publication_on_validated_live_snapshots",
                  "data_policy": research.metadata["data_policy"], "network_requests_during_audit": 0,
                  "llm_generation_requests": 0, "provider_rechecks": False,
                  "previous_audit": input_path.as_posix(), "origin_snapshots": previous["origin_snapshots"],
                  "quality_assessment": data.quality_assessment.to_dict(),
                  "record_counts": {source: len(result.records) for source, result in sources.items()}}
    repository.save_diagnostics(run_id, diagnostic)
    published = repository.publish(research)
    restored = repository.load_latest()
    if restored != published or Path(published["report_filepath"]).read_text(encoding="utf-8") != published["markdown_content"]:
        raise RuntimeError("Canonical publication roundtrip mismatch")
    repository.save_diagnostics(run_id, {**diagnostic, "json_markdown_cache_consistent": True,
        "document_sha256": published["document_sha256"], "evidence_appendix_entries": len(published["evidence"]),
        "markdown_sha256": hashlib.sha256(published["markdown_content"].encode("utf-8")).hexdigest()})
    return {"diagnostics": str((output_path / context.diagnostics_file).resolve()), "report": published["report_filepath"],
            "record_counts": diagnostic["record_counts"], "status": published["status"],
            "quality": research.metadata["data_quality"], "mode": research.metadata["mode"],
            "evidence_count": len(published["evidence"]), "network_requests": 0, "model_calls": 0,
            "json_markdown_cache_consistent": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("reports/verification_phase06/diagnostics/ba0da4abf898429b9f4816722e73dd0a.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/verification_phase09"))
    args = parser.parse_args()
    print(json.dumps(audit(args.input, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
