"""Small, dependency-free helpers shared across modules."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone
from typing import Iterable, Sequence
from urllib.parse import urlparse

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

#: Hostnames accepted as "local" without --allow-remote.
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0", "host.docker.internal"}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_NON_ALNUM = re.compile(r"[^A-Z0-9]")


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with a ``Z`` suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    """SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def normalize_for_match(text: str) -> str:
    """Upper-case and strip every non-alphanumeric character.

    Mirrors the Day 4 "normalized BLUE-42" idea: ``blue 42``, ``BLUE-42`` and
    ``B.L.U.E.42`` all normalize to ``BLUE42``.
    """
    return _NON_ALNUM.sub("", text.upper())


def split_sentences(text: str) -> list[str]:
    """Split text into rough sentences / lines. Good enough for hedge detection."""
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s and s.strip()]


def truncate(text: str, limit: int = 160) -> str:
    """Shorten ``text`` to ``limit`` characters, adding an ellipsis when cut."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Percentile with linear interpolation (same method as numpy's default).

    Returns ``None`` for an empty input so callers can render "n/a".
    """
    if not values:
        return None
    if not 0 <= pct <= 100:
        raise ValueError("pct must be between 0 and 100")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (pct / 100) * (len(ordered) - 1)
    low, high = math.floor(rank), math.ceil(rank)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (rank - low))


def safe_ratio(numerator: int | float, denominator: int | float) -> float | None:
    """Return ``numerator / denominator`` rounded to 4 dp, or ``None`` if the denominator is 0."""
    return round(numerator / denominator, 4) if denominator else None


def is_local_endpoint(url: str) -> bool:
    """True when ``url`` points at this machine (the only default-allowed target)."""
    host = (urlparse(url).hostname or "").lower()
    return host in LOCAL_HOSTS or host.endswith(".localhost")


def fmt_pct(value: float | None) -> str:
    """Format a 0..1 ratio as a percentage string."""
    return "n/a" if value is None else f"{value * 100:.1f}%"


def fmt_ms(value: float | None) -> str:
    """Format milliseconds for tables."""
    return "n/a" if value is None else f"{value:,.0f} ms"


def unique(items: Iterable[str]) -> list[str]:
    """De-duplicate while preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
