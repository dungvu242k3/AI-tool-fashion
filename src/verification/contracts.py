"""Safe verification errors: codes/paths, never provider bodies or credentials."""


class AuditFailure(ValueError):
    def __init__(self, code: str, path: str = "$"):
        self.code, self.path = code, path
        super().__init__(f"{code} at {path}")


def check(condition, code, path="$"):
    if not condition:
        raise AuditFailure(code, path)
