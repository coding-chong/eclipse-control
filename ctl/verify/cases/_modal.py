"""Shared plumbing for the resilience cases: a modal dialog, and a timed request.

Both resilience cases need the same three things, and getting any of them wrong
silently invalidates the measurement:

* address the dialog-class window (``#32770``) of **this instance only** -- never
  by title and never across processes, for the same reason ``Runner.clean_room``
  gives: ``ui.open`` retitles the main shell, so a title-addressed ``WM_CLOSE``
  can reach the workbench itself;
* **poll** for it: SWT creates the shell asynchronously, *after* the command that
  asked for it has already returned;
* time each call on a **fresh connection** (`Client` opens one per request), which
  is what makes "the bridge is still serving other connections" a statement about
  the bridge rather than about a shared socket.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional, Tuple

from ... import screen
from ..runner import Skip
from ._util import search

#: Win32 class of a real dialog (same vocabulary as ``runner.DIALOG_CLASSES``).
DIALOG_CLASS = "#32770"

#: Poll cadence while waiting for the shell to appear.
POLL_S = 0.4


def dialogs(ctx) -> Dict[str, Tuple[int, str, str]]:
    """Visible ``#32770`` windows of this instance -> ``{hwnd: (pid, class, title)}``."""
    windows = screen.visible_windows(ctx.screen_pids)
    return {hwnd: meta for hwnd, meta in windows.items() if meta[1] == DIALOG_CLASS}


def dialog_item(hwnd: str, meta: Tuple[int, str, str]) -> Dict[str, object]:
    """The shape ``Runner.answer_modal`` / ``Runner.close_modal`` take."""
    pid, cls, title = meta
    return {"hwnd": hwnd, "pid": pid, "class": cls, "title": title}


def probe(ctx, method: str, budget: float) -> Tuple[object, float]:
    """One request on a **fresh connection**, with the round trip timed."""
    started = time.time()
    response = ctx.client.request(method, timeout=budget)
    return response, time.time() - started


def ui_timeout_ms(ctx) -> Optional[int]:
    """The bridge's own ``uiTimeoutMs``, read from ``sys.env`` (never assumed)."""
    text = ctx.request("sys.env").text
    value = search(r"uiTimeoutMs=(\d+)", text)
    ctx.note("bridge: uiTimeoutMs=%s (read from sys.env)" % value)
    return int(value) if value else None


class ModalWrite:
    """A ``cmd.run <id>`` sent from its own connection, with the modal it opens.

    ``start()`` returns immediately, ``wait_dialog()`` polls for the shell, and
    ``join()`` blocks for the answer.  The three are separate on purpose: what a
    modal *costs* cannot be measured after it is gone, and what the bridge does
    *for everybody else* has to be observed while it is still on screen.
    """

    def __init__(self, ctx, request: str, client_wait: float = 40.0,
                 dialog_wait: float = 12.0, poll: float = POLL_S):
        self.ctx = ctx
        self.request = request
        self.client_wait = client_wait
        self.dialog_wait = dialog_wait
        self.poll = poll
        self.sent_at = 0.0
        self.appeared_after: Optional[float] = None
        self.dialog: Optional[Tuple[str, Tuple[int, str, str]]] = None
        self.status_line = ""
        self.raw = ""
        self.elapsed = 0.0
        self.error = ""
        self._box: Dict[str, object] = {}
        self._thread: Optional[threading.Thread] = None

    # -- lifecycle ---------------------------------------------------------- #

    def start(self) -> None:
        # Resolve the client before the thread starts: `Ctx.client` builds on
        # first use, and racing that from two threads would be a harness bug.
        client = self.ctx.client
        self.sent_at = time.time()
        self.ctx.note("1. request  at=%s  sent=%r"
                      % (time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.sent_at)),
                         self.request))

        def initiator():
            started = time.time()
            try:
                self._box["response"] = client.request(self.request, timeout=self.client_wait)
            except Exception as exc:  # noqa: BLE001 - evidence, judged by expect
                self._box["error"] = repr(exc)
            self._box["elapsed"] = time.time() - started

        self._thread = threading.Thread(target=initiator, name="resilience.initiator")
        self._thread.start()

    def wait_dialog(self) -> Optional[Tuple[float, str, Tuple[int, str, str]]]:
        """Poll for the shell; ``None`` when it never showed (the caller decides)."""
        started = time.time()
        while time.time() - started < self.dialog_wait:
            found = dialogs(self.ctx)
            if found:
                hwnd = sorted(found)[0]
                self.appeared_after = time.time() - started
                self.dialog = (hwnd, found[hwnd])
                pid, cls, title = found[hwnd]
                self.ctx.note('screen: modal on screen %.2fs after the send -- hwnd=%s '
                              'class=%s pid=%s title="%s"' % (self.appeared_after, hwnd, cls, pid, title))
                return (self.appeared_after, hwnd, found[hwnd])
            time.sleep(self.poll)
        self.appeared_after = None
        return None

    def join(self) -> Dict[str, object]:
        """Block for the initiator's own answer; returns the segment-2 evidence."""
        if self._thread is not None:
            self._thread.join(self.client_wait + 5)
        response = self._box.get("response")
        self.elapsed = float(self._box.get("elapsed") or 0.0)
        self.status_line = getattr(response, "status_line", None) or str(self._box.get("error") or "")
        self.raw = getattr(response, "raw", "") or ""
        self.error = str(self._box.get("error") or "")
        self.ctx.note("2. initiator answered %.2fs after the request (delta from segment 1) "
                      "-> %s" % (self.elapsed, self.status_line))
        for line in self.raw.splitlines():
            if line.strip().startswith("dialog="):
                self.ctx.note("2. bridge's own window-diff line: %s" % line.strip())
        return self.as_dict()

    # -- views -------------------------------------------------------------- #

    def as_dict(self) -> Dict[str, object]:
        hwnd, meta = self.dialog if self.dialog else ("", (0, "", ""))
        return {
            "request": self.request,
            "sent_at": self.sent_at,
            "appeared_after": self.appeared_after,
            "dialog": dialog_item(hwnd, meta) if self.dialog else None,
            "status_line": self.status_line,
            "raw": self.raw,
            "elapsed": self.elapsed,
            "error": self.error,
            "bridge_dialog_lines": [line.strip() for line in self.raw.splitlines()
                                    if line.strip().startswith("dialog=")],
        }

    def require_dialog(self) -> Dict[str, object]:
        """``Skip`` (never a silent pass) when this instance did not pop a modal."""
        if self.dialog is None:
            raise Skip("no %s dialog appeared within %.0f s, so this instance cannot "
                       "exercise the modal path (initiator answered %r)"
                       % (DIALOG_CLASS, self.dialog_wait, self.join()["status_line"]))
        return self.as_dict()
