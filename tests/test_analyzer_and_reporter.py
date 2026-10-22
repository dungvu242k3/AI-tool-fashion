"""Verify truthful execution metadata and safe handling of unavailable AI."""
import pytest

from src.analyzers.llm_analyzer import LLMAnalyzer
from src.models.schemas import KeywordSignal, NicheData, ProductItem
from src.reporters.report_generator import ReportGenerator


@pytest.fixture
def evidence(qualified_data_factory):
    return qualified_data_factory(NicheData(
        niche_name="Fixture niche", collected_at="2026-10-21T00:00:00+07:00",
        keywords=[
            KeywordSignal("fixture one", score=50, trend="stable", source_url="https://trends.google.com/trends/explore?q=one"),
            KeywordSignal("fixture two", score=60, trend="rising", source_url="https://trends.google.com/trends/explore?q=two"),
        ],
        products=[ProductItem("Fixture product", price="$18.00", url="https://www.amazon.com/dp/B000000001")],
    ))


def test_no_llm_mode_renders_observations_only(evidence):
    section = LLMAnalyzer(fast_mode=True).analyze(evidence.niche_name, evidence)
    assert section.analysis_status == "not_requested"
    assert section.generation_mode == "deterministic"
    assert "fixture one" in section.keywords_content
    assert "$18.00" in section.analysis_content
    assert section.ideas == []


def test_ollama_failure_preserves_evidence_without_inventing_ideas(monkeypatch, evidence):
    from src.analyzers.ollama_client import GenerationError
    analyzer = LLMAnalyzer()
    def unavailable(*args, **kwargs):
        raise GenerationError("ollama_connection_error")
    monkeypatch.setattr(analyzer, "_call_ollama", unavailable)
    section = analyzer.analyze(evidence.niche_name, evidence)
    assert section.analysis_status == "failed"
    assert section.ideas == []
    assert "fixture one" in section.keywords_content
    assert section.warnings


@pytest.mark.parametrize("output", [
    "### 1. Keyword\nSome text\n### 2. Phân tích\nMissing ideas",
    "### 1. Keyword\nSome text\n### 2. Phân tích\nText\n### 3. Idea sản phẩm\n1. **Incomplete idea**",
])
def test_incomplete_llm_response_is_rejected(monkeypatch, evidence, output):
    analyzer = LLMAnalyzer()
    monkeypatch.setattr(analyzer, "_call_ollama", lambda *a, **kw: output)
    section = analyzer.analyze(evidence.niche_name, evidence)
    assert section.analysis_status == "invalid_output"
    assert section.generation_mode == "deterministic"
    assert not section.ideas


def test_valid_llm_output_records_actual_mode(monkeypatch, evidence, grounded_payload_factory):
    import json
    output = json.dumps(grounded_payload_factory(evidence))
    analyzer = LLMAnalyzer()
    monkeypatch.setattr(analyzer, "_call_ollama", lambda *a, **kw: output)
    section = analyzer.analyze(evidence.niche_name, evidence)
    assert section.generation_mode == "ollama"
    assert section.analysis_status == "success"
    assert len(section.ideas) == 2
    assert "50/100" in section.keywords_content


def test_summary_is_not_a_fixed_ranking():
    summary = LLMAnalyzer(fast_mode=True).summarize({})
    assert "Bảng xếp hạng" in summary
    assert "Top 3 Idea" in summary
    assert "9.5/10" not in summary


def test_report_generator_records_failure_and_actual_mode(research_result_factory):
    result = research_result_factory(state="partial")
    text = ReportGenerator().render(result)
    assert "### 1. Keyword\n" in text
    assert "### 2. Phân tích\n" in text
    assert "### 3. Idea sản phẩm\n" in text
    assert "| reddit | failed | 0 |" in text
    assert "BÁO CÁO CHƯA ĐẦY ĐỦ" in text
    assert "Chạy Local qua Ollama" not in text
    assert "Amazon Best Sellers" not in text


def test_report_names_do_not_collide(tmp_path, research_result_factory):
    from src.reporters.report_repository import ReportRepository
    repository = ReportRepository(tmp_path)
    first = repository.publish(research_result_factory())
    second = repository.publish(research_result_factory())
    assert first["report_filename"] != second["report_filename"]
