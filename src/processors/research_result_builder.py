"""The single assembly point between analysis and publication views."""
from dataclasses import dataclass
from typing import Mapping

from src.config import DATA_POLICY_VERSION
from src.models.research_result import ResearchResult
from src.models.schemas import NicheData, NicheReportSection
from src.processors.data_processor import DataProcessor


@dataclass(frozen=True, slots=True)
class RunContext:
    run_id: str
    category: str
    timestamp: str
    requested_mode: str
    requested_model: str
    model_attempted: bool
    elapsed_seconds: float
    diagnostics_file: str
    execution_kind: str = "live_collection"
    research_input: dict | None = None


def build_research_result(*, context: RunContext, processed: Mapping[str, NicheData],
                          sections: Mapping[str, NicheReportSection], source_statuses: dict,
                          source_health: dict, request_metadata: dict, ranking_assessment: dict,
                          analysis_summary: dict, warnings: list[str]) -> ResearchResult:
    """Capture results, not provider dependencies. No I/O, AI, ranking or timestamps."""
    if set(processed) != set(sections):
        raise ValueError("Analysis and processed niche sets disagree")
    qualities = [data.quality_assessment.status for data in processed.values()]
    all_sufficient = bool(qualities) and all(value == "sufficient" for value in qualities)
    any_sufficient = any(value != "insufficient" for value in qualities)
    quality = "sufficient" if all_sufficient else ("partial" if any_sufficient else "insufficient")
    ai_complete = context.requested_mode == "deterministic" or all(section.analysis_status == "success" for section in sections.values())
    success = all_sufficient and ai_complete
    totals = {key: sum(len(getattr(data, key)) for data in processed.values()) for key in ("keywords", "products", "discussions")}
    status = "success" if success else ("partial" if sum(totals.values()) else "failed")
    model_used = any(section.generation_mode == "ollama" for section in sections.values())
    mode = "deterministic"
    if model_used:
        mode = "ollama" if all(section.generation_mode == "ollama" for section in sections.values()) else "mixed"
    notes = list(warnings)
    if not success:
        notes.insert(0, "Báo cáo chưa đầy đủ; không đủ cơ sở xác nhận toàn bộ khuyến nghị.")
    metadata = {
        "run_id": context.run_id, "data_policy": DATA_POLICY_VERSION, "execution_kind": context.execution_kind,
        "category": context.category, "timestamp": context.timestamp, "status": status,
        "data_quality": quality, "mode": mode, "requested_mode": context.requested_mode,
        "quality_assessments": {name: data.quality_assessment.to_dict() for name, data in processed.items()},
        "model_name": context.requested_model if model_used else None,
        "model_attempted": context.requested_model if context.model_attempted else None,
        "cost": "$0.00 API (không gồm chi phí máy và điện)", "elapsed_seconds": context.elapsed_seconds,
        "total_niches": len(processed), **{f"total_{key}": value for key, value in totals.items()},
        "ranking_status": ranking_assessment["status"], "ranking_method": ranking_assessment["method"],
        "ranking_policy_id": ranking_assessment["policy_id"], "top_ideas_status": analysis_summary["status"],
        "ai_validation": {name: section.ai_validation for name, section in sections.items()},
        "warnings": list(dict.fromkeys(notes)), "source_health": source_health,
        "diagnostics_file": context.diagnostics_file,
    }
    if context.research_input is not None:
        metadata["research_input"] = context.research_input
    details = {}
    for name, data in processed.items():
        section = sections[name]
        price_ranges = DataProcessor.extract_price_ranges(data.products)
        details[name] = {
            **data.to_dict(), "name": name, "data_quality": data.quality_assessment.status,
            "source_statuses": source_statuses[name],
            "price_range": "; ".join(item["formatted"] for item in price_ranges) or "Chưa có mẫu giá kèm currency hợp lệ.",
            "price_ranges": price_ranges, "keywords_content": section.keywords_content,
            "analysis_text": section.analysis_content, "ideas_content": section.ideas_content,
            "ideas": [idea.to_dict() for idea in section.ideas],
            "reddit_pain_points": [point.to_dict() for point in section.reddit_pain_points],
            "analysis_status": section.analysis_status, "generation_mode": section.generation_mode,
            "grounded_analysis": section.grounded_analysis.to_dict() if section.grounded_analysis else None,
            "ai_validation": section.ai_validation,
        }
    return ResearchResult(metadata=metadata, niches=details, source_statuses=source_statuses,
                          request_metadata=request_metadata, ranking_assessment=ranking_assessment,
                          analysis_summary=analysis_summary)
