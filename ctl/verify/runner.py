"""Acceptance-case executor: pre-snapshot -> action -> assert -> post -> rollback.

The tuple shape mirrors `design.md` §10.  Assertions must be computable
predicates (set diff / counter diff / field equality / regex); a PASS without
evidence is treated as a defect.

Writes are additionally wrapped in the **screen guard** (`ctl/screen.py`): a
before/after enumeration of visible top-level windows, independent of the
bridge.  The rule (`design.md` §4.3):

* a *new* visible window during a write that did not declare
  ``expects_dialog`` -> the case **FAILS**, with the screenshot, the title read
  from the window and the dismissal action in the evidence;
* ``expects_dialog=True`` -> the dialog appearing is a PASS, screenshotted too;
* the bridge's own ``dialog=`` payload line is cross-checked against the
  enumeration -- the two channels disagreeing is itself reported;
* every dialog is dismissed and its disappearance re-observed before the next
  case, because a modal shell left behind blocks the UI thread and poisons the
  whole rest of the run.
"""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .. import screen
from ..client import Client
from ..errors import CtlError, EndpointNotFound, NotFoundError, PrereqNotReady
from ..lifecycle import latest_run_id, list_processes, run_paths
from ..targets import Config

#: Group vocabulary (`design.md` §10): read|write|errors|resilience|input.
GROUPS = ("read", "write", "errors", "resilience", "input")

#: Exceptions a case body may raise to mean "the environment is not ready".
ENV_NOT_READY = (PrereqNotReady, EndpointNotFound)

#: Seconds to wait after dismissing a dialog before re-observing that it is gone.
DISMISS_SETTLE = 0.6

#: Win32 classes that are dialogs by construction.  Used *only* by the unguarded
#: rescue path, which must never identify a dialog by its title.
DIALOG_CLASSES = ("#32770",)


