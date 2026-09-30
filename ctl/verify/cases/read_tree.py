"""read.tree -- `ui.tree <depth>`.

`design.md` §6: non-empty, contains a ``Shell`` and at least one ``ToolBar``.
Depth 7 is the depth proved to reach toolbars in the measured runs
(`research/facts-baseline.md` §4, "实测能读到的结构（ui.tree 7）").
"""

from __future__ import annotations

from typing import Tuple

from ..runner import Case
from ._util import verdict

TREE_DEPTH = 7


def _action(ctx):
    return ctx.request("ui.tree %d" % TREE_DEPTH)


def _expect(ctx, response) -> Tuple[bool, str]:
    text = response.text
    lines = [line for line in text.splitlines() if line.strip()]

    problems = []
    if not response.ok:
        problems.append("expected OK, got %r" % response.status_line)
    if len(lines) <= 1:
        problems.append("tree has %d line(s); expected a real tree" % len(lines))
    if "no visible shell" in text:
        problems.append("bridge reported 'no visible shell'")
    if "Shell" not in text:
        problems.append("no Shell node in the tree")
    if "ToolBar" not in text:
        problems.append("no ToolBar node at depth %d" % TREE_DEPTH)
    return verdict(problems, "depth=%d lines=%d hasShell=%s hasToolBar=%s"
                   % (TREE_DEPTH, len(lines), "Shell" in text, "ToolBar" in text))


CASE = Case(
    name="read.tree",
    group="read",
    targets=("gs32", "ccs12"),
    description="ui.tree is non-empty and contains a Shell and a ToolBar",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
