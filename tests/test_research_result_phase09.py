"""Isolated phase-9 publication checks; no provider/model live requests."""
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path

import pytest

from src.models.research_result import ResearchResult, freeze_json, thaw_json
from src.reporters.report_generator import ReportGenerator
from src.reporters.report_repository import ReportRepository
from src.reporters.result_codec import document_digest
from src.reporters.text import markdown_link, markdown_text


def document(tmp_path, research):
    return ReportRepository(tmp_path).publish(research)


def test_pipeline_constructs_once_and_passes_same_snapshot_to_views(tmp_path, research_result_factory, monkeypatch):
    created, rendered, serialized = [], [], []
    original_init, original_render, original_dict = ResearchResult.__post_init__, ReportGenerator.render, ResearchResult.to_dict

    def init(self):
        created.append(self)
        original_init(self)

    def render(self, result):
        rendered.append(result)
        return original_render(self, result)

    def serialize(self):
        serialized.append(self)
        return original_dict(self)

    monkeypatch.setattr(ResearchResult, "__post_init__", init)
    monkeypatch.setattr(ReportGenerator, "render", render)
    monkeypatch.setattr(ResearchResult, "to_dict", serialize)
    # Factory also decodes once for this test; pipeline alone constructs the first object.
    research_result_factory()
    assert len(created) == 2 and len(rendered) == len(serialized) == 1
    assert created[0] is rendered[0] is serialized[0]
    cached = json.loads((tmp_path / "latest_data.json").read_text(encoding="utf-8"))
    assert cached["markdown_content"] == Path(cached["report_filepath"]).read_text(encoding="utf-8")


def test_snapshot_owns_nested_inputs_and_serializer_copies(research_result_factory):
    original = research_result_factory()
    source = thaw_json(original.niches)
    owned = replace(original, niches=source)
    source["Fixture"]["keywords"][0]["score"] = 99
    assert owned.niches["Fixture"]["keywords"][0]["score"] == 0
    with pytest.raises(TypeError):
        owned.niches["Fixture"]["keywords"][0]["score"] = 99
    with pytest.raises(FrozenInstanceError):
        owned.metadata = {}
    exported = owned.to_dict()
    exported["niches"]["Fixture"]["products"].clear()
    assert len(owned.niches["Fixture"]["products"]) == 5
    assert exported["ranking"] is exported["ranking_assessment"]["ranking"]
    assert exported["top_ideas"] is exported["analysis_summary"]["top_ideas"]


@pytest.mark.parametrize("state", ["complete", "partial", "failed", "insufficient"])
def test_roundtrip_and_report_share_status_source_and_missing_values(tmp_path, research_result_factory, state):
    research = research_result_factory(state=state)
    exported = document(tmp_path, research)
    assert ReportRepository(tmp_path).load_latest() == exported
    assert exported["status"] == exported["metadata"]["status"]
    assert exported["success"] is (state == "complete")
    assert ("[!WARNING]" in exported["markdown_content"]) is (state != "complete")
    for source, status in exported["source_statuses"]["Fixture"].items():
        assert f"| {markdown_text(source)} | {status['status']} | {status['record_count']} |" in exported["markdown_content"]
    if state == "complete":
        assert exported["niches"]["Fixture"]["keywords"][0]["score"] == 0
        assert exported["niches"]["Fixture"]["products"][0]["price"] is None
    if state == "failed":
        assert exported["evidence"] == []
        assert "không tạo URL hoặc timestamp thay thế" in exported["markdown_content"]


def test_evidence_appendix_keeps_niche_associations_and_original_dependencies(research_result_factory):
    research = research_result_factory(names=("Fixture A", "Fixture B"))
    assert len(research.evidence) == 20
    report = ReportGenerator().render(research).split("## Phụ lục evidence", 1)[1]
    for entry in research.evidence:
        assert markdown_text(entry["niche"]) in report
        assert markdown_text(entry["evidence_id"]) in report
        assert entry["source_url"] in report
        assert entry["retrieved_at"] in report
        assert all(identity in report for identity in entry["request_ids"])
    assert {e["niche"] for e in research.evidence} == {"Fixture A", "Fixture B"}


