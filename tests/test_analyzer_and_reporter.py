"""
Unit tests for LLMAnalyzer fallbacks and ReportGenerator Markdown output formatting.
"""
import os
import pytest
from src.analyzers.llm_analyzer import LLMAnalyzer
from src.reporters.report_generator import ReportGenerator
from src.models.schemas import NicheData, KeywordSignal, ProductItem, DiscussionItem, NicheReportSection


def test_analyzer_fallback_sections():
    analyzer = LLMAnalyzer(model="test-model")
    niche_data = NicheData(
        niche_name="Christmas Gift Ideas",
        collected_at="2026-10-20",
        keywords=[KeywordSignal(keyword="personalized ornament", trend="rising", score=90.0, source_url="https://trends.google.com")],
        products=[ProductItem(title="Family Ornament 2026", price="$18.99")],
        discussions=[DiscussionItem(title="Best gifts?", score=300)],
    )

    sec = analyzer.analyze("Christmas Gift Ideas", niche_data)
    assert sec.niche_name == "Christmas Gift Ideas"
    assert "personalized ornament" in sec.keywords_content
    assert "Xu hướng thị trường" in sec.analysis_content
    assert "Bán cái gì" in sec.ideas_content


def test_analyzer_summarize():
    analyzer = LLMAnalyzer(model="test-model")
    niche_results = {
        "Christmas Gift Ideas": NicheReportSection(
            niche_name="Christmas Gift Ideas",
            keywords_content="Keywords test",
            analysis_content="Analysis test",
            ideas_content="Ideas test",
        )
    }
    summary = analyzer.summarize(niche_results)
    assert "Bảng xếp hạng" in summary
    assert "Top 3 Idea" in summary


def test_report_generator(tmp_path):
    reporter = ReportGenerator(output_dir=str(tmp_path))
    category = "Quà tặng theo mùa (Seasonal Gifts)"
    niches = [{"name": "Christmas Gift Ideas"}]

    analysis_results = {
        "Christmas Gift Ideas": NicheReportSection(
            niche_name="Christmas Gift Ideas",
            keywords_content="- `christmas gift ideas`: Score 95/100 [Link](https://trends.google.com)",
            analysis_content="Niche đang tăng mạnh mùa Q4.",
            ideas_content="1. **Hộp Quà Cozy Winter**\n- Bán cái gì: Combo chăn và nến\n- Cho ai: Người thân\n- Vì sao: Đang mùa đông\n- Dựa trên: Trends",
        )
    }
    summary = "### 1. Bảng xếp hạng\nTop 1: Christmas\n### 2. Top 3 ideas\n1. Cozy Winter"

    file_path = reporter.generate(
        category=category,
        niches=niches,
        analysis_results=analysis_results,
        summary=summary,
        model_name="local-bench-qwen35-2b-q4km:latest",
    )

    assert os.path.exists(file_path)

    # Check contents strictly meet TASK-1.md requirements
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "BÁO CÁO NGHIÊN CỨU XU HƯỚNG SẢN PHẨM" in content
    assert "1. Niche: Christmas Gift Ideas" in content
    assert "### 1. Keyword" in content
    assert "### 2. Phân tích" in content
    assert "### 3. Idea sản phẩm" in content
    assert "TỔNG KẾT VÀ KHUYẾN NGHỊ ĐẦU TƯ" in content
    assert "$0.00" in content
