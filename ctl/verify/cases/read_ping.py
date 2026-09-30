"""read.ping -- liveness floor.

`design.md` §6: ``sys.ping`` 恒 ``OK``.  Assertion is a predicate over the raw
payload, and the raw response is kept as evidence.
"""

from __future__ import annotations

from typing import Tuple

from ..runner import Case
from ._util import verdict


def _action(ctx):
    return ctx.request("sys.ping")


def _expect(ctx, response) -> Tuple[bool, str]:
    problems = []
    if not response.ok:
        problems.append("expected OK, got %r" % response.status_line)
    body = response.text.strip()
    if response.ok and "pong" not in body.lower():
        problems.append("payload carries no pong: %r" % body)
    if response.timed_out:
        problems.append("client timeout marker present")
    return verdict(problems, "status=%r body=%r elapsed=%.3fs"
                   % (response.status_line, body, response.elapsed))


CASE = Case(
    name="read.ping",
    group="read",
    targets=("gs32", "ccs12"),
    description="sys.ping returns OK with a pong payload (bridge is alive)",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
