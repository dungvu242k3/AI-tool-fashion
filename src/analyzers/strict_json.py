"""Bounded strict JSON decoding before schema validation (no model repair)."""
import json
import math


class AnalysisValidationError(ValueError):
    """Only server-owned codes/paths; never echo model text or source secrets."""
    def __init__(self, code: str, path: str = "$"):
        self.code = code
        self.path = path
        super().__init__(f"{path}: {code}")

    def to_dict(self):
        return {"code": self.code, "path": self.path}


def strict_loads(text: str, *, max_bytes=65536, max_depth=12):
    if not isinstance(text, str):
        raise AnalysisValidationError("json_string_required")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        raise AnalysisValidationError("invalid_unicode") from None
    if size > max_bytes:
        raise AnalysisValidationError("response_size_limit")
    depth, in_string, escaped = 0, False, False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > max_depth:
                raise AnalysisValidationError("json_depth_limit")
        elif char in "]}":
            depth -= 1

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise AnalysisValidationError("duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(_):
        raise AnalysisValidationError("non_finite_number")

    try:
        payload = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except AnalysisValidationError:
        raise
    except (ValueError, RecursionError):
        raise AnalysisValidationError("invalid_json") from None

    budget = [1500]
    def bounded(value):
        budget[0] -= 1
        if budget[0] < 0:
            raise AnalysisValidationError("json_node_limit")
        if isinstance(value, dict):
            for key, item in value.items():
                bounded(key)
                bounded(item)
        elif isinstance(value, list):
            for item in value:
                bounded(item)
        elif isinstance(value, str):
            if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
                raise AnalysisValidationError("invalid_unicode")
        elif not isinstance(value, bool) and isinstance(value, (int, float)):
            if not -(2**53 - 1) <= value <= 2**53 - 1 or not math.isfinite(value):
                raise AnalysisValidationError("unsafe_number")
    bounded(payload)
    return payload
