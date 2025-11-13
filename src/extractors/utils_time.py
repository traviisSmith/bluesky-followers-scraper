import datetime as _dt
from typing import Optional

def ensure_iso8601(value: Optional[str]) -> Optional[str]:
    """
    Ensure a timestamp string is valid ISO 8601.

    - Accepts common Bluesky/ISO patterns like '2023-07-27T23:07:25.712Z'.
    - Converts 'Z' suffix to '+00:00'.
    - Returns the original string if parsing fails.
    """
    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = _dt.datetime.fromisoformat(text)
        # Normalize microseconds precision to milliseconds (optional)
        micro = dt.microsecond
        ms = (micro // 1000) * 1000
        dt = dt.replace(microsecond=ms)
        return dt.isoformat()
    except Exception:  # noqa: BLE001
        # If anything goes wrong, just return the original value.
        return value

def sanitize_output_format(fmt: Optional[str]) -> Optional[str]:
    """
    Normalize output format aliases.

    Supports: json, csv, xml, html, rss
    """
    if not fmt:
        return None
    normalized = fmt.strip().lower()
    aliases = {
        "json": "json",
        "csv": "csv",
        "xml": "xml",
        "html": "html",
        "htm": "html",
        "rss": "rss",
    }
    return aliases.get(normalized, normalized)