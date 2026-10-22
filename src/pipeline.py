"""Orchestrate live collection, evidence gating, analysis and report persistence."""
import time
from threading import Lock
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from src.analyzers.llm_analyzer import LLMAnalyzer
from src.analyzers.grounded_summary import GroundedSummaryService
from src.collectors.collection_runtime import collect_sources
from src.collectors.http_policy import HTTPPolicy
from src.collectors.performance_settings import PerformanceSettings
from src.collectors.validation import Collector
from src.config import CATEGORY, DATA_POLICY_VERSION, NICHES, OLLAMA_MODEL, REPORTS_DIR
from src.models.research_request import ResearchRequest
from src.processors.data_processor import DataProcessor
from src.processors.data_quality import assess_data_quality
from src.collectors.evidence_validation import valid_text
from src.processors.source_health import aggregate_source_health
from src.processors.research_result_builder import RunContext, build_research_result
from src.reporters.report_repository import ReportRepository
from src.reporters.collection_snapshots import CollectionSnapshotWriter
from src.ranking.policy import MAX_NICHES
from src.ranking.service import RankingService

SOURCE_FIELDS = {
    "google_trends": "keywords_data", "amazon": "products_data", "reddit": "discussions_data",
}


def _record_provenances(record):
    seen = set()
    for provenance in [record.provenance, *(listing.provenance for listing in getattr(record, "listings", []))]:
        if provenance.evidence_id not in seen:
            seen.add(provenance.evidence_id)
            yield provenance


