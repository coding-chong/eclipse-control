"""resilience.timeout-applied -- a write that TIMED OUT may still have applied.

P3.8, audit grade A.  ``ERR timeout`` says the *wait* ended, not that the action
did not run (``protocol.md`` 4.2; the bridge says so itself on ``sys.help``), and
the bridge's own log line for it is "the runnable is still queued on the SWT event
thread and MAY still take effect".  So the only honest judge is a read-back taken
**after** the modal was answered, diffed against a snapshot taken **before** the
write -- and the diff has to be *known to be sensitive*, which is what the two
directions here are for.

Both directions use one perturbation: ``org.eclipse.ui.views.TaskList``, a view
in the C/C++ perspective's default layout (measured: a fresh instance lists it),
is closed first, so the observable difference is exactly "did the perspective get
reset?".

* **cancel** (``WM_CLOSE`` == the title bar's X, nothing pressed) -> the read-back
  must be **unchanged** -> ``applied=no``, and that matches the ground truth that
  nothing was decided;
* **apply** (the case declares ``expects_modal`` and ``BM_CLICK`` presses
  ``&Reset Perspective``) -> the read-back must **move** (the default view comes
  back) -> ``applied=yes``, and that matches the ground truth that the question
  was answered yes.

One perturbation, two answers, two opposite diffs: the pair is its own control.
The verdict is computed by ``_util.applied_verdict`` and carried in the evidence
as ``applied=yes|no|unknown`` (``unknown`` = a read-back failed, and it is never
folded into ``no``).

Everything measured 2026-10-01 on a live GS32 Studio instance: the initiator
answers ``ERR timeout`` after ~15.4 s in both directions, the reset restores a
missing default view, and a cancelled reset changes nothing.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Set, Tuple

from ..runner import DISMISS_SETTLE, Case, Skip
from ._modal import ModalWrite, dialogs, dialog_item, ui_timeout_ms
from ._util import applied_verdict, verdict, view_ids

#: The command that pops the modal, and the shell's real title (measured).
COMMAND = "org.eclipse.ui.window.resetPerspective"
DIALOG_TITLE = "Reset Perspective"
#: Declared on purpose: this is the *only* case allowed to press a button, and the
#: declaration is what `Runner.answer_modal` checks before it does.
DECLARED_BUTTON = "&Reset Perspective"

#: A view in the C/C++ perspective's default layout: closing it is the
#: perturbation, and a real reset re-opens it (both measured).
PERTURB_VIEW = "org.eclipse.ui.views.TaskList"

DIALOG_WAIT_S = 12.0
CLIENT_WAIT_S = 40.0
#: `elapsed ≈ uiTimeoutMs` -- see resilience.modal-reset for the measurement.
TIMEOUT_SLACK_S = 5.0
#: Let the answered dialog's effect land before reading the workspace back.
#: Measured: the reset's views are back well inside 2 s.
READBACK_SETTLE_S = 2.5
#: Let an `ui.close` / `showView` land before believing the read-back.
VIEW_SETTLE_S = 1.0


# --------------------------------------------------------------------------- #
# the perturbation
# --------------------------------------------------------------------------- #

def _sweep_dialogs(ctx) -> None:
    """Close any dialog left on this instance, *before* issuing more commands.

    Measured 2026-10-01: sending ``showView`` while a modal is still up leaves an
    Eclipse error box (``Multiple problems have occurred``) parked behind it.  So
    the room is cleared first -- and never by title, only ``#32770`` scoped to this
    instance's pid, the same rule ``Runner.clean_room`` follows.
    """
    leftover = dialogs(ctx)
    for hwnd, meta in sorted(leftover.items()):
        ctx.note("cleanup: %s" % ctx.runner.close_modal(ctx, dialog_item(hwnd, meta)))
    if leftover:
        time.sleep(DISMISS_SETTLE)


def _present(ctx) -> Set[str]:
    return set(view_ids(ctx.request("ui.parts").text))


def _set_view(ctx, want_open: bool) -> Set[str]:
    """Open/close the perturbation view and return the resulting view set."""
    ids = _present(ctx)
    if want_open and PERTURB_VIEW not in ids:
        ctx.note("setup: opening the perturbation view %s -> %r"
                 % (PERTURB_VIEW, ctx.request(
                     "cmd.runp org.eclipse.ui.views.showView viewId=%s" % PERTURB_VIEW).status_line))
    elif not want_open and PERTURB_VIEW in ids:
        ctx.note("setup: closing the perturbation view %s -> %r"
                 % (PERTURB_VIEW, ctx.request("ui.close %s" % PERTURB_VIEW).status_line))
    else:
        return ids
    time.sleep(VIEW_SETTLE_S)
    return _present(ctx)


def _pre(ctx):
    ids = _set_view(ctx, True)
    return "%s open=%s (%d views)" % (PERTURB_VIEW, PERTURB_VIEW in ids, len(ids))


# --------------------------------------------------------------------------- #
# one direction
# --------------------------------------------------------------------------- #

def _direction(ctx, label: str, mode: str) -> Dict[str, object]:
    """Perturb -> send the modal write -> answer it -> read back -> verdict."""
    _sweep_dialogs(ctx)          # a leftover modal would poison the next command
    before = _set_view(ctx, False)
    if PERTURB_VIEW in before:
        raise Skip("could not close %s, so the read-back diff would have nothing to move"
                   % PERTURB_VIEW)
    ctx.note("%s: pre snapshot -- %s closed, views=%d" % (label, PERTURB_VIEW, len(before)))

    run = ModalWrite(ctx, "cmd.run " + COMMAND, client_wait=CLIENT_WAIT_S,
                     dialog_wait=DIALOG_WAIT_S)
    run.start()
    if run.wait_dialog() is None:
        run.require_dialog()          # raises Skip with the answer recorded
    fired = run.join()

    hwnd, (pid, cls, title) = run.dialog
    disposal = ctx.runner.answer_modal(ctx, dialog_item(hwnd, (pid, cls, title)), mode=mode)

    time.sleep(READBACK_SETTLE_S)
    after = _present(ctx)
    applied = applied_verdict(before, after)
    ctx.note("applied=%s (%s): %s before=%s after=%s | lost=%s gained=%s"
             % (applied, label, PERTURB_VIEW, PERTURB_VIEW in before, PERTURB_VIEW in after,
                sorted(before - after), sorted(after - before)))
    return {"label": label, "mode": mode, "fired": fired, "disposal": disposal,
            "before": before, "after": after, "applied": applied,
            "perturb_present_after": PERTURB_VIEW in after}


def _action(ctx):
    ui_timeout = ui_timeout_ms(ctx)
    cancel = _direction(ctx, "cancel", "close")
    apply_ = _direction(ctx, "apply", "auto")
    return {"ui_timeout_ms": ui_timeout, "cancel": cancel, "apply": apply_}


# --------------------------------------------------------------------------- #
# verdict
# --------------------------------------------------------------------------- #

def _timeout_problems(fired: Dict[str, object], ui_timeout: Optional[int]) -> List[str]:
    problems: List[str] = []
    status = str(fired.get("status_line") or "")
    elapsed = float(fired.get("elapsed") or 0.0)
    if "ERR timeout" not in status:
        problems.append("the initiator answered %r, expected `ERR timeout` -- without a timeout "
                        "there is no post-timeout effect to re-check" % status)
    if ui_timeout is None:
        problems.append("sys.env did not report uiTimeoutMs, so the timeout cannot be checked")
    elif elapsed < ui_timeout / 1000.0 or elapsed > ui_timeout / 1000.0 + TIMEOUT_SLACK_S:
        problems.append("the initiator answered after %.2fs, expected ~%.1fs (+<=%.0fs)"
                        % (elapsed, ui_timeout / 1000.0, TIMEOUT_SLACK_S))
    return problems


def _expect(ctx, result) -> Tuple[bool, str]:
    problems: List[str] = []
    ui_timeout = result["ui_timeout_ms"]
    cancel = result["cancel"]
    apply_ = result["apply"]

    for direction in (cancel, apply_):
        for problem in _timeout_problems(direction["fired"], ui_timeout):
            problems.append("%s: %s" % (direction["label"], problem))

    # -- cancel: nothing pressed, so nothing may have moved ----------------- #
    if cancel["disposal"].get("action") != "wm_close":
        problems.append("cancel: disposal was %r, expected WM_CLOSE"
                        % cancel["disposal"].get("action"))
    if cancel["applied"] != "no":
        problems.append("cancel: applied=%s, but a cancelled reset must not change the "
                        "workspace (before=%s after=%s)"
                        % (cancel["applied"], sorted(cancel["before"]), sorted(cancel["after"])))
    if cancel["perturb_present_after"]:
        problems.append("cancel: %s is back even though nothing was pressed" % PERTURB_VIEW)

    # -- apply: the declared button was pressed, so the reset must have run -- #
    if apply_["disposal"].get("action") != "bm_click":
        problems.append("apply: disposal was %r, expected the declared button to be pressed"
                        % apply_["disposal"].get("action"))
    elif DECLARED_BUTTON not in str(apply_["disposal"].get("output") or ""):
        problems.append("apply: the click output %r does not name the declared button %r"
                        % (apply_["disposal"].get("output"), DECLARED_BUTTON))
    if apply_["applied"] != "yes":
        problems.append("apply: applied=%s, but pressing %r must reset the perspective "
                        "(before=%s after=%s)"
                        % (apply_["applied"], DECLARED_BUTTON,
                           sorted(apply_["before"]), sorted(apply_["after"])))
    if not apply_["perturb_present_after"]:
        problems.append("apply: %s did not come back after the reset" % PERTURB_VIEW)

    # -- the pair is its own control --------------------------------------- #
    if cancel["before"] != apply_["before"]:
        problems.append("the two directions did not start from the same perturbation "
                        "(cancel=%s, apply=%s)"
                        % (sorted(cancel["before"]), sorted(apply_["before"])))

    detail = ("uiTimeoutMs=%s; cancel: `ERR timeout` after %.2fs, disposal=%s, applied=%s; "
              "apply: `ERR timeout` after %.2fs, disposal=%s, applied=%s"
              % (ui_timeout, cancel["fired"]["elapsed"], cancel["disposal"].get("action"),
                 cancel["applied"], apply_["fired"]["elapsed"],
                 apply_["disposal"].get("action"), apply_["applied"]))
    return verdict(problems, detail)


def _rollback(ctx):
    """Clear the room, then put the perturbation view back."""
    try:
        _sweep_dialogs(ctx)
        ids = _set_view(ctx, True)
        ctx.note("rollback: %s open=%s" % (PERTURB_VIEW, PERTURB_VIEW in ids))
    except Exception as exc:  # noqa: BLE001 - rollback must not mask the real verdict
        ctx.note("rollback failed: %r" % (exc,))
    time.sleep(DISMISS_SETTLE)


CASE = Case(
    name="resilience.timeout-applied",
    group="resilience",
    targets=("gs32",),
    description="a write that answered ERR timeout is judged by the read-back after the modal "
                "is answered: cancelled -> applied=no, pressed -> applied=yes",
    pre=_pre,
    action=_action,
    expect=_expect,
    rollback=_rollback,
    # The action drives its own snapshots and answers its own modal (twice, in two
    # directions), which the guard's single before/after pair cannot express.
    screen_guard=False,
    expects_modal={"title": DIALOG_TITLE, "button": DECLARED_BUTTON},
    evidence=("raw:action", "applied"),
)