def test_cache_provenance_keeps_original_time(research_result_factory):
    changed = research_result_factory(cached=True)
    report = ReportGenerator().render(changed).split("## Phụ lục evidence", 1)[1]
    for entry in changed.evidence:
        assert entry["retrieved_at"] in report
    assert "| có |" in report


@pytest.mark.parametrize("target,value", [
    ("mode", "ollama"), ("model_name", "invented-model"), ("status", "partial"),
    ("data_quality", "partial"), ("total_keywords", 88), ("total_products", False),
    ("ranking_status", "invented"), ("top_ideas_status", "available"),
    ("diagnostics_file", "../../secret.json"), ("timestamp", "no-zone"), ("run_id", "../outside"),
])
def test_inconsistent_metadata_is_rejected(research_result_factory, target, value):
    result = research_result_factory()
    metadata = thaw_json(result.metadata)
    metadata[target] = value
    with pytest.raises(ValueError):
        replace(result, metadata=metadata)


@pytest.mark.parametrize("alteration", ["record_count", "source", "quality", "ai_validation", "evidence_time", "missing_request", "unsafe_url", "ranking_digest"])
def test_conflicting_output_views_are_rejected(research_result_factory, alteration):
    payload = research_result_factory().to_dict()
    niche = payload["niches"]["Fixture"]
    if alteration == "record_count":
        niche["source_statuses"]["amazon"]["record_count"] = 0
    elif alteration == "source":
        niche["keywords"][0]["provenance"]["source"] = "reddit"
    elif alteration == "quality":
        niche["quality_assessment"]["status"] = "insufficient"
    elif alteration == "ai_validation":
        niche["ai_validation"] = {}
    elif alteration == "evidence_time":
        niche["keywords"][0]["provenance"]["retrieved_at"] = "2026-10-20T00:00:00Z"
    elif alteration == "missing_request":
        payload["request_metadata"].clear()
    elif alteration == "unsafe_url":
        niche["keywords"][0]["provenance"]["source_url"] = "javascript:alert(1)"
    else:
        payload["ranking_assessment"]["ranking"][0]["evidence_digest"] = "stale"
    with pytest.raises(ValueError):
        ResearchResult.from_dict(payload)


@pytest.mark.parametrize("key,value", [("ranking", []), ("top_ideas", [{"name": "Invented"}]),
                                     ("success", False), ("message", "Invented"),
                                     ("markdown_content", "Invented Markdown"), ("evidence", []),
                                     ("report_filename", "../outside.md"), ("source_health", {})])
def test_cache_rejects_disagreement_even_with_recomputed_checksum(tmp_path, research_result_factory, key, value):
    exported = document(tmp_path, research_result_factory())
    exported[key] = value
    exported["document_sha256"] = document_digest(exported)
    ReportRepository(tmp_path).save_latest(exported)
    loaded = ReportRepository(tmp_path).load_latest()
    assert loaded["status"] == "invalid_cache" and loaded["success"] is False
    assert "metadata" not in loaded


@pytest.mark.parametrize("body", ['{"metadata":{},"metadata":{}}', '{"value":NaN}', '{"value":Infinity}',
                                   '{"value":1e9999}', '[]', 'null', '[' * 2000 + ']' * 2000])
def test_unsafe_json_cache_fails_without_fallback(tmp_path, body):
    (tmp_path / "latest_data.json").write_text(body, encoding="utf-8")
    assert ReportRepository(tmp_path).load_latest()["status"] == "invalid_cache"


def test_oversize_cache_has_bounded_read(tmp_path, monkeypatch):
    monkeypatch.setattr("src.reporters.result_codec.MAX_DOCUMENT_BYTES", 64)
    (tmp_path / "latest_data.json").write_text(" " * 65, encoding="utf-8")
    assert ReportRepository(tmp_path).load_latest()["status"] == "invalid_cache"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 10**500, {"x": object()}, {1: "key"}, "\ud800"])