def execute_pipeline(
    fast_mode: bool = False,
    model_name: Optional[str] = None,
    niche_list=None,
    output_dir: str = REPORTS_DIR,
    progress_callback=None,
    *,
    collectors: Optional[Dict[str, Collector]] = None,
    ranking_service: Optional[RankingService] = None,
    request: Optional[ResearchRequest] = None,
) -> Dict[str, Any]:
    """Return a diagnostic report even when upstream data is insufficient.

    success means all configured sources and the requested analysis completed.
    Partial/failed runs retain collected records, warnings and their report path.
    fast_mode explicitly disables LLM; it never supplies sample data.
    """
    started = time.monotonic()
    run_id = uuid4().hex
    if request is not None and not isinstance(request, ResearchRequest):
        raise ValueError("ResearchRequest required")
    if request is not None:
        if niche_list is not None:
            raise ValueError("ResearchRequest and niche_list cannot be combined")
        niches = request.collector_niches()
        fast_mode = request.mode == "deterministic"
    else:
        niches = NICHES if niche_list is None else niche_list
    if not isinstance(niches, (list, tuple)) or not 0 < len(niches) <= MAX_NICHES or any(
        not isinstance(n, dict) or not valid_text(n.get("name"), 200)
        for n in niches
    ):
        raise ValueError("Danh sách niche phải có tên hợp lệ.")
    if len({n["name"].strip().casefold() for n in niches}) != len(niches):
        raise ValueError("Tên niche không được trùng nhau.")
    selected_model = model_name or OLLAMA_MODEL
    ranking_service = ranking_service if ranking_service is not None else RankingService()
    if collectors is not None and set(collectors) != set(SOURCE_FIELDS):
        raise ValueError("Cần cấu hình đủ Google Trends, Amazon và Reddit collector.")

    progress_lock = Lock()

    def progress(step, title, detail=""):
        if progress_callback is not None:
            with progress_lock:
                progress_callback(step, 5, title, detail)

    warnings = []
    source_statuses = {}
    settings = PerformanceSettings.from_env()
    http_policy = HTTPPolicy.from_env()
    snapshots = CollectionSnapshotWriter(output_dir, run_id, [n["name"] for n in niches], settings)
    progress(1, "Thu thập dữ liệu live")

    def collection_progress(name, source, result):
        detail = "bắt đầu" if result is None else f"{result.status}; {len(result.records)} bản ghi"
        progress(1, "Thu thập dữ liệu live", f"{name} / {source}: {detail}")

    collected = collect_sources(niches, settings=settings, http_policy=http_policy, collectors=collectors,
                                progress=collection_progress, on_result=snapshots.capture)
    snapshot_manifest = snapshots.commit()
    for name, sources in collected.items():
        source_statuses[name] = {source: result.status_dict() for source, result in sources.items()}
        for source, result in sources.items():
            warnings.extend(f"{name} / {source}: [{warning.code}] {warning}" for warning in result.warnings)
    source_health = aggregate_source_health(collected)
    request_metadata = {}
    for sources in collected.values():
        for result in sources.values():
            for trace in result.request_metadata:
                previous = request_metadata.get(trace.request_id)
                if previous is None or (previous["cache_reused"] and not trace.cache_reused):
                    request_metadata[trace.request_id] = asdict(trace)
    repository = ReportRepository(output_dir)
    diagnostics = {
        "run_id": run_id, "data_policy": DATA_POLICY_VERSION,
        "snapshot_manifest": snapshot_manifest, "collection_policy": asdict(settings),
        "transport_policy": asdict(http_policy),
        "source_statuses": source_statuses, "source_health": source_health,
        "request_metadata": request_metadata,
        "evidence": [
            {"niche": name, **asdict(provenance)}
            for name, sources in collected.items() for result in sources.values()
            for record in result.records
            for provenance in _record_provenances(record)
        ],
    }
    diagnostics_file = repository.save_diagnostics(run_id, diagnostics)

    progress(2, "Chuẩn hóa dữ liệu và kiểm tra điều kiện tối thiểu")
    processor = DataProcessor()
    processed = {}
    quality_assessments = {}
    timestamp = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")
    for name, sources in collected.items():
        raw = {"niche": name, "collected_at": timestamp}
        raw.update({SOURCE_FIELDS[source]: result.records for source, result in sources.items()})
        data = processor.process(raw)
        assessment = assess_data_quality(data, sources)
        data.quality_assessment = assessment
        processed[name] = data
        quality_assessments[name] = assessment.to_dict()
        warnings.extend(f"{name}: [{issue.code}] {issue.message}" for issue in assessment.issues)
    # Exactly one scoring call. Persist the same canonical breakdown before AI.
    ranking_assessment = ranking_service.rank(processed.values()).to_dict()
    warnings.extend(ranking_assessment["warnings"])
    repository.save_diagnostics(run_id, {**diagnostics, "quality_assessments": quality_assessments,
                                         "ranking_assessment": ranking_assessment})

    progress(3, "Tổng hợp dữ liệu" if fast_mode else "Phân tích với Ollama")
    sections = {}
    with LLMAnalyzer(model=selected_model, fast_mode=fast_mode) as analyzer:
        for name, data in processed.items():
            section = analyzer.analyze(name, data)
            sections[name] = section
            warnings.extend(f"{name}: {warning}" for warning in section.warnings)

    progress(4, "Tổng kết kết quả và giới hạn dữ liệu")
    analysis_summary = GroundedSummaryService().build(processed, sections, ranking_assessment)
    warnings.extend(analysis_summary["warnings"])
    ai_validation = {name: section.ai_validation for name, section in sections.items()}
    repository.save_diagnostics(run_id, {**diagnostics, "quality_assessments": quality_assessments,
        "ranking_assessment": ranking_assessment, "ai_validation": ai_validation,
        "grounded_analysis": {name: section.grounded_analysis.to_dict() if section.grounded_analysis else None
                              for name, section in sections.items()}, "analysis_summary": analysis_summary})
    progress(5, "Xuất báo cáo")
    research = build_research_result(
        context=RunContext(run_id=run_id, category=request.category if request else CATEGORY, timestamp=timestamp,
                           requested_mode="deterministic" if fast_mode else "ollama", requested_model=selected_model,
                           model_attempted=analyzer.attempted, elapsed_seconds=round(time.monotonic() - started, 2),
                           diagnostics_file=diagnostics_file, research_input=request.to_dict() if request else None),
        processed=processed, sections=sections, source_statuses=source_statuses,
        source_health=source_health, request_metadata=request_metadata, ranking_assessment=ranking_assessment,
        analysis_summary=analysis_summary, warnings=warnings)
    result = repository.publish(research)
    progress(5, "Hoàn tất" if result["success"] else "Báo cáo chưa đầy đủ", result["report_filename"])
    return result
