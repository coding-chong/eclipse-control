"""write.runp-show-view -- `cmd.runp … showView viewId=<real view>` opens exactly one view.

`design.md` §4.3 + measured contract (2026-10-01):

* 1st call -> ``OK``, ``views`` **+1**, the requested id appears;
* 2nd call -> ``OK``, ``views`` **unchanged**: the *idempotent* kind of "nothing
  changed", which must not be confused with the *failure* kind (see
  ``errors.plugin-id-as-view`` for the same call shape with a bogus id).

The case opens, reads back, opens again, reads back, then closes the view, so it
ends where it started.
"""

from __future__ import annotations

from typing import Tuple

from ..runner import Case, Skip
from ._util import parts_counts, verdict, view_ids

def _view_id(ctx) -> str:
    """The target's declared probe view -- per-target data, same case on both.

    See ``write_close_view._view_id`` for why a fixed ``.memory.view`` suffix
    could never cross targets.
    """
    view = ctx.target.probe_view
    if not view:
        raise Skip("target %s declares no probe_view" % ctx.target.name)
    return view


def _pre(ctx):
    """Start from "the view is closed" so the +1 arithmetic is meaningful."""
    view = _view_id(ctx)
    parts = ctx.request("ui.parts")
    if view in view_ids(parts.text):
        closed = ctx.request("ui.close %s" % view)
        parts = ctx.request("ui.parts")
        ctx.note("setup: view was already open, closed it first (%r)" % closed.status_line)
    if view in view_ids(parts.text):
        raise Skip("view %s cannot be closed on this instance" % view)
    return "%s not open (%s)" % (view, parts_counts(parts.text))


def _action(ctx):
    view = _view_id(ctx)
    base = ctx.request("ui.parts")
    first = ctx.request("cmd.runp org.eclipse.ui.views.showView viewId=%s" % view)
    after_first = ctx.request("ui.parts")
    second = ctx.request("cmd.runp org.eclipse.ui.views.showView viewId=%s" % view)
    after_second = ctx.request("ui.parts")
    closed = ctx.request("ui.close %s" % view)
    restored = ctx.request("ui.parts")
    return {"view": view, "base": base, "first": first, "after_first": after_first,
            "second": second, "after_second": after_second, "closed": closed,
            "restored": restored}


def _expect(ctx, result) -> Tuple[bool, str]:
    view = result["view"]
    problems = []
    for label, response in (("1st cmd.runp", result["first"]), ("2nd cmd.runp", result["second"])):
        if not response.ok:
            problems.append("%s -> %r" % (label, response.status_line))

    base = parts_counts(result["base"].text)["views"]
    v1 = parts_counts(result["after_first"].text)["views"]
    v2 = parts_counts(result["after_second"].text)["views"]
    v3 = parts_counts(result["restored"].text)["views"]
    if None in (base, v1, v2, v3):
        problems.append("ui.parts did not report views= (%r/%r/%r/%r)" % (base, v1, v2, v3))
    else:
        if v1 != base + 1:
            problems.append("1st showView did not add exactly one view: %d -> %d" % (base, v1))
        if v2 != v1:
            problems.append("2nd showView was not idempotent: views %d -> %d" % (v1, v2))
        if v3 != base:
            problems.append("closing the view did not restore the baseline: %d -> %d" % (base, v3))
    if view not in view_ids(result["after_first"].text):
        problems.append("%s is not listed after the 1st showView" % view)
    if view not in view_ids(result["after_second"].text):
        problems.append("%s disappeared after the 2nd showView" % view)
    if view in view_ids(result["restored"].text):
        problems.append("%s is still listed after the closing ui.close" % view)

    ctx.note("read-back: views %s -> %s (2nd call idempotent) -> %s after close"
             % (base, v1, v3))
    return verdict(problems, "view=%s views=%s->%s->%s->%s; 2nd showView idempotent=%s"
                   % (view, base, v1, v2, v3, v1 == v2))


def _rollback(ctx):
    view = _view_id(ctx)
    parts = ctx.request("ui.parts")
    if view in view_ids(parts.text):
        ctx.note("rollback close: %s" % ctx.request("ui.close %s" % view).status_line)


CASE = Case(
    name="write.runp-show-view",
    group="write",
    targets=("gs32", "ccs12"),
    description="cmd.runp showView adds one view, the 2nd call is idempotent, close restores it",
    pre=_pre,
    action=_action,
    expect=_expect,
    rollback=_rollback,
    evidence=("raw:action",),
)