def test_snapshot_rejects_non_json_values(value):
    with pytest.raises(ValueError):
        freeze_json(value)


def test_snapshot_rejects_cycle_and_depth():
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError):
        freeze_json(cycle)


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://user:secret@example.test/", "https://example.test/\nheader"])
def test_report_links_fail_closed(url):
    with pytest.raises(ValueError):
        markdown_link("Source", url)


def test_report_link_cannot_escape_markdown_or_html():
    result = markdown_link("<img src=x>|[bad]", 'https://example.test/a)\"<script>|(b')
    assert "<img" not in result and "<script>" not in result
    assert "%29" in result and "%22" in result and "%3C" in result and "%7C" in result


def test_header_uses_canonical_values_and_escapes_untrusted_labels(research_result_factory):
    result = research_result_factory()
    metadata = thaw_json(result.metadata)
    metadata.update(category="<script>bad()</script>|[link]", warnings=["<img src=x>"], cost="Unmeasured machine costs")
    result = replace(result, metadata=metadata)
    report = ReportGenerator().render(result)
    assert "<script>" not in report and "<img" not in report
    assert "Unmeasured machine costs" in report and "$0.00" not in report
    assert result.metadata["timestamp"] in report and result.metadata["run_id"] in report


@pytest.mark.parametrize("failure_target", ["report", "latest"])
def test_atomic_failure_keeps_previous_latest_and_removes_temporary(tmp_path, research_result_factory, monkeypatch, failure_target):
    import src.reporters.report_repository as repository_module
    research = research_result_factory()
    repository = ReportRepository(tmp_path)
    previous = (tmp_path / "latest_data.json").read_bytes()
    original_replace = repository_module.os.replace

    def fail(source, target):
        if (Path(target).name == "latest_data.json") == (failure_target == "latest"):
            raise OSError("Fixture disk failure")
        return original_replace(source, target)

    monkeypatch.setattr(repository_module.os, "replace", fail)
    with pytest.raises(OSError):
        repository.publish(research)
    assert (tmp_path / "latest_data.json").read_bytes() == previous
    assert not list(tmp_path.glob("*.tmp"))


def test_current_policy_minimal_cache_is_not_accepted(tmp_path):
    from src.config import DATA_POLICY_VERSION
    ReportRepository(tmp_path).save_latest({"metadata": {"data_policy": DATA_POLICY_VERSION}, "markdown_content": "Fixture", "niches": {}})
    assert ReportRepository(tmp_path).load_latest()["status"] == "invalid_cache"


def test_v8_cache_cannot_bypass_canonical_contract(tmp_path):
    ReportRepository(tmp_path).save_latest({"metadata": {"data_policy": "live-only-v8"}, "markdown_content": "Fixture", "niches": {}})
    assert ReportRepository(tmp_path).load_latest()["status"] == "legacy"


def test_reporter_rejects_loose_dictionary():
    with pytest.raises(TypeError):
        ReportGenerator().render({"metadata": {}})


@pytest.mark.parametrize("case", ["measured_scalar", "raw_alias", "derived_alias", "cached_provenance"])
def test_serialized_evidence_cannot_change_after_gate(research_result_factory, case):
    result = research_result_factory()
    niches = thaw_json(result.niches)
    keyword = niches["Fixture"]["keywords"][0]
    if case == "measured_scalar":
        keyword["score"] = keyword["raw_metric"]["score"] = 99
    elif case == "raw_alias":
        keyword["raw_metric"]["score"] = False  # False must not equal measured zero.
    elif case == "derived_alias":
        keyword["derived_metric"] = {}
    else:
        keyword["provenance"]["from_cache"] = True
    with pytest.raises(ValueError):
        replace(result, niches=niches)


