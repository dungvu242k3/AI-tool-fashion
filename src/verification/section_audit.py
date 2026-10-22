"""Rebuild source-bound text/facts without calling an LLM or changing publication."""
from src.analyzers.analysis_policy import AnalysisPolicy
from src.analyzers.evidence_catalog import EvidenceCatalog
from src.analyzers.grounded_validator import validate_analysis
from src.models.analysis import ANALYSIS_VERSION
from src.reporters.evidence_renderer import EvidenceRenderer
from src.reporters.grounded_renderer import GroundedRenderer
from src.reporters.result_codec import canonical_json
from src.verification.contracts import check


def rebuild_section(data, niche):
    if niche["generation_mode"] != "ollama":
        section = EvidenceRenderer.section(data, niche["analysis_status"])
        check(not niche["reddit_pain_points"], "unsupported_pain_point")
    else:
        saved = niche["grounded_analysis"]
        policy = AnalysisPolicy(**niche["ai_validation"]["policy"])
        catalog = EvidenceCatalog.from_data(data, policy)
        check(canonical_json(catalog.context_summary()) == canonical_json(niche["ai_validation"]["context"]),
              "ai_context_mismatch")
        payload = {
            "schema_version": ANALYSIS_VERSION,
            "facts": [{key: item[key] for key in ("fact_id", "kind", "metric", "value", "evidence_ids")}
                      for item in saved["facts"]],
            "quotes": [{key: item[key] for key in ("quote_id", "quote", "evidence_ids")} for item in saved["quotes"]],
            "ideas": [{"kind": "proposal", "name": item["name"], "what_to_sell": item["rationale"],
                       **{key: item[key] for key in ("target_audience", "basis_fact_ids", "basis_quote_ids", "evidence_ids")}}
                      for item in saved["ideas"]],
            "limitations": saved["limitations"],
        }
        analysis = validate_analysis(canonical_json(payload), catalog, max_bytes=policy.max_response_bytes)
        check(canonical_json(analysis.to_dict()) == canonical_json(saved), "grounded_analysis_mismatch")
        section = GroundedRenderer.section(data, analysis, catalog, niche["ai_validation"])
        check(canonical_json([item.to_dict() for item in section.reddit_pain_points])
              == canonical_json(niche["reddit_pain_points"]), "pain_point_mismatch")
    for target, field in (("keywords_content", "keywords_content"), ("analysis_text", "analysis_content"),
                          ("ideas_content", "ideas_content")):
        check(niche[target] == getattr(section, field), "rendered_section_not_source_bound", target)
    return section
