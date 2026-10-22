"""Read the real archived publication through the local Web API, without research.

No collector replacements, fake responses, model generation or provider requests.
This verifies local read compatibility, NOT a positive live research job/browser QA.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from http.server import ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import threading
from uuid import uuid4

from src.config import DATA_POLICY_VERSION
from src.reporters.report_repository import ReportRepository
from src.web import server


def audit(input_dir: Path, output_dir: Path):
    expected = ReportRepository(input_dir).load_latest()
    if expected.get("metadata", {}).get("execution_kind") != "offline_publication_audit":
        raise ValueError("Expected an already archived, canonical offline publication")
    original_bytes = (input_dir / "latest_data.json").read_bytes()
    prior_directory = server.REPORTS_DIR
    httpd = None
    try:
        server.REPORTS_DIR = str(input_dir.resolve())
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.TrendToolServer)
        httpd.daemon_threads = True
        jobs, _ = server.services(httpd)
        thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=.01), daemon=True)
        thread.start()
        observed = {}
        for path in ("/api/config", "/api/latest", "/api/jobs/active"):
            client = http.client.HTTPConnection(*httpd.server_address, timeout=3)
            try:
                client.request("GET", path)
                response = client.getresponse()
                data = json.loads(response.read())
                if response.status != 200:
                    raise RuntimeError("Local read did not succeed")
                observed[path] = {"status": response.status, "cache_control": response.getheader("Cache-Control")}
                if path == "/api/latest" and data != expected:
                    raise RuntimeError("API changed the archived canonical publication")
                if path == "/api/config":
                    observed[path].update(mode_default=data["defaults"]["mode"], niche_limit=data["limits"]["max_niches"])
                if path == "/api/jobs/active" and data != {"job": None}:
                    raise RuntimeError("An unexpected research job was started")
            finally:
                client.close()
        if jobs.active() is not None or (input_dir / "latest_data.json").read_bytes() != original_bytes:
            raise RuntimeError("Read-only audit changed the input or started collection")
    finally:
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
            server.services(httpd)[0].close()
        server.REPORTS_DIR = prior_directory
    run_id = uuid4().hex
    payload = {
        "run_id": run_id, "data_policy": DATA_POLICY_VERSION,
        "audit_kind": "offline_local_web_reads_on_archived_real_publication",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "input": {"cache": (input_dir / "latest_data.json").as_posix(),
                  "run_id": expected["metadata"]["run_id"], "document_sha256": expected["document_sha256"],
                  "file_sha256_before_and_after": hashlib.sha256(original_bytes).hexdigest()},
        "http_reads": observed, "loopback_http_requests": 3, "provider_requests": 0,
        "model_generation_requests": 0, "research_jobs_started": 0, "fixture_or_mock_data": False,
        "api_preserves_canonical_publication": True, "source_collection_validation_reexecuted": False,
        "provider_records_refetched": False,
        "status": expected["status"], "data_quality": expected["metadata"]["data_quality"],
        "source_record_counts": {source: sum(len(niche[field]) for niche in expected["niches"].values())
                                 for source, field in (("google_trends", "keywords"), ("amazon", "products"), ("reddit", "discussions"))},
        "evidence": expected["evidence"], "ranking": expected["ranking"], "top_ideas": expected["top_ideas"],
        "browser_visual_qa_or_positive_live_research_job_verified": False,
        "limitations": ["Read-only local HTTP compatibility, not new live research.",
                        "The three default input niches are query configuration, not three observed market samples.",
                        "Archived source timestamps, failures, insufficient gate and empty ideas remain unchanged."],
    }
    relative = ReportRepository(output_dir).save_diagnostics(run_id, payload)
    return {"audit": str((output_dir / relative).resolve()), "record_counts": payload["source_record_counts"],
            "api_preserves_canonical_publication": True, "loopback_requests": 3, "provider_requests": 0,
            "model_generation_requests": 0, "research_jobs_started": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("reports/verification_phase09"))
    parser.add_argument("--output", type=Path, default=Path("reports/verification_phase10"))
    args = parser.parse_args()
    print(json.dumps(audit(args.input, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
