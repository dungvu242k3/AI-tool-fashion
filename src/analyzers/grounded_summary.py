"""Deterministic summary of complete grounded ideas and canonical niche scores."""
from src.models.analysis import GroundedAnalysis
from src.processors.data_quality import has_sufficient_evidence


class GroundedSummaryService:
    """No extra model call or fictional per-idea score.

    Up to three research slots, round-robin over canonical niche order. Within
    a niche, content-derived IDs stabilise display, not a claim of superiority.
    All proposals, fact metrics and canonical score references remain visible.
    """

    def build(self, data_by_niche, sections, ranking):
        available, contexts = {}, []
        for name, data in data_by_niche.items():
            section = sections[name]
            analysis = section.grounded_analysis
            if (not isinstance(analysis, GroundedAnalysis) or section.analysis_status != "success"
                    or section.generation_mode != "ollama" or section.ai_validation.get("outcome") != "source_references_verified"
                    or not has_sufficient_evidence(data) or analysis.niche_name != name
                    or analysis.evidence_digest != data.quality_assessment.data_digest):
                continue
            available[name] = analysis
            contexts.append({"niche": name, "evidence_digest": analysis.evidence_digest,
                             "facts": [fact.to_dict() for fact in analysis.facts],
                             "quotes": [item.to_dict() for item in analysis.quotes],
                             "ideas": [idea.to_dict() for idea in sorted(analysis.ideas, key=lambda item: item.idea_id)]})
        queues, ranks = {}, {}
        for row in ranking["ranking"]:
            name = row["niche"]
            if (name in available and available[name].ideas and row.get("status") == "ranked"
                    and row.get("evidence_digest") == available[name].evidence_digest):
                queues[name] = sorted(available[name].ideas, key=lambda idea: idea.idea_id)
                ranks[name] = row["rank"]
        selected = []
        while len(selected) < 3 and any(queues.values()):
            for name, ideas in queues.items():
                if not ideas:
                    continue
                idea = ideas.pop(0)
                data = data_by_niche[name]
                evidence = {record.provenance.evidence_id: record.provenance for record in
                            [*data.keywords, *data.products, *data.discussions]}
                selected.append({
                    **idea.to_dict(), "selection_position": len(selected) + 1, "niche": name, "niche_rank": ranks[name],
                    "title": idea.name, "what_to_sell": idea.rationale,
                    "source_links": [{"evidence_id": key, "url": evidence[key].source_url,
                                      "retrieved_at": evidence[key].retrieved_at} for key in idea.evidence_ids],
                })
                if len(selected) == 3:
                    break
        status = "available" if len(selected) == 3 else ("partial" if selected else "unavailable_no_grounded_ranked_ideas")
        return {
            "method": "grounded_research_slots_round_robin_v1", "status": status,
            "selection_policy": "canonical_niche_order_round_robin_then_content_id_not_idea_quality_score",
            "ranking_policy_id": ranking["policy_id"],
            "ranking_reference": "ranking_assessment: canonical scores, full component metrics/breakdown and inputs",
            "niches": sorted(contexts, key=lambda row: (row["niche"].casefold(), row["niche"])), "top_ideas": selected,
            "warnings": [
                "Tối đa ba đề xuất thử nghiệm theo thứ tự niche và phân bổ vòng; không phải ba sản phẩm đã chứng minh bán tốt nhất.",
                "ID nội dung chỉ ổn định lựa chọn trong niche; không có điểm chất lượng/lợi nhuận giả cho ý tưởng.",
                "Đã đối chiếu metric/citation/quote, chưa chứng minh market fit, nguyên nhân hoặc chân dung khách hàng.",
            ],
        }
