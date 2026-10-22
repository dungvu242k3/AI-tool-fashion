"""Local-only, bounded Ollama transport; no redirects, ambient auth or raw logs."""
import ipaddress
import logging
import math
import re
import time
from urllib.parse import urlsplit

import requests

from src.analyzers.analysis_policy import AnalysisPolicy
from src.analyzers.grounded_schema import output_schema
from src.analyzers.strict_json import AnalysisValidationError, strict_loads

logger = logging.getLogger(__name__)


class _NoAmbientAuth(requests.auth.AuthBase):
    def __call__(self, request):
        request.headers.pop("Authorization", None)
        return request


class GenerationError(ValueError):
    def __init__(self, code: str, *, repairable=False, http_status=None):
        self.code, self.repairable, self.http_status = code, repairable, http_status
        super().__init__(code)


def validate_local_model(model):
    if (not isinstance(model, str) or len(model) > 200
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?(?::[A-Za-z0-9][A-Za-z0-9_.-]*)?", model) is None
            or model.lower().endswith((":cloud", "-cloud"))):
        raise GenerationError("invalid_model_name")


def local_endpoint(base_url):
    if not isinstance(base_url, str) or len(base_url) > 256 or any(char.isspace() for char in base_url) or any(char in base_url for char in "\\%"):
        raise ValueError("Ollama endpoint must be an explicit loopback URL")
    try:
        parts = urlsplit(base_url)
        host = parts.hostname
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
        port = parts.port
    except (ValueError, TypeError):
        raise ValueError("Ollama endpoint must use localhost or a literal loopback address") from None
    if (not loopback or parts.scheme not in {"http", "https"} or parts.username or parts.password
            or parts.path not in {"", "/"} or parts.query or parts.fragment or (port is not None and not 1 <= port <= 65535)):
        raise ValueError("Ollama endpoint must be loopback without credentials, path, query or fragment")
    normalized_host = "127.0.0.1" if host == "localhost" else (f"[{host}]" if ":" in host else host)
    return f"{parts.scheme}://{normalized_host}{':' + str(port) if port is not None else ''}/api/generate"


class OllamaClient:
    def __init__(self, base_url, timeout, policy: AnalysisPolicy, session=None, monotonic=time.monotonic):
        if not isinstance(policy, AnalysisPolicy):
            raise TypeError("AnalysisPolicy required")
        self.url = local_endpoint(base_url)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 1 <= timeout <= 600:
            raise ValueError("Ollama timeout must be finite and within 1..600 seconds")
        self.timeout, self.policy, self.monotonic = timeout, policy, monotonic
        self._owned = session is None
        self.session = session if session is not None else requests.Session()
        if self._owned:
            self.session.trust_env = False

    def generate(self, model, prompt, system):
        validate_local_model(model)
        if not isinstance(prompt, str) or not isinstance(system, str):
            raise GenerationError("invalid_prompt")
        try:
            if len((system + prompt).encode("utf-8")) > self.policy.max_prompt_bytes:
                raise GenerationError("prompt_size_limit")
        except UnicodeError:
            raise GenerationError("invalid_prompt") from None
        response = None
        try:
            started = self.monotonic()
            response = self.session.post(
                self.url, json={"model": model, "prompt": prompt, "system": system, "stream": False,
                                "format": output_schema(), "options": {"temperature": 0,
                                    "num_predict": self.policy.max_output_tokens, "num_ctx": self.policy.context_tokens}},
                timeout=(min(5, self.timeout), self.timeout), allow_redirects=False, stream=True,
                auth=_NoAmbientAuth(), headers={"Authorization": "", "Cookie": ""},
                proxies={"http": None, "https": None, "all": None},
            )
            if response.status_code != 200:
                raise GenerationError("ollama_http_error", http_status=response.status_code)
            if response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise GenerationError("invalid_content_type", repairable=True)
            limit = self.policy.max_response_bytes * 2 + 4096
            body = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                if self.monotonic() - started > self.timeout:
                    raise GenerationError("generation_deadline_exceeded")
                if len(body) + len(chunk) > limit:
                    raise GenerationError("response_size_limit", repairable=True)
                body.extend(chunk)
            try:
                payload = strict_loads(body.decode("utf-8"), max_bytes=limit)
            except (UnicodeError, AnalysisValidationError):
                raise GenerationError("invalid_generation_envelope", repairable=True) from None
            if (not isinstance(payload, dict) or payload.get("done") is not True
                    or payload.get("done_reason") == "length" or not isinstance(payload.get("response"), str)):
                raise GenerationError("generation_incomplete", repairable=True)
            if len(payload["response"].encode("utf-8")) > self.policy.max_response_bytes:
                raise GenerationError("response_size_limit", repairable=True)
            return payload["response"]
        except requests.RequestException:
            logger.warning("ollama_transport_failed", extra={"error_code": "ollama_connection_error"})
            raise GenerationError("ollama_connection_error") from None
        finally:
            if response is not None:
                response.close()

    def close(self):
        if self._owned:
            self.session.close()
