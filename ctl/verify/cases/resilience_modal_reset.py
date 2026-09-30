"""resilience.modal-reset -- a connection stuck in a modal must not take the bridge with it.

P3.3 (six evidence segments) + P3.4 (what ``ERR timeout`` does and does not mean),
all of it measured 2026-10-01 on a live GS32 Studio instance:

* ``cmd.run org.eclipse.ui.window.resetPerspective`` pops the SWT confirmation
  shell ``Reset Perspective`` (class ``#32770``, buttons ``&Reset Perspective`` /
  ``&No``), and **the connection that sent it** answers
  ``ERR timeout UI task did not finish within 15000 ms; …`` after ~15.4 s.
* that dialog does **not** stop the bridge: other connections answer ``sys.ping``
  and ``ui.parts`` in ~0.02 s *while it is on screen*.  SWT runs a modal from a
  **nested event loop**, so ``Display.asyncExec`` work keeps being dispatched --
  which is also why the tempting phrasing "a modal makes every UI call time out"
  is **wrong** and is not asserted here.  The measured pair is: *the initiator*
  times out, *everybody else* carries on.
* segment 3 shoots the live modal with ``flags=0`` -- a **conservative choice**.
  (A claim that the tool's default ``flags=2`` makes the shell disappear and the
  pending request answer ``OK`` was made but **not reproduced** in two independent
  attempts with a no-screenshot control; see ``ctl/screen.py::shoot_verbose``.
  Do not assert it.  The two flags do produce different bytes, 15821 vs 14057.)

**Asserted by this case**: segment 2 (the timeout, and its arithmetic against the
bridge's own ``uiTimeoutMs``), segment 4 (the child-window enumeration), segment 5
(the disposal really happened), segment 6 (recovery), and the P3.4 pair (the two
other-connection probes answer while the modal is up).
**Recorded, not asserted**: the pixel text of segment 3 -- the evidence names the
PNG, and a reviewing agent reads it (``read <path>``); that is how the title
``Reset Perspective``, the question ``Reset the C/C++ perspective to its
defaults?`` and the buttons ``Reset Perspective`` / ``No`` were read here.  Also
recorded: the bridge's own ``dialog=`` line, kept as the second, independent
channel and cross-checked against the enumeration when it is present.

The case ends where it started: the modal is closed with ``WM_CLOSE`` -- the
window's X, i.e. cancel, with nothing pressed -- and ``rollback`` sweeps anything
a failure left behind.
"""

from __future__ import annotations

import os
import time
from typing import List, Tuple

from ... import screen
from ..runner import DISMISS_SETTLE, Case
from ._modal import ModalWrite, dialogs, dialog_item, probe, ui_timeout_ms
from ._util import verdict

#: The command that pops the modal (`recipes/diag-when-hung.md`; measured again here).
COMMAND = "org.eclipse.ui.window.resetPerspective"
#: The title the shell actually gets -- pinned because segment 4 addresses it by name.
DIALOG_TITLE = "Reset Perspective"

#: The shell is created asynchronously, so the case polls for it instead of
#: sleeping a fixed amount and hoping.
DIALOG_WAIT_S = 12.0
#: Client-side ceiling for the initiating request: it must out-wait the bridge's
#: ``uiTimeoutMs`` (the thing under test), otherwise segment 2 would measure the
#: client's patience rather than the bridge's.
CLIENT_WAIT_S = 40.0
#: ``elapsed ≈ uiTimeoutMs``: dispatch + ``-Dctl.dialogSettleMs`` + socket.  The
#: overhead measured 0.42 s; 5 s is a ceiling that still fails loudly on a real
#: regression (a timeout that no longer fires, or one that fires early).
TIMEOUT_SLACK_S = 5.0
#: A healthy bridge answers a non-UI call in ~0.02 s (measured).  5 s is generous
#: and still fails loudly if a modal really did wedge the whole bridge.
PROBE_BUDGET_S = 5.0
#: A real dialog renders to far more than this; a blank capture does not.
SHOT_MIN_BYTES = 4096


