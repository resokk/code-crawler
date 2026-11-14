"""Deterministic case-sensitive suffix routes shared by capture and registry."""

import re
from collections.abc import Mapping


def valid_suffix(suffix: str) -> bool:
    """Return whether a route is a simple or compound file suffix."""
    return re.fullmatch(r"\.[A-Za-z0-9_+-]+(?:\.[A-Za-z0-9_+-]+)*", suffix) is not None


def source_language(path: str, languages: Mapping[str, str]) -> str | None:
    """Choose the longest registered suffix, independent of registration order."""
    matches = [suffix for suffix in languages if path.endswith(suffix)]
    return languages[max(matches, key=len)] if matches else None
