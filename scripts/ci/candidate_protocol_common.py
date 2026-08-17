from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse


def parse_rfc3339_time(value: str, field: str = "timestamp") -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty RFC3339 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"{field} must be a valid RFC3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include Z or an explicit UTC offset")
    return parsed


def validate_https_url(value: str, field: str = "url") -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty HTTPS URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(f"{field} must use HTTPS and include a hostname")
    return value
