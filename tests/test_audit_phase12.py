"""Phase-12 audit contracts on explicit isolated fixtures, never market reports."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path

import pytest

from src.models.research_result import ResearchResult
from src.models.schemas import ProductItem
from src.reporters.report_repository import ReportRepository
from src.reporters.result_codec import canonical_json, read_document
from src.verification.collection_codec import restore_collection
from src.verification.contracts import AuditFailure
from src.verification.numeric_inventory import markdown_numbers, numeric_spans, pointer, structured_numbers
from src.verification.publication_audit import audit_publication


@pytest.fixture
def document_factory(tmp_path, research_result_factory):
    def create(**options):
        research = research_result_factory(**options)
        publication = read_document(tmp_path / "latest_data.json")
        return publication, tmp_path, research.metadata["run_id"]
    return create


def audit(document):
    _, root, run_id = document
    return audit_publication(root / "latest_data.json", root, run_id)


def reseal(document):
    """Test-only malicious local writer: update checksum/Markdown, not source input."""
    publication, root, _ = document
    return ReportRepository(root).publish(ResearchResult.from_dict(publication))


@pytest.mark.parametrize("state", ["complete", "partial", "failed", "insufficient"])
def test_complete_audit_reconstructs_all_views_across_quality_states(document_factory, state):
    document = document_factory(state=state)
    publication, root, _ = document
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    report = audit(document)
    assert report["status"] == "consistent_with_collector_snapshots"
    assert report["network_requests"] == report["model_calls"] == 0
    assert report["research_status"] == publication["status"]
    assert report["structured_numeric_fields"]
    inventory = report["markdown_numeric_inventory"]
    assert len(inventory["occurrences"]) == sum(inventory["counts"].values())
    assert len(inventory["occurrences"]) == len(list(numeric_spans(publication["markdown_content"])))
    assert before == {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_cached_and_multi_niche_sources_preserve_original_context(document_factory):
    document = document_factory(names=("Bravo", "Alpha"), cached=True)
    report = audit(document)
    assert [item["niche"] for item in report["sources"]][::3] == ["Bravo", "Alpha"]
    assert report["research_status"] == "success"
    assert all(item["json_pointer"].startswith("/niches/") for item in report["sources"])


@pytest.mark.parametrize("injection", ["9999% growth", "one million buyers", "９９％", "½ market share", "60/100"])
def test_rehashed_fabricated_prose_is_rejected_even_if_number_exists_elsewhere(document_factory, injection):
    document = document_factory()
    document[0]["niches"]["Fixture"]["analysis_text"] += "\n- " + injection
    reseal(document)
    with pytest.raises(AuditFailure) as error:
        audit(document)
    assert error.value.code == "rendered_section_not_source_bound"


@pytest.mark.parametrize("field", ["keywords_content", "ideas_content"])
def test_other_rendered_sections_cannot_smuggle_metrics(document_factory, field):
    document = document_factory()
    document[0]["niches"]["Fixture"][field] += "\n999999"
    reseal(document)
    with pytest.raises(AuditFailure, match="rendered_section_not_source_bound"):
        audit(document)


def test_rehashed_wrong_ranking_is_not_just_compared_with_its_own_markdown(document_factory):
    document = document_factory()
    row = document[0]["ranking_assessment"]["ranking"][0]
    row["observed_score"] += 0.123456
    reseal(document)
    with pytest.raises(AuditFailure, match="ranking_recompute_mismatch"):
        audit(document)


def test_unknown_ranking_policy_fields_fail_closed(document_factory):
    document = document_factory()
    document[0]["ranking_assessment"]["policy"]["eval"] = "no execution"
    reseal(document)
    with pytest.raises(AuditFailure, match="ranking_policy_fields"):
        audit(document)


@pytest.mark.parametrize("kind", ["price-table", "price-text", "request-elapsed"])
def test_rehashed_metadata_and_price_views_still_require_snapshot_correspondence(document_factory, kind):
    document = document_factory()
    if kind == "price-table":
        document[0]["niches"]["Fixture"]["price_ranges"] = [{"currency": "USD", "avg": "99.00", "formatted": "USD 99.00"}]
        code = "price_range_mismatch"
    elif kind == "price-text":
        document[0]["niches"]["Fixture"]["price_range"] = "USD 9999.00"
        code = "price_range_text_mismatch"
    else:
        next(iter(document[0]["request_metadata"].values()))["elapsed_ms"] = 999
        code = "request_journal_mismatch"
    reseal(document)
    with pytest.raises(AuditFailure, match=code):
        audit(document)


def test_actual_markdown_file_is_audited_not_only_embedded_text(document_factory):
    document = document_factory()
    Path(document[0]["report_filepath"]).write_text("9999% unsupported", encoding="utf-8")
    with pytest.raises(AuditFailure, match="markdown_file_mismatch"):
        audit(document)


def test_invalid_cache_is_never_repaired_or_replaced_by_audit(document_factory):
    document = document_factory()
    target = document[1] / "latest_data.json"
    target.write_bytes(b'{"schema_version":')
    with pytest.raises(AuditFailure, match="invalid_or_unreadable_audit_input"):
        audit(document)
    assert target.read_bytes() == b'{"schema_version":'


def test_snapshot_run_mismatch_is_not_silently_accepted_for_live_publication(document_factory):
    document = document_factory()
    with pytest.raises(AuditFailure, match="snapshot_run_mismatch"):
        audit_publication(document[1] / "latest_data.json", document[1], "a" * 32)


def test_metadata_warning_numbers_are_not_certified_as_market_metrics(document_factory):
    document = document_factory()
    document[0]["metadata"]["warnings"].append("Unverified operator note 9999")
    reseal(document)
    report = audit(document)
    rows = [item for item in report["markdown_numeric_inventory"]["occurrences"] if item["token"] == "9999"]
    assert rows and all(item["classification"] == "metadata_input_warning_identifier_or_template" for item in rows)
    assert all(not item["section_references"] for item in rows)
    assert any("not a semantic proof" in note for note in report["limitations"])


def test_numeric_ledger_keeps_exact_unicode_spelling_offsets_and_not_bool_values():
    text = "Header 2026\nobserved １２.５% and ½; unknown 99\n"
    block = {"text": "observed １２.５% and ½", "reference": "/niches/A~1B/analysis_text"}
    ledger = markdown_numbers(text, [block])
    assert [row["token"] for row in ledger["occurrences"]] == ["2026", "１２.５%", "½", "99"]
    assert ledger["occurrences"][1]["line"] == 2 and ledger["occurrences"][1]["column"] == 10
    assert ledger["occurrences"][1]["section_references"] == [block["reference"]]
    assert not ledger["occurrences"][-1]["section_references"]
    numbers = structured_numbers({"value": 0, "unknown": None, "bool": False})
    assert [item["value"] for item in numbers] == [0]
    assert pointer("niches", "A/B~C", "score") == "/niches/A~1B~0C/score"


def test_numeric_inventory_budget_is_enforced_before_unbounded_output(monkeypatch):
    monkeypatch.setattr("src.verification.numeric_inventory.MAX_TOKENS", 2)
    with pytest.raises(AuditFailure, match="numeric_token_budget"):
        markdown_numbers("1 2 3", [])
    monkeypatch.setattr("src.verification.numeric_inventory.MAX_NUMERIC_FIELDS", 1)
    with pytest.raises(AuditFailure, match="numeric_field_budget"):
        structured_numbers({"one": 1, "two": 2})


@pytest.fixture
def raw_collection(collection_factory):
    from src.collectors.validation import validate_collection_result
    result = validate_collection_result("amazon", collection_factory("amazon", [
        ProductItem("Fixture", url="https://www.amazon.com/dp/B000000001")]))
    return json.loads(canonical_json(asdict(result)))


@pytest.mark.parametrize("kind", ["unknown-field", "missing-field", "raw-secret", "bad-source", "bad-asin", "bool-count", "wrong-retained",
                                 "duplicate-trace", "unsafe-url", "oversize-records", "unbalanced-rejections"])
def test_closed_snapshot_codec_rejects_schema_provenance_and_count_abuse(raw_collection, kind):
    raw = deepcopy(raw_collection)
    if kind == "unknown-field": raw["execute"] = "never"
    elif kind == "missing-field": raw["records"][0].pop("rating")
    elif kind == "raw-secret": raw["records"][0]["cookie"] = "fixture-private-cookie"
    elif kind == "bad-source": raw["source"] = "https://attacker.test"
    elif kind == "bad-asin": raw["records"][0]["asin"] = "INVALID"
    elif kind == "bool-count": raw["validation"]["candidate_count"] = True
    elif kind == "wrong-retained": raw["validation"]["retained_count"] = 99
    elif kind == "duplicate-trace": raw["request_metadata"].append(deepcopy(raw["request_metadata"][0]))
    elif kind == "unsafe-url": raw["request_metadata"][0]["url"] = "https://www.amazon.com/s?token=fixture-private-secret"
    elif kind == "oversize-records": raw["records"] *= 1001
    else: raw["validation"]["rejection_counts"] = [["invalid_schema", 1]]
    with pytest.raises(AuditFailure):
        restore_collection(raw)


def test_codec_retains_rejected_candidate_counts_without_inventing_rejected_records(raw_collection):
    raw = deepcopy(raw_collection)
    raw["status"] = "partial"
    raw["warnings"] = [{"code": "invalid_schema", "message": "Fixture rejected candidate", "request_id": None,
                        "operation": None, "retryable": False}]
    raw["validation"].update(candidate_count=2, rejected_count=1, rejection_counts=[["invalid_schema", 1]])
    result = restore_collection(raw)
    assert result.validation.candidate_count == 2 and result.validation.retained_count == len(result.records) == 1
    assert result.validation.rejected_count == 1


def test_codec_owns_nested_data_and_does_not_mutate_snapshot(raw_collection):
    original = deepcopy(raw_collection)
    result = restore_collection(raw_collection)
    result.records[0].provenance.query["caller"] = "mutation"
    assert raw_collection == original


def test_grounded_ollama_publication_is_revalidated_without_another_generation(
        tmp_path, research_result_factory, grounded_payload_factory, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from src.analyzers.llm_analyzer import LLMAnalyzer
    client = SimpleNamespace(generate=Mock(side_effect=lambda model, prompt, system: json.dumps(
        grounded_payload_factory(prompt=prompt))), close=Mock())
    monkeypatch.setattr("src.pipeline.LLMAnalyzer", lambda **options: LLMAnalyzer(generation_client=client, **options))
    research = research_result_factory(fast_mode=False)
    assert research.metadata["mode"] == "ollama"
    before = client.generate.call_count
    result = audit_publication(tmp_path / "latest_data.json", tmp_path, research.metadata["run_id"])
    assert result["status"] == "consistent_with_collector_snapshots"
    assert client.generate.call_count == before == 1


def test_audit_cli_failure_is_persisted_without_claiming_pass(tmp_path):
    from scripts.audit_publication_phase12 import audit as command
    result = command(tmp_path / "missing.json", tmp_path, "a" * 32, tmp_path / "audit")
    assert result["status"] == "failed" and result["error_code"] == "invalid_or_unreadable_audit_input"
    saved = read_document(Path(result["audit_file"]))
    assert saved["status"] == "failed" and saved["network_requests"] == saved["model_calls"] == 0
