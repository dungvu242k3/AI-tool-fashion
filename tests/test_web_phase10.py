"""Loopback HTTP tests with isolated runners; never call live collectors."""
from http.server import ThreadingHTTPServer
import http.client
import json
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.models.research_request import ResearchRequest
from src.web import server


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "REPORTS_DIR", str(tmp_path))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.TrendToolServer)
    httpd.daemon_threads = True
    jobs, token = server.services(httpd)
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=.01), daemon=True)
    thread.start()

    def request(method, path, body=None, *, headers=None, csrf=True):
        client = http.client.HTTPConnection(*httpd.server_address, timeout=3)
        fields = {"Content-Type": "application/json"}
        if method == "POST":
            fields["Idempotency-Key"] = uuid4().hex
            if csrf:
                fields["X-CSRF-Token"] = token
        fields.update(headers or {})
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        try:
            client.request(method, path, body=body, headers=fields)
            response = client.getresponse()
            raw = response.read()
            return response.status, (json.loads(raw) if "application/json" in response.getheader("Content-Type", "") else raw.decode("utf-8")), dict(response.getheaders())
        finally:
            client.close()

    def terminal(job_id):
        for _ in range(200):
            status, job, _ = request("GET", f"/api/jobs/{job_id}")
            if status != 200 or job["status"] in {"completed", "failed"}:
                return status, job
            threading.Event().wait(.005)
        pytest.fail("Fixture job did not reach terminal state")

    yield SimpleNamespace(request=request, jobs=jobs, terminal=terminal, port=httpd.server_address[1], httpd=httpd)
    httpd.shutdown()
    httpd.server_close()
    jobs.close(3)
    thread.join(3)


def test_config_exposes_intent_not_fake_metrics_and_ollama_default(site):
    status, config, headers = site.request("GET", "/api/config")
    assert status == 200 and config["defaults"]["mode"] == "ollama"
    assert len(config["defaults"]["niches"]) == 3 and config["limits"]["max_niches"] == 5
    assert "metadata" not in config and "ranking" not in config and "records" not in config
    assert config["csrf_token"] and headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in headers


@pytest.mark.parametrize("headers", [{"Host": "attacker.test"}, {"Origin": "https://attacker.test"},
    {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}])
def test_foreign_origin_and_dns_rebinding_cannot_read_config(site, headers):
    status, body, _ = site.request("GET", "/api/config", headers=headers)
    assert status == 403 and "csrf_token" not in body


@pytest.mark.parametrize("csrf,headers", [(False, {}), (True, {"X-CSRF-Token": "wrong"}),
    (True, {"Origin": "https://attacker.test"}), (True, {"Sec-Fetch-Site": "cross-site"})])
def test_cross_origin_or_missing_token_never_starts_research(site, monkeypatch, csrf, headers):
    monkeypatch.setattr(server, "execute_pipeline", lambda **kw: pytest.fail("Must not execute"))
    status, body, _ = site.request("POST", "/api/run", ResearchRequest.defaults().to_dict(), csrf=csrf, headers=headers)
    assert status == 403 and body["success"] is False and site.jobs.active() is None


@pytest.mark.parametrize("body,headers,expected", [
    ({}, {}, 400), ('{"category":"a","category":"b"}', {}, 400),
    ('{"number":NaN}', {}, 400), ('[]', {}, 400),
    ("x" * 32769, {}, 413), ('{}', {"Content-Type": "text/plain"}, 415),
    ('{}', {"Transfer-Encoding": "chunked"}, 400), ('{}', {"Expect": "100-continue"}, 400),
    ('{}', {"Content-Length": "-1"}, 400), ('{}', {"Content-Length": "999999999"}, 400),
], ids=["missing", "duplicate", "nan", "array", "oversize", "mime", "chunked", "expect", "negative-length", "huge-length"])
def test_http_input_is_bounded_before_worker(site, monkeypatch, body, headers, expected):
    monkeypatch.setattr(server, "execute_pipeline", lambda **kw: pytest.fail("Must not execute"))
    status, error, response_headers = site.request("POST", "/api/run", body, headers=headers)
    assert status == expected and error["success"] is False
    assert site.jobs.active() is None and response_headers["Connection"] == "close"


