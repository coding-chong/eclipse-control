"""read.cmd.list -- `cmd.list <prefix>`.

`design.md` §6: ``org.eclipse.ui.edit`` must have matches and the product's
vendor prefix (``com.gs`` / ``com.ti``) must have vendor commands.  The payload
is the full (uncapped) table: ``total/matched/returned/truncated`` are
cross-checked so a silent truncation cannot pass.
"""

from __future__ import annotations

import re
from typing import Tuple

from ..runner import Case
from ._util import verdict

_SUMMARY = (r"definedCommandIds total=(\d+) matched\(prefix=(\S*)\)=(\d+) "
            r"returned=(\d+) truncated=(true|false)")


def _summary(text):
    match = re.search(_SUMMARY, text)
    if not match:
        return None
    return {"total": int(match.group(1)), "prefix": match.group(2),
            "matched": int(match.group(3)), "returned": int(match.group(4)),
            "truncated": match.group(5) == "true"}


def _handler_only(text):
    match = re.search(r"^handlerOnly registry=(\S+) total=(\d+)", text, re.M)
    return int(match.group(2)) if match else None


def _action(ctx):
    core = ctx.request("cmd.list org.eclipse.ui.edit")
    prefix = ctx.target.vendor_prefix
    vendor = ctx.request("cmd.list %s" % prefix) if prefix else None
    return core, vendor, prefix


def _check(summary, label, problems):
    if summary is None:
        problems.append("%s: missing 'definedCommandIds ...' summary" % label)
        return ""
    if summary["returned"] > summary["matched"]:
        problems.append("%s: returned=%d > matched=%d" % (label, summary["returned"], summary["matched"]))
    if not summary["truncated"] and summary["returned"] != summary["matched"]:
        problems.append("%s: truncated=false but returned=%d != matched=%d"
                        % (label, summary["returned"], summary["matched"]))
    return "%s total=%d matched=%d returned=%d" % (label, summary["total"], summary["matched"], summary["returned"])


def _expect(ctx, result) -> Tuple[bool, str]:
    core, vendor, prefix = result
    problems = []
    if not core.ok:
        problems.append("cmd.list org.eclipse.ui.edit -> %r" % core.status_line)
    core_summary = _summary(core.text)
    detail = _check(core_summary, "org.eclipse.ui.edit", problems)
    if core_summary is not None and core_summary["matched"] < 1:
        problems.append("prefix org.eclipse.ui.edit matched 0 commands")

    extra = ""
    if vendor is not None:
        vendor_summary = _summary(vendor.text)
        if not vendor.ok:
            problems.append("cmd.list %s -> %r" % (prefix, vendor.status_line))
        extra = " | " + _check(vendor_summary, prefix, problems)
        if vendor_summary is not None and vendor_summary["matched"] < 1:
            problems.append("vendor prefix %r matched 0 commands" % prefix)
    handler_only = _handler_only(core.text)
    return verdict(problems, detail + extra + " | handlerOnly=%s" % handler_only)


CASE = Case(
    name="read.cmd.list",
    group="read",
    targets=("gs32", "ccs12"),
    description="cmd.list matches org.eclipse.ui.edit and the vendor prefix, uncapped summary",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
