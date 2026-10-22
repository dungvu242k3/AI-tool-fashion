import json

from src.config import DATA_POLICY_VERSION
from src.reporters.report_repository import ReportRepository


def test_legacy_cache_cannot_enter_live_dashboard(tmp_path):
    (tmp_path / "latest_data.json").write_text(json.dumps({"success": True, "metadata": {}}))
    result = ReportRepository(tmp_path).load_latest()
    assert result["success"] is False
    assert result["status"] == "legacy"
    assert "metadata" not in result


def test_markdown_file_does_not_create_fake_metadata(tmp_path):
    (tmp_path / "report_trend_legacy.md").write_text("Legacy fixture")
    result = ReportRepository(tmp_path).load_latest()
    assert result["success"] is False
    assert result["status"] == "no_report"
    assert "metadata" not in result


def test_partial_cache_is_preserved_without_becoming_successful(tmp_path, research_result_factory):
    repository = ReportRepository(tmp_path)
    expected = repository.publish(research_result_factory(state="partial"))
    assert not expected["success"] and expected["status"] == "partial"
    assert repository.load_latest() == expected
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_cache_has_no_fallback(tmp_path):
    (tmp_path / "latest_data.json").write_text("{broken")
    result = ReportRepository(tmp_path).load_latest()
    assert result["status"] == "invalid_cache"
    assert "metadata" not in result


def test_report_listing_separates_unverified_legacy_files(tmp_path):
    (tmp_path / "report_trend_old.md").write_text("# Fixture legacy")
    (tmp_path / "report_trend_new.md").write_text(f"# Fixture\n<!-- data-policy: {DATA_POLICY_VERSION} -->")
    result = ReportRepository(tmp_path).list_reports()
    assert result["reports"] == ["report_trend_new.md"]
    assert result["legacy_reports"] == ["report_trend_old.md"]
