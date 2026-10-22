"""Final-source coverage batch: NEW cases only, never rerun earlier passing cases."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.models.research_result import ResearchResult, thaw_json
from src.pipeline import execute_pipeline
from src.reporters.collection_snapshots import read_collection_snapshots
from src.reporters.report_repository import ReportRepository
from src.reporters.result_codec import canonical_json, document_digest, read_document
from src.verification.collection_codec import restore_collection, restore_record
from src.verification.contracts import AuditFailure
from src.verification.publication_audit import audit_publication


def reseal(root, publication):
    return ReportRepository(root).publish(ResearchResult.from_dict(publication))


def collectors_from(research, collection_factory, *, prices=False):
    niche = next(iter(thaw_json(research.niches).values()))
    sources = {}
    for source, field in (("google_trends", "keywords"), ("amazon", "products"), ("reddit", "discussions")):
        records = [restore_record(source, {key: value for key, value in raw.items() if key not in {"raw_metric", "derived_metric"}})
                   for raw in niche[field]]
        if prices and source == "amazon":
            records = [replace(record, price=price) for record, price in zip(records, ("USD 10.00", "USD 20.00", "VND 270000", None, None))]
        sources[source] = SimpleNamespace(collect=lambda query, s=source, items=records: collection_factory(s, items))
    return sources


def test_valid_but_different_source_measurement_cannot_match_a_rehashed_snapshot(tmp_path, research_result_factory):
    research = research_result_factory()
    directory = tmp_path / "snapshots" / research.metadata["run_id"]
    manifest_path = directory / "manifest.json"
    manifest = read_document(manifest_path)
    entry = next(item for item in manifest["entries"] if item["source"] == "amazon")
    path = directory / entry["filename"]
    document = read_document(path)
    document["collection"]["records"][0]["rating"] = 3.5
    body = canonical_json(document).encode("utf-8")
    manifest["total_bytes"] += len(body) - entry["bytes"]
    entry.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    path.write_bytes(body)
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    with pytest.raises(AuditFailure, match="record_snapshot_mismatch"):
        audit_publication(tmp_path / "latest_data.json", tmp_path, research.metadata["run_id"])


def test_forged_quality_issue_is_not_accepted_as_a_numeric_source_statement(tmp_path, research_result_factory):
    research = research_result_factory()
    publication = read_document(tmp_path / "latest_data.json")
    quality = publication["niches"]["Fixture"]["quality_assessment"]
    quality["issues"].append({"code": "operator_claim", "message": "9999 independently verified buyers"})
    publication["metadata"]["quality_assessments"]["Fixture"] = deepcopy(quality)
    reseal(tmp_path, publication)
    with pytest.raises(AuditFailure, match="quality_recompute_mismatch"):
        audit_publication(tmp_path / "latest_data.json", tmp_path, research.metadata["run_id"])


def test_currency_separated_audit_has_an_independent_exact_mean_oracle(tmp_path, research_result_factory, collection_factory):
    original = research_result_factory()
    result = execute_pipeline(fast_mode=True, niche_list=[{"name": "Fixture"}],
        collectors=collectors_from(original, collection_factory, prices=True), output_dir=tmp_path)
    prices = {row["currency"]: row for row in result["niches"]["Fixture"]["price_ranges"]}
    assert prices["USD"]["min"] == "10.00" and prices["USD"]["max"] == "20.00"
    assert prices["USD"]["avg"] == "15.00" and prices["USD"]["sample_size"] == 2
    assert prices["VND"]["avg"] == "270000.00" and prices["VND"]["sample_size"] == 1
    report = audit_publication(tmp_path / "latest_data.json", tmp_path, result["metadata"]["run_id"])
    assert report["status"] == "consistent_with_collector_snapshots"
    assert report["network_requests"] == report["model_calls"] == 0


def test_unbounded_saved_ai_policy_is_not_trusted_during_offline_verification(
        tmp_path, research_result_factory, grounded_payload_factory, monkeypatch):
    from src.analyzers.llm_analyzer import LLMAnalyzer
    client = SimpleNamespace(generate=Mock(side_effect=lambda model, prompt, system: json.dumps(
        grounded_payload_factory(prompt=prompt))), close=Mock())
    monkeypatch.setattr("src.pipeline.LLMAnalyzer", lambda **options: LLMAnalyzer(generation_client=client, **options))
    research = research_result_factory(fast_mode=False)
    publication = read_document(tmp_path / "latest_data.json")
    journal = publication["niches"]["Fixture"]["ai_validation"]
    journal["policy"]["max_prompt_bytes"] = 999999999
    publication["metadata"]["ai_validation"]["Fixture"] = deepcopy(journal)
    reseal(tmp_path, publication)
    with pytest.raises(AuditFailure, match="invalid_or_unreadable_audit_input"):
        audit_publication(tmp_path / "latest_data.json", tmp_path, research.metadata["run_id"])
    assert client.generate.call_count == 1


def test_actual_markdown_symlink_cannot_escape_the_publication_directory(tmp_path, research_result_factory):
    research = research_result_factory()
    publication = read_document(tmp_path / "latest_data.json")
    path = Path(publication["report_filepath"])
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "fixture-private.md"
    target.write_text("Fixture private data", encoding="utf-8")
    # Recoverable, test-only move inside tmp_path; never touch user artifacts.
    path.rename(tmp_path / "original-fixture-report.md")
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("OS cannot create symlinks; no simulated symlink fallback")
    publication["report_filepath"] = str(target.resolve())
    publication["document_sha256"] = document_digest(publication)
    (tmp_path / "latest_data.json").write_text(canonical_json(publication), encoding="utf-8")
    with pytest.raises(AuditFailure) as error:
        audit_publication(tmp_path / "latest_data.json", tmp_path, research.metadata["run_id"])
    # The canonical path guard may reject first (platform-dependent resolution);
    # both boundaries must fail closed, never read/certify the linked content.
    assert error.value.code in {"markdown_path_escape", "invalid_or_unreadable_audit_input"}
    assert target.read_text(encoding="utf-8") == "Fixture private data"


def test_unknown_validation_counts_after_collector_crash_stay_unknown(tmp_path, research_result_factory, collection_factory):
    original = research_result_factory()
    sources = collectors_from(original, collection_factory)
    sources["amazon"] = SimpleNamespace(collect=Mock(side_effect=RuntimeError("Fixture private failure")))
    result = execute_pipeline(fast_mode=True, niche_list=[{"name": "Fixture"}], collectors=sources, output_dir=tmp_path)
    state = result["source_statuses"]["Fixture"]["amazon"]
    assert state["validation"] is None and state["status"] == "failed"
    documents = read_collection_snapshots(tmp_path, result["metadata"]["run_id"])
    amazon = next(item for item in documents if item["source"] == "amazon")
    assert restore_collection(amazon["collection"]).validation is None
    report = audit_publication(tmp_path / "latest_data.json", tmp_path, result["metadata"]["run_id"])
    assert report["status"] == "consistent_with_collector_snapshots"


def test_retry_count_is_recomputed_from_request_journal_not_operator_metadata(tmp_path, research_result_factory):
    research = research_result_factory()
    publication = read_document(tmp_path / "latest_data.json")
    publication["metadata"]["source_health"]["amazon"]["retry_count"] = 9999
    reseal(tmp_path, publication)
    with pytest.raises(AuditFailure, match="health_recompute_mismatch"):
        audit_publication(tmp_path / "latest_data.json", tmp_path, research.metadata["run_id"])
