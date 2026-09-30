"""Shared predicate helpers for the acceptance cases.

Assertions are expressed as computable predicates over the bridge payload; no
case hardcodes a length or a line count that drifts with the environment. Where
a numeric threshold is used, its source is named in the case.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ..runner import Skip  # re-exported so cases only import from here

__all__ = ["Skip", "search", "searchall", "kv", "verdict", "view_rows",
           "simple_ids", "int_or_none"]


def search(pattern: str, text: str, group: int = 1) -> Optional[str]:
    """First regex match (MULTILINE), or ``None``."""
    match = re.search(pattern, text, re.M)
    return match.group(group) if match else None


def searchall(pattern: str, text: str) -> List[str]:
    """All first-group matches (MULTILINE)."""
    return re.findall(pattern, text, re.M)


def kv(line: str) -> Dict[str, str]:
    """``key=value`` pairs on a single line (first occurrence wins)."""
    out: Dict[str, str] = {}
    for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_.\-]*)=(\S*)", line or ""):
        out.setdefault(key, value)
    return out


def kv_line(text: str, needle: str) -> Dict[str, str]:
    """``kv()`` of the first line containing ``needle``."""
    for line in (text or "").splitlines():
        if needle in line:
            return kv(line)
    return {}


def view_rows(text: str) -> List[Tuple[str, str]]:
    """``[(id, title_or_label), ...]`` from ``view id=... title=|label="..."`` rows."""
    return re.findall(r'^\s*view id=(\S+) (?:title|label)="([^"]*)"', text, re.M)


def persp_rows(text: str) -> List[Tuple[str, str]]:
    """``[(id, label), ...]`` from ``persp id=... label="..."`` rows."""
    return re.findall(r'^\s*persp id=(\S+) label="([^"]*)"', text, re.M)


def simple_ids(text: str) -> List[str]:
    """Bare ``  <id>`` rows (cmd.list and ui.viewids style, no spaces)."""
    return re.findall(r"^\s{2}(\S+)\s*$", text, re.M)


def int_or_none(value: Optional[str]) -> Optional[int]:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def verdict(problems: List[str], detail: str) -> Tuple[bool, str]:
    """``(passed, detail)`` with every failed predicate named in the detail."""
    if problems:
        return (False, detail + " | FAILED: " + "; ".join(problems))
    return (True, detail)
