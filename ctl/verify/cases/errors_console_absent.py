"""errors.console-absent -- an absent Console page must be an error, not silence.

`design.md` D3 / §3.4: ``ui.console`` fails with ``notfound`` when no Console
page exists.  An ``OK`` with an empty payload would be indistinguishable from
"there is no console", so an empty success is explicitly a **failure** here.

If this instance does happen to have an active console, the absent path simply
cannot be exercised -- that is recorded as a skip with the reason.
"""

from __future__ import annotations

from typing import Tuple

from ..runner import Case, Skip
from ._util import verdict


def _action(ctx):
    return ctx.request("ui.console")


def _expect(ctx, response) -> Tuple[bool, str]:
    if not response.ok:
        if response.code == "notfound":
            return verdict([], "status=%r code=notfound message=%r (absent-console path verified)"
                           % (response.status_line, response.message))
        return verdict(["code=%r, expected 'notfound' for an absent console" % response.code],
                       "status=%r code=%r message=%r"
                       % (response.status_line, response.code, response.message))

    payload = [line for line in response.payload if line.strip()]
    if not payload:
        return verdict(["OK with an empty payload: 'no console' is indistinguishable from 'empty console'"],
                       "status=%r payload=%r" % (response.status_line, response.payload))
    return Skip("an active console exists in this instance, so the absent-console path is not exercisable")


CASE = Case(
    name="errors.console-absent",
    group="errors",
    targets=("gs32", "ccs12"),
    description="ui.console returns ERR notfound when no console exists (never an empty OK)",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
