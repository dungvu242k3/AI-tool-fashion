"""Read-only rendering of the single canonical RankingResult JSON view."""
from src.reporters.text import markdown_text
from urllib.parse import quote
from collections.abc import Mapping


def _number(value):
    return "chưa có dữ liệu" if value is None else f"{value:.6f}"


class RankingRenderer:
    @staticmethod
    def summary(assessment: dict | None, sections=None, analysis_summary=None) -> str:
        lines = ["### 1. Bảng xếp hạng", ""]
        if assessment is None:
            lines.append("Chưa có kết quả từ RankingService; không tự tạo bảng xếp hạng.")
        else:
            lines.append(f"Method: {markdown_text(assessment['method'])}; policy: {markdown_text(assessment['policy_id'])}; trạng thái: {markdown_text(assessment['status'])}.")
            lines.extend(["", *("> " + markdown_text(note) for note in assessment["warnings"]), ""])
            ranked = assessment["ranking"]
            if ranked:
                lines.extend(["| Hạng | Niche | Đóng góp quan sát /100 | Tổng đủ 5 nhóm /100 | Cận trên /100 | Phủ trọng số | Confidence dữ liệu |",
                              "|---|---|---|---|---|---|---|"])
                for row in ranked:
                    confidence = "chưa xác định" if row["confidence"] is None else f"{row['confidence']:.6f}%"
                    lines.append(f"| {row['rank']} | {markdown_text(row['niche'])} | {_number(row['observed_score'])} | {_number(row['total_score'])} | {_number(row['score_upper_bound'])} | {row['component_coverage']:.1%} | {confidence} |")
            else:
                lines.append("Chưa có niche đủ điều kiện xếp hạng; xem lý do và breakdown bên dưới.")
            for row in [*ranked, *assessment["unranked"]]:
                lines.extend(["", f"#### {markdown_text(row['niche'])} — {markdown_text(row['status'])}", "",
                              markdown_text(row["explanation"]), "",
                              "| Component | Trọng số cố định | Điểm /100 | Contribution | Mẫu dùng/candidate | Trạng thái / lý do |",
                              "|---|---|---|---|---|---|"])
                for component in row["components"]:
                    lines.append(f"| {markdown_text(component['label'])} | {component['weight']:.1%} | {_number(component['score'])} | {_number(component['contribution'])} | {component['sample_size']}/{component['candidate_count']} | {markdown_text(component['status'])} / {markdown_text(component['reason'])} |")
                for component in row["components"]:
                    lines.extend(["", f"- {markdown_text(component['key'])}: {markdown_text(component['formula'])}."])
                    for item in component["inputs"]:
                        measures = "; ".join(f"{key}={value}" for key, value in item["measurements"].items())
                        url = quote(item["source_url"], safe=":/?&=%#@+-,._~")
                        lines.append(f"  - Evidence [{markdown_text(item['evidence_id'])}]({url}): {markdown_text(item['identity'])}; {markdown_text(measures)}; thu thập {markdown_text(item['retrieved_at'])}; request {markdown_text(item['request_id'])}{'; cache giữ timestamp gốc' if item['from_cache'] else ''}.")
        lines.extend(["", "### 2. Top 3 Idea", ""])
        if analysis_summary is not None:
            lines.extend("> " + markdown_text(note) for note in analysis_summary["warnings"])
            for item in analysis_summary["top_ideas"]:
                links = ", ".join(f"[{markdown_text(link['evidence_id'])}]({quote(link['url'], safe=':/?&=%#@+-,._~')})" for link in item["source_links"])
                lines.extend(["", f"{item['selection_position']}. **Đề xuất chưa kiểm chứng: {markdown_text(item['title'])}** — {markdown_text(item['niche'])}",
                    f"   - Bán cái gì: {markdown_text(item['what_to_sell'])}",
                    f"   - Đối tượng giả định: {markdown_text(item['target_audience'])}",
                    f"   - Cơ sở quan sát: {markdown_text(item['why_now'])}", f"   - Evidence: {links}."])
        if analysis_summary is None or not analysis_summary["top_ideas"]:
            lines.append("Chưa có đề xuất đã kiểm tra evidence từ niche đủ điều kiện xếp hạng; không tự tạo Top 3.")
        for name, section in (sections or {}).items():
            status = section["analysis_status"] if isinstance(section, Mapping) else section.analysis_status
            mode = section["generation_mode"] if isinstance(section, Mapping) else section.generation_mode
            if status == "insufficient_data":
                lines.append(f"- {markdown_text(name)}: Dữ liệu chưa đủ; không xếp hạng hoặc khuyến nghị.")
            else:
                lines.append(f"- {markdown_text(name)}: chế độ {markdown_text(mode)}; phân tích {markdown_text(status)}.")
        return "\n".join(lines)
