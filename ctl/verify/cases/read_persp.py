"""read.persp -- `ui.persp`.

`design.md` §6: the payload must list the registered perspectives and the active
one.  Predicate: the active id is non-null and is one of the listed ids.
"""

from __future__ import annotations

from typing import Tuple

from ..runner import Case
from ._util import int_or_none, persp_rows, search, verdict


def _action(ctx):
    return ctx.request("ui.persp")


def _expect(ctx, response) -> Tuple[bool, str]:
    text = response.text
    count = int_or_none(search(r"^perspectives=(\d+)", text))
    active = search(r"^active=(\S+)", text)
    rows = persp_rows(text)
    ids = [pid for pid, _label in rows]

    problems = []
    if not response.ok:
        problems.append("expected OK, got %r" % response.status_line)
    if count is None:
        problems.append("no perspectives= field")
    elif count < 1:
        problems.append("perspectives=%d, expected >= 1" % count)
    if count is not None and count != len(rows):
        problems.append("perspectives=%d but %d persp rows" % (count, len(rows)))
    if not active or active == "null":
        problems.append("active perspective is %r" % active)
    elif ids and active not in ids:
        problems.append("active %r is not among the registered ids" % active)
    if any(not label.strip() for _pid, label in rows):
        problems.append("a perspective row has an empty label")
    return verdict(problems, "perspectives=%s(rows=%d) active=%r listed=%s"
                   % (count, len(rows), active, active in ids if active else False))


CASE = Case(
    name="read.persp",
    group="read",
    targets=("gs32", "ccs12"),
    description="ui.persp lists perspectives and reports an active one from that list",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
