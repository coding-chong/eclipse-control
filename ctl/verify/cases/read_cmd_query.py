"""read.cmd.query -- `cmd.query <id>`.

`design.md` §6: for an existing id, ``defined=true``; the payload must carry
``name`` and ``category``.  `research/facts-baseline.md` §3 records that
``getParameters()`` may return ``null`` for vendor commands, so a ``null``
parameter list is accepted (and reported), never treated as a failure.
"""

from __future__ import annotations

from typing import Tuple

from ..runner import Case
from ._util import search, verdict

COMMAND_ID = "org.eclipse.ui.window.resetPerspective"


def _action(ctx):
    return ctx.request("cmd.query %s" % COMMAND_ID)


def _expect(ctx, response) -> Tuple[bool, str]:
    text = response.text
    cid = search(r"^id=(\S+)", text)
    defined = search(r"^defined=(\w+)", text)
    handled = search(r"^handled=(\w+)", text)
    name = search(r'^name="([^"]*)"', text)
    category = search(r"^category=(.*)$", text)

    problems = []
    if not response.ok:
        problems.append("expected OK, got %r" % response.status_line)
    if cid != COMMAND_ID:
        problems.append("id=%r, expected %r" % (cid, COMMAND_ID))
    if defined != "true":
        problems.append("defined=%r, expected true" % defined)
    if handled != "true":
        problems.append("handled=%r, expected true" % handled)
    if not name or not name.strip():
        problems.append("name is empty or missing: %r" % name)
    if category is None or not category.strip():
        problems.append("category is missing")
    return verdict(problems, "id=%r defined=%s handled=%s name=%r category=%r"
                   % (cid, defined, handled, name, category))


CASE = Case(
    name="read.cmd.query",
    group="read",
    targets=("gs32", "ccs12"),
    description="cmd.query reports defined/handled/name/category for a known id",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
