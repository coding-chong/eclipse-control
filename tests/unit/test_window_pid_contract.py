"""The window-addressing *pid contract* (`A4-1a` / `A4-1b`).

Two defects, one rule: a dialog is addressed **inside a process**, and when that
process is unknown the addressing must fail rather than widen.

* ``A4-1a`` -- ``screen.close`` / ``buttons`` / ``click_button`` passed
  ``-ProcId`` only when the caller handed over *exactly one* pid; a set (the
  runner widens the recorded pid by command line when the launcher hands the
  workbench to a child JVM) silently dropped the constraint, so a same-titled
  window of **any** process became fair game -- a silent wrong-target close or
  button press.
* ``A4-1b`` -- ``ctl act click-button`` / ``send-keys`` / ``set-text`` never
  passed a pid at all, while the run door's ``run.py::_click_button`` always
  did.

The helpers here are pure argv builders plus one in-process call with the tool
runner replaced by a mock: **no window is ever touched**.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from ctl import __main__ as cli
from ctl import screen

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


class ActPidResolutionTest(unittest.TestCase):
    """``ctl act *`` addresses the run recorded in ``endpoint.json`` (`A4-1b`)."""

    RUN = "gs32-20261004-1010"

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="eclipse-ctl-pid-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.config = os.path.join(self.root, "config.json")
        with open(self.config, "w", encoding="utf-8") as fh:
            json.dump({"run_root": self.root, "default_target": "gs32"}, fh)
        # The environment layer sits above the file layer; a machine with
        # ECLIPSE_CTL_RUN_ROOT set must not redirect this test at its real runs.
        removed = {}
        for key in ("ECLIPSE_CTL_RUN_ROOT", "ECLIPSE_CTL_DEFAULT_TARGET"):
            if key in os.environ:
                removed[key] = os.environ.pop(key)
        self.addCleanup(os.environ.update, removed)

    def _endpoint(self, pid):
        run = os.path.join(self.root, self.RUN)
        os.makedirs(run, exist_ok=True)
        with open(os.path.join(run, "endpoint.json"), "w", encoding="utf-8") as fh:
            json.dump({"port": 50999, "pid": pid}, fh)

    def _args(self, **kw):
        base = dict(config=self.config, target=None, run_id=self.RUN, port=None,
                    json=False, yes=True, act_action="click-button", title="T",
                    text="OK", index=None, path=None, key=None, class_="Edit")
        base.update(kw)
        return argparse.Namespace(**base)

    def _call(self, args):
        buf = io.StringIO()
        with mock.patch.object(cli.shutil, "which", return_value="pwsh"), \
                mock.patch.object(cli, "_run", return_value=(0, _LISTING)) as run, \
                contextlib.redirect_stdout(buf):
            rc = cli._cmd_act(args)
        return rc, [call.args[0] for call in run.call_args_list]

    def test_act_reaches_the_tool_with_the_recorded_pid(self):
        self._endpoint(4242)
        cases = (self._args(),
                 self._args(act_action="send-keys", text=None, key="RETURN"),
                 self._args(act_action="set-text", text="hello", key=None))
        for args in cases:
            with self.subTest(action=args.act_action):
                rc, argvs = self._call(args)
                self.assertEqual(rc, 0)
                self.assertTrue(argvs)
                for argv in argvs:
                    self.assertEqual(_proc_id(argv), "4242")

    def test_act_fails_closed_when_the_run_records_no_pid(self):
        self._endpoint(None)
        with mock.patch.object(cli, "_run") as run:
            with self.assertRaises(cli.PrereqNotReady) as caught:
                cli._cmd_act(self._args())
        self.assertIn("records no pid", str(caught.exception))
        self.assertIn("retry:", str(caught.exception))
        run.assert_not_called()

    def test_usage_errors_win_over_the_missing_pid(self):
        # A missing --key is the caller's mistake and must be reported as such,
        # not masked by "this run records no pid" (no pid is resolvable here).
        with mock.patch.object(cli, "_run") as run:
            with self.assertRaises(cli.UsageError):
                cli._cmd_act(self._args(act_action="send-keys", text=None, key=None,
                                        run_id=None))
        run.assert_not_called()

    def test_act_fails_closed_when_the_run_does_not_exist(self):
        with mock.patch.object(cli, "_run") as run:
            with self.assertRaises(cli.PrereqNotReady):
                cli._cmd_act(self._args(run_id="gs32-nope"))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
