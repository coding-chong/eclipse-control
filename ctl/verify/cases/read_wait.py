"""read.wait -- `sys.wait [<ms>|jobs-idle]`.

`design.md` §6 / D2: the payload carries ``waited_ms`` / ``idle`` / the pending
job count, and a wait that exhausts its budget is a **normal ``OK``** with
``idle=false`` -- *not* ``ERR timeout``.

So this case has both paths:
* positive: ``sys.wait jobs-idle`` returns OK and ``idle`` is consistent with
  the pending count;
* negative: ``sys.wait 0`` (budget exhausted immediately) still returns OK and
  must **not** be an ``ERR timeout``.
"""

from __future__ import annotations

from typing import Tuple

from ..runner import Case
from ._util import int_or_none, search, verdict


def _action(ctx):
    idle = ctx.request("sys.wait jobs-idle")
    zero = ctx.request("sys.wait 0")
    return idle, zero


def _check(label, response, problems):
    text = response.text
    mode = search(r"^mode=(\S+)", text)
    waited = int_or_none(search(r"^waited_ms=(\d+)", text))
    idle = search(r"^idle=(\w+)", text)
    pending = int_or_none(search(r"^pending=(\d+)", text))
    if not response.ok:
        problems.append("%s -> %r (a wait that exhausts its budget must still be OK)"
                        % (label, response.status_line))
    if mode is None or waited is None or idle is None or pending is None:
        problems.append("%s: missing mode/waited_ms/idle/pending" % label)
    elif idle not in ("true", "false"):
        problems.append("%s: idle=%r is not a boolean" % (label, idle))
    elif (idle == "true") != (pending == 0):
        problems.append("%s: idle=%s but pending=%d (inconsistent)" % (label, idle, pending))
    return mode, waited, idle, pending


def _expect(ctx, result) -> Tuple[bool, str]:
    idle_response, zero_response = result
    problems = []
    i_mode, i_waited, i_idle, i_pending = _check("sys.wait jobs-idle", idle_response, problems)
    z_mode, z_waited, z_idle, z_pending = _check("sys.wait 0", zero_response, problems)

    if i_mode is not None and i_mode != "jobs-idle":
        problems.append("sys.wait jobs-idle reported mode=%r" % i_mode)
    if z_mode is not None and z_mode != "budget":
        problems.append("sys.wait 0 reported mode=%r" % z_mode)
    if zero_response.code == "timeout":
        problems.append("sys.wait 0 returned ERR timeout; design says budget exhaustion is OK/idle=false")
    return verdict(problems, "jobs-idle: waited_ms=%s idle=%s pending=%s | budget0: waited_ms=%s idle=%s pending=%s"
                   % (i_waited, i_idle, i_pending, z_waited, z_idle, z_pending))


CASE = Case(
    name="read.wait",
    group="read",
    targets=("gs32", "ccs12"),
    description="sys.wait returns OK with waited_ms/idle/pending; an exhausted budget is OK, not ERR timeout",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