@pytest.mark.parametrize("kind", ["ollama", "mixed", "context_rejected"])
def test_ai_execution_header_and_cache_keep_actual_modes(tmp_path, research_result_factory, grounded_payload_factory, monkeypatch, kind):
    from src.analyzers.llm_analyzer import LLMAnalyzer
    from src.analyzers.ollama_client import GenerationError

    def generate(self, prompt, **kwargs):
        if json.loads(prompt)["niche_name"] == "Unavailable":
            raise GenerationError("ollama_connection_error")
        return json.dumps(grounded_payload_factory(prompt=prompt))

    monkeypatch.setattr(LLMAnalyzer, "_call_ollama", generate)
    kwargs = {"fast_mode": False, "model_name": "fixture-model"}
    if kind == "mixed":
        kwargs["names"] = ("Fixture", "Unavailable")
    if kind == "context_rejected":
        kwargs["model_name"] = "fixture:cloud"
    result = research_result_factory(**kwargs)
    exported = document(tmp_path, result)
    assert ReportRepository(tmp_path).load_latest() == exported
    mode = "deterministic" if kind == "context_rejected" else kind
    assert result.metadata["mode"] == mode
    assert f"**Chế độ thực tế:** {mode}" in exported["markdown_content"]
    if kind == "context_rejected":
        assert result.metadata["model_name"] is result.metadata["model_attempted"] is None
        assert "Model đã thử gọi" not in exported["markdown_content"]
        assert not result.analysis_summary["top_ideas"]
    else:
        assert "**Model có đầu ra được sử dụng:** fixture-model" in exported["markdown_content"]
        assert "**Model đã thử gọi:** fixture-model" in exported["markdown_content"]
        assert exported["top_ideas"] == exported["analysis_summary"]["top_ideas"]


def test_publication_size_failure_does_not_touch_latest(tmp_path, research_result_factory, monkeypatch):
    result = research_result_factory()
    previous = (tmp_path / "latest_data.json").read_bytes()
    monkeypatch.setattr("src.reporters.report_repository.MAX_DOCUMENT_BYTES", 1)
    with pytest.raises(ValueError, match="byte budget"):
        ReportRepository(tmp_path).publish(result)
    assert (tmp_path / "latest_data.json").read_bytes() == previous


def test_document_tree_budgets_are_enforced():
    with pytest.raises(ValueError):
        freeze_json([1, 2], budget=[1, 100])
    with pytest.raises(ValueError):
        freeze_json("1234", budget=[10, 3])


@pytest.mark.parametrize("field,value", [("record_count", 99), ("status", "failed"), ("niche_count", True),
                                         ("request_count", -1), ("retry_count", "<script>"), ("cached_record_count", 1)])
def test_health_metadata_cannot_invent_totals_or_inject_markup(research_result_factory, field, value):
    result = research_result_factory()
    metadata = thaw_json(result.metadata)
    metadata["source_health"]["google_trends"][field] = value
    with pytest.raises(ValueError):
        replace(result, metadata=metadata)


@pytest.mark.parametrize("field,value", [("gate_passed", 1), ("valid_count", False), ("valid_ratio", 2)])
def test_quality_views_require_strict_types_and_valid_ranges(research_result_factory, field, value):
    result = research_result_factory()
    metadata, niches = thaw_json(result.metadata), thaw_json(result.niches)
    metadata["quality_assessments"]["Fixture"][field] = value
    niches["Fixture"]["quality_assessment"][field] = value
    with pytest.raises(ValueError):
        replace(result, metadata=metadata, niches=niches)


def test_quality_metadata_cannot_replace_zero_with_boolean(research_result_factory):
    result = research_result_factory()
    metadata = thaw_json(result.metadata)
    metadata["quality_assessments"]["Fixture"]["rejected_count"] = False
    with pytest.raises(ValueError, match="Quality views"):
        replace(result, metadata=metadata)


@pytest.mark.parametrize("field,value", [("title", "Invented"), ("why_now", "Invented"),
                                         ("selection_position", 3), ("niche_rank", True), ("source_links", [])])
