"""Render observed facts when AI is disabled, unavailable or evidence is insufficient."""
from collections import Counter
from datetime import datetime, timezone

from src.models.schemas import NicheData, NicheReportSection
from src.models.commerce import SOURCE_LABELS
from src.processors.data_processor import DataProcessor
from src.reporters.text import markdown_text
from src.reporters.ranking_renderer import RankingRenderer


class EvidenceRenderer:
    @staticmethod
    def _text(value: str) -> str:
        """Treat source strings as text, never executable HTML or Markdown links."""
        return markdown_text(value)

    @staticmethod
    def keywords(data: NicheData) -> str:
        lines = []
        for keyword in data.keywords:
            score = f"{keyword.score:g}/100" if keyword.score is not None else "chưa có số đo"
            lines.append(
                f"- **{EvidenceRenderer._text(keyword.keyword)}**: {score}; {keyword.trend}. "
                f"{EvidenceRenderer._text(keyword.signal_summary)} [{EvidenceRenderer._text(keyword.source)}]({keyword.source_url})"
            )
            if keyword.metrics:
                metric = keyword.metrics
                growth = f"{metric.growth_percent:.2f}%" if metric.growth_percent is not None else "chưa xác định"
                lines.append(
                    f"  - Interest trung bình kỳ trước/gần đây: {metric.previous_mean:.2f}/{metric.recent_mean:.2f}; "
                    f"thay đổi: {growth}; slope: {metric.slope:.3f} điểm/ngày; "
                    f"volatility: {metric.volatility:.3f} điểm; {metric.window_points_used} điểm/cửa sổ."
                )
                lines.append(f"  - Cửa sổ: {metric.previous_start} → {metric.previous_end}; {metric.recent_start} → {metric.recent_end}.")
            if keyword.related_queries:
                lines.append(f"  - Truy vấn liên quan: {', '.join(map(EvidenceRenderer._text, keyword.related_queries))}")
            if keyword.suggestions:
                lines.append(f"  - Google Suggest (gợi ý truy vấn, không phải tín hiệu tăng trưởng): {', '.join(map(EvidenceRenderer._text, keyword.suggestions))}")
            if keyword.provenance and keyword.provenance.from_cache:
                lines.append(f"  - Dùng lại dữ liệu live từ cache; thời điểm thu thập gốc: {keyword.provenance.retrieved_at}.")
        return "\n".join(lines) or "Không thu thập được dữ liệu Google Trends hợp lệ."

    @staticmethod
    def section(data: NicheData, status: str, warnings=None) -> NicheReportSection:
        lines = []
        trends = Counter(keyword.trend for keyword in data.keywords)
        if trends:
            lines.append("- Nhãn xu hướng của các keyword đã đo: " + ", ".join(
                f"{label}: {count}" for label, count in sorted(trends.items())
            ) + ". Chưa kết luận nguyên nhân hoặc xu hướng chung của niche.")
        else:
            lines.append("- Xu hướng thị trường: chưa đủ dữ liệu để kết luận.")
        lines.append(f"- Khoảng giá theo currency từ mẫu Amazon: {DataProcessor.format_price_ranges(data.products)}")
        for product in data.products:
            details = []
            if product.price is not None:
                details.append(f"giá {EvidenceRenderer._text(product.price)}")
            if product.rating is not None:
                details.append(f"rating {product.rating:g}/5")
            if product.reviews_count is not None:
                details.append(f"{product.reviews_count} đánh giá")
            suffix = f" — {', '.join(details)}" if details else " — chưa có giá/rating/review"
            lines.append(f"- [{EvidenceRenderer._text(product.title)}]({product.url}) ({EvidenceRenderer._text(product.source)}){suffix}.")
            if product.asin:
                lines.append(f"  - ASIN: {product.asin}.")
            for listing in product.listings:
                label = SOURCE_LABELS[listing.source_type]
                rank = f"vị trí tìm kiếm {listing.search_position}" if listing.source_type == "search" else (
                    f"hạng trong danh sách {listing.listing_rank}" if listing.listing_rank is not None else "chưa có hạng được công bố"
                )
                ad = "; Sponsored" if listing.is_sponsored else ""
                lines.append(f"  - [{label}]({listing.listing_url}): {rank}{ad}; thu thập {listing.provenance.retrieved_at}; evidence {listing.provenance.evidence_id}.")
        for discussion in data.discussions:
            lines.append(f"- [{EvidenceRenderer._text(discussion.title)}]({discussion.url}) ({EvidenceRenderer._text(discussion.source)}).")
            details = [f"post ID {EvidenceRenderer._text(discussion.post_id or 'chưa có')}"]
            if discussion.provider:
                details.append(f"adapter {EvidenceRenderer._text(discussion.provider)}")
            if discussion.created_utc is not None:
                details.append("tạo " + datetime.fromtimestamp(discussion.created_utc, timezone.utc).isoformat())
            details.extend([f"điểm Reddit {discussion.score if discussion.score is not None else 'chưa có'}",
                            f"bình luận {discussion.comments if discussion.comments is not None else 'chưa có'}"])
            lines.append("  - " + "; ".join(details) + ".")
            if discussion.provenance:
                lines.append(f"  - Evidence {EvidenceRenderer._text(discussion.provenance.evidence_id)}; thu thập {EvidenceRenderer._text(discussion.provenance.retrieved_at)}.")
            if discussion.content_summary:
                lines.append(f"  - Trích đoạn nguyên văn (không phải summary/pain point): {EvidenceRenderer._text(discussion.content_summary)}")
        lines.append("- Pain point: chưa xác minh; không tạo tóm tắt nhu cầu từ bài thiếu nội dung hoặc suy rộng thành nhu cầu thị trường.")
        lines.append("- Chưa xác minh chân dung khách hàng, nguyên nhân xu hướng và mức cạnh tranh.")
        if status == "not_requested":
            ideas = "Chế độ tổng hợp dữ liệu: không gọi AI và không tạo ý tưởng sản phẩm."
        elif status == "insufficient_data":
            ideas = "Không đủ dữ liệu để khuyến nghị hoặc tạo ý tưởng sản phẩm."
        else:
            ideas = "Phân tích AI chưa thành công; chưa có ý tưởng sản phẩm được chấp nhận."
        return NicheReportSection(
            niche_name=data.niche_name,
            keywords_content=EvidenceRenderer.keywords(data),
            analysis_content="\n".join(lines), ideas_content=ideas,
            analysis_status=status, warnings=list(warnings or []),
        )

    @staticmethod
    def reddit_pain_points(points, discussions) -> str:
        evidence = {post.provenance.evidence_id: post for post in discussions if post.provenance}
        lines = ["#### Trích dẫn ứng viên pain point Reddit (cần đọc ngữ cảnh, không đại diện toàn thị trường)"]
        for point in points:
            links = ", ".join(f"[{EvidenceRenderer._text(key)}]({evidence[key].url})" for key in point.evidence_ids)
            lines.append(f"- {EvidenceRenderer._text(point.quote)} — evidence: {links}.")
        return "\n".join(lines) if points else "- Chưa có trích dẫn pain point Reddit được kiểm chứng với evidence."

    @staticmethod
    def summary(sections) -> str:
        # Compatibility for callers without a ranking result: never recompute.
        return RankingRenderer.summary(None, sections)
