"""read.shells -- `ui.shells`.

`design.md` §6: ``shellCount ≥ 1`` and the main shell's title carries the
workspace name (the invisible ``PartRenderingEngine's limbo`` shell must not be
mistaken for the main one).
"""

from __future__ import annotations

import os
import re
from typing import Tuple

from ..runner import Case
from ._util import int_or_none, search, verdict

#: Workspace directory names that are too generic to anchor a title assertion.
_GENERIC_WORKSPACES = ("ws", "workspace")


def _action(ctx):
    return ctx.request("ui.shells")


def _expect(ctx, response) -> Tuple[bool, str]:
    text = response.text
    rows = re.findall(r'^shell text="([^"]*)" vis=(\w+)', text, re.M)
    count = int_or_none(search(r"^shellCount=(\d+)", text))
    visible = [(title, vis) for title, vis in rows if vis == "true"]
    visible_titled = [title for title, _vis in visible if title.strip()]

    problems = []
    if not response.ok:
        problems.append("expected OK, got %r" % response.status_line)
    if count is None:
        problems.append("no shellCount field")
    elif count < 1:
        problems.append("shellCount=%d, expected >= 1" % count)
    if count is not None and count != len(rows):
        problems.append("shellCount=%d but %d shell rows" % (count, len(rows)))
    if not visible_titled:
        problems.append("no visible shell with a non-empty title")

    workspace = os.path.basename(ctx.paths.workspace) if ctx.paths else ""
    anchored = False
    if workspace and workspace.lower() not in _GENERIC_WORKSPACES and len(workspace) >= 3:
        anchored = any(workspace.lower() in title.lower() for title in visible_titled)
        if not anchored:
            problems.append("no visible shell title contains workspace %r" % workspace)
    return verdict(problems, "shellCount=%s visible=%d titles=%r workspace=%r%s"
                   % (count, len(visible_titled), visible_titled[:4], workspace or "<unknown>",
                      "" if anchored else " (workspace-title anchor N/A for a generic name)"))


CASE = Case(
    name="read.shells",
    group="read",
    targets=("gs32", "ccs12"),
    description="ui.shells reports >=1 shell and a visible titled main shell",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
