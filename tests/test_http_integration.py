"""Real loopback HTTP tests, with outbound requests restricted to this fixture server."""
import json
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest
import requests

from src.collectors.errors import CollectionError
from src.collectors.http import HTTPClient
from src.collectors.http_policy import HTTPPolicy

REAL_SESSION_REQUEST = requests.sessions.Session.request


@pytest.fixture
def http_server(monkeypatch):
    requests_seen = []
    counts = Counter()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path
            requests_seen.append(self.path)
            counts[path] += 1
            status, headers = 200, {}
            if path == "/recover" and counts[path] == 1:
                status = 503
            elif path == "/blocked":
                status = 403
            elif path == "/cooldown":
                status, headers = 429, {"Retry-After": "999"}
            elif path == "/redirect":
                status, headers = 302, {"Location": "/observed"}
            body = json.dumps({"observed_path": self.path}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    address = f"http://127.0.0.1:{server.server_port}"

    def local_only(session, method, url, **kwargs):
        assert urlsplit(url).netloc == urlsplit(address).netloc
        return REAL_SESSION_REQUEST(session, method, url, **kwargs)

    monkeypatch.setattr(requests.sessions.Session, "request", local_only)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    yield address, requests_seen
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


@pytest.mark.parametrize(("path", "statuses"), [("/recover", [503, 200]), ("/redirect", [302, 200])])
def test_real_requests_match_the_complete_audit_log(http_server, path, statuses):
    address, seen = http_server
    journal = []
    with HTTPClient(policy=HTTPPolicy(backoff_base=0.01, backoff_cap=0.02)) as client:
        response = client.fetch(
            "GET", address + path, source="loopback", operation="fixture", query={"fixture": True},
            params={"q": "observed fixture", "token": "private-token"}, journal=journal,
        )
    assert [entry.status_code for entry in journal] == statuses
    assert len(seen) == len(journal)
    assert response.json()["observed_path"] == seen[-1]
    assert all(entry.elapsed_ms >= 0 for entry in journal)
    assert "private-token" not in str(journal)


@pytest.mark.parametrize("path", ["/blocked", "/cooldown"])
def test_real_permanent_failure_or_long_cooldown_is_not_retried(http_server, path):
    address, seen = http_server
    journal = []
    with HTTPClient(policy=HTTPPolicy()) as client:
        with pytest.raises(CollectionError):
            client.fetch("GET", address + path, source="loopback", operation="fixture", query={}, journal=journal)
    assert len(seen) == len(journal) == 1
