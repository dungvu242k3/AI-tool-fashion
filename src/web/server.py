"""Local-only Web transport: validated intent → bounded job → canonical result."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import logging
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit
import webbrowser

from src.config import REPORTS_DIR, OLLAMA_MODEL
from src.models.research_request import ResearchRequest, decode_request, MAX_BODY_BYTES, MAX_KEYWORDS, MAX_SUBREDDITS
from src.pipeline import execute_pipeline
from src.reporters.report_repository import ReportRepository
from src.web.jobs import ResearchJobs, JobBusy, IdempotencyConflict

logger = logging.getLogger(__name__)
WEB_ROOT = Path(__file__).resolve().parent
_SERVICES_LOCK = threading.Lock()
ASSETS = {"/static/css/styles.css": "text/css", **{
    f"/static/js/{name}.js": "text/javascript" for name in ("api", "ui", "form", "app")}}


def services(server):
    """One job store/token per server instance, never process-global running flags."""
    with _SERVICES_LOCK:
        if not hasattr(server, "research_jobs"):
            directory = str(Path(REPORTS_DIR).resolve())
            server.research_jobs = ResearchJobs(lambda request, progress: execute_pipeline(
                request=request, output_dir=directory, progress_callback=progress))
            server.csrf_token = secrets.token_urlsafe(32)
        return server.research_jobs, server.csrf_token


class TrendToolServer(BaseHTTPRequestHandler):
    server_version = "TrendResearch"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format, *args):
        pass

    def _headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "connect-src 'self'; img-src 'self' data:; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.send_header("Connection", "close")
        self.close_connection = True

    def _send_bytes(self, body, status=200, mime="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self._headers()
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass  # A disconnected browser does not cancel/restart the worker.

    def _send_json(self, data, status=200):
        self._send_bytes(json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"), status)

    def _error(self, status, message):
        self._send_json({"success": False, "error": message}, status)

    def _trusted(self):
        hosts = self.headers.get_all("Host", [])
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        if len(hosts) != 1 or hosts[0] not in allowed or not ipaddress.ip_address(self.client_address[0]).is_loopback:
            self._error(403, "Chỉ hỗ trợ truy cập loopback bằng Host hợp lệ.")
            return False
        origins = self.headers.get_all("Origin", [])
        sites = self.headers.get_all("Sec-Fetch-Site", [])
        if len(origins) > 1 or len(sites) > 1 or (origins and origins[0] != f"http://{hosts[0]}") or (sites and sites[0] not in {"same-origin", "none"}):
            self._error(403, "Request khác nguồn gốc bị từ chối.")
            return False
        return True

    def do_OPTIONS(self):
        self._error(403, "Cross-origin API không được hỗ trợ.")

    def do_GET(self):
        if not self._trusted():
            return
        try:
            self._get()
        except Exception:
            logger.exception("web_read_failed")
            self._error(500, "Không đọc được dữ liệu server; xem log server.")

    def _get(self):
        path = urlsplit(self.path).path
        if path in {"/", "/index.html"}:
            return self._asset(WEB_ROOT / "index.html", "text/html")
        if path in ASSETS:
            return self._asset(WEB_ROOT / path.lstrip("/"), ASSETS[path])
        if path == "/api/config":
            try:
                jobs, token = services(self.server)
                self._send_json({"defaults": ResearchRequest.defaults().to_dict(), "model_name": OLLAMA_MODEL,
                    "csrf_token": token, "limits": {"min_niches": 3, "max_niches": 5,
                    "max_keywords": MAX_KEYWORDS, "max_subreddits": MAX_SUBREDDITS}, "poll_interval_ms": 1000})
            except ValueError:
                logger.exception("web_configuration_invalid")
                self._error(500, "Cấu hình server không hợp lệ; xem log server.")
            return
        if path == "/api/latest":
            self._send_json(ReportRepository(REPORTS_DIR).load_latest())
            return
        if path == "/api/reports":
            self._send_json(ReportRepository(REPORTS_DIR).list_reports())
            return
        if path == "/api/jobs/active":
            self._send_json({"job": services(self.server)[0].active()})
            return
        parts = path.split("/")
        if len(parts) in {4, 5} and parts[:3] == ["", "api", "jobs"]:
            jobs = services(self.server)[0]
            job = jobs.get(parts[3])
            if job is None:
                self._error(404, "Job không tồn tại hoặc đã hết hạn; xem báo cáo gần nhất.")
            elif len(parts) == 4:
                self._send_json(job)
            elif parts[4] == "result":
                body = jobs.result(parts[3])
                if body is not None:
                    self._send_bytes(body)
                elif job["status"] == "failed":
                    self._error(500, job["error"])
                elif job["status"] == "completed":
                    self._error(404, "Kết quả job đã hết hạn; xem báo cáo gần nhất.")
                else:
                    self._send_json({"job_id": parts[3], "status": job["status"], "result_available": False}, 202)
            else:
                self._error(404, "Endpoint không tồn tại.")
            return
        self._error(404, "Endpoint không tồn tại.")

    def _asset(self, path, mime):
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(WEB_ROOT):
                raise ValueError("Unsafe asset path")
            with resolved.open("rb") as stream:
                body = stream.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                raise ValueError("Asset exceeds budget")
            self._send_bytes(body, mime=f"{mime}; charset=utf-8")
        except (OSError, ValueError):
            self._error(404, "Không đọc được tài nguyên.")

    def do_POST(self):
        if not self._trusted():
            return
        if urlsplit(self.path).path != "/api/run":
            self._error(404, "Endpoint không tồn tại.")
            return
        jobs, token = services(self.server)
        tokens = self.headers.get_all("X-CSRF-Token", [])
        supplied = tokens[0] if len(tokens) == 1 else ""
        if not supplied.isascii() or not hmac.compare_digest(token, supplied):
            self._error(403, "Thiếu hoặc sai CSRF token; tải lại cấu hình trước khi gửi.")
            return
        payload = self._body()
        if payload is None:
            return
        try:
            request = decode_request(payload)
            if len(self.headers.get_all("Idempotency-Key", [])) != 1:
                raise ValueError("Cần một Idempotency-Key duy nhất.")
            job = jobs.submit(request, self.headers.get("Idempotency-Key", ""))
        except IdempotencyConflict as exc:
            self._error(409, str(exc))
        except JobBusy as exc:
            self._error(429, str(exc))
        except ValueError as exc:
            self._error(400, str(exc))
        except Exception:
            logger.exception("research_job_submission_failed")
            self._error(500, "Không khởi tạo được job; xem log server.")
        else:
            self._send_json(job, 202)

    def _body(self):
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get_all("Transfer-Encoding") or self.headers.get_all("Expect") or len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 8:
            self._error(400, "Cần một Content-Length hợp lệ; không hỗ trợ chunked/Expect.")
            return None
        length = int(lengths[0])
        if length > MAX_BODY_BYTES:
            self._error(413, "Payload vượt giới hạn 32 KiB.")
            return None
        if len(self.headers.get_all("Content-Type", [])) != 1 or self.headers.get_content_type() != "application/json" or self.headers.get_content_charset("utf-8") != "utf-8" or self.headers.get_all("Content-Encoding"):
            self._error(415, "Chỉ nhận application/json.")
            return None
        try:
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Incomplete body")
            return body
        except (TimeoutError, OSError, ValueError):
            self._error(408, "Không nhận đủ request trong thời hạn.")
            return None


def run_web_server(host="127.0.0.1", port=5000, auto_open=True):
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Web server chỉ được bind loopback IPv4; không dùng public host.")
    httpd = ThreadingHTTPServer((host, port), TrendToolServer)
    httpd.daemon_threads = True
    jobs, _ = services(httpd)
    url = f"http://{host}:{httpd.server_address[1]}"
    print(f"Product Trend Intelligence — local only: {url}")
    if auto_open:
        timer = threading.Timer(1, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        jobs.close()


if __name__ == "__main__":
    run_web_server()
