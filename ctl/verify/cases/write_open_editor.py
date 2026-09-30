"""write.open-editor -- `ui.open` lands an editor, and re-opening is idempotent.

`design.md` §4.3: a write may answer ``OK`` and still fail.  So the judgement is
the read-back diff, not the status line:

* 1st ``ui.open <abs .c>``  -> ``editors`` +1 and the new row's id contains
  ``CEditor`` (a *C* editor, not a plain text fallback);
* 2nd ``ui.open <same>``    -> ``OK`` and ``editors`` **unchanged** (idempotent).

The case runs under the screen guard, so a silent dialog during either call is a
FAIL.  Measured here: the first open makes Eclipse put the file into the main
window title, and the *bridge* (which diffs titles, not window handles) reports
that as ``dialog=appeared``; the guard's enumeration sees no new window and
classifies it as a title change -- recorded, not failed (see
``runner._explain_as_title_change``).

The editor is deliberately left open afterwards: the bridge has no
"close editor" method, so there is nothing to roll back to.  That is stated in
the evidence, not silently ignored.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Tuple

from ..runner import Case, Skip
from ._util import editor_rows, parts_counts, search, verdict

#: Override the fixture (a real ``.c`` file that the C editor will claim).
FIXTURE_ENV = "ECLIPSE_CTL_OPEN_FIXTURE"
FIXTURE_BODY = ("/* eclipse-ctl verify fixture: opened by ui.open */\n"
                "int ctl_fixture_main(void) { return 0; }\n")


def _fixture_path(ctx) -> str:
    """A ``.c`` file that is **not** open yet, so the 1st open is a real +1.

    The name walks a counter inside the run directory: re-running the case on the
    same instance writes the next file instead of re-opening one that is already
    in an editor (which would turn the 1st call into an idempotent no-op and make
    the "+1" assertion meaningless).
    """
    override = os.environ.get(FIXTURE_ENV)
    if override:
        return override
    if ctx.paths is None:
        raise Skip("no run directory to hold the fixture; retry with --run-id")
    directory = os.path.join(ctx.paths.run_root, ctx.paths.run_id, "fixtures")
    os.makedirs(directory, exist_ok=True)
    index = 1
    while True:
        path = os.path.join(directory, "ctl-open-editor-%d.c" % index)
        if not os.path.isfile(path):
            break
        index += 1
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(FIXTURE_BODY)
    return path


def _pre(ctx):
    return ctx.request("ui.parts")


def _action(ctx):
    path = _fixture_path(ctx)
    before = ctx.request("ui.parts")
    first = ctx.request("ui.open %s" % path)
    mid = ctx.request("ui.parts")
    second = ctx.request("ui.open %s" % path)
    after = ctx.request("ui.parts")
    return {"path": path, "before": before, "first": first, "mid": mid,
            "second": second, "after": after}


def _expect(ctx, result) -> Tuple[bool, str]:
    path = result["path"]
    before, first, mid = result["before"], result["first"], result["mid"]
    second, after = result["second"], result["after"]
    problems = []

    if not first.ok:
        problems.append("1st ui.open -> %r" % first.status_line)
    if not second.ok:
        problems.append("2nd ui.open -> %r" % second.status_line)

    counts0 = parts_counts(before.text)
    counts1 = parts_counts(mid.text)
    counts2 = parts_counts(after.text)
    e0, e1, e2 = counts0["editors"], counts1["editors"], counts2["editors"]
    if e0 is None or e1 is None or e2 is None:
        problems.append("ui.parts did not report editors= (%r/%r/%r)"
                        % (counts0, counts1, counts2))
    else:
        if e1 != e0 + 1:
            problems.append("1st ui.open did not add exactly one editor: %d -> %d" % (e0, e1))
        if e2 != e1:
            problems.append("2nd ui.open was not idempotent: editors %d -> %d" % (e1, e2))

    rows0 = Counter(editor_rows(before.text))
    rows1 = editor_rows(mid.text)
    added = list((Counter(rows1) - rows0).elements())
    if not added:
        problems.append("no new editor row after the 1st ui.open")
    else:
        editor_id, name = added[0]
        if "CEditor" not in editor_id:
            problems.append("the new editor is %r, not a CEditor" % editor_id)
        if name and os.path.basename(path) not in name:
            problems.append("the new editor is %r, not %r" % (name, os.path.basename(path)))
    if search(r"^editors=(\d+)", after.text) is None:
        problems.append("no editors= field in the final ui.parts")

    ctx.note("read-back: editors %s -> %s -> %s (2nd open idempotent)"
             % (e0, e1, e2))
    ctx.note("editor left open on purpose: the bridge has no close-editor method")
    return verdict(problems, "path=%s editors=%s->%s->%s; new editor id=%r class~CEditor=%s"
                   % (os.path.basename(path), e0, e1, e2,
                      added[0][0] if added else "?",
                      bool(added) and "CEditor" in added[0][0]))


CASE = Case(
    name="write.open-editor",
    group="write",
    targets=("gs32", "ccs12"),
    description="ui.open adds one CEditor and re-opening the same file is idempotent",
    pre=_pre,
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
