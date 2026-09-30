"""errors.unhandled -- "the command exists but cannot run here" is an error code.

`design.md` §3: the closed set has both ``unhandled`` and ``disabled``.  A
command that is *defined* but unreachable in the current context must say so --
``OK`` here would be the same lie as the bogus-viewId case, only quieter.

Two probes whose unavailability is structural, not focus-dependent (measured
2026-10-01, verified again with an editor focused):

* ``org.eclipse.debug.ui.commands.Resume`` -- no debug session exists, so the
  handler is never enabled -> ``ERR disabled``;
* ``org.eclipse.ui.edit.redo`` -- nothing was ever typed into an editor, so the
  redo history is empty -> ``ERR unhandled`` / ``ERR disabled``.

``org.eclipse.ui.edit.selectAll`` used to be the probe here, but it is
**focus-dependent**: it answers ``ERR unhandled`` with the focus outside an
editor and ``OK`` once an editor is focused.  It is still run and its status line
pasted verbatim, but it is *evidence, not an assertion* -- asserting on it would
make the errors group flip with focus.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from ..runner import Case
from ._util import verdict

#: (request, why it must not be available here)
PROBES: List[Tuple[str, str]] = [
    ("cmd.run org.eclipse.debug.ui.commands.Resume", "no debug session is active"),
    ("cmd.run org.eclipse.ui.edit.redo", "no edit history exists"),
]

#: Recorded verbatim, not asserted (focus-dependent -- see the module docstring).
OBSERVED: List[str] = ["cmd.run org.eclipse.ui.edit.selectAll"]

_SHAPE = re.compile(r"^ERR (unhandled|disabled)\b")


def _action(ctx):
    asserted = [(request, reason, ctx.request(request)) for request, reason in PROBES]
    observed = [(request, ctx.request(request)) for request in OBSERVED]
    return asserted, observed


def _expect(ctx, result) -> Tuple[bool, str]:
    asserted, observed = result
    problems = []
    lines = []
    for request, reason, response in asserted:
        lines.append("%s -> %r" % (request, response.status_line))
        if response.ok:
            problems.append("%s returned OK although %s" % (request, reason))
            continue
        if not _SHAPE.match(response.status_line):
            problems.append("%s -> %r, expected 'ERR unhandled' or 'ERR disabled'"
                            % (request, response.status_line))
        if not (response.message or "").strip():
            problems.append("%s has an empty message" % request)
    for request, response in observed:
        ctx.note("observed (not asserted, focus-dependent): %s -> %r"
                 % (request, response.status_line))
    return verdict(problems, " | ".join(lines))


CASE = Case(
    name="errors.unhandled",
    group="errors",
    targets=("gs32", "ccs12"),
    description="a defined-but-unavailable command returns ERR unhandled/disabled (never OK)",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
