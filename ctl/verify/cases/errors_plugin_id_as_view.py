"""errors.plugin-id-as-view -- the regression lock for "``OK`` is not trustworthy".

The defect (measured 2026-10-01, and again by this case):

```
cmd.runp org.eclipse.ui.views.showView viewId=com.gs.liveview
OK                                        <- the protocol says success
executeCommand returned: null             <- the platform says success
dialog=appeared "Problem Occurred"        <- Eclipse disagrees
ui.parts                                  -> views 8 -> 8, nothing happened
```

``com.gs.liveview`` is a *plugin* id used where a *view* id belongs, so
``showView`` fails asynchronously and pops an error box.  A verifier that trusts
the status line plus the read-back diff reads this as **PASS** -- "nothing
changed" is exactly what a successful *idempotent* write looks like
(``write.runp-show-view`` proves the other branch of that fork).

**This case passes when the guarded verdict says FAIL/SUSPECT.**  That is the
whole point: the assertion locks in the *judgement*, not the bug.  Evidence
carries the screenshot path, the title read from the window, and the dismissal
action (close the dialog, then read back) -- the three things a human would do.

The archived PNG (``shots/errors.plugin-id-as-view-*-Problem_Occurred.png``)
reads, verbatim::

    Problem Occurred
    View could not be found: com.gs.liveview
    org.eclipse.core.commands.ExecutionException
      [ OK ]  [ Details >> ]

so the second observation channel does not merely say "a window appeared", it
says *what the window says* -- which is what turns "nothing changed" from a PASS
into a FAIL.

With the screen guard switched off (``verify --no-screen-guard``) the same run
demonstrates the hole: the naive verdict reads PASS and this case fails open.
"""

from __future__ import annotations

from typing import Tuple

from ..runner import Case, Skip
from ._util import dialog_lines, parse_appeared, verdict, view_ids

#: A plugin id, not a view id -- the measured trap (`skill/SKILL.md` §反例).
REQUEST = "cmd.runp org.eclipse.ui.views.showView viewId=com.gs.liveview"


def _action(ctx):
    before = ctx.request("ui.parts")
    response = ctx.request(REQUEST)
    return {"before": before, "response": response}


def _expect(ctx, result) -> Tuple[bool, str]:
    response = result["response"]
    before = result["before"]

    if not response.ok:
        # The bridge was fixed to fail this up front: the OK-lies path is gone.
        raise Skip("bogus viewId now answers %r; the OK-lies path is not exercisable"
                   % response.status_line)

    after = ctx.request("ui.parts")
    unchanged = set(view_ids(before.text)) == set(view_ids(after.text))
    views = len(view_ids(after.text))
    bridge = dialog_lines("\n".join(response.payload))
    appeared = [line for line in bridge if line.startswith("dialog=appeared")]
    titles = [title for line in appeared for title in parse_appeared(line)]

    problems = []
    if not unchanged:
        problems.append("the view set DID change (%d views) -- the trap did not reproduce "
                        "as measured; re-measure before trusting this case" % views)
    if not ctx.guarded:
        problems.append("SCREEN GUARD OFF: with only the status line + read-back diff this "
                        "write reads as PASS (OK, views unchanged).  Re-run without "
                        "--no-screen-guard to exercise the guard")
    if not ctx.dialogs:
        problems.append("the independent window enumeration saw no new window -- expected the "
                        "'Problem Occurred' box (screenshots: %s)"
                        % [item["screenshot"] for item in ctx.dialogs])
    if not appeared:
        problems.append("the bridge reported no 'dialog=appeared' line: %r" % bridge)

    naive = "PASS" if (response.ok and unchanged) else "FAIL"
    guarded = "FAIL/SUSPECT" if (ctx.guarded and ctx.dialogs) else "unverified"
    shots = "; ".join(str(item["screenshot"] or "<not written>") for item in ctx.dialogs)
    seen = "; ".join('hwnd=%s class=%s title=%r' % (item["hwnd"], item["class"], item["title"])
                     for item in ctx.dialogs)
    ctx.note("verdict: naive(status+read-back) = %s | guarded(screen+channels) = %s"
             % (naive, guarded))
    ctx.note("action taken on the evidence: dismissed the dialog (%s), then read ui.parts"
             % (seen or "none"))
    return verdict(problems,
                   "protocol=%r views=%d (unchanged=%s) titles=%r bridge=%r screen=[%s] "
                   "shots=[%s] naive verdict=%s -> guarded verdict=%s"
                   % (response.status_line, views, unchanged, titles,
                      appeared[0] if appeared else None, seen, shots, naive, guarded))


CASE = Case(
    name="errors.plugin-id-as-view",
    group="errors",
    targets=("gs32", "ccs12"),
    description="a write that answers OK, changes nothing and pops a dialog is judged FAIL/SUSPECT",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
    # The dialog IS the expected outcome here, so its appearance is a PASS...
    expects_dialog=True,
    # ...and this case must always run under the guard, whatever its group.
    screen_guard=True,
)
