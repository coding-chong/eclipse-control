"""read.viewids -- `ui.viewids [prefix]`.

`design.md` §6 assertion points: ``total ≥ 50`` (threshold from that table, the
measured GS32 value is 55) and the prefix filter narrows the result.  The
summary line reports ``total/matched/returned/truncated``; consistency between
those is checked instead of trusting any single number.
"""

from __future__ import annotations

import re
from typing import Tuple

from ..runner import Case
from ._util import verdict

#: Threshold from `design.md` §6 ("total ≥ 50").
MIN_REGISTERED_VIEWS = 50

_SUMMARY = (r"registeredViews total=(\d+) matched\(prefix=(\S*)\)=(\d+) "
            r"returned=(\d+) truncated=(true|false)")


def _summary(text):
    match = re.search(_SUMMARY, text)
    if not match:
        return None
    return {
        "total": int(match.group(1)),
        "prefix": match.group(2),
        "matched": int(match.group(3)),
        "returned": int(match.group(4)),
        "truncated": match.group(5) == "true",
    }


def _action(ctx):
    base = ctx.request("ui.viewids")
    prefix = ctx.target.vendor_prefix
    filtered = ctx.request("ui.viewids %s" % prefix) if prefix else None
    return base, filtered, prefix


def _expect(ctx, result) -> Tuple[bool, str]:
    base, filtered, prefix = result
    summary = _summary(base.text)

    problems = []
    if not base.ok:
        problems.append("ui.viewids -> %r" % base.status_line)
    if summary is None:
        problems.append("missing 'registeredViews total=... matched=... returned=...' summary")
    else:
        if summary["total"] < MIN_REGISTERED_VIEWS:
            problems.append("total=%d < %d (design.md section 6)" % (summary["total"], MIN_REGISTERED_VIEWS))
        if summary["returned"] > summary["matched"]:
            problems.append("returned=%d > matched=%d" % (summary["returned"], summary["matched"]))
        if not summary["truncated"] and summary["returned"] != summary["matched"]:
            problems.append("truncated=false but returned=%d != matched=%d"
                            % (summary["returned"], summary["matched"]))

    note = ""
    if filtered is not None:
        fsummary = _summary(filtered.text)
        if not filtered.ok or fsummary is None:
            problems.append("ui.viewids %s -> %r" % (prefix, filtered.status_line))
        else:
            ids = re.findall(r"^\s*view id=(\S+)", filtered.text, re.M)
            off_prefix = [vid for vid in ids if not vid.startswith(prefix)]
            if off_prefix:
                problems.append("prefix filter leaked ids: %r" % off_prefix[:3])
            if fsummary["matched"] < 1:
                problems.append("vendor prefix %r matched 0 views" % prefix)
            note = " prefix=%r matched=%d" % (prefix, fsummary["matched"])
    else:
        note = " (no vendor prefix for this target; prefix filter not exercised)"
    return verdict(problems, "total=%s matched=%s returned=%s%s"
                   % (summary["total"] if summary else "?", summary["matched"] if summary else "?",
                      summary["returned"] if summary else "?", note))


CASE = Case(
    name="read.viewids",
    group="read",
    targets=("gs32", "ccs12"),
    description="ui.viewids has total>=50 and the prefix filter narrows the set",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