class Skip(Exception):
    """Raised *or returned* by ``expect`` when the case cannot be exercised here.

    A skipped case is neither a pass that hides missing coverage nor a failure:
    the reason is recorded verbatim and surfaced as ``SKIP`` (`implement.md`
    P1.1 forbids silent skips).
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class Case:
    """One verifiable interaction with a real target."""

    name: str
    group: str
    targets: Tuple[str, ...]
    description: str
    action: Callable[["Ctx"], object]
    expect: Callable[["Ctx", object], Tuple[bool, str]]
    pre: Optional[Callable[["Ctx"], object]] = None
    post: Optional[Callable[["Ctx"], object]] = None
    rollback: Optional[Callable[["Ctx"], object]] = None
    evidence: Tuple[str, ...] = ()
    requires_bridge: bool = True
    #: ``None`` = automatic (on for group ``write``); ``True``/``False`` = explicit.
    screen_guard: Optional[bool] = None
    #: The dialog is the *expected* outcome here, so its appearance is a PASS
    #: (it is still screenshotted and dismissed).
    expects_dialog: bool = False
    #: A modal this case is *allowed to answer with a button press*, e.g.
    #: ``{"title": "Reset Perspective", "button": "&Reset Perspective"}``.
    #: ``None`` (the default, and every case but the deliberate ones) means the
    #: only disposal available is ``WM_CLOSE`` -- the window's X, i.e. cancel.
    #: Pressing a button decides *for the user*, so it happens only when the case
    #: has said out loud which dialog and which button (``Runner.answer_modal``).
    expects_modal: Optional[Dict[str, str]] = None


@dataclass
class CaseResult:
    name: str
    group: str
    passed: bool
    detail: str
    evidence: List[str] = field(default_factory=list)
    skipped: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "group": self.group,
            "passed": self.passed,
            "skipped": self.skipped,
            "detail": self.detail,
            "evidence": self.evidence,
            "error": self.error,
        }


class Ctx:
    """Per-run case context: bridge connection plus evidence collection."""

    def __init__(self, runner: "Runner", case: Case):
        self.runner = runner
        self.case = case
        self.config: Config = runner.config
        self.target = runner.target
        self.run_id = runner.run_id
        self.paths = runner.paths
        self.evidence: List[str] = []
        self._client: Optional[Client] = None
        # -- screen guard state (filled by Runner.run_case) ------------------ #
        self.guarded: bool = False
        self.dismissed: bool = False
        self.dialogs: List[Dict[str, object]] = []
        self.screen_info: Optional[Dict[str, object]] = None
        self.screen_pre: Optional[screen.WindowMap] = None
        self.screen_pids: Optional[List[int]] = None

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = self.runner.connect()
        return self._client

    def note(self, line: str) -> None:
        self.evidence.append(str(line))

    def request(self, method: str):
        response = self.client.request(method)
        self.note("raw: %s" % (response.raw.strip() or "<empty>"))
        return response


class Runner:
    """Selects and executes cases against one target instance."""

    def __init__(self, config: Config, target_name: Optional[str] = None,
                 run_id: Optional[str] = None, port: Optional[int] = None,
                 token: str = "", screen_guard: bool = True):
        self.config = config
        self.target = config.target(target_name)
        self.port = port
        self.token = token or config.token
        self.screen_guard = screen_guard
        self.run_id = run_id or latest_run_id(config.run_root, self.target.name)
        self.paths = run_paths(config.run_root, self.run_id) if self.run_id else None
        self._client: Optional[Client] = None
        self._screen_pids: Optional[List[int]] = None

    # -- connection -------------------------------------------------------- #

    def connect(self) -> Client:
        if self._client is not None:
            return self._client
        if self.port is not None:
            client = Client(port=int(self.port), token=self.token)
        elif self.run_id:
            client = Client(run_root=self.config.run_root, run_id=self.run_id,
                            token=self.token)
        else:
            raise PrereqNotReady(
                "no run for target %s under %s; retry: python -m ctl install --target %s"
                % (self.target.name, self.config.run_root, self.target.name))
        if not client.ping(timeout=5.0):
            raise PrereqNotReady(
                "bridge not answering for run %s; retry: python -m ctl install --target %s --run-id %s"
                % (self.run_id or "<none>", self.target.name, self.run_id or "<run_id>"))
        self._client = client
        return client

    # -- screen guard plumbing --------------------------------------------- #

    def shots_dir(self) -> str:
        """``<run_root>/<run_id>/shots`` (a temp dir when no run is resolvable)."""
        if self.paths is not None:
            return self.paths.shots
        return os.path.join(tempfile.gettempdir(), "eclipse-ctl-shots",
                            self.run_id or "adhoc")

    def instance_pid(self) -> int:
        """The pid recorded in ``endpoint.json`` (0 when unknown)."""
        path = self.paths.endpoint if self.paths is not None else ""
        if not path or not os.path.isfile(path):
            return 0
        try:
            import json
            with open(path, "r", encoding="utf-8") as fh:
                return int(json.load(fh).get("pid") or 0)
        except (OSError, ValueError, TypeError):
            return 0

    def screen_pids(self) -> Optional[List[int]]:
        """Process set whose windows count as "this instance's".

        Starts from the recorded pid; when that process owns no visible window
        (the launcher can hand the workbench to a child JVM) the set is widened
        by command line.  ``None`` = every process.
        """
        if self._screen_pids is not None:
            return self._screen_pids
        recorded = self.instance_pid()
        if not recorded:
            return None
        pids = [recorded]
        try:
            if screen.visible_windows(pids):
                self._screen_pids = pids
                return pids
        except screen.ScreenError:
            return pids  # let `guard` surface the tool failure itself
        pids = sorted(set(pids) | set(self._pids_by_cmdline()))
        self._screen_pids = pids
        return pids

    def _pids_by_cmdline(self) -> List[int]:
        if self.paths is None:
            return []
        conf = self.paths.configuration.replace("\\", "/")
        ws = self.paths.workspace.replace("\\", "/")
        found: List[int] = []
        for row in list_processes():
            cmdline = (row.get("cmdline") or "").replace("\\", "/")
            if conf in cmdline or ws in cmdline:
                try:
                    found.append(int(row["pid"]))
                except (TypeError, ValueError):
                    continue
        return found

    def guarded(self, case: Case) -> bool:
        """Whether this case runs under the screen guard."""
        if not self.screen_guard:
            return False
        if case.screen_guard is None:
            return case.group == "write"
        return bool(case.screen_guard)

    # -- selection --------------------------------------------------------- #

    def select(self, case: Optional[str] = None, group: Optional[str] = None,
               all_: bool = False) -> List[Case]:
        from .cases import ALL_CASES

        if case:
            for candidate in ALL_CASES:
                if candidate.name == case:
                    return [candidate]
            raise NotFoundError(
                "no such case: %s; retry: python -m ctl verify --case read.ping" % case)
        if group:
            return [c for c in ALL_CASES if c.group == group]
        return list(ALL_CASES)

    # -- execution --------------------------------------------------------- #

    def run_case(self, case: Case) -> CaseResult:
        ctx = Ctx(self, case)
        pre = None
        result: object = None
        problems: List[str] = []
        passed = False
        detail = ""
        skipped = False
        error: Optional[str] = None
        try:
            if case.requires_bridge:
                self.connect()
                # Environment hygiene for the guard's pre-snapshot: a dialog-class
                # window left over from an earlier case sits *inside* the pre
                # snapshot, so a new identical failure looks like "nothing
                # happened" and `expects_dialog` cases fail spuriously (Eclipse
                # also coalesces repeats into "Multiple problems have occurred").
                #
                # It is NOT about a wedged UI thread.  Measured 2026-10-01: while
                # a modal is on screen, *other* connections' `ui.*` calls answer
                # normally -- SWT modality runs a nested event loop, so the
                # `asyncExec` queue keeps draining -- and only the request that
                # raised the dialog waits (then gets `ERR timeout`).
                # Scoped by class + pid, never by title; see clean_room.
                ctx.screen_pids = self.screen_pids()
                problems = self.clean_room(ctx)
            if case.pre is not None:
                pre = case.pre(ctx)
                ctx.note("pre: %s" % _short(pre))
            if self.guarded(case):
                ctx.guarded = True
                result, dialogs, info = screen.guard(
                    lambda: case.action(ctx), self.shots_dir(), case.name,
                    pids=ctx.screen_pids)
                ctx.dialogs, ctx.screen_info = dialogs, info
                ctx.screen_pre = info["pre"]              # type: ignore[assignment]
                _note_screen(ctx, dialogs, info)
                # A modal shell blocks the UI thread: dismiss it *before* the
                # read-back, otherwise every later `ui.*` call in this case
                # would come back as `ERR timeout`.
                problems = problems + self.dismiss(ctx)
            else:
                result = case.action(ctx)
                if bridge_dialog_lines(result):
                    # Unguarded mode only: the bridge says it saw a dialog, so make
                    # sure it cannot stay on screen and freeze the next case.
                    problems = problems + self.rescue_dialogs(ctx)
            outcome = case.expect(ctx, result)
            if isinstance(outcome, Skip):
                skipped, passed, detail = True, True, "skipped: " + outcome.reason
            else:
                passed, detail = outcome
            if ctx.guarded:
                screen_problems = _screen_verdict(case, ctx, result)
                problems = problems + screen_problems
            if case.post is not None:
                ctx.note("post: %s" % _short(case.post(ctx)))
        except Skip as skip_exc:
            skipped, passed, detail = True, True, "skipped: " + skip_exc.reason
        except ENV_NOT_READY:
            raise
        except screen.ScreenError as exc:
            passed, detail, error = False, "screen guard could not run: %s" % exc, str(exc)
        except CtlError as exc:
            passed, detail, error = False, "error: %s" % exc.line(), exc.line()
        except Exception as exc:  # noqa: BLE001 - a case must never kill the run
            passed, detail, error = False, "unexpected: %r" % (exc,), repr(exc)

        # A guard whose action blew up still leaves a dialog behind: dismiss on
        # every path, then sweep whatever appeared later (rollback, post, …).
        if ctx.dialogs and not ctx.dismissed:
            problems = problems + self.dismiss(ctx)
        leftover = self.final_sweep(ctx)
        if leftover:
            passed = False
            detail = detail + " | SCREEN: " + "; ".join(leftover)
        if problems:
            passed = False
            skipped = False          # a screen defect is not "cannot be exercised"
            detail = detail + " | SCREEN: " + "; ".join(problems)
        if not passed and case.rollback is not None:
            try:
                case.rollback(ctx)
                ctx.note("rollback: applied")
            except Exception as exc:  # noqa: BLE001
                ctx.note("rollback: failed %r" % (exc,))
        return CaseResult(case.name, case.group, bool(passed), detail, ctx.evidence,
                          skipped=skipped, error=error)

    # -- dialog dismissal --------------------------------------------------- #

    def clean_room(self, ctx: Ctx) -> List[str]:
        """Ask already-open dialogs to leave *before* the guard takes its pre-snapshot.

        Why this is load-bearing (measured 2026-10-01, on a real instance):
        Eclipse **coalesces repeated identical errors**.  The first bad
        ``showView`` pops ``Problem Occurred``; the next identical failure turns
        into the aggregate ``Multiple problems have occurred``, and the single
        box is replaced.  So if a dialog-class window is already on screen when a
        case starts -- left by an earlier probe, or by the previous run of this
        very case -- the guard's pre-snapshot *contains* it, a new identical
        failure is no longer "new", and ``expects_dialog`` cases fail spuriously:
        the case would be judging the environment, not the product.

        **Never by title.**  Only ``#32770`` (the Win32 dialog class) and only
        windows belonging to *this* instance (pid-scoped): ``ui.open`` retitles
        the main shell, so closing by name would close the workbench.
        """
        if not ctx.screen_pids:
            # ``screen_pids() is None`` means "every process".  Closing dialogs
            # system-wide would reach other applications' windows, so without the
            # instance's pid there is nothing safe to do here.
            ctx.note("screen: clean room skipped -- instance pid unknown, so the "
                     "dismissal cannot be scoped to this instance")
            return []
        try:
            windows = screen.visible_windows(ctx.screen_pids)
        except screen.ScreenError as exc:
            return ["clean room could not enumerate windows: %s" % exc]
        stale = {hwnd: meta for hwnd, meta in windows.items()
                 if meta[1] in DIALOG_CLASSES}
        if not stale:
            return []
        ctx.note("screen: clean room -- dismissing %d pre-existing dialog(s): %s"
                 % (len(stale), screen.describe(stale)))
        for _hwnd, (_pid, cls, title) in sorted(stale.items()):
            screen.close(title, cls, pids=ctx.screen_pids)
        time.sleep(DISMISS_SETTLE)
        try:
            left = screen.visible_windows(ctx.screen_pids)
        except screen.ScreenError as exc:
            return ["clean room re-check failed: %s" % exc]
        problems: List[str] = []
        for hwnd, (_pid, cls, title) in sorted(stale.items()):
            if hwnd in left:
                problems.append('pre-existing dialog survived the clean room: %s "%s" (%s)'
                                % (hwnd, title, cls))
        ctx.note("screen: clean room verified -- %d/%d pre-existing dialog(s) gone"
                 % (len(stale) - len(problems), len(stale)))
        return problems

    def rescue_dialogs(self, ctx: Ctx) -> List[str]:
        """Unguarded fallback: close dialog-class windows before they can linger.

        Only ``#32770`` (the Win32 dialog class) is targeted -- **never by title**:
        the bridge diffs *titles*, so a retitled main window (``ui.open``) would
        otherwise be closed by name.  The workbench shell is ``SWT_Window0``.
        """
        pids = ctx.screen_pids if ctx.screen_pids is not None else self.screen_pids()
        if not pids:
            # Same reasoning as `clean_room`: `None` = every process, and a
            # WM_CLOSE aimed at another application's dialog is worse than a
            # dialog left on screen.
            ctx.note("screen: unguarded rescue skipped -- instance pid unknown")
            return []
        try:
            windows = screen.visible_windows(pids)
        except screen.ScreenError as exc:
            return ["dialog rescue could not enumerate windows: %s" % exc]
        targets = {hwnd: meta for hwnd, meta in windows.items() if meta[1] in DIALOG_CLASSES}
        if not targets:
            ctx.note("screen: unguarded rescue -- bridge reported a dialog, no "
                     "%s window is on screen" % (", ".join(DIALOG_CLASSES),))
            return []
        ctx.note("screen: unguarded rescue -- %s" % screen.describe(targets))
        for hwnd, (pid, cls, title) in sorted(targets.items()):
            ctx.dialogs.append({"hwnd": hwnd, "pid": pid, "class": cls, "title": title,
                                "screenshot": None, "shot_note": "unguarded rescue"})
        return self.dismiss(ctx)

    def dismiss(self, ctx: Ctx) -> List[str]:
        """Answer every dialog the guard saw -- ``WM_CLOSE`` unless the case declared a
        button (see :meth:`answer_modal`) -- then prove each one is gone."""
        ctx.dismissed = True
        if not ctx.dialogs:
            return []
        if not ctx.screen_pids:
            # A WM_CLOSE without a pid scope could land on another application's
            # window.  Refusing is the safe side of that trade: the modal stays
            # (and later calls time out visibly) instead of someone else's
            # unsaved dialog being closed silently.
            return ["cannot dismiss dialogs: the instance pid is unknown, so a "
                    "WM_CLOSE could reach another application's window"]
        problems: List[str] = []
        for item in ctx.dialogs:
            self.answer_modal(ctx, item)
        time.sleep(DISMISS_SETTLE)
        left = screen.visible_windows(ctx.screen_pids)
        for item in ctx.dialogs:
            hwnd = str(item["hwnd"]).upper()
            if hwnd in left:
                problems.append('modal window survived WM_CLOSE: %s "%s" (%s)'
                                % (hwnd, item["title"], item["class"]))
        ctx.note("screen: dismissal verified -- %d/%d dialog(s) gone"
                 % (len(ctx.dialogs) - len(problems), len(ctx.dialogs)))
        return problems

    def close_modal(self, ctx: Ctx, item: Dict[str, object]) -> Dict[str, object]:
        """``WM_CLOSE`` one dialog: the window's X, i.e. *cancel*, never a choice.

        Split out of :meth:`answer_modal` so that a case can say "this run
        cancels" even while it has declared a button elsewhere.  Refuses without a
        pid scope, for the same reason :meth:`dismiss` does: an unscoped
        ``WM_CLOSE`` can land on another application's window.
        """
        title = str(item.get("title") or "")
        cls = str(item.get("class") or "")
        if not ctx.screen_pids:
            ctx.note('screen: refused WM_CLOSE "%s" -- the instance pid is unknown, so the '
                     "close cannot be scoped to this instance" % title)
            return {"action": "refused", "title": title, "class": cls,
                    "output": "no pid scope"}
        out = screen.close(title, cls, pids=ctx.screen_pids)
        ctx.note('screen: WM_CLOSE "%s" (%s) -> %s' % (title, cls, _short(out, 160) or "<no output>"))
        return {"action": "wm_close", "title": title, "class": cls, "output": out}

    def answer_modal(self, ctx: Ctx, item: Dict[str, object],
                     mode: str = "auto") -> Dict[str, object]:
        """Answer one modal dialog.  The **only** place a button is ever pressed.

        Default is ``WM_CLOSE`` -- exactly what clicking the title bar's X does:
        the dialog goes away, the pending action is cancelled, nothing is decided.
        A ``BM_CLICK`` on a named button happens *only* when the case declared it
        as ``expects_modal={"title": …, "button": …}`` and this dialog's title
        matches that declaration: pressing a button is an irreversible decision
        taken on the user's behalf, so it may never happen silently.

        ``mode="close"`` forces the cancel path for a case that deliberately
        measures "cancelled means unchanged" while still declaring the button for
        its sibling direction.
        """
        declared = ctx.case.expects_modal or {}
        want = str(declared.get("button") or "")
        want_title = str(declared.get("title") or "")
        title = str(item.get("title") or "")
        if mode != "close" and want and want_title and want_title.lower() in title.lower():
            out = screen.click_button(title, want, pids=ctx.screen_pids)
            # The tool prints the dialog and every child first and the click last;
            # the *click* is the part that must survive into the evidence.
            hits = [line.strip() for line in out.splitlines() if "BM_CLICK" in line]
            ctx.note('screen: BM_CLICK "%s" on "%s" (declared by the case) -> %s'
                     % (want, title, hits[0] if hits else _short(out, 200) or "<no output>"))
            return {"action": "bm_click", "title": title, "button": want, "output": out}
        return self.close_modal(ctx, item)

    def final_sweep(self, ctx: Ctx) -> List[str]:
        """Close anything that appeared after the guard's snapshot (rollback etc.)."""
        if not ctx.guarded or ctx.screen_pre is None:
            return []
        try:
            current = screen.visible_windows(ctx.screen_pids)
        except screen.ScreenError as exc:
            return ["final window sweep failed: %s" % exc]
        extra = screen.new_windows(ctx.screen_pre, current)
        known = {str(item["hwnd"]).upper() for item in ctx.dialogs}
        extra = {hwnd: meta for hwnd, meta in extra.items() if hwnd not in known}
        if not extra:
            ctx.note("screen: final sweep clean -- no window left behind")
            return []
        problems = []
        for hwnd, (pid, cls, title) in sorted(extra.items()):
            landed, note = screen.shoot_verbose(title, screen.shot_path(self.shots_dir(), ctx.case.name, title))
            ctx.note('screen: leftover window hwnd=%s class=%s title="%s" pid=%d shot=%s'
                     % (hwnd, cls, title, pid, note[:160] if landed else "<not written>"))
            ctx.dialogs.append({"hwnd": hwnd, "pid": pid, "class": cls, "title": title,
                                "screenshot": note if landed else None, "shot_note": note})
        problems += self.dismiss_one(ctx, extra)
        return problems

    def dismiss_one(self, ctx: Ctx, windows: screen.WindowMap) -> List[str]:
        problems: List[str] = []
        for hwnd, (pid, cls, title) in sorted(windows.items()):
            out = screen.close(title, cls, pids=ctx.screen_pids)
            ctx.note('screen: WM_CLOSE "%s" (%s) -> %s' % (title, cls, _short(out, 160) or "<no output>"))
        time.sleep(DISMISS_SETTLE)
        left = screen.visible_windows(ctx.screen_pids)
        for hwnd in windows:
            if hwnd.upper() in left:
                problems.append('leftover window survived WM_CLOSE: %s "%s"'
                                % (hwnd, windows[hwnd][2]))
        ctx.note("screen: leftover sweep verified -- %d/%d window(s) gone"
                 % (len(windows) - len(problems), len(windows)))
        return problems

    # -- batch ------------------------------------------------------------- #

    def run(self, cases: Sequence[Case]) -> List[CaseResult]:
        results = []
        for case in cases:
            if case.targets and self.target.name not in case.targets:
                results.append(CaseResult(case.name, case.group, True,
                                          "skipped: not applicable to target %s" % self.target.name,
                                          skipped=True))
                continue
            results.append(self.run_case(case))
        return results


