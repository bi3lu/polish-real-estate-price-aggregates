"""Path and normalization helpers for project configuration."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def normalize_url(url: str) -> str:
    """Normalize project URLs loaded from environment-like sources.

    Args:
        url: Raw URL value.

    Returns:
        URL stripped of leading and trailing whitespace.
    """
    return url.strip()
