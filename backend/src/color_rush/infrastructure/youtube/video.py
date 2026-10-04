from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from color_rush.domain.errors import InvalidCommandError

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def parse_video_ref(value: str) -> str:
    """Accept a video ID or supported YouTube URL. Does not fetch the URL."""
    text = value.strip()
    if _VIDEO_ID.match(text):
        return text
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        raise InvalidCommandError("unsupported video reference")
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
        if _VIDEO_ID.match(candidate):
            return candidate
        raise InvalidCommandError("unsupported video reference")
    query_id = parse_qs(parsed.query).get("v", [None])[0]
    if query_id and _VIDEO_ID.match(query_id):
        return query_id
    parts = [item for item in parsed.path.split("/") if item]
    if len(parts) >= 2 and parts[0] in {"live", "shorts", "embed"} and _VIDEO_ID.match(parts[1]):
        return parts[1]
    raise InvalidCommandError("unsupported video reference")