# --------------------------------------------------------------------------- #
# Screen verdict / evidence
# --------------------------------------------------------------------------- #

def bridge_dialog_lines(result: object) -> List[str]:
    """Every ``dialog=`` payload line the bridge returned for this action."""
    lines: List[str] = []
    for response in _iter_responses(result):
        for raw in response.payload:
            text = raw.strip()
            if text.startswith("dialog="):
                lines.append(text)
    return lines


def _iter_responses(value: object, depth: int = 0) -> Iterable[object]:
    """Walk a case result for bridge responses (tuples/lists/dicts, 3 levels)."""
    if depth > 3:
        return
    if hasattr(value, "payload") and hasattr(value, "status_line"):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            for found in _iter_responses(item, depth + 1):
                yield found
    elif isinstance(value, dict):
        for item in value.values():
            for found in _iter_responses(item, depth + 1):
                yield found


def _screen_verdict(case: Case, ctx: Ctx, result: object) -> List[str]:
    """The guard's pass/fail input: unexpected dialog, or a channel mismatch."""
    problems: List[str] = []
    dialogs = ctx.dialogs
    if dialogs:
        names = ", ".join('"%s" (%s)' % (item["title"], item["class"]) for item in dialogs)
        shots = "; ".join(str(item["screenshot"] or "<no shot>") for item in dialogs)
        if case.expects_dialog:
            ctx.note("screen: expected dialog observed -- %s; screenshot(s): %s" % (names, shots))
        else:
            problems.append(
                "unexpected visible window during the write: %s; screenshot(s): %s "
                "-- read the shot and the read-back diff before trusting this call"
                % (names, shots))
    elif case.expects_dialog:
        problems.append("expects_dialog=True but no new visible window appeared")

    lines = bridge_dialog_lines(result)
    bridge_appeared = [line for line in lines if line.startswith("dialog=appeared")]
    bridge_unknown = [line for line in lines if line.startswith("dialog=unknown")]
    explained: List[str] = []
    if bridge_appeared and not dialogs:
        # The bridge diffs *titles*; this guard diffs *window handles*.  A write
        # that renames an existing shell (Eclipse puts the active editor into the
        # main window title on `ui.open`) shows up there as `dialog=appeared`
        # while nothing new appeared.  Say which of the two it was.
        titles = [title for line in bridge_appeared for title in screen.appeared_titles(line)]
        explained, unexplained = _explain_as_title_change(ctx, titles)
        if unexplained:
            problems.append("CHANNEL MISMATCH: the bridge reported %r but the independent "
                            "window enumeration saw no new window (and it is not a title "
                            "change of an existing one)" % (unexplained,))
    if dialogs and not bridge_appeared and not bridge_unknown:
        problems.append("CHANNEL MISMATCH: the window enumeration saw a new window but the "
                        "bridge reported no dialog= line (%s)" % (lines or ["<none>"]))
    if bridge_appeared or bridge_unknown:
        if problems:
            verdict_text = "MISMATCH"
        elif bridge_appeared and dialogs:
            verdict_text = "agree"
        elif bridge_appeared and explained:
            verdict_text = "title change on an existing window"
        elif bridge_unknown:
            verdict_text = "bridge blind, enumeration authoritative"
        else:
            verdict_text = "agree (no dialog on either channel)"
        ctx.note("screen: cross-check -- bridge %r | enumeration saw %d new window(s) -> %s"
                 % (lines[0], len(dialogs), verdict_text))
        if explained:
            ctx.note("screen: bridge dialog= explained as a title change, not a new window: %s"
                     % "; ".join(explained))
    elif dialogs:
        ctx.note("screen: cross-check -- bridge reported no dialog= line | enumeration saw "
                 "%d new window(s)" % len(dialogs))
    return problems


