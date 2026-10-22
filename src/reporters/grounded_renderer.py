"""Render verified fact templates and explicitly unverified design proposals."""
from urllib.parse import quote

from src.models.community import RedditPainPoint
from src.reporters.evidence_renderer import EvidenceRenderer
from src.reporters.text import markdown_text


LIMITATION_LABELS = {
    "proposals_require_market_validation": "Đề xuất cần thử nghiệm thị trường, chưa chứng minh market fit.",
    "source_samples_not_market_representative": "Mẫu nguồn không đại diện toàn bộ thị trường.",
    "causality_not_established": "Chưa chứng minh nguyên nhân của biến động tìm kiếm.",
    "customer_profile_not_verified": "Đối tượng khách hàng chỉ là giả định cần kiểm chứng.",
    "insufficient_grounded_basis": "Chưa đủ cơ sở để đề xuất sản phẩm.",
}


def evidence_links(ids, catalog):
    return ", ".join(f"[{markdown_text(key)}]({quote(catalog.records[key].source_url, safe=':/?&=%#@+-,._~')})" for key in ids)


class GroundedRenderer:
    @staticmethod
    def section(data, analysis, catalog, validation):
        section = EvidenceRenderer.section(data, "not_requested")
        lines = [section.analysis_content, "", "#### Dữ kiện AI chọn — đã đối chiếu giá trị với nguồn"]
        for fact in analysis.facts:
            lines.append(f"- {fact.fact_id}: {markdown_text(fact.text)} Evidence: {evidence_links(fact.evidence_ids, catalog)}.")
        if analysis.quotes:
            lines.extend(["", "#### Trích dẫn nguồn — không phải kết luận nhu cầu toàn thị trường"])
            for item in analysis.quotes:
                lines.append(f"- {item.quote_id}: {markdown_text(item.quote)} — {evidence_links(item.evidence_ids, catalog)}.")
        lines.extend(["", "#### Giới hạn", "- Ý tưởng là đề xuất chưa kiểm chứng; liên kết nguồn không chứng minh sản phẩm chắc chắn bán được."])
        lines.extend("- " + LIMITATION_LABELS[key] for key in analysis.limitations)
        ideas = []
        for index, idea in enumerate(analysis.ideas, 1):
            ideas.extend([f"{index}. **Đề xuất chưa kiểm chứng: {markdown_text(idea.name)}**",
                f"- **Bán cái gì (thiết kế đề xuất)**: {markdown_text(idea.rationale)}",
                f"- **Cho ai (giả định)**: {markdown_text(idea.target_audience)}",
                f"- **Vì sao xem xét lúc này**: {markdown_text(idea.why_now)}",
                f"- **Dựa trên**: {evidence_links(idea.evidence_ids, catalog)}; facts {', '.join(idea.basis_fact_ids)}; quotes {', '.join(idea.basis_quote_ids) or 'không có'}.\n"])
        section.analysis_content = "\n".join(lines)
        section.ideas_content = "\n".join(ideas) if ideas else "AI không đề xuất sản phẩm; không tạo ý tưởng thay thế để đủ số lượng."
        section.ideas = list(analysis.ideas)
        section.reddit_pain_points = [RedditPainPoint(item.quote, item.evidence_ids) for item in analysis.quotes]
        section.grounded_analysis = analysis
        section.ai_validation = validation
        section.analysis_status = "success"
        section.generation_mode = "ollama"
        section.warnings = ["Fact/quote đã đối chiếu nguồn; thiết kế, đối tượng và market fit vẫn là đề xuất chưa kiểm chứng."]
        if catalog.omitted_for_context_count:
            section.warnings.append(f"Context AI dùng {len(catalog.records)}/{catalog.available_scoped_count} record đúng scope; {catalog.omitted_for_context_count} record không gửi do ngân sách. Dữ liệu gốc/ranking không bị cắt.")
        return section
