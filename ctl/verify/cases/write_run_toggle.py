"""write.run-toggle -- a toggle command is **not** idempotent, and the bounds prove it.

`design.md` §4.3 / §7: ``cmd.run`` idempotence is **per-command**, not a property
of the method.  ``org.eclipse.ui.window.fullscreenmode`` is the measured
counter-example:

* 1st call -> ``OK``, the main shell bounds change (1024x768 -> 1440x900 here);
* 2nd call -> ``OK``, the bounds go **back**.

Both calls answer ``OK``, so only the read-back tells them apart.  The bounds are
read from ``ui.shells`` (the largest visible shell = the workbench window, the
same rule ``ui.tree`` uses).  Two calls restore the original geometry by
construction; ``rollback`` re-toggles if something went wrong, so the window is
never left fullscreen.
"""

from __future__ import annotations

import time
from typing import Tuple

from ..runner import Case
from ._util import main_shell, verdict

TOGGLE_COMMAND = "org.eclipse.ui.window.fullscreenmode"
#: Let the OS finish the resize before reading the shells back.
SETTLE = 0.6


def _shells(ctx):
    return ctx.request("ui.shells")


def _action(ctx):
    baseline = _shells(ctx)
    first = ctx.request("cmd.run %s" % TOGGLE_COMMAND)
    time.sleep(SETTLE)
    after_first = _shells(ctx)
    second = ctx.request("cmd.run %s" % TOGGLE_COMMAND)
    time.sleep(SETTLE)
    after_second = _shells(ctx)
    ctx.toggle_baseline = main_shell(baseline.text)      # for the rollback
    return {"baseline": baseline, "first": first, "after_first": after_first,
            "second": second, "after_second": after_second}


def _expect(ctx, result) -> Tuple[bool, str]:
    problems = []
    for label, response in (("1st cmd.run", result["first"]), ("2nd cmd.run", result["second"])):
        if not response.ok:
            problems.append("%s -> %r" % (label, response.status_line))

    before = main_shell(result["baseline"].text)
    first = main_shell(result["after_first"].text)
    second = main_shell(result["after_second"].text)
    if before is None or first is None or second is None:
        problems.append("ui.shells has no visible shell to measure (%r/%r/%r)"
                        % (before, first, second))
        return verdict(problems, "no measurable shell")

    geometry = lambda row: (row[1], row[2], row[3], row[4])   # noqa: E731
    if geometry(first) == geometry(before):
        problems.append("the 1st %s did not change the bounds: %s" % (TOGGLE_COMMAND, geometry(before)))
    if geometry(second) != geometry(before):
        problems.append("the 2nd %s did not restore the bounds: %s -> %s"
                        % (TOGGLE_COMMAND, geometry(before), geometry(second)))
    ctx.note("read-back: bounds %s -> %s -> %s (toggle is NOT idempotent)"
             % (geometry(before), geometry(first), geometry(second)))
    return verdict(problems, "shell=%r bounds=%s->%s->%s"
                   % (before[0], geometry(before), geometry(first), geometry(second)))


def _rollback(ctx):
    """Never leave the workbench fullscreen."""
    expected = getattr(ctx, "toggle_baseline", None)
    if expected is None:
        return
    current = main_shell(_shells(ctx).text)
    if current is None or (current[1], current[2], current[3], current[4]) == \
            (expected[1], expected[2], expected[3], expected[4]):
        return
    ctx.note("rollback toggle: %s" % ctx.request("cmd.run %s" % TOGGLE_COMMAND).status_line)
    time.sleep(SETTLE)
    restored = main_shell(_shells(ctx).text)
    ctx.note("rollback bounds=%s (expected %s)"
             % (restored and (restored[1], restored[2], restored[3], restored[4]),
                (expected[1], expected[2], expected[3], expected[4])))


CASE = Case(
    name="write.run-toggle",
    group="write",
    targets=("gs32", "ccs12"),
    description="fullscreenmode changes the main shell bounds and a 2nd call reverts them",
    action=_action,
    expect=_expect,
    rollback=_rollback,
    evidence=("raw:action",),
)
