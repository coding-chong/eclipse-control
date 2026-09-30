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
import shutil
import subprocess
import time
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
ENUM_PS1 = os.path.join(TOOLS_DIR, "win-enum.ps1")
SHOT_PS1 = os.path.join(TOOLS_DIR, "shot-window-pw.ps1")
CLOSE_PS1 = os.path.join(TOOLS_DIR, "win-close.ps1")

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

def tools_available() -> bool:
    """True when the three ``tools/*.ps1`` helpers can be reached at all."""
    return (shutil.which("pwsh") is not None
            and all(os.path.isfile(p) for p in (ENUM_PS1, SHOT_PS1, CLOSE_PS1)))


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


def shoot(title_like: str, out_path: str, timeout: float = 60.0) -> bool:
    """Screenshot the visible window whose title contains ``title_like``.

    Returns whether the PNG actually landed on disk (``shot-window-pw.ps1`` uses
    PrintWindow, so the shot is immune to occlusion and DPI virtualisation).
    """
    ok, _note = shoot_verbose(title_like, out_path, timeout)
    return ok


def shoot_verbose(title_like: str, out_path: str,
                  timeout: float = 60.0) -> Tuple[bool, str]:
    """``shoot`` plus the tool's verbatim output (kept as evidence)."""
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    _code, note = _pwsh([SHOT_PS1, "-TitleLike", title_like, "-Out", out_path], timeout=timeout)
    return os.path.isfile(out_path), note.strip()[:400]


def close(title_like: str, cls: str = "", pids: Optional[Iterable[int]] = None,
          timeout: float = 60.0) -> str:
    """Post ``WM_CLOSE`` to every visible window whose title contains ``title_like``.

    Returns the tool's verbatim output (``no window matched '…'`` when nothing
    matched).  Callers must *re-observe* afterwards: a posted ``WM_CLOSE`` is a
    request, not a guarantee.
    """
    args = [CLOSE_PS1, "-TitleLike", title_like]
    if cls:
        args += ["-Class", cls]
    if pids is not None:
        wanted = [int(p) for p in pids]
        if len(wanted) == 1:
            args += ["-ProcId", str(wanted[0])]
    _code, out = _pwsh(args, timeout=timeout)
    return out.strip()[:400]


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
        landed, note = shoot_verbose(title, path)
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
