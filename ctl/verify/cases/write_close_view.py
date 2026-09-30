"""write.close-view -- `ui.close` removes a view, and closing it twice is an error.

`design.md` §4.3 + the measured contract (2026-10-01):

* ``ui.close <id>`` on an open view -> ``OK``, ``views`` **-1**, the id is gone
  (the payload also reports ``before: views=N`` / ``after: views=N-1``);
* the same call again -> ``ERR notfound`` and **no** further change.  A second
  ``OK`` would make "already closed" indistinguishable from "closed now".

The view is opened in ``pre`` (setup), so the guarded action is exactly the two
closes and the case ends in the state it started in.
"""

from __future__ import annotations

from typing import Tuple

from ..runner import Case, Skip
from ._util import parts_counts, verdict, view_ids

#: `com.gs` + this suffix is the vendor memory view (id measured, not guessed).
VIEW_SUFFIX = ".memory.view"


def _view_id(ctx) -> str:
    prefix = ctx.target.vendor_prefix
    if not prefix:
        raise Skip("target %s declares no vendor_prefix" % ctx.target.name)
    return prefix + VIEW_SUFFIX


def _pre(ctx):
    """Guarantee the view is open before the guarded action runs."""
    view = _view_id(ctx)
    parts = ctx.request("ui.parts")
    opened = None
    if view not in view_ids(parts.text):
        opened = ctx.request("cmd.runp org.eclipse.ui.views.showView viewId=%s" % view)
        parts = ctx.request("ui.parts")
    if view not in view_ids(parts.text):
        raise Skip("view %s cannot be opened on this instance" % view)
    counts = parts_counts(parts.text)
    ctx.note("setup: %s open, views=%s (opened here: %s)"
             % (view, counts["views"], opened is not None))
    return "%s open (%s)" % (view, counts)


def _action(ctx):
    view = _view_id(ctx)
    base = ctx.request("ui.parts")
    first = ctx.request("ui.close %s" % view)
    mid = ctx.request("ui.parts")
    again = ctx.request("ui.close %s" % view)
    after = ctx.request("ui.parts")
    return {"view": view, "base": base, "first": first, "mid": mid,
            "again": again, "after": after}


def _expect(ctx, result) -> Tuple[bool, str]:
    view = result["view"]
    base, first, mid = result["base"], result["first"], result["mid"]
    again, after = result["again"], result["after"]
    problems = []

    if not first.ok:
        problems.append("ui.close on an open view -> %r" % first.status_line)
    counts0 = parts_counts(base.text)
    counts1 = parts_counts(mid.text)
    counts2 = parts_counts(after.text)
    v0, v1, v2 = counts0["views"], counts1["views"], counts2["views"]
    if None in (v0, v1, v2):
        problems.append("ui.parts did not report views= (%r/%r/%r)"
                        % (counts0, counts1, counts2))
    else:
        if v1 != v0 - 1:
            problems.append("ui.close did not remove exactly one view: views %d -> %d" % (v0, v1))
        if v2 != v1:
            problems.append("the 2nd ui.close changed views after the error: %d -> %d" % (v1, v2))
    if view in view_ids(mid.text):
        problems.append("%s is still listed after ui.close" % view)
    if again.ok:
        problems.append("the 2nd ui.close returned OK: %r (expected ERR notfound)"
                        % again.status_line)
    elif again.code != "notfound":
        problems.append("the 2nd ui.close code=%r, expected 'notfound'" % again.code)
    if view in view_ids(after.text):
        problems.append("%s reappeared after the failed ui.close" % view)

    ctx.note("read-back: views %s -> %s -> %s; 2nd close -> %r"
             % (v0, v1, v2, again.status_line))
    return verdict(problems, "view=%s views=%s->%s->%s; 2nd close=%r code=%r"
                   % (view, v0, v1, v2, again.status_line, again.code))


def _rollback(ctx):
    """Best effort: never leave the view open when the case failed."""
    view = _view_id(ctx)
    parts = ctx.request("ui.parts")
    if view in view_ids(parts.text):
        ctx.note("rollback close: %s" % ctx.request("ui.close %s" % view).status_line)


CASE = Case(
    name="write.close-view",
    group="write",
    targets=("gs32",),
    description="ui.close drops one view and a 2nd close of the same id is ERR notfound",
    pre=_pre,
    action=_action,
    expect=_expect,
    rollback=_rollback,
    evidence=("raw:action",),
)