def _action(ctx):
    run = ModalWrite(ctx, "cmd.run " + COMMAND, client_wait=CLIENT_WAIT_S,
                     dialog_wait=DIALOG_WAIT_S)
    ui_timeout = ui_timeout_ms(ctx)
    run.start()

    # --- the modal, if this instance pops one ------------------------------ #
    if run.wait_dialog() is None:
        run.require_dialog()          # raises Skip with the answer recorded

    # --- P3.4: other connections, *while the modal is up* ------------------ #
    others = {}
    for method in ("sys.ping", "ui.parts"):
        response, elapsed = probe(ctx, method, PROBE_BUDGET_S)
        others[method] = (response, elapsed)
        ctx.note("P3.4 another connection while the modal is up: %s -> %r in %.2fs"
                 % (method, response.status_line, elapsed))

    # --- 2. the initiator's own answer ------------------------------------- #
    fired = run.join()
    hwnd, (pid, cls, title) = run.dialog

    # --- 3. the screenshot (flags=0: conservative; see shoot_verbose) -------- #
    shot = screen.shot_path(ctx.runner.shots_dir(), ctx.case.name, title)
    landed, note = screen.shoot_verbose(title, shot, flags=0)
    shot_bytes = os.path.getsize(shot) if os.path.exists(shot) else 0
    ctx.note("3. modal shot -> %s (%d bytes, PrintWindow -Flags 0) | %s"
             % (shot if landed else "<not written>", shot_bytes, note))
    ctx.note('3. read that PNG to see it: title bar "Reset Perspective"; the question '
             '"Reset the C/C++ perspective to its defaults?"; buttons "Reset Perspective" / "No"')

    # --- 4. child windows of the dialog ------------------------------------ #
    buttons = screen.buttons(title, pids=ctx.screen_pids)
    ctx.note("4. child windows of %r: %s"
             % (title, "; ".join("%s %r" % (h, t) for h, t in buttons) or "<none>"))

    # --- 5. disposal: WM_CLOSE only -- this case declares no button -------- #
    item = dialog_item(hwnd, (pid, cls, title))
    item["screenshot"] = shot if landed else None
    item["shot_note"] = note
    disposal = ctx.runner.answer_modal(ctx, item)      # auto -> WM_CLOSE (nothing declared)
    time.sleep(DISMISS_SETTLE)
    gone = hwnd.upper() not in screen.visible_windows(ctx.screen_pids)
    ctx.note("5. disposal=%s -> the modal is %s"
             % (disposal.get("action"), "gone" if gone else "STILL ON SCREEN"))

    # --- 6. recovery ------------------------------------------------------- #
    recovery = {}
    for method in ("sys.ping", "ui.parts"):
        response, elapsed = probe(ctx, method, PROBE_BUDGET_S)
        recovery[method] = (response, elapsed)
        ctx.note("6. after disposal: %s -> %r in %.2fs" % (method, response.status_line, elapsed))

    return {"fired": fired, "ui_timeout_ms": ui_timeout, "others": others,
            "shot": {"path": shot, "landed": landed, "bytes": shot_bytes},
            "buttons": buttons, "disposal": disposal, "gone": gone, "recovery": recovery}


