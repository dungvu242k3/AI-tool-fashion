"""Audit an existing publication against real retained collector snapshots; no I/O to providers."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from src.models.research_result import MAX_DOCUMENT_BYTES
from src.reporters.report_repository import ReportRepository
from src.verification.contracts import AuditFailure
from src.verification.publication_audit import audit_publication


def audit(publication: Path, snapshots: Path, snapshot_run_id: str, output: Path):
    run_id = uuid4().hex
    try:
        report = audit_publication(publication, snapshots, snapshot_run_id)
    except AuditFailure as exc:
        report = {"status": "failed", "error_code": exc.code, "error_path": exc.path,
                  "network_requests": 0, "model_calls": 0}
    report.update(audit_run_id=run_id, audited_at=datetime.now(timezone.utc).isoformat(),
                  audit_kind="offline_publication_to_collector_snapshots", publication=str(publication.resolve()),
                  snapshot_root=str(snapshots.resolve()))
    if len(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")) > MAX_DOCUMENT_BYTES:
        report = {"audit_run_id": run_id, "status": "failed", "error_code": "audit_output_byte_budget",
                  "network_requests": 0, "model_calls": 0}
    relative = ReportRepository(output).save_diagnostics(run_id, report)
    return {"status": report["status"], "audit_file": str((output / relative).resolve()),
            "numeric_occurrences": len(report.get("markdown_numeric_inventory", {}).get("occurrences", [])),
            "structured_numeric_fields": len(report.get("structured_numeric_fields", [])),
            "error_code": report.get("error_code"), "network_requests": 0, "model_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication", type=Path, default=Path("reports/verification_phase09/latest_data.json"))
    parser.add_argument("--snapshots", type=Path, default=Path("reports/verification_phase11"))
    parser.add_argument("--snapshot-run-id", default="5b83164ff7214ddfba9b3dcf460007e2")
    parser.add_argument("--output", type=Path, default=Path("reports/verification_phase12"))
    args = parser.parse_args()
    result = audit(args.publication, args.snapshots, args.snapshot_run_id, args.output)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "consistent_with_collector_snapshots" else 1


if __name__ == "__main__":
    raise SystemExit(main())
