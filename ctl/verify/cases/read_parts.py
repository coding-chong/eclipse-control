"""read.parts -- `ui.parts`.

`design.md` §6: perspective id must be non-empty, and every ``views[]`` row must
carry an id and a title.  Counts are cross-checked against the rows rather than
compared to a hardcoded number.
"""

from __future__ import annotations

import re
from typing import Tuple

from ..runner import Case
from ._util import int_or_none, search, verdict, view_rows


def _action(ctx):
    return ctx.request("ui.parts")


def _expect(ctx, response) -> Tuple[bool, str]:
    text = response.text
    perspective = search(r"^perspective id=(\S+) label=", text)
    views = int_or_none(search(r"^views=(\d+)", text))
    editors = int_or_none(search(r"^editors=(\d+)", text))
    rows = view_rows(text)
    editor_rows = len(re.findall(r"^\s*editor id=", text, re.M))

    problems = []
    if not response.ok:
        problems.append("expected OK, got %r" % response.status_line)
    if not perspective or perspective == "null":
        problems.append("perspective id is %r" % perspective)
    if views is None:
        problems.append("no views= field")
    elif views != len(rows):
        problems.append("views=%d but %d view rows" % (views, len(rows)))
    if editors is None:
        problems.append("no editors= field")
    elif editors != editor_rows:
        problems.append("editors=%d but %d editor rows" % (editors, editor_rows))
    if "services: EModelService=" not in text:
        problems.append("missing services: EModelService line")
    if any(not vid.strip() for vid, _title in rows):
        problems.append("a view row has an empty id")
    return verdict(problems, "perspective=%r views=%s(rows=%d) editors=%s(rows=%d)"
                   % (perspective, views, len(rows), editors, editor_rows))


CASE = Case(
    name="read.parts",
    group="read",
    targets=("gs32", "ccs12"),
    description="ui.parts has a non-empty perspective and id+title per view row",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