def _expect(ctx, result) -> Tuple[bool, str]:
    problems: List[str] = []
    fired = result["fired"]
    dialog = fired["dialog"]
    status = fired["status_line"] or ""
    elapsed = fired["elapsed"]

    # -- segment 2: the initiator itself times out, honestly timed ---------- #
    if "ERR timeout" not in status:
        problems.append("segment 2: the initiating connection answered %r, expected "
                        "`ERR timeout` (the modal is still up, so its UI task cannot finish)"
                        % status)
    ui_timeout = result["ui_timeout_ms"]
    if ui_timeout is None:
        problems.append("sys.env did not report uiTimeoutMs, so the timeout cannot be checked")
    else:
        expected = ui_timeout / 1000.0
        if elapsed < expected:
            problems.append("segment 2: answered after %.2fs, before the bridge's own "
                            "uiTimeoutMs (%.0f ms)" % (elapsed, ui_timeout))
        elif elapsed > expected + TIMEOUT_SLACK_S:
            problems.append("segment 2: answered after %.2fs, expected ~%.1fs + at most %.0fs"
                            % (elapsed, expected, TIMEOUT_SLACK_S))

    # -- P3.4: other connections are served while the modal is up ----------- #
    for method in ("sys.ping", "ui.parts"):
        response, probe_elapsed = result["others"][method]
        if not getattr(response, "ok", False):
            problems.append("P3.4: %s on another connection answered %r while the modal was up"
                            % (method, getattr(response, "status_line", "<no answer>")))
        elif probe_elapsed > PROBE_BUDGET_S:
            problems.append("P3.4: %s took %.2fs, over the %.0fs ceiling"
                            % (method, probe_elapsed, PROBE_BUDGET_S))

    # -- segments 3 and 4 --------------------------------------------------- #
    shot = result["shot"]
    if not shot["landed"]:
        problems.append("segment 3: the modal screenshot did not land (%s)" % shot["path"])
    elif shot["bytes"] < SHOT_MIN_BYTES:
        problems.append("segment 3: the modal screenshot is only %d bytes -- too small to be "
                        "the dialog" % shot["bytes"])
    buttons = result["buttons"]
    if not buttons:
        problems.append("segment 4: no visible Button child was enumerated on %r" % DIALOG_TITLE)
    if any(not text.strip() for _hwnd, text in buttons):
        problems.append("segment 4: a Button child has an empty text")

    # -- cross-channel: the bridge's own diff must not contradict us -------- #
    appeared = [line for line in fired["bridge_dialog_lines"] if line.startswith("dialog=appeared")]
    if appeared and DIALOG_TITLE not in appeared[0]:
        problems.append("the bridge reported %r, but the enumerated dialog is %r"
                        % (appeared[0], DIALOG_TITLE))

    # -- segment 5: disposal actually disposed ------------------------------ #
    if result["disposal"].get("action") != "wm_close":
        problems.append("segment 5: disposal was %r; this case declares no button, so the only "
                        "permitted disposal is WM_CLOSE" % result["disposal"].get("action"))
    if not result["gone"]:
        problems.append("segment 5: the modal is still on screen after %r"
                        % result["disposal"].get("output", "<no output>"))

    # -- segment 6: the bridge is usable again ------------------------------ #
    for method in ("sys.ping", "ui.parts"):
        response, recover_elapsed = result["recovery"][method]
        if not getattr(response, "ok", False):
            problems.append("segment 6: %s answered %r after the modal was dismissed"
                            % (method, getattr(response, "status_line", "<no answer>")))
        elif recover_elapsed > PROBE_BUDGET_S:
            problems.append("segment 6: %s took %.2fs to recover (ceiling %.0fs)"
                            % (method, recover_elapsed, PROBE_BUDGET_S))

    detail = ("modal=%r up after %.2fs; initiator `ERR timeout` after %.2fs (uiTimeoutMs=%s); "
              "other connections while it was up: sys.ping %.2fs, ui.parts %.2fs; shot=%d bytes; "
              "buttons=%s; disposal=%s; recovered: sys.ping %.2fs, ui.parts %.2fs"
              % ((dialog or {}).get("title"), fired["appeared_after"], elapsed, ui_timeout,
                 result["others"]["sys.ping"][1], result["others"]["ui.parts"][1],
                 shot["bytes"], [text for _h, text in buttons],
                 result["disposal"].get("action"),
                 result["recovery"]["sys.ping"][1], result["recovery"]["ui.parts"][1]))
    return verdict(problems, detail)


def _rollback(ctx):
    """Sweep dialogs a failure may have left, so the next case starts clean."""
    try:
        found = dialogs(ctx)
    except screen.ScreenError as exc:
        ctx.note("rollback: could not enumerate dialogs: %s" % exc)
        return
    if not found:
        ctx.note("rollback: no dialog left behind")
        return
    for hwnd, meta in sorted(found.items()):
        ctx.note("rollback: %s" % ctx.runner.close_modal(ctx, dialog_item(hwnd, meta)))
    time.sleep(DISMISS_SETTLE)


CASE = Case(
    name="resilience.modal-reset",
    group="resilience",
    targets=("gs32",),
    description="a connection stuck in a modal resetPerspective times out, the bridge keeps "
                "serving other connections, and the modal is dismissed with a screenshot",
    action=_action,
    expect=_expect,
    rollback=_rollback,
    # The action takes its own window snapshots -- it must see the modal *while it
    # is up*, which the guard's post-action snapshot cannot -- and disposes of it
    # itself with the same `answer_modal` the guard uses.
    screen_guard=False,
    evidence=("raw:action", "screen:shots"),
)
