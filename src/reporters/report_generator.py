"""
Report Generator.
Assembles the complete final Markdown report adhering to the strict mandatory structure in TASK-1.md.
"""
import os
import re
from datetime import datetime
from typing import Dict, Any, List

from src.models.schemas import NicheReportSection, NicheData
from src.config import REPORTS_DIR


class ReportGenerator:
    """Generates clean, standardized, beautifully formatted Markdown reports."""

    def __init__(self, output_dir: str = REPORTS_DIR):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(
        self,
        category: str,
        niches: List[Dict[str, Any]],
        analysis_results: Dict[str, NicheReportSection],
        summary: str,
        model_name: str,
        processed_data: Dict[str, NicheData] = None,
    ) -> str:
        """
        Generates and saves the Markdown report file.

        Returns:
            Absolute filepath of the saved report.
        """
        now = datetime.now()
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
        file_slug = now.strftime("%Y%m%d_%H%M%S")
        filename = f"report_trend_{file_slug}.md"
        filepath = os.path.join(self.output_dir, filename)

        lines: List[str] = []

        # =====================================================================
        # Header & Metadata
        # =====================================================================
        lines.append("# BÁO CÁO NGHIÊN CỨU XU HƯỚNG SẢN PHẨM (AI PRODUCT TREND REPORT)")
        lines.append("")
        lines.append(f"> **Thời gian tạo:** {timestamp_str}  ")
        lines.append(f"> **Danh mục:** {category}  ")
        lines.append(f"> **AI Model sử dụng:** `{model_name}` (Chạy Local qua Ollama)  ")
        lines.append(f"> **Chi phí API:** **$0.00 (Hoàn toàn miễn phí)**  ")
        lines.append(f"> **Nguồn dữ liệu:** Google Trends, Amazon Best Sellers & Movers, Reddit Communities  ")
        lines.append("")
        lines.append("---")
        lines.append("")

        # =====================================================================
        # Niches Sections (Mandatory Structure)
        # =====================================================================
        for idx, niche in enumerate(niches, start=1):
            niche_name = niche["name"]
            sec = analysis_results.get(niche_name)
            if not sec:
                continue

            lines.append(f"## {idx}. Niche: {niche_name}")
            lines.append("")

            # 1. Keyword
            lines.append("### 1. Keyword")
            lines.append(sec.keywords_content.strip())
            lines.append("")

            # 2. Phân tích
            lines.append("### 2. Phân tích")
            lines.append(sec.analysis_content.strip())
            lines.append("")

            # 3. Idea sản phẩm
            lines.append("### 3. Idea sản phẩm")
            lines.append(sec.ideas_content.strip())
            lines.append("")
            lines.append("---")
            lines.append("")

        # =====================================================================
        # Tổng kết (Mandatory Structure)
        # =====================================================================
        lines.append("## 🏆 TỔNG KẾT VÀ KHUYẾN NGHỊ ĐẦU TƯ")
        lines.append("")
        lines.append(summary.strip())
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("*Báo cáo được tạo tự động bởi AI Trend Research Tool MVP.*")

        content = "\n".join(lines)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return os.path.abspath(filepath)
