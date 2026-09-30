"""errors.bad-param -- malformed parameters are ``ERR badrequest``, never a guess.

`design.md` §3: a bad argument must be rejected up front.  Three independent
shapes, all measured (2026-10-01):

* ``ui.tree notanumber``  -> ``ERR badrequest ui.tree depth must be an integer, got: notanumber``
* ``ui.tree -1``          -> ``ERR badrequest ui.tree depth must be >= 0``
* ``ui.close`` (no id)    -> ``ERR badrequest usage: ui.close <viewId>``

The raw status line of each is kept verbatim in the evidence.
"""

from __future__ import annotations

from typing import List, Tuple

from ..runner import Case
from ._util import verdict

PROBES: List[str] = ["ui.tree notanumber", "ui.tree -1", "ui.close"]


def _action(ctx):
    return [(request, ctx.request(request)) for request in PROBES]


def _expect(ctx, result) -> Tuple[bool, str]:
    problems = []
    lines = []
    for request, response in result:
        lines.append("%s -> %r" % (request, response.status_line))
        if response.ok:
            problems.append("%s returned OK for a malformed parameter" % request)
        elif response.code != "badrequest":
            problems.append("%s code=%r, expected 'badrequest'" % (request, response.code))
        if not (response.message or "").strip():
            problems.append("%s has an empty message" % request)
    return verdict(problems, " | ".join(lines))


CASE = Case(
    name="errors.bad-param",
    group="errors",
    targets=("gs32", "ccs12"),
    description="malformed arguments return ERR badrequest with a message (never OK)",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
