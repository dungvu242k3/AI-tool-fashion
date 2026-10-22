"""Apply the grounded-analysis gate to previously validated real snapshots.

No collectors, fixture data, model-response substitutions or current-run cache.
The available archived input is insufficient, so the real analyzer must make
zero generation calls and return data-only output. This does NOT verify the
positive Ollama/schema path on a sufficiently grounded live run.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from scripts.audit_ranking_phase07 import load_validated_evidence
from src.analyzers.grounded_summary import GroundedSummaryService
from src.analyzers.llm_analyzer import LLMAnalyzer
from src.config import DATA_POLICY_VERSION
from src.processors.data_quality import has_sufficient_evidence
from src.ranking.service import RankingService
from src.reporters.report_repository import ReportRepository


def audit(input_path: Path, output_path: Path):
    previous, data, sources = load_validated_evidence(input_path)
    if has_sufficient_evidence(data):
        raise ValueError("This offline gate audit requires insufficient evidence; it must never send archived records to a model")
    with LLMAnalyzer() as analyzer:
        section = analyzer.analyze(data.niche_name, data)
        if analyzer.attempted or section.ai_validation["attempts"]:
            raise RuntimeError("Unexpected model attempt during offline audit")
    ranking = RankingService().rank([data]).to_dict()
    summary = GroundedSummaryService().build({data.niche_name: data}, {data.niche_name: section}, ranking)
    run_id = uuid4().hex
    payload = {
        "run_id": run_id, "data_policy": DATA_POLICY_VERSION,
        "audit_kind": "offline_grounded_analysis_gate_on_validated_live_snapshots",
        "audited_at": datetime.now(timezone.utc).isoformat(), "network_requests_during_audit": 0,
        "llm_generation_requests": 0, "provider_rechecks": False, "record_validation_reused_from_phase06": True,
        "not_a_new_live_collection_or_market_recommendation": True,
        "previous_audit": {"snapshot": input_path.as_posix(), "run_id": previous["run_id"]},
        "origin_snapshots": previous["origin_snapshots"],
        "record_counts": {source: len(result.records) for source, result in sources.items()},
        "original_evidence": [{"source": source, **asdict(record.provenance)}
                              for source, result in sources.items() for record in result.records],
        "quality_assessment": data.quality_assessment.to_dict(), "ai_validation": section.ai_validation,
        "analysis_status": section.analysis_status, "generation_mode": section.generation_mode,
        "grounded_analysis": section.grounded_analysis.to_dict() if section.grounded_analysis else None,
        "ranking_assessment": ranking, "analysis_summary": summary, "ideas": [], "top_ideas": [],
    }
    relative = ReportRepository(output_path).save_diagnostics(run_id, payload)
    return {"audit_file": str((output_path / relative).resolve()), "record_counts": payload["record_counts"],
            "quality": data.quality_assessment.status, "analysis_status": section.analysis_status,
            "generation_mode": section.generation_mode, "model_calls": 0, "top_ideas": len(summary["top_ideas"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("reports/verification_phase06/diagnostics/ba0da4abf898429b9f4816722e73dd0a.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/verification_phase08"))
    args = parser.parse_args()
    print(json.dumps(audit(args.input, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
