"""Input and export string cleanup."""

from __future__ import annotations

import re
import unicodedata

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean_name(name: str | None, fallback: str) -> str:
    if name is None:
        return fallback
    text = _CONTROL.sub(" ", name)
    text = " ".join(text.split())
    text = text[:120].strip()
    return text or fallback


def csv_safe(value: object) -> str | int | float:
    """Keep numbers numeric and stop spreadsheet formula injection in text cells."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return ""
        return round(value, 4)
    text = _CONTROL.sub(" ", str(value))
    text = " ".join(text.split())
    if text[:1] in {"=", "+", "-", "@"}:
        return "'" + text
    return text


def ascii_fold(value: object) -> str:
    text = "" if value is None else str(value)
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(folded.split())


def slug(value: object) -> str:
    text = ascii_fold(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60] or "region"
