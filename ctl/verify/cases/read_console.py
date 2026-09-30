"""read.console -- `ui.console [--tail <n>]`.

`design.md` §6: the payload carries the active console's name and the tail of
its text.  D3 makes the bridge **fail with ``notfound``** when no console page
exists (rather than an empty success that would be indistinguishable from "no
console").

Consequence for this case: on an instance with no Console page the read path is
simply not exercisable, so it is recorded as an explicit **skip with the
bridge's own reason** -- not scored as a failure, and not silently green.
"""

from __future__ import annotations

from typing import Tuple

from ..runner import Case, Skip
from ._util import int_or_none, search, verdict

TAIL = 20


def _action(ctx):
    return ctx.request("ui.console --tail %d" % TAIL)


def _expect(ctx, response) -> Tuple[bool, str]:
    if not response.ok:
        if response.code == "notfound":
            return Skip("no console to read in this instance: %s" % response.message)
        return verdict(["unexpected error from ui.console: %r" % response.status_line],
                       "status=%r code=%r message=%r"
                       % (response.status_line, response.code, response.message))

    text = response.text
    name = search(r'^console name="([^"]*)"', text)
    total = int_or_none(search(r"^consoles total=(\d+)", text))
    lines = int_or_none(search(r"^text lines=(\d+)", text))
    returned = int_or_none(search(r"^text returned=(\d+)", text)) or int_or_none(
        search(r"^text lines=\d+ returned=(\d+)", text))
    available = search(r"^textAvailable=(\w+)", text)

    problems = []
    if name is None:
        problems.append("missing 'console name=\"...\"' line")
    if total is None or total < 1:
        problems.append("consoles total=%r, expected >= 1" % total)
    if lines is None:
        problems.append("missing 'text lines=... returned=...' summary")
    if available == "false" and lines is not None and lines != 0:
        problems.append("textAvailable=false but lines=%d" % lines)
    if available != "false" and lines is not None and returned is not None:
        if lines >= 1 and returned < 1:
            problems.append("text lines=%d but returned=%d (tail selection failed)" % (lines, returned))
    return verdict(problems, "name=%r consoles=%s lines=%s returned=%s textAvailable=%s"
                   % (name, total, lines, returned, available or "true"))


CASE = Case(
    name="read.console",
    group="read",
    targets=("gs32", "ccs12"),
    description="ui.console names the active console and returns its tail (skips when none exists)",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
