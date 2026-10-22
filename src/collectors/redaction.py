"""Sanitize request diagnostics without retaining auth headers, cookies or bodies."""
import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE_KEY = re.compile(r"token|secret|password|passwd|authorization|cookie|signature|credential|api[_-]?key|access[_-]?key|^key$", re.I)


def redact_query(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if SENSITIVE_KEY.search(str(key)) else redact_query(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_query(item) for item in value]
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                return json.dumps(redact_query(json.loads(value)), ensure_ascii=False)
            except ValueError:
                pass
        return value
    return value


def redact_url(url: str) -> str:
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    authority = f"{hostname}:{parsed.port}" if parsed.port is not None else hostname
    query = [
        (key, "[REDACTED]" if SENSITIVE_KEY.search(key) else redact_query(value))
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, authority, parsed.path, urlencode(query), ""))
