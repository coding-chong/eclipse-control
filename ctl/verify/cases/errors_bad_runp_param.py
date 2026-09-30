"""errors.bad-runp-param -- an unresolvable parameter id fails **and lists the candidates**.

`cmd.runp` accepts short parameter names (``viewId=…``), which is a convenience
and a trap: the bridge refuses to guess.  Measured (2026-10-01):

```
cmd.runp org.eclipse.ui.views.showView id=x
ERR notfound command org.eclipse.ui.views.showView has no parameter id;
    declared: viewId (org.eclipse.ui.views.showView.viewId),
              secondaryId (org.eclipse.ui.views.showView.secondaryId),
              makeFast (org.eclipse.ui.views.showView.makeFast)
```

so the contract is *two* things: an error code, and the candidate list that makes
the error actionable.  A second probe covers the missing-argument shape
(``cmd.runp <id>`` with no ``k=v``).
"""

from __future__ import annotations

from typing import Tuple

from ..runner import Case
from ._util import verdict

UNCALLABLE = "cmd.runp org.eclipse.ui.views.showView id=x"
NO_PARAMETER = "cmd.runp org.eclipse.ui.views.showView"


def _action(ctx):
    return [(UNCALLABLE, ctx.request(UNCALLABLE)),
            (NO_PARAMETER, ctx.request(NO_PARAMETER))]


def _expect(ctx, result) -> Tuple[bool, str]:
    problems = []
    lines = []
    for request, response in result:
        lines.append("%s -> %r" % (request, response.status_line))
        if response.ok:
            problems.append("%s returned OK for an unresolvable parameter" % request)
        elif response.code not in ("notfound", "badrequest"):
            problems.append("%s code=%r, expected 'notfound' or 'badrequest'"
                            % (request, response.code))
        if not (response.message or "").strip():
            problems.append("%s has an empty message" % request)

    message = result[0][1].message or ""
    if "declared:" not in message and "matches" not in message:
        problems.append("the notfound message does not list candidates: %r" % message)
    candidates = message.split("declared:")[-1].split("matches")[-1]
    if candidates.count("(") < 2:
        problems.append("fewer than two candidates listed: %r" % candidates)
    return verdict(problems, " | ".join(lines) + " | candidates=%r" % candidates.strip()[:160])


CASE = Case(
    name="errors.bad-runp-param",
    group="errors",
    targets=("gs32", "ccs12"),
    description="an unresolvable cmd.runp parameter fails and names the declared candidates",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
