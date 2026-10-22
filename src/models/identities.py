"""Stable record identity, shared by validation and processing; never by display title."""


def keyword_identity(record) -> tuple[str, str, str]:
    return record.keyword.strip().casefold(), record.geo, record.timeframe


def record_identity(source: str, record) -> tuple:
    if source == "google_trends":
        return keyword_identity(record)
    if source == "amazon":
        return (record.asin,)
    if source == "reddit":
        return (record.post_id,)
    raise ValueError("Unsupported evidence source")
