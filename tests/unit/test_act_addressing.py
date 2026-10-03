"""The ``act`` addressing contract: text must be unique -- or ``--index`` pins one.

``design-project.md`` section 18.3 fixes three addressing tiers and one rule:
hitting zero or more than one control must **fail closed**; the only escape hatch
for "several matches" is an explicit ordinal (``--index``), which is documented as
stable **within one session only** -- hence it is never applied automatically.

The tool runner is replaced by a mock, so **no window is ever touched**; the
listing below is the shape ``tools/win-click-button.ps1 -ListOnly`` really prints.
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

# Three Buttons, no two with the same text; ``o`` matches Abort and Ignore (two
# hits, so only ``--index`` can pin one), ``zzz`` matches none, ``&Abort`` is unique.
_LISTING = (
    'dialog hwnd=0x1\n'
    '-- child windows --\n'
    '  hwnd=0x2 class=Button vis=True text="&Abort" rect=0,0,10,10\n'
    '  hwnd=0x3 class=Button vis=True text="&Retry" rect=0,20,10,30\n'
    '  hwnd=0x4 class=Button vis=True text="&Ignore" rect=0,40,10,50\n'
    '  hwnd=0x5 class=Edit vis=True text="" rect=0,60,10,70\n'
)


class ActClickButtonAddressingTest(unittest.TestCase):
    """``ctl act click-button``: what reaches the tool, and what is refused."""

    RUN = "gs32-20261004-1200"

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="eclipse-ctl-act-")
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
        run = os.path.join(self.root, self.RUN)
        os.makedirs(run, exist_ok=True)
        with open(os.path.join(run, "endpoint.json"), "w", encoding="utf-8") as fh:
            json.dump({"port": 50999, "pid": 4242}, fh)

    def _args(self, **kw):
        base = dict(config=self.config, target=None, run_id=self.RUN, port=None,
                    json=False, yes=True, act_action="click-button", title="T",
                    text="&Abort", index=None, path=None, key=None, class_="Edit")
        base.update(kw)
        return argparse.Namespace(**base)

    def _call(self, args, listing=_LISTING):
        buf = io.StringIO()
        with mock.patch.object(cli.shutil, "which", return_value="pwsh"), \
                mock.patch.object(cli, "_run", return_value=(0, listing)) as run, \
                contextlib.redirect_stdout(buf):
            rc = cli._cmd_act(args)
        return rc, [call.args[0] for call in run.call_args_list]

    def _refuses(self, args, exc_type):
        with mock.patch.object(cli.shutil, "which", return_value="pwsh"), \
                mock.patch.object(cli, "_run", return_value=(0, _LISTING)) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(exc_type) as caught:
                cli._cmd_act(args)
        # A refusal must happen *before* anything is pressed: the only call allowed
        # is the side-effect-free enumeration.
        for call in run.call_args_list:
            self.assertIn("-ListOnly", call.args[0])
        return str(caught.exception)

    def test_a_unique_text_reaches_the_tool_without_an_index(self):
        rc, argvs = self._call(self._args(text="&Abort"))
        self.assertEqual(rc, 0)
        self.assertIn("-Text", argvs[-1])
        self.assertNotIn("-Index", argvs[-1])

    def test_zero_matches_is_not_found_and_presses_nothing(self):
        message = self._refuses(self._args(text="zzz"), cli.NotFoundError)
        self.assertIn("no Button containing", message)
        self.assertIn("retry:", message)

    def test_several_matches_without_an_index_is_a_usage_error(self):
        message = self._refuses(self._args(text="o"), cli.UsageError)
        self.assertIn("ambiguous: 2 Buttons", message)
        self.assertIn("--index", message)

    def test_index_picks_the_nth_match_of_the_same_text_filter(self):
        rc, argvs = self._call(self._args(text="o", index=1))
        self.assertEqual(rc, 0)
        # Same filter on both sides, so the tool re-derives the same two hits and
        # takes the second one -- Ignore, not Abort.
        self.assertEqual(argvs[-1][argvs[-1].index("-Text") + 1], "o")
        self.assertEqual(argvs[-1][argvs[-1].index("-Index") + 1], "1")

    def test_index_alone_counts_every_visible_button(self):
        rc, argvs = self._call(self._args(text=None, index=2))
        self.assertEqual(rc, 0)
        self.assertNotIn("-Text", argvs[-1])
        self.assertEqual(argvs[-1][argvs[-1].index("-Index") + 1], "2")

    def test_index_out_of_range_fails_closed(self):
        message = self._refuses(self._args(text="o", index=2), cli.UsageError)
        self.assertIn("out of range", message)

    def test_negative_index_fails_closed(self):
        self._refuses(self._args(text="o", index=-1), cli.UsageError)

    def test_neither_text_nor_index_is_a_usage_error(self):
        message = self._refuses(self._args(text=None, index=None), cli.UsageError)
        self.assertIn("--text", message)
        self.assertIn("--index", message)

    def test_path_is_ruled_out_rather_than_improvised(self):
        message = self._refuses(self._args(path="0/1"), cli.UsageError)
        self.assertIn("--path is not supported", message)
        self.assertIn("N11", message)

    def test_the_tools_own_markup_is_not_a_label(self):
        # "rect" and "Button" appear on every line; treating the raw line as the
        # label would invent hits (and an ordinal the tool cannot reproduce).
        message = self._refuses(self._args(text="rect"), cli.NotFoundError)
        self.assertIn("no Button containing", message)

    def test_an_invisible_button_is_not_addressable(self):
        # The tool only clicks `IsWindowVisible` children, so an invisible Button
        # must not make a unique label look ambiguous here.
        listing = _LISTING + '  hwnd=0x6 class=Button vis=False text="&Abort 2" rect=0,80,1,1\n'
        rc, argvs = self._call(self._args(text="Abort"), listing=listing)
        self.assertEqual(rc, 0)
        self.assertEqual(argvs[-1][argvs[-1].index("-Text") + 1], "Abort")


if __name__ == "__main__":
    unittest.main()