def test_async_accepted_job_returns_exact_canonical_publication(site, tmp_path, research_result_factory, monkeypatch):
    from src.reporters.report_repository import ReportRepository
    expected = ReportRepository(tmp_path).publish(research_result_factory(state="partial"))
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        kwargs["progress_callback"](2, 5, "Fixture normalization", "real callback, no timer")
        return expected

    monkeypatch.setattr(server, "execute_pipeline", run)
    payload = ResearchRequest.defaults().to_dict()
    del payload["mode"]
    status, accepted, _ = site.request("POST", "/api/run", payload, headers={"Idempotency-Key": "fixture-idempotency-10"})
    assert status == 202
    terminal_status, finished = site.terminal(accepted["job_id"])
    assert terminal_status == 200 and finished["status"] == "completed"
    assert finished["progress"]["step"] == 2 and finished["finished_at"]
    result_status, result, _ = site.request("GET", f"/api/jobs/{accepted['job_id']}/result")
    latest_status, latest, _ = site.request("GET", "/api/latest")
    assert result_status == latest_status == 200 and result == expected == latest
    assert calls[0]["request"].mode == "ollama" and "fast_mode" not in calls[0]
    status, duplicate, _ = site.request("POST", "/api/run", payload, headers={"Idempotency-Key": "fixture-idempotency-10"})
    assert status == 202 and duplicate["job_id"] == accepted["job_id"] and len(calls) == 1


def test_worker_exception_is_private_and_status_endpoint_stays_available(site, monkeypatch, caplog):
    def broken(**kwargs):
        raise RuntimeError("fixture secret provider detail")
    monkeypatch.setattr(server, "execute_pipeline", broken)
    status, accepted, _ = site.request("POST", "/api/run", ResearchRequest.defaults().to_dict())
    assert status == 202
    _, job = site.terminal(accepted["job_id"])
    assert job["status"] == "failed" and "secret provider" not in job["error"]
    status, error, _ = site.request("GET", f"/api/jobs/{accepted['job_id']}/result")
    assert status == 500 and "secret provider" not in json.dumps(error)
    assert any(getattr(record, "job_id", None) == accepted["job_id"] for record in caplog.records)


