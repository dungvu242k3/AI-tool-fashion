"""Offline phase-11 persistence audit on archived REAL provider observations.

No replacement collectors, no fake HTTP/clock, no model/provider request. This is
not a fresh research run or a benchmark/certification of live provider accuracy.
"""
import argparse
import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from scripts.audit_ranking_phase07 import load_validated_evidence
from src.collectors.collection_cache import ValidatedCollectionCache
from src.collectors.performance_settings import PerformanceSettings, SOURCES
from src.collectors.validation import validate_collection_result
from src.models.collection import RequestMetadata
from src.reporters.collection_snapshots import CollectionSnapshotWriter, read_collection_snapshots
from src.reporters.report_repository import ReportRepository
from src.reporters.result_codec import canonical_json, read_document


def audit(input_path: Path, output_path: Path) -> dict:
    previous, data, sources = load_validated_evidence(input_path)
    for source, origin in previous["origin_snapshots"].items():
        original = read_document(Path(origin["snapshot"]))["request_metadata"]
        traces = {item["request_id"]: item for item in original} if isinstance(original, list) else original
        sources[source].request_metadata = [RequestMetadata(**traces[key]) for key in origin["original_request_ids"]]
        sources[source] = validate_collection_result(source, sources[source])
    run_id = uuid4().hex
    writer = CollectionSnapshotWriter(output_path, run_id, [data.niche_name], PerformanceSettings())
    expected = {}
    cache = ValidatedCollectionCache()  # Actual clock: old archives cannot get a new TTL.
    accepted = {}
    for source in SOURCES:
        result = sources[source]
        expected[source] = json.loads(canonical_json(asdict(result)))
        writer.capture(0, source, result)
        accepted[source] = cache.put(source, result, 300)
    manifest = writer.commit()
    restored = read_collection_snapshots(output_path, run_id)
    if {item["source"]: item["collection"] for item in restored} != expected:
        raise RuntimeError("Archived source snapshot roundtrip mismatch")
    if any(accepted.values()):
        raise RuntimeError("Archived evidence must not be admitted as fresh cache data")
    diagnostic = {
        "run_id": run_id, "audit_kind": "offline_snapshot_roundtrip_on_archived_real_evidence",
        "not_a_fresh_live_run": True, "network_requests": 0, "model_calls": 0,
        "previous_audit": input_path.as_posix(), "origin_snapshots": previous["origin_snapshots"],
        "snapshot_manifest": manifest, "snapshot_boundary": "validated_collector_output_before_processing",
        "not_http_html_or_oauth_body": True, "roundtrip_exact": True,
        "original_ids_and_timestamps_preserved": True,
        "archive_accepted_as_fresh_cache": accepted,
        "record_counts": {source: len(result.records) for source, result in sources.items()},
        "original_quality_assessment": data.quality_assessment.to_dict(),
        "limitations": ["No live concurrency/speed/accuracy certification", "No positive Reddit OAuth or Ollama recheck",
                        "Checksum is not authentication; protect output directory", "No latest_data.json publication in this audit"],
    }
    path = ReportRepository(output_path).save_diagnostics(run_id, diagnostic)
    return {"diagnostics": str((output_path / path).resolve()), "snapshot_manifest": manifest,
            "record_counts": diagnostic["record_counts"], "roundtrip_exact": True,
            "network_requests": 0, "model_calls": 0, "archive_accepted_as_fresh_cache": accepted}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(
        "reports/verification_phase06/diagnostics/ba0da4abf898429b9f4816722e73dd0a.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/verification_phase11"))
    args = parser.parse_args()
    print(json.dumps(audit(args.input, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
