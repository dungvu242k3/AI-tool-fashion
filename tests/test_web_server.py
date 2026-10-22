"""Exercise the actual local HTTP handler; no external HTTP is used."""
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from src.web import server
from src.models.research_request import ResearchRequest


@pytest.fixture
def local_server(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "REPORTS_DIR", str(tmp_path))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.TrendToolServer)
    jobs, token = server.services(httpd)
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()

    def request(method, path, body=None):
        client = http.client.HTTPConnection(*httpd.server_address, timeout=3)
        try:
            headers = {"Content-Type": "application/json"}
            if method == "POST":
                from uuid import uuid4
                headers.update({"X-CSRF-Token": token, "Idempotency-Key": uuid4().hex})
            client.request(method, path, body=body, headers=headers)
            response = client.getresponse()
            request.last_headers = dict(response.getheaders())
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def wait_job(job_id):
        for _ in range(200):
            _, job = request("GET", f"/api/jobs/{job_id}")
            if job["status"] in {"completed", "failed"}:
                return job
            threading.Event().wait(.005)
        pytest.fail("Fixture job did not finish")
    request.wait_job = wait_job
    request.jobs = jobs
    yield request
    httpd.shutdown()
    httpd.server_close()
    jobs.close(3)
    thread.join(timeout=3)


def test_api_latest_refuses_legacy_cache(local_server, tmp_path):
    (tmp_path / "latest_data.json").write_text('{"success": true}')
    status, body = local_server("GET", "/api/latest")
    assert status == 200
    assert body["success"] is False
    assert body["status"] == "legacy"
    assert "metadata" not in body


def test_phase09_api_run_and_latest_return_same_canonical_publication(local_server, tmp_path, monkeypatch, research_result_factory):
    from src.reporters.report_repository import ReportRepository
    expected = ReportRepository(tmp_path).publish(research_result_factory(state="partial"))
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        return expected

    monkeypatch.setattr(server, "execute_pipeline", run)
    payload = ResearchRequest.defaults().to_dict()
    payload["mode"] = "deterministic"
    status, accepted = local_server("POST", "/api/run", json.dumps(payload))
    assert status == 202
    assert local_server.wait_job(accepted["job_id"])["status"] == "completed"
    status, posted = local_server("GET", f"/api/jobs/{accepted['job_id']}/result")
    latest_status, latest = local_server("GET", "/api/latest")
    assert status == latest_status == 200 and posted == latest == expected
    assert len(calls) == 1 and calls[0]["request"].mode == "deterministic"
    assert latest["success"] is False and latest["status"] == "partial"


def test_phase09_api_rejects_inconsistent_cache_without_metadata(local_server, tmp_path, research_result_factory):
    from src.reporters.report_repository import ReportRepository
    expected = ReportRepository(tmp_path).publish(research_result_factory())
    expected["markdown_content"] = "Inconsistent fixture"
    ReportRepository(tmp_path).save_latest(expected)
    status, body = local_server("GET", "/api/latest")
    assert status == 200 and body["status"] == "invalid_cache"
    assert "metadata" not in body and body["success"] is False


def test_phase09_json_responses_are_not_browser_cached(local_server):
    status, body = local_server("GET", "/api/latest")
    assert status == 200 and body["status"] == "no_report"
    assert local_server.last_headers["Cache-Control"] == "no-store"
    assert local_server.last_headers["X-Content-Type-Options"] == "nosniff"


def test_api_default_does_not_silently_select_no_ai_mode(local_server, monkeypatch):
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        return {"success": False, "status": "failed", "message": "Fixture offline"}

    monkeypatch.setattr(server, "execute_pipeline", run)
    payload = ResearchRequest.defaults().to_dict()
    del payload["mode"]
    status, accepted = local_server("POST", "/api/run", json.dumps(payload))
    assert status == 202
    assert local_server.wait_job(accepted["job_id"])["status"] == "completed"
    status, body = local_server("GET", f"/api/jobs/{accepted['job_id']}/result")
    assert status == 200
    assert len(calls) == 1 and calls[0]["request"].mode == "ollama"
    assert body["success"] is False
    assert body["status"] == "failed"


@pytest.mark.parametrize("payload", ['{"fast_mode":"false"}', '[]', '{invalid'])
def test_invalid_requests_do_not_start_pipeline(local_server, monkeypatch, payload):
    monkeypatch.setattr(server, "execute_pipeline", lambda **kw: pytest.fail("Invalid input must not run"))
    status, body = local_server("POST", "/api/run", payload)
    assert status == 400
    assert body["success"] is False
    assert local_server.jobs.active() is None