def test_busy_job_and_idempotency_conflict_cannot_spawn_second_worker(site, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        entered.set()
        assert release.wait(3)
        return {"fixture_only": True}

    monkeypatch.setattr(server, "execute_pipeline", run)
    payload = ResearchRequest.defaults().to_dict()
    try:
        _, accepted, _ = site.request("POST", "/api/run", payload, headers={"Idempotency-Key": "fixture-single-flight"})
        assert entered.wait(2)
        status, pending, _ = site.request("GET", f"/api/jobs/{accepted['job_id']}/result")
        assert status == 202 and pending["result_available"] is False
        status, active, _ = site.request("GET", "/api/jobs/active")
        assert status == 200 and active["job"]["job_id"] == accepted["job_id"]
        assert site.request("POST", "/api/run", payload)[0] == 429
        changed = {**payload, "category": "different"}
        assert site.request("POST", "/api/run", changed, headers={"Idempotency-Key": "fixture-single-flight"})[0] == 409
        assert len(calls) == 1
    finally:
        release.set()


@pytest.mark.parametrize("path", ["/api/jobs/not-a-job", "/api/jobs/" + "a" * 32, "/static/../server.py", "/static/%2e%2e/server.py", "/reports/latest_data.json"])
def test_unknown_jobs_and_private_paths_are_not_served(site, path):
    assert site.request("GET", path)[0] == 404


def test_index_has_dynamic_editor_no_inline_handlers_or_external_requests(site):
    status, html, headers = site.request("GET", "/")
    assert status == 200 and 'id="nicheInputs"' in html and 'id="nichePanes"' in html
    assert "onclick=" not in html and "https://fonts" not in html and 'id="withoutAI"' not in html
    assert "script-src 'self'" in headers["Content-Security-Policy"] and headers["X-Frame-Options"] == "DENY"
    assert site.request("GET", "/static/js/form.js")[0] == 200


def test_internal_cache_read_error_is_safe_json(site, monkeypatch):
    def broken(self):
        raise OSError("fixture private storage path")
    monkeypatch.setattr(server.ReportRepository, "load_latest", broken)
    status, error, _ = site.request("GET", "/api/latest")
    assert status == 500 and "private storage" not in error["error"]


def test_public_bind_is_not_allowed():
    with pytest.raises(ValueError):
        server.run_web_server(host="0.0.0.0", auto_open=False)


def test_full_async_pipeline_uses_validated_input_and_never_rewrites_failed_research_as_success(site, monkeypatch, collection_factory):
    from src.pipeline import execute_pipeline
    calls = []

    def collect(source, niche):
        calls.append((source, niche))
        return collection_factory(source, [])

    collectors = {source: SimpleNamespace(collect=lambda niche, s=source: collect(s, niche)) for source in ("google_trends", "amazon", "reddit")}
    monkeypatch.setattr(server, "execute_pipeline", lambda **kwargs: execute_pipeline(**kwargs, collectors=collectors))
    payload = ResearchRequest.defaults().to_dict()
    payload.update(category="Custom research category", geo="VN", timeframe="today 12-m", mode="deterministic")
    status, accepted, _ = site.request("POST", "/api/run", payload)
    assert status == 202
    _, finished = site.terminal(accepted["job_id"])
    assert finished["status"] == "completed"  # Execution finished; research still failed.
    _, result, _ = site.request("GET", f"/api/jobs/{accepted['job_id']}/result")
    assert result["success"] is False and result["status"] == "failed"
    assert result["metadata"]["research_input"] == payload
    assert result["metadata"]["category"] == payload["category"]
    assert result["metadata"]["model_attempted"] is None and result["evidence"] == []
    assert len(calls) == 9 and all(niche["geo"] == "VN" and niche["timeframe"] == "today 12-m" for _, niche in calls)
    assert "Thông số nghiên cứu được yêu cầu" in result["markdown_content"] and "today 12-m" in result["markdown_content"]
    assert site.request("GET", "/api/latest")[1] == result


@pytest.mark.parametrize("name", ["Content-Length", "Content-Type", "Origin", "X-CSRF-Token", "Idempotency-Key"])
def test_ambiguous_duplicate_headers_are_rejected(site, name):
    client = http.client.HTTPConnection("127.0.0.1", site.port, timeout=3)
    body = json.dumps(ResearchRequest.defaults().to_dict()).encode("utf-8")
    headers = {"Content-Length": str(len(body)), "Content-Type": "application/json",
        "Origin": f"http://127.0.0.1:{site.port}", "X-CSRF-Token": site.httpd.csrf_token, "Idempotency-Key": "fixture-duplicate-header"}
    try:
        client.putrequest("POST", "/api/run")
        for key, value in headers.items():
            client.putheader(key, value)
            if key == name:
                client.putheader(key, value)
        client.endheaders(body)
        response = client.getresponse()
        response.read()
        assert response.status in {400, 403, 415} and site.jobs.active() is None
    finally:
        client.close()


@pytest.mark.parametrize("headers", [{"Content-Type": "application/json; charset=utf-16"}, {"Content-Encoding": "gzip"}])
def test_unsupported_body_encodings_are_not_silently_interpreted(site, headers):
    assert site.request("POST", "/api/run", ResearchRequest.defaults().to_dict(), headers=headers)[0] == 415