def test_summary_must_match_canonical_idea_content_and_source_links(tmp_path, research_result_factory, grounded_payload_factory, monkeypatch, field, value):
    from src.analyzers.llm_analyzer import LLMAnalyzer
    monkeypatch.setattr(LLMAnalyzer, "_call_ollama", lambda self, prompt, **kw: json.dumps(grounded_payload_factory(prompt=prompt)))
    result = research_result_factory(fast_mode=False)
    exported = document(tmp_path, result)
    # Positive read also exercises the new summary/health consistency checks.
    assert ReportRepository(tmp_path).load_latest() == exported
    summary = thaw_json(result.analysis_summary)
    summary["top_ideas"][0][field] = value
    with pytest.raises(ValueError):
        replace(result, analysis_summary=summary)


def test_builder_rejects_mismatched_niche_sets(grounded_data_factory):
    from src.processors.research_result_builder import RunContext, build_research_result
    data = grounded_data_factory()
    # A mismatched set is rejected before it could publish or fabricate a section.
    context = RunContext("a" * 32, "Fixture", "2026-10-21T00:00:00Z", "deterministic", "fixture", False, 0, f"diagnostics/{'a' * 32}.json")
    with pytest.raises(ValueError, match="niche sets"):
        build_research_result(context=context, processed={"Fixture": data}, sections={}, source_statuses={},
            source_health={}, request_metadata={}, ranking_assessment={}, analysis_summary={}, warnings=[])


@pytest.mark.parametrize("case", ["cached_count", "wrong_request_source"])
def test_source_provenance_summary_cannot_disagree_with_records(research_result_factory, case):
    result = research_result_factory()
    states, niches = thaw_json(result.source_statuses), thaw_json(result.niches)
    if case == "cached_count":
        states["Fixture"]["google_trends"]["cached_record_count"] = 1
    else:
        states["Fixture"]["google_trends"]["request_ids"] = states["Fixture"]["amazon"]["request_ids"]
    niches["Fixture"]["source_statuses"] = states["Fixture"]
    with pytest.raises(ValueError):
        replace(result, source_statuses=states, niches=niches)


def test_report_listing_is_chronological_not_random_uuid_order(tmp_path):
    import os
    from src.config import DATA_POLICY_VERSION
    older = tmp_path / f"report_trend_{'f' * 32}.md"
    newer = tmp_path / f"report_trend_{'a' * 32}.md"
    for path in (older, newer):
        path.write_text(f"<!-- data-policy: {DATA_POLICY_VERSION} -->", encoding="utf-8")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))
    assert ReportRepository(tmp_path).list_reports()["reports"] == [newer.name, older.name]


def test_offline_publication_labels_original_request_counts(research_result_factory):
    result = research_result_factory()
    metadata = thaw_json(result.metadata)
    metadata["execution_kind"] = "offline_publication_audit"
    rendered = ReportGenerator().render(replace(result, metadata=metadata))
    assert "không phải request trong audit" in rendered
    assert "**Loại lần chạy:** offline\\_publication\\_audit" in rendered


@pytest.mark.parametrize("field,value", [("evidence_id", "missing"), ("source_url", "javascript:alert(1)"),
                                         ("retrieved_at", "2026-10-20T00:00:00Z"), ("request_id", "missing"),
                                         ("source", "reddit"), ("from_cache", 0)])
def test_ranking_input_provenance_must_match_canonical_evidence(research_result_factory, field, value):
    result = research_result_factory()
    ranking = thaw_json(result.ranking_assessment)
    row = ranking["ranking"][0]
    item = next(component["inputs"][0] for component in row["components"] if component["inputs"])
    item[field] = value
    with pytest.raises(ValueError, match="Ranking evidence"):
        replace(result, ranking_assessment=ranking)


def test_markdown_bytes_equal_serialized_content_across_platforms(tmp_path, research_result_factory):
    exported = document(tmp_path, research_result_factory())
    raw = Path(exported["report_filepath"]).read_bytes()
    assert raw == exported["markdown_content"].encode("utf-8")
    assert b"\r\n" not in raw
