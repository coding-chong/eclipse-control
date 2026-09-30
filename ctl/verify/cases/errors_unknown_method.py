"""errors.unknown-method -- the protocol's badrequest contract.

`design.md` §3 fixes the error shape; an unknown method must come back as
``ERR badrequest ...`` and never as a bare exception string.
"""

from __future__ import annotations

from typing import Tuple

from ..runner import Case
from ._util import verdict

METHOD = "nosuch.method"


def _action(ctx):
    return ctx.request(METHOD)


def _expect(ctx, response) -> Tuple[bool, str]:
    problems = []
    if response.ok:
        problems.append("unknown method returned OK: %r" % response.status_line)
    if response.code != "badrequest":
        problems.append("code=%r, expected 'badrequest'" % response.code)
    if "unknown method" not in (response.message or ""):
        problems.append("message does not name the unknown method: %r" % response.message)
    return verdict(problems, "status=%r code=%r message=%r"
                   % (response.status_line, response.code, response.message))


CASE = Case(
    name="errors.unknown-method",
    group="errors",
    targets=("gs32", "ccs12"),
    description="an unknown method returns ERR badrequest (never a bare exception)",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
