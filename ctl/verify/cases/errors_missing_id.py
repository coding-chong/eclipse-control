"""errors.missing-id -- ``notfound`` for ids that do not exist.

Two independent surfaces are checked so the contract is not one luck:

* ``ui.close`` on a view that is not open in the active page;
* ``cmd.query`` on a command id that is not registered.

Both must return ``ERR notfound`` (not ``OK``, not ``badrequest``).
"""

from __future__ import annotations

from typing import Tuple

from ..runner import Case
from ._util import verdict

MISSING_VIEW = "com.gs.definitely.not.a.view"
MISSING_COMMAND = "com.gs.definitely.not.a.command"


def _action(ctx):
    close = ctx.request("ui.close %s" % MISSING_VIEW)
    query = ctx.request("cmd.query %s" % MISSING_COMMAND)
    return close, query


def _expect(ctx, result) -> Tuple[bool, str]:
    close, query = result
    problems = []
    for label, response in (("ui.close %s" % MISSING_VIEW, close),
                            ("cmd.query %s" % MISSING_COMMAND, query)):
        if response.ok:
            problems.append("%s returned OK for a non-existent id" % label)
        elif response.code != "notfound":
            problems.append("%s code=%r, expected 'notfound'" % (label, response.code))
        if response.message is not None and response.message.startswith("java."):
            problems.append("%s leaked a bare exception string: %r" % (label, response.message))
    return verdict(problems, "ui.close=%r | cmd.query=%r"
                   % (close.status_line, query.status_line))


CASE = Case(
    name="errors.missing-id",
    group="errors",
    targets=("gs32", "ccs12"),
    description="ui.close/cmd.query on non-existent ids return ERR notfound",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