def _explain_as_title_change(ctx: Ctx, titles: List[str]
                             ) -> Tuple[List[str], List[str]]:
    """Split bridge-reported titles into "renamed existing window" and unexplained."""
    pre = ctx.screen_pre or {}
    post = (ctx.screen_info or {}).get("post") or {}
    pre_titles = {hwnd: meta[2] for hwnd, meta in pre.items()}
    explained: List[str] = []
    unexplained: List[str] = []
    for title in titles:
        renamed = [hwnd for hwnd, meta in post.items()
                   if meta[2] == title and hwnd in pre_titles and pre_titles[hwnd] != title]
        if renamed:
            explained.append('%s "%s" -> "%s"' % (renamed[0], pre_titles[renamed[0]], title))
        else:
            unexplained.append(title)
    return explained, unexplained


def _note_screen(ctx: Ctx, dialogs: List[Dict[str, object]], info: Dict[str, object]) -> None:
    ctx.note("screen: pre=%d post=%d new=%d (pid_filter=%s, settle=%.1fs, %.2fs)"
             % (len(info["pre"]), len(info["post"]), len(dialogs),  # type: ignore[arg-type]
                info["pid_filter"], info["settle"], info["elapsed"]))
    ctx.note("screen: post snapshot = %s" % _short(screen.describe(info["post"]), 400))  # type: ignore[arg-type]
    for item in dialogs:
        ctx.note('screen: dialog hwnd=%s class=%s title="%s" pid=%s'
                 % (item["hwnd"], item["class"], item["title"], item["pid"]))
        ctx.note("screen: shot -> %s | %s"
                 % (item["screenshot"] or "<not written>", item["shot_note"]))


def _short(value: object, limit: int = 120) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."
