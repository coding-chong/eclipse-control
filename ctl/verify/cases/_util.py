"""Shared predicate helpers for the acceptance cases.

Assertions are expressed as computable predicates over the bridge payload; no
case hardcodes a length or a line count that drifts with the environment. Where
a numeric threshold is used, its source is named in the case.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple

from ..runner import Skip  # re-exported so cases only import from here

__all__ = ["Skip", "search", "searchall", "kv", "verdict", "view_rows",
           "int_or_none", "parts_counts", "view_ids", "editor_rows",
           "visible_shells", "main_shell", "dialog_lines", "parse_appeared",
           "applied_verdict"]


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


def view_rows(text: str) -> List[Tuple[str, str]]:
    """``[(id, title_or_label), ...]`` from ``view id=... title=|label="..."`` rows."""
    return re.findall(r'^\s*view id=(\S+) (?:title|label)="([^"]*)"', text, re.M)


def persp_rows(text: str) -> List[Tuple[str, str]]:
    """``[(id, label), ...]`` from ``persp id=... label="..."`` rows."""
    return re.findall(r'^\s*persp id=(\S+) label="([^"]*)"', text, re.M)


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


# --------------------------------------------------------------------------- #
# `ui.parts` / `ui.shells` payload helpers (write-surface cases)
# --------------------------------------------------------------------------- #

def parts_counts(text: str) -> Dict[str, Optional[int]]:
    """``{"views": n, "editors": n}`` from an ``ui.parts`` payload (None = absent)."""
    return {"views": int_or_none(search(r"^views=(\d+)", text)),
            "editors": int_or_none(search(r"^editors=(\d+)", text))}


def view_ids(text: str) -> List[str]:
    """Every ``view id=…`` in an ``ui.parts`` payload, in page order."""
    return searchall(r"^\s*view id=(\S+)", text)


def editor_rows(text: str) -> List[Tuple[str, str]]:
    """``[(id, name), ...]`` from an ``ui.parts`` payload."""
    return re.findall(r'^\s*editor id=(\S+) name="([^"]*)"', text, re.M)


def visible_shells(text: str) -> List[Tuple[str, int, int, int, int]]:
    """``[(title, x, y, w, h), ...]`` for ``vis=true`` rows of ``ui.shells``."""
    rows = []
    for match in re.finditer(
            r'shell text="([^"]*)" vis=true b=Rectangle \{(-?\d+), (-?\d+), (\d+), (\d+)\}',
            text):
        title = match.group(1)
        x, y, w, h = (int(value) for value in match.groups()[1:])
        rows.append((title, x, y, w, h))
    return rows


def main_shell(text: str) -> Optional[Tuple[str, int, int, int, int]]:
    """The largest visible shell -- the workbench window (same rule as ``ui.tree``)."""
    rows = visible_shells(text)
    if not rows:
        return None
    return max(rows, key=lambda row: row[3] * row[4])


def dialog_lines(text: str) -> List[str]:
    """``dialog=…`` payload lines, verbatim."""
    return [line.strip() for line in (text or "").splitlines()
            if line.strip().startswith("dialog=")]


def parse_appeared(line: str) -> List[str]:
    """Titles of a bridge ``dialog=appeared "<a>", "<b>"`` line."""
    return re.findall(r'"([^"]*)"', line or "")


# --------------------------------------------------------------------------- #
# The `applied` verdict (P3.8): did a write that TIMED OUT still take effect?
# --------------------------------------------------------------------------- #

def applied_verdict(pre: Optional[Iterable[str]], post: Optional[Iterable[str]]) -> str:
    """``"yes"`` / ``"no"`` / ``"unknown"`` -- the semantic carrier for ``applied=``.

    ``ERR timeout`` says the *wait* ended, not that the action did not run
    (``protocol.md`` 4.2; the bridge's own note is on ``sys.help``), so a timed-out
    write can only be judged by a read-back taken **after** the modal was answered
    and diffed against the snapshot taken **before** the write:

    * ``yes``     -- the read-back moved, so the timed-out write did take effect;
    * ``no``      -- the read-back is unchanged, so nothing observable happened;
    * ``unknown`` -- the read-back itself failed on one side.  It is deliberately
      *not* folded into ``no``: "I could not look" must never read as "nothing
      happened".

    A verdict is only worth something if the diff is known to be *sensitive*, so
    every user of this helper has to pair it with a control (a perturbation it
    knows the action undoes, or one it knows the action cannot touch).
    """
    if pre is None or post is None:
        return "unknown"
    return "no" if set(pre) == set(post) else "yes"
