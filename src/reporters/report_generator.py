"""Pure Markdown view of ResearchResult; no clocks, scoring or persistence."""
from src.models.research_result import ResearchResult
from src.reporters.text import markdown_text, markdown_link
from src.reporters.ranking_renderer import RankingRenderer


class ReportGenerator:
    def render(self, result: ResearchResult) -> str:
        if not isinstance(result, ResearchResult):
            raise TypeError("ReportGenerator requires a canonical ResearchResult")
        metadata = result.metadata
        lines = [
            "# BÁO CÁO NGHIÊN CỨU XU HƯỚNG SẢN PHẨM",
            f"<!-- data-policy: {metadata['data_policy']} -->",
            f"<!-- result-schema: {result.schema_version} -->", "",
        ]
        if metadata["status"] != "success":
            lines.extend(["> [!WARNING]", "> **BÁO CÁO CHƯA ĐẦY ĐỦ — không đủ cơ sở xác nhận toàn bộ khuyến nghị.**", ""])
        for label, key in (("Run ID", "run_id"), ("Thời gian tạo", "timestamp"), ("Loại lần chạy", "execution_kind"), ("Danh mục", "category"),
                           ("Trạng thái", "status"), ("Chất lượng dữ liệu", "data_quality"),
                           ("Chế độ yêu cầu", "requested_mode"), ("Chế độ thực tế", "mode"), ("Chi phí API", "cost")):
            lines.append(f"> **{label}:** {markdown_text(metadata[key])}  ")
        used = metadata["model_name"] or "không có; chỉ tổng hợp dữ liệu thu thập."
        lines.append(f"> **Model có đầu ra được sử dụng:** {markdown_text(used)}  ")
        if metadata["model_attempted"]:
            lines.append(f"> **Model đã thử gọi:** {markdown_text(metadata['model_attempted'])}  ")
        lines.append(f"> **Nhật ký thu thập:** [{metadata['run_id']}]({metadata['diagnostics_file']})  ")
        lines.extend(["", *(f"> Lưu ý: {markdown_text(w)}" for w in metadata["warnings"]), ""])
        intent = metadata.get("research_input")
        if intent is not None:
            lines.extend(["## Thông số nghiên cứu được yêu cầu", "",
                          f"- Geo Trends: {markdown_text(intent['geo'] or 'toàn cầu')}; timeframe Trends: {markdown_text(intent['timeframe'])}.",
                          "- Amazon: marketplace US, tối đa hai seed đầu mỗi niche. Reddit: cửa sổ riêng theo cấu hình server.",
                          "- Đây là input truy vấn, không phải kết quả thu thập hoặc bằng chứng về thị trường.", "",
                          "| Niche | Seed keywords yêu cầu | Subreddits cấu hình |", "|---|---|---|"])
            for niche in intent["niches"]:
                lines.append(f"| {markdown_text(niche['name'])} | {markdown_text('; '.join(niche['seed_keywords']))} | {markdown_text(', '.join(niche['subreddits']) or 'chưa cấu hình')} |")
            lines.append("")
        lines.extend(self._sources(result))
        lines.extend(self._quality(result))
        lines.extend(["", "---", ""])
        sufficient, insufficient = [], []
        for index, (name, niche) in enumerate(result.niches.items(), 1):
            assessment = niche["quality_assessment"]
            blocked = niche["analysis_status"] == "insufficient_data" or (
                assessment["gate_passed"] is not True or assessment["status"] not in {"sufficient", "partial"})
            (insufficient if blocked else sufficient).append((index, name, niche))
        for index, name, niche in sufficient:
            lines.extend([
                f"## {index}. Niche: {markdown_text(name)}", "",
                f"> Phân tích: {markdown_text(niche['analysis_status'])}; chế độ: {markdown_text(niche['generation_mode'])}.", "",
                "### 1. Keyword", niche["keywords_content"].strip(), "",
                "### 2. Phân tích", niche["analysis_text"].strip(), "",
                "### 3. Idea sản phẩm", niche["ideas_content"].strip(), "", "---", "",
            ])
        if insufficient:
            lines.extend(["## Dữ liệu chưa đủ", "", "> Các niche dưới đây chỉ có dữ kiện chẩn đoán; không đủ cơ sở khuyến nghị.", ""])
            for index, name, niche in insufficient:
                accepted = niche["analysis_status"] == "insufficient_data"
                keywords = niche["keywords_content"].strip() if accepted else "Phân tích không khớp gate; không có nội dung được chấp nhận."
                observations = niche["analysis_text"].strip() if accepted else "Cần đánh giá lại từ evidence đã validation."
                lines.extend([f"### {index}. Niche: {markdown_text(name)}", "",
                              "#### Keyword đã thu thập", keywords, "",
                              "#### Quan sát và giới hạn dữ liệu", observations, "",
                              "Không tạo ý tưởng/khuyến nghị cho niche chưa qua quality gate.", "", "---", ""])
        lines.extend(["## TỔNG KẾT", "", RankingRenderer.summary(
            result.ranking_assessment, result.niches, result.analysis_summary).strip(), ""])
        lines.extend(self._evidence(result))
        return "\n".join(lines)

    @staticmethod
    def _sources(result):
        lines = ["## Tình trạng nguồn dữ liệu", "", "| Niche | Nguồn | Trạng thái | Bản ghi |",
                 "|---|---|---|---|"]
        for name, sources in result.source_statuses.items():
            for source, state in sources.items():
                lines.append(f"| {markdown_text(name)} | {markdown_text(source)} | {markdown_text(state['status'])} | {state['record_count']} |")
        heading = ("### Tình trạng nguồn tại lần thu thập gốc — không phải request trong audit"
                   if result.metadata["execution_kind"] == "offline_publication_audit" else "### Tình trạng nguồn toàn lần chạy")
        lines.extend(["", heading, "",
                      "| Nguồn | Trạng thái | Request mới | Retry | Bản ghi từ cache | Bản ghi thu thập |",
                      "|---|---|---|---|---|---|"])
        for source, health in result.metadata["source_health"].items():
            lines.append(f"| {markdown_text(source)} | {markdown_text(health['status'])} | {health['request_count']} | {health['retry_count']} | {health['cached_record_count']} | {health['record_count']} |")
        return lines

    @staticmethod
    def _quality(result):
        lines = ["", "## Validation và điều kiện dữ liệu", "",
                 "| Niche | Chất lượng | Keyword có series | Evidence bổ sung | Candidate hợp lệ | Phủ nguồn cấu hình |",
                 "|---|---|---|---|---|---|"]
        for name, assessment in result.metadata["quality_assessments"].items():
            ratio = assessment["valid_ratio"]
            valid = f"{assessment['valid_count']}/{assessment['candidate_count']} ({ratio:.1%})" if ratio is not None else "chưa xác định"
            lines.append(f"| {markdown_text(name)} | {markdown_text(assessment['status'])} | {assessment['qualifying_keyword_count']} | {assessment['supporting_record_count']} | {valid} | {assessment['observed_source_count']}/{assessment['configured_source_count']} |")
            lines.extend(f"> {markdown_text(name)}: {markdown_text(issue['message'])}" for issue in assessment["issues"])
        return lines

    @staticmethod
    def _evidence(result):
        lines = ["## Phụ lục evidence", "",
                 "Timestamp dưới đây là thời điểm thu thập gốc, không phải thời điểm mở báo cáo. Cache không làm mới timestamp.",
                 "URL/ID xác định nguồn quan sát, không chứng minh nội dung nguồn đúng hoặc sản phẩm phù hợp thị trường.", "",
                 "| Niche | Evidence | Nguồn | URL | Thu thập lúc | Request gốc | Dependencies | Từ cache |",
                 "|---|---|---|---|---|---|---|---|"]
        for item in result.evidence:
            dependencies = ", ".join(item["request_ids"])
            lines.append(f"| {markdown_text(item['niche'])} | {markdown_text(item['evidence_id'])} | {markdown_text(item['source'])} | "
                         f"{markdown_link('Nguồn', item['source_url'])} | {markdown_text(item['retrieved_at'])} | "
                         f"{markdown_text(item['request_id'])} | {markdown_text(dependencies)} | {'có' if item['from_cache'] else 'không'} |")
        if not result.evidence:
            lines.append("Chưa có evidence hợp lệ; không tạo URL hoặc timestamp thay thế.")
        lines.append("")
        return lines
