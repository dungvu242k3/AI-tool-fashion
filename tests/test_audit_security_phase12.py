"""Adversarial audit boundaries; fixture-only mutations, never provider requests."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.processors.data_processor import DataProcessor
from src.processors.data_quality import assess_data_quality
from src.reporters.collection_snapshots import read_collection_snapshots
from src.reporters.result_codec import canonical_json, read_document
from src.verification.collection_codec import restore_collection
from src.verification.contracts import AuditFailure
from src.verification.numeric_inventory import markdown_numbers, numeric_spans
from src.verification.publication_audit import audit_publication
from src.verification.section_audit import rebuild_section


@pytest.mark.parametrize("kind", ["fact-value", "quote", "proposal", "context"])
def test_reauditing_grounded_text_rejects_tampering_without_new_generation(
        kind, tmp_path, research_result_factory, grounded_payload_factory, monkeypatch):
    from src.analyzers.llm_analyzer import LLMAnalyzer
    client = SimpleNamespace(generate=Mock(side_effect=lambda model, prompt, system: json.dumps(
        grounded_payload_factory(prompt=prompt))), close=Mock())
    monkeypatch.setattr("src.pipeline.LLMAnalyzer", lambda **options: LLMAnalyzer(generation_client=client, **options))
    research = research_result_factory(fast_mode=False)
    publication = read_document(tmp_path / "latest_data.json")
    niche = publication["niches"]["Fixture"]
    documents = read_collection_snapshots(tmp_path, research.metadata["run_id"])
    sources = {document["source"]: restore_collection(document["collection"]) for document in documents}
    data = DataProcessor().process({"niche": "Fixture", "collected_at": niche["collected_at"],
        "keywords_data": sources["google_trends"].records, "products_data": sources["amazon"].records,
        "discussions_data": sources["reddit"].records})
    data.quality_assessment = assess_data_quality(data, sources)
    if kind == "fact-value": niche["grounded_analysis"]["facts"][0]["value"] = 9999
    elif kind == "quote": niche["grounded_analysis"]["quotes"][0]["quote"] = "Fixture fabricated quote never in the source"
    elif kind == "proposal": niche["grounded_analysis"]["ideas"][0]["target_audience"] = "9999 customers"
    else: niche["ai_validation"]["context"]["selected_records"] += 1
    with pytest.raises(ValueError):
        rebuild_section(data, niche)
    assert client.generate.call_count == 1


def test_extra_snapshot_header_fields_are_not_silently_trusted(tmp_path, research_result_factory):
    research = research_result_factory()
    root = tmp_path / "snapshots" / research.metadata["run_id"]
    manifest_path = root / "manifest.json"
    manifest = read_document(manifest_path)
    entry = manifest["entries"][0]
    path = root / entry["filename"]
    document = read_document(path)
    document["raw_http_auth_body"] = "Fixture private secret must not be trusted"
    body = canonical_json(document).encode("utf-8")
    manifest["total_bytes"] += len(body) - entry["bytes"]
    entry.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    path.write_bytes(body)
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    with pytest.raises(AuditFailure, match="unknown_snapshot_envelope_field"):
        audit_publication(tmp_path / "latest_data.json", tmp_path, research.metadata["run_id"])


def test_oversize_audit_artifact_fails_before_unreadable_report_is_written(tmp_path, monkeypatch):
    import scripts.audit_publication_phase12 as command
    monkeypatch.setattr(command, "MAX_DOCUMENT_BYTES", 512)
    monkeypatch.setattr(command, "audit_publication", lambda *args: {"status": "consistent_with_collector_snapshots", "noise": "x" * 2000})
    result = command.audit(tmp_path / "fixture.json", tmp_path, "a" * 32, tmp_path / "output")
    saved = read_document(Path(result["audit_file"]))
    assert result["status"] == saved["status"] == "failed"
    assert saved["error_code"] == "audit_output_byte_budget" and saved["network_requests"] == saved["model_calls"] == 0
    assert Path(result["audit_file"]).stat().st_size <= 512


def test_repeated_block_match_work_is_bounded_before_token_scanning(monkeypatch):
    monkeypatch.setattr("src.verification.numeric_inventory.MAX_BLOCK_MATCHES", 2)
    with pytest.raises(AuditFailure, match="numeric_block_match_budget"):
        markdown_numbers("1|1|1", [{"text": "1", "reference": "/fixture"}])


def test_signed_and_trailing_unicode_numbers_remain_exact():
    assert [token for _, _, token in numeric_spans("delta −2.50% then ３.")] == ["−2.50%", "３"]
