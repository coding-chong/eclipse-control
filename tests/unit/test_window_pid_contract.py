"""The window-addressing *pid contract* (`A4-1a` / `A4-1b`).

Two defects, one rule: a dialog is addressed **inside a process**, and when that
process is unknown the addressing must fail rather than widen.

* ``A4-1a`` -- ``screen.close`` / ``buttons`` / ``click_button`` passed
  ``-ProcId`` only when the caller handed over *exactly one* pid; a set (the
  runner widens the recorded pid by command line when the launcher hands the
  workbench to a child JVM) silently dropped the constraint, so a same-titled
  window of **any** process became fair game -- a silent wrong-target close or
  button press.
* ``A4-1b`` -- the element-addressed input primitives (``act_click_button`` /
  ``act_send_keys`` / ``act_set_text``; the ``ctl act`` CLI subcommand that once
  fronted them is gone, ``deliverable-shape.md`` C3) never passed a pid at all,
  while the run door's ``run.py::_click_button`` always did.

The helpers here are pure argv builders plus one in-process call with the tool
runner replaced by a mock: **no window is ever touched**.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from ctl import run
from ctl import screen
from ctl.client import Client
from ctl.errors import PrereqNotReady, UsageError

_LISTING = ('dialog hwnd=0x1\n-- child windows --\n'
            '  hwnd=0x2 class=Button vis=True text="OK" rect=0,0,10,10\n'
            '  hwnd=0x3 class=Edit vis=True text="" rect=0,0,10,10\n')


def _proc_id(argv):
    """The ``-ProcId`` value in ``argv`` (``None`` when the flag is absent)."""
    return argv[argv.index("-ProcId") + 1] if "-ProcId" in argv else None


class ScreenPidScopeTest(unittest.TestCase):
    """``close`` / ``buttons`` / ``click_button``: one pid -- or refuse."""

    def _builders(self, pids):
        return (lambda: screen.close_argv("T", "", pids),
                lambda: screen.buttons_argv("T", pids),
                lambda: screen.click_button_argv("T", "OK", pids))

    def test_single_pid_reaches_every_helper(self):
        for build in self._builders([4242]):
            self.assertEqual(_proc_id(build()), "4242")

    def test_multi_pid_is_refused_and_names_the_candidates(self):
        for build in self._builders([5150, 4242]):
            with self.assertRaises(screen.ScreenError) as caught:
                build()
            self.assertIn("4242", str(caught.exception))
            self.assertIn("5150", str(caught.exception))

    def test_empty_scope_is_refused_rather_than_widened(self):
        for build in self._builders([]):
            with self.assertRaises(screen.ScreenError):
                build()

    def test_none_is_the_explicit_any_process_scope(self):
        # `visible_windows`' documented default, and what the guard passes when
        # the instance pid is unknown.  It must stay distinguishable from a set
        # that got silently dropped.
        for build in self._builders(None):
            self.assertIsNone(_proc_id(build()))

    def test_ambiguous_scope_never_reaches_the_tool(self):
        with mock.patch.object(screen, "_pwsh") as pwsh:
            for call in (lambda: screen.close("T", "", [1, 2]),
                         lambda: screen.buttons("T", [1, 2]),
                         lambda: screen.click_button("T", "OK", [1, 2])):
                with self.assertRaises(screen.ScreenError):
                    call()
        pwsh.assert_not_called()


class ShotPidScopeTest(unittest.TestCase):
    """``shoot`` / ``shoot_verbose``: the frame is of *that window's* process.

    Title alone is not an address (measured: two processes both called
    ``ws - GS32_Studio``), so the screenshot -- evidence for a FAIL -- must carry
    the same pid scope as the action it documents.
    """

    def test_single_pid_reaches_the_shot_tool(self):
        for flags in (None, 0):
            argv = screen.shoot_argv("T", "out.png", flags, [4242])
            self.assertEqual(_proc_id(argv), "4242")
            self.assertIn("out.png", argv)

    def test_multi_pid_is_refused_rather_than_photographed(self):
        with self.assertRaises(screen.ScreenError) as caught:
            screen.shoot_argv("T", "out.png", None, [4242, 5150])
        self.assertIn("4242", str(caught.exception))

    def test_none_stays_the_explicit_any_process_scope(self):
        self.assertIsNone(_proc_id(screen.shoot_argv("T", "out.png", 0, None)))

    def test_guard_shoots_a_dialog_in_its_own_process(self):
        main = {"0X1": (4242, "SWT_Window0", "Main")}
        post = dict(main)
        post["0X2"] = (5150, "#32770", "Problem Occurred")
        shots = tempfile.mkdtemp(prefix="eclipse-ctl-shots-")
        self.addCleanup(shutil.rmtree, shots, ignore_errors=True)
        calls = []
        with mock.patch.object(screen, "visible_windows", side_effect=[main, post]), \
                mock.patch.object(screen, "_pwsh",
                                  side_effect=lambda argv, timeout=60.0: (calls.append(list(argv)) or (0, ""))):
            _result, dialogs, _info = screen.guard(lambda: None, shots, "case",
                                                   pids=[4242, 5150], settle=0)
        self.assertEqual([item["title"] for item in dialogs], ["Problem Occurred"])
        # The window's *own* pid -- not the caller's widened set, which the shot
        # tool cannot express and which would therefore have to be refused.
        self.assertEqual(_proc_id(calls[-1]), "5150")


class _Recorder:
    """A ``run._tool`` stand-in: records argv, answers one fixed listing."""

    def __init__(self, listing=_LISTING):
        self.listing = listing
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        return (0, self.listing)


class RunDoorPidTest(unittest.TestCase):
    """The library input primitives address the run recorded in ``endpoint.json``.

    They used to live behind ``ctl act`` (``A4-1b``); the door is gone and the rule
    is unchanged -- the pid comes from ``<run_root>/<run_id>/endpoint.json``, and a
    run that records none fails closed instead of addressing any process's window.
    """

    RUN = "gs32-20261004-1010"

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="eclipse-ctl-pid-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        # The environment layer sits above the file layer; a machine with
        # ECLIPSE_CTL_RUN_ROOT set must not redirect this test at its real runs.
        removed = {}
        for key in ("ECLIPSE_CTL_RUN_ROOT", "ECLIPSE_CTL_DEFAULT_TARGET"):
            if key in os.environ:
                removed[key] = os.environ.pop(key)
        self.addCleanup(os.environ.update, removed)
        self.tool = _Recorder()
        self._tool = run._tool
        run._tool = self.tool
        self.addCleanup(setattr, run, "_tool", self._tool)
        which = mock.patch.object(run.shutil, "which", return_value="pwsh")
        which.start()
        self.addCleanup(which.stop)

    def _endpoint(self, pid):
        run_dir = os.path.join(self.root, self.RUN)
        os.makedirs(run_dir, exist_ok=True)
        with open(os.path.join(run_dir, "endpoint.json"), "w", encoding="utf-8") as fh:
            json.dump({"port": 50999, "pid": pid}, fh)

    def _client(self, run_id=None):
        return Client(port=50999, run_root=self.root, run_id=run_id or self.RUN)

    def test_every_call_carries_the_recorded_pid(self):
        self._endpoint(4242)
        run._click_button(self._client(), "OK", None, "T", True)
        run._send_input(self._client(), "send-keys", "T", "Edit", None, "RETURN", None, True)
        run._send_input(self._client(), "set-text", "T", "Edit", None, None, "hello", True)
        self.assertTrue(self.tool.calls)
        for argv in self.tool.calls:
            self.assertEqual(_proc_id(argv), "4242")

    def test_a_run_recording_no_pid_fails_closed(self):
        self._endpoint(None)
        with mock.patch.object(run, "_tool") as tool:
            with self.assertRaises(PrereqNotReady) as caught:
                run._click_button(self._client(), "OK", None, "T", True)
        self.assertIn("records no pid", str(caught.exception))
        self.assertIn("retry:", str(caught.exception))
        tool.assert_not_called()

    def test_a_missing_run_fails_closed(self):
        with mock.patch.object(run, "_tool") as tool:
            with self.assertRaises(PrereqNotReady):
                run._click_button(self._client(run_id="gs32-nope"), "OK", None, "T", True)
        tool.assert_not_called()

    def test_usage_errors_win_over_the_missing_pid(self):
        # A missing key is the caller's mistake and must be reported as such, not
        # masked by "this run records no pid" (no pid is resolvable here).
        with mock.patch.object(run, "_tool") as tool:
            with self.assertRaises(UsageError):
                run._send_input(self._client(run_id="gs32-nope"), "send-keys", "T",
                                "Edit", None, None, None, True)
        tool.assert_not_called()


class ButtonListingTest(unittest.TestCase):
    """``screen.buttons`` reads the same listing; a label stays one control.

    ``text="…"`` is a JSON string body written by ``tools/win-click-button.ps1``
    (its ``Esc``), so the label comes back exactly as ``GetWindowTextW`` gave it --
    line breaks included, and never as a second ``hwnd=…`` control line.
    """

    LABEL = 'x\r\n  hwnd=0x3 class=Button vis=True text="y" rect=0,0,1,1'
    ESCAPED = r'x\r\n  hwnd=0x3 class=Button vis=True text=\"y\" rect=0,0,1,1'

    def _listing(self, field):
        return ('window hwnd=0x1\n-- child windows --\n'
                '  hwnd=0x2 class=Button vis=True text="%s" rect=0,0,10,10\n' % field)

    def _buttons(self, listing):
        with mock.patch.object(screen, "_pwsh", return_value=(0, listing)):
            return screen.buttons("T", [4242])

    def test_a_label_with_a_line_break_decodes_to_one_button(self):
        self.assertEqual(self._buttons(self._listing(self.ESCAPED)),
                         [("0X2", self.LABEL)])

    def test_an_unescaped_line_break_is_not_a_second_button(self):
        self.assertEqual(len(self._buttons(self._listing(self.LABEL))), 1)


if __name__ == "__main__":
    unittest.main()
