"""Screen guard -- a second observation channel, independent of the bridge.

**Why it exists.**  The bridge answers ``OK`` for a write that fails
*asynchronously* (measured 2026-10-01: ``cmd.runp org.eclipse.ui.views.showView
viewId=com.gs.liveview`` -> ``OK`` + ``executeCommand returned: null``, while
Eclipse pops a ``Problem Occurred`` dialog and ``ui.parts`` does not move).  The
read-back diff alone cannot separate the two opposite causes of "the UI did not
change": *idempotent success* vs *failure*.  ``ICommandService``'s
``addExecutionListener`` cannot see it either -- the handler returns normally and
the error surfaces later, on the UI thread.

**What it does.**  Enumerate the visible top-level windows before and after a
write; the difference is a dialog.  Screenshot it, and hand back the facts.  It
never decides pass/fail by itself -- :class:`ctl.verify.runner.Runner` owns the
rule (see ``ctl/verify/runner.py``).

**Two measured traps that must not be simplified away:**

* enumerate **only** ``vis=true`` windows -- invisible top-level windows
  (tooltips, ``ForegroundStaging``, GDI+ hooks) are pure noise, and a real
  dialog is visible by definition;
* **drop windows with an empty title** -- toggling fullscreen pops an untitled
  transient top-level window; counting it as a dialog would be a false positive
  (the bridge's own probe applies the same rule, see ``LiveBridge.dispatch``).

All shelling out goes through ``pwsh -NoProfile`` so the user's PowerShell
profile (which sets proxies and prints to stdout) cannot contaminate the output.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
ENUM_PS1 = os.path.join(TOOLS_DIR, "win-enum.ps1")
SHOT_PS1 = os.path.join(TOOLS_DIR, "shot-window-pw.ps1")
CLOSE_PS1 = os.path.join(TOOLS_DIR, "win-close.ps1")
CLICK_PS1 = os.path.join(TOOLS_DIR, "win-click-button.ps1")

#: Win32 class of a classic menu popup: visible while a menu is tracked, never a
#: dialog.  (``#32770`` -- the dialog class -- is deliberately *not* ignored.)
MENU_CLASS = "#32768"
IGNORE_CLASSES: Tuple[str, ...] = (MENU_CLASS,)

#: Seconds to let an asynchronous dialog appear after the action returned.
#: Measured: the Eclipse error box shows up well inside this window.
SETTLE = 1.5

#: ``pid=… hwnd=0x… vis=… en=… owner=0x… class=… title=…`` (``win-enum.ps1``).
_LINE = re.compile(
    r"^pid=(\d+)\s+hwnd=(0x[0-9A-Fa-f]+)\s+vis=(\w+)\s+en=(\w+)\s+"
    r"owner=(0x[0-9A-Fa-f]+)\s+class=(\S*)\s+title=(.*)$")

#: ``{hwnd: (pid, class, title)}``
WindowMap = Dict[str, Tuple[int, str, str]]

#: Titles quoted inside a bridge ``dialog=appeared "a", "b"`` payload line.
_QUOTED = re.compile(r'"([^"]*)"')


def appeared_titles(line: str) -> List[str]:
    """The window titles a bridge ``dialog=appeared …`` line lists."""
    return _QUOTED.findall(line or "")


class ScreenError(RuntimeError):
    """The guard could not produce a trustworthy observation.

    Raised instead of returning "no dialogs": a broken enumeration must never be
    mistaken for "the write popped nothing".
    """


# --------------------------------------------------------------------------- #
# Tool plumbing
# --------------------------------------------------------------------------- #

def _proc_id_arg(tool: str, pids: Optional[Iterable[int]]) -> List[str]:
    """The ``-ProcId`` argv slice for one ``tools/*.ps1`` call -- or fail closed.

    ``-ProcId`` is a single ``[int]`` (``0`` = any process) in every helper, so a
    *set* of candidate pids cannot be expressed.  Dropping the constraint when
    there was more than one candidate made ``close`` / ``buttons`` /
    ``click_button`` act on a same-titled window of **any** process -- a silent
    wrong-target press or ``WM_CLOSE``, the failure class this module exists to
    notice (``A4-1a``).  Refusing names the candidates so the caller can narrow
    them, instead of quietly widening the scope.

    ``pids=None`` is kept as the caller's *explicit* "every process" (the default
    :func:`visible_windows` documents); it is never reached by dropping a set.
    """
    if pids is None:
        return []
    wanted = sorted({int(p) for p in pids})
    if len(wanted) == 1:
        return ["-ProcId", str(wanted[0])]
    raise ScreenError(
        "%s cannot be scoped to %d candidate pid(s) [%s]: its -ProcId takes one int, "
        "so dropping the scope would act on any process's window; narrow the instance "
        "to a single pid first"
        % (os.path.basename(tool), len(wanted), ", ".join(str(p) for p in wanted)))


def _tool_argv(tool: str, flags: Sequence[str],
               pids: Optional[Iterable[int]]) -> List[str]:
    """``[tool, *flags, …]`` with the pid scope appended (see :func:`_proc_id_arg`)."""
    return [tool] + list(flags) + _proc_id_arg(tool, pids)


def _pwsh(args: Sequence[str], timeout: float = 60.0) -> Tuple[int, str]:
    """Run ``pwsh -NoProfile -File …``; -> ``(returncode, stdout+stderr)``."""
    argv = ["pwsh", "-NoProfile", "-File"] + list(args)
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise ScreenError("pwsh is not on PATH (%s)" % exc)
    except subprocess.TimeoutExpired:
        raise ScreenError("pwsh timed out after %.0fs: %s" % (timeout, " ".join(argv[1:])))
    raw = (proc.stdout or b"") + (proc.stderr or b"")
    text = raw.decode("utf-8", "replace")
    if "\ufffd" in text:
        # PowerShell encodes its own output with the *console* code page when
        # stdout is redirected (GBK on this box), so non-ASCII window titles come
        # back as replacement chars.  Re-decode with the ANSI page before giving
        # up; ASCII titles (every dialog we assert on) are unaffected.
        for encoding in ("cp936", "mbcs", "latin-1"):
            try:
                fallback = raw.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
            if "\ufffd" not in fallback:
                text = fallback
                break
    return proc.returncode, text


# --------------------------------------------------------------------------- #
# Window enumeration
# --------------------------------------------------------------------------- #

def visible_windows(pids: Optional[Iterable[int]] = None) -> WindowMap:
    """Visible top-level windows with a non-empty title -> ``{hwnd: (pid, class, title)}``.

    ``pids`` restricts the result to a process set (``None`` = every process).
    Raises :class:`ScreenError` when the enumeration itself failed, so an empty
    mapping always means "no such window", never "the tool broke".
    """
    code, out = _pwsh([ENUM_PS1], timeout=60.0)
    parsed: WindowMap = {}
    matched = 0
    for line in out.splitlines():
        match = _LINE.match(line.strip())
        if not match:
            continue
        matched += 1
        pid_text, hwnd, vis, _enabled, _owner, cls, title = match.groups()
        if vis.lower() != "true":
            continue
        title = title.strip()
        if not title:            # fullscreen toggles pop untitled transient windows
            continue
        parsed[hwnd.upper()] = (int(pid_text), cls, title)
    if code != 0 or (matched == 0 and out.strip()):
        raise ScreenError("win-enum.ps1 failed (rc=%d): %s" % (code, out.strip()[:400]))
    if pids is not None:
        wanted = set(int(p) for p in pids)
        parsed = {hwnd: meta for hwnd, meta in parsed.items() if meta[0] in wanted}
    return parsed


def new_windows(pre: WindowMap, post: WindowMap,
                ignore_classes: Sequence[str] = IGNORE_CLASSES) -> WindowMap:
    """Windows present in ``post`` but not in ``pre`` (i.e. newly appeared)."""
    added: WindowMap = {}
    for hwnd, meta in post.items():
        if hwnd in pre:
            continue
        if meta[1] in ignore_classes:
            continue
        added[hwnd] = meta
    return added


def describe(windows: WindowMap) -> str:
    """One-line, evidence-friendly rendering of a window map."""
    if not windows:
        return "0 window(s)"
    return "%d window(s): %s" % (len(windows), ", ".join(
        '%s "%s" (%s, pid=%d)' % (hwnd, title, cls, pid)
        for hwnd, (pid, cls, title) in sorted(windows.items())))


# --------------------------------------------------------------------------- #
# Screenshots / dismissal
# --------------------------------------------------------------------------- #

def shot_path(shots_dir: str, tag: str, title: str, when: Optional[time.struct_time] = None) -> str:
    """``<shots_dir>/<tag>-<HHMMSS>-<title-slug>.png`` (case name + wall clock)."""
    stamp = time.strftime("%H%M%S", when or time.localtime())
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", title or "").strip("_")[:40] or "dialog"
    base = re.sub(r"[^0-9A-Za-z._-]+", "_", tag).strip("_") or "case"
    return os.path.join(shots_dir, "%s-%s-%s.png" % (base, stamp, slug))


def shoot_argv(title_like: str, out_path: str, flags: Optional[int] = None,
               pids: Optional[Iterable[int]] = None) -> List[str]:
    """The exact argv :func:`shoot_verbose` runs (printable without touching any window)."""
    args = ["-TitleLike", title_like, "-Out", out_path]
    if flags is not None:
        args += ["-Flags", str(int(flags))]
    return _tool_argv(SHOT_PS1, args, pids)


def shoot(title_like: str, out_path: str, timeout: float = 60.0,
          flags: Optional[int] = None, pids: Optional[Iterable[int]] = None) -> bool:
    """Screenshot the visible window whose title contains ``title_like``.

    Returns whether the PNG actually landed on disk (``shot-window-pw.ps1`` uses
    PrintWindow, so the shot is immune to occlusion and DPI virtualisation).
    ``pids`` carries the same single-pid-or-refuse contract as :func:`close`.
    """
    ok, _note = shoot_verbose(title_like, out_path, timeout, flags=flags, pids=pids)
    return ok


def shoot_verbose(title_like: str, out_path: str,
                  timeout: float = 60.0, flags: Optional[int] = None,
                  pids: Optional[Iterable[int]] = None
                  ) -> Tuple[bool, str]:
    """``shoot`` plus the tool's verbatim output (kept as evidence).

    ``pids`` is **not optional in practice for evidence**: window titles are not
    unique (measured: two processes both called ``ws - GS32_Studio``), so a shot
    taken by title alone can be another instance's window -- a wrong picture that
    *looks* like proof (`facts-runtime.md` §13 / §13.2: pick the pid from
    ``endpoint.json`` first).  Callers that already know the window's own pid must
    pass it as ``pids=[pid]``; a *set* is refused (see :func:`_proc_id_arg`).

    ``flags`` is ``PrintWindow``'s flag word.  Live modals are shot with
    ``flags=0`` as a **conservative choice**: it renders the dialog legibly and is
    the least intrusive render available.

    ⚠️ **A stronger claim was made about ``flags=2`` and is NOT substantiated --
    do not repeat it as fact.**  It was reported that the default ``2``
    (``PW_RENDERFULLCONTENT``) makes a live SWT modal *disappear a few seconds
    later*, flipping the pending request from ``ERR timeout`` to ``OK`` (i.e. the
    observation destroying what it observes).  Two independent attempts to
    reproduce it (2026-10-01, screenshots taken ~0.7 s and ~13 s after the dialog
    appeared, with a no-screenshot control) showed the dialog staying on screen
    for 49 s and the initiator answering ``ERR timeout`` in both arms --
    identical to the control.  What *is* real: the two flag words produce
    different bytes (15821 vs 14057 on the same dialog), so they are not
    interchangeable renderings.
    """
    argv = shoot_argv(title_like, out_path, flags, pids)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    _code, note = _pwsh(argv, timeout=timeout)
    return os.path.isfile(out_path), note.strip()[:400]


def close_argv(title_like: str, cls: str = "",
               pids: Optional[Iterable[int]] = None) -> List[str]:
    """The exact argv :func:`close` runs (printable without touching any window)."""
    flags = ["-TitleLike", title_like]
    if cls:
        flags += ["-Class", cls]
    return _tool_argv(CLOSE_PS1, flags, pids)


def close(title_like: str, cls: str = "", pids: Optional[Iterable[int]] = None,
          timeout: float = 60.0) -> str:
    """Post ``WM_CLOSE`` to every visible window whose title contains ``title_like``.

    ``pids`` is the instance scope: a **single** pid becomes ``-ProcId``, and a
    *set* (the runner widens the recorded pid by command line when the launcher
    handed the workbench to a child JVM) is **refused** -- the tool cannot express
    a set, and dropping the constraint would close another instance's window
    (``A4-1a``).  ``pids=None`` stays the explicit "every process" scope.

    Returns the tool's verbatim output (``no window matched '…'`` when nothing
    matched).  Callers must *re-observe* afterwards: a posted ``WM_CLOSE`` is a
    request, not a guarantee.
    """
    _code, out = _pwsh(close_argv(title_like, cls, pids), timeout=timeout)
    return out.strip()[:400]


#: ``  hwnd=0x… class=Button vis=True text="…" rect=…`` from ``win-click-button.ps1``.
_BUTTON = re.compile(r'^\s*hwnd=(0x[0-9A-Fa-f]+)\s+class=(\S+)\s+vis=(\w+)\s+text="(.*)"\s+rect=')


def buttons_argv(title_like: str,
                 pids: Optional[Iterable[int]] = None) -> List[str]:
    """The exact argv :func:`buttons` runs (printable without touching any window)."""
    return _tool_argv(CLICK_PS1, ["-TitleLike", title_like, "-ListOnly"], pids)


def buttons(title_like: str, pids: Optional[Iterable[int]] = None,
            timeout: float = 60.0) -> List[Tuple[str, str]]:
    """``[(hwnd, text), …]`` for the visible ``Button`` children of a dialog.

    The dialog is addressed **by title** (``win-click-button.ps1`` has no class
    filter); callers that need the identity of the window must cross-check it
    against :func:`visible_windows` first.  ``pids`` carries the same
    single-pid-or-refuse contract as :func:`close` (``A4-1a``).
    """
    _code, out = _pwsh(buttons_argv(title_like, pids), timeout=timeout)
    found: List[Tuple[str, str]] = []
    for line in out.splitlines():
        match = _BUTTON.match(line)
        if match and match.group(3).lower() == "true" and match.group(2) == "Button":
            found.append((match.group(1).upper(), match.group(4)))
    return found


def click_button_argv(title_like: str, text: str,
                      pids: Optional[Iterable[int]] = None) -> List[str]:
    """The exact argv :func:`click_button` runs (printable without touching any window)."""
    return _tool_argv(CLICK_PS1, ["-TitleLike", title_like, "-Text", text], pids)


def click_button(title_like: str, text: str, pids: Optional[Iterable[int]] = None,
                 timeout: float = 60.0) -> str:
    """Press the ``Button`` whose text contains ``text`` via ``BM_CLICK``.

    A button press **answers a question on the user's behalf**; it is the caller's
    job to have narrowed that to a declared, deliberate decision (see
    ``Runner.answer_modal``).  ``pids`` carries the same single-pid-or-refuse
    contract as :func:`close`: pressing the identically-labelled button of another
    instance is exactly the "silent wrong click" this refusal prevents (``A4-1a``).
    Returns the tool's verbatim output, which names the ``hwnd`` it actually
    clicked -- or says that nothing matched, which the caller must treat as
    "not pressed".
    """
    _code, out = _pwsh(click_button_argv(title_like, text, pids), timeout=timeout)
    return out.strip()[:1200]


# --------------------------------------------------------------------------- #
# The guard itself
# --------------------------------------------------------------------------- #

def guard(do_action: Callable[[], object], shots_dir: str, tag: str,
          pids: Optional[Iterable[int]] = None, settle: float = SETTLE
          ) -> Tuple[object, List[Dict[str, object]], Dict[str, object]]:
    """Run ``do_action`` with a before/after window snapshot around it.

    -> ``(action_result, dialogs, info)`` where ``dialogs`` holds one record per
    newly appeared window (``hwnd``, ``pid``, ``class``, ``title``,
    ``screenshot``, ``shot_note``) and ``info`` carries the raw snapshots,
    the elapsed time and the process filter used.
    """
    pre = visible_windows(pids)
    if pids is not None and not pre:
        raise ScreenError(
            "no visible top-level window for pid(s) %s -- the recorded instance pid is "
            "stale or the window belongs to another process" % (list(pids),))
    started = time.time()
    result = do_action()
    if settle > 0:
        time.sleep(settle)
    post = visible_windows(pids)
    fresh = new_windows(pre, post)

    dialogs: List[Dict[str, object]] = []
    if fresh:
        os.makedirs(shots_dir, exist_ok=True)
    for hwnd, (pid, cls, title) in sorted(fresh.items()):
        path = shot_path(shots_dir, tag, title)
        if os.path.isfile(path):
            path = path[:-4] + "-" + hwnd.lstrip("0x")[-4:] + ".png"
        landed, note = shoot_verbose(title, path, pids=[pid])
        dialogs.append({
            "hwnd": hwnd,
            "pid": pid,
            "class": cls,
            "title": title,
            "screenshot": path if landed else None,
            "shot_note": note,
        })
    info = {"pre": pre, "post": post, "new": fresh, "pid_filter": list(pids) if pids else None,
            "settle": settle, "elapsed": round(time.time() - started, 2),
            "shots_dir": shots_dir}
    return result, dialogs, info
