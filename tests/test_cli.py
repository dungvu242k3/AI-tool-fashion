from click.testing import CliRunner

from src import main as cli


def test_cli_partial_run_returns_nonzero_and_keeps_diagnostics(monkeypatch, tmp_path):
    result = {
        "success": False, "status": "partial", "report_filepath": str(tmp_path / "diagnostic.md"),
        "metadata": {"elapsed_seconds": 0.1, "data_quality": "insufficient", "warnings": ["Fixture source failed"]},
    }
    monkeypatch.setattr(cli, "execute_pipeline", lambda **kwargs: result)
    output = CliRunner().invoke(cli.main, ["--fast", "--output", str(tmp_path)])
    assert output.exit_code == 1
    assert "Fixture source failed" in output.output
    assert "100%" not in output.output


def test_cli_preserves_config_for_a_known_niche(monkeypatch, tmp_path):
    calls = []

    def pipeline(**kwargs):
        calls.append(kwargs)
        return {
            "success": True, "status": "success", "report_filepath": str(tmp_path / "fixture.md"),
            "metadata": {"elapsed_seconds": 0.1, "data_quality": "sufficient", "warnings": []},
        }

    monkeypatch.setattr(cli, "execute_pipeline", pipeline)
    output = CliRunner().invoke(cli.main, ["--niches", "Gift for Him", "--fast", "--output", str(tmp_path)])
    assert output.exit_code == 0
    assert calls[0]["niche_list"][0]["subreddits"]
    assert len(calls[0]["niche_list"][0]["seed_keywords"]) > 1
    assert calls[0]["fast_mode"] is True


def test_cli_rejects_empty_niche(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "execute_pipeline", lambda **kwargs: None)
    output = CliRunner().invoke(cli.main, ["--niches", "one,", "--output", str(tmp_path)])
    assert output.exit_code == 2
