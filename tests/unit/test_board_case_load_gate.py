"""The board case's load gate: what makes its verdict red (AC3(c)/(d)) and green.

The hardware half of ``board.led_chase`` is verified by running it against the
board; these are the *judgement* contracts that must not rot, because both of
them are wording the acceptance criteria name explicitly:

* **AC3(c)** -- with the ``Resume`` step removed the case must FAIL and name the
  not-running state ("never released from its entry point ... NOT RUNNING"), not
  crash and not pass;
* **AC3(d)** -- with the ``device/device.h`` clock patch removed the case must
  FAIL naming the clock source (an XTAL build halts in ``SysCtl_selectXTAL()``
  on this board: Y1/R61/R51 are not fitted);
* the load gate itself -- the debug perspective **and** a non-empty Debug-view
  ``Tree``, both read-only -- must be what decides whether a ``Resume`` answer
  means anything, so a closed gate is a FAIL that names the stage.

Two more kinds of contract live here, both about the **producers** rather than
about the wording (a judgement-layer test cannot show that a production step still
exists -- measured 2026-10-07: with ``_pre``/``_generated``/``_action`` replaced by
a bomb the whole module still ran green, `implement.md` §5.6):

* ``PreGuardTest`` / ``GeneratedMuxTest`` drive ``_pre`` and ``_generated``, so
  deleting a guard there turns them red (R-3/R-4/R-5, AC3(a)/AC3(b)/AC4);
* ``ResumeDialogTest`` drives ``_load`` for R-1 -- an ``OK`` that also carries the
  bridge's ``dialog=`` line is never read as "the target is running" -- and
  ``PerspectiveIsNotACriterionTest`` pins that a ``parts_after`` read from outside
  the observation window cannot move the verdict (R-2).

Shapes are fed in as raw bridge replies (``ctl.client.Response``); no IDE, no
window, no board, no network.  ``_expect`` takes the case context only for
signature symmetry -- these assertions never reach it (it is passed ``None``).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from ctl.client import Response
from ctl.verify.cases import board_led_chase as case

_NAME = "board_led_chase"
_MARKER = "CTL-BOARD-deadbeef"
_LAUNCH = "C:/ws/%s/.launches/ctl_board_chase.launch" % _NAME

#: Verbatim answer shapes (the payload lines are the bridge's own).
_RESUME_RAN = "\n".join([
    "OK",
    "ICommandService via IWorkbench.getService -> true",
    "IHandlerService -> true",
    "before: defined=true handled=true",
    "executeCommand returned: org.eclipse.core.runtime.Status Status OK: unknown code=0 OK",
    "OK executed org.eclipse.debug.ui.commands.Resume",
    "END"])
_DISABLED = "\n".join([
    "ERR disabled command is disabled: org.eclipse.core.commands.NotEnabledException: "
    "Trying to execute the disabled command org.eclipse.debug.ui.commands.Resume",
    "ICommandService via IWorkbench.getService -> true",
    "IHandlerService -> true",
    "before: defined=true handled=true",
    "END"])
_LAUNCH_RAN = _RESUME_RAN.replace("debug.ui.commands.Resume",
                                  "launchbar.ui.command.launchActive")
_PARTS_DEBUG = ("OK\nperspective id=com.ti.ccstudio.TIDebugPerspective label=\"CCS Debug\"\n"
                "views=6\neditors=1\nEND")


def _result():
    return {
        "errors": [],
        "plan": {"killed": []},
        "name": _NAME,
        "marker": _MARKER,
        "started_at": 1000.0,
        "seed": {"ok": True, "ccxml_exists": True, "clock_patch": {},
                 "device": "TMS320C28XX.TMS320F280025C"},
        "clock": {"path": "ws/%s/device/device.h" % _NAME, "source": "INTOSC"},
        "build": {"logs": {"CPU1_RAM": {"rc": 0, "timed_out": False, "errors": "0",
                                        "total": "1"}},
                  "errors_line": "0 out of 1 projects have errors"},
        "board_c": {"path": "board.c", "mux": list(case._MUX_LINES), "missing": []},
        "artifact": {"path": "ws/%s/CPU1_RAM/%s.out" % (_NAME, _NAME), "size": 65972,
                     "elf": {"class": 1, "endian": 1, "machine": case._MACHINE},
                     "marker_offset": 6776, "marker_encoding": "u16le",
                     "mtime": 2000.0},
        "cdt_configs": ["CPU1_RAM"],
        "registered_after": [_NAME],
        "launch_files": [_LAUNCH],
        "load": {
            "launch_file": _LAUNCH,
            "launch_before": "sha/size=1/mtime=1",
            "launch_after": "sha/size=1/mtime=1",
            "parts_before": Response("OK\nperspective id=com.ti.ccstudio.TICPerspective "
                                     "label=\"CCS Edit\"\nEND"),
            "parts_after": Response(_PARTS_DEBUG),
            "resume_before": Response(_DISABLED),
            "launch": Response(_LAUNCH_RAN),
            "wait": {"rounds": [{"round": 1}, {"round": 2}]},
            "gate": {"open": True, "opened_at_round": 2, "debug_items": 2,
                     "perspective": "com.ti.ccstudio.TIDebugPerspective"},
            "resume_attempts": [Response(_RESUME_RAN), Response(_DISABLED)],
            "resume": Response(_RESUME_RAN),
            "resume_probe": Response(_DISABLED),
            "running": True,
        },
    }


class ClockSourceReadbackTest(unittest.TestCase):
    """`_clock_source` judges the active define, and nothing else."""

    def test_template_activates_xtal(self):
        text = ("// To use INTOSC, comment the #define USE_PLL_SRC_XTAL\n"
                "#define USE_PLL_SRC_XTAL\n//#define USE_PLL_SRC_INTOSC\n")
        self.assertEqual(case._clock_source(text), "XTAL")

    def test_patched_activates_intosc(self):
        text = "//#define USE_PLL_SRC_XTAL\n#define USE_PLL_SRC_INTOSC\n"
        self.assertEqual(case._clock_source(text), "INTOSC")

    def test_both_or_neither_is_not_a_source(self):
        self.assertIsNone(case._clock_source(""))
        self.assertIsNone(case._clock_source("#define USE_PLL_SRC_XTAL\n"
                                             "#define USE_PLL_SRC_INTOSC\n"))


class DebugViewItemsTest(unittest.TestCase):
    """The count is attributed to the Debug view, not to whichever tree comes first."""

    #: Trimmed from a real `ui.tree 16 --shell all` dump: the navigator's tree
    #: precedes the Debug view's, and the Registers view's follows it.
    DUMP = ("OK\n"
            "root text=\"limbo\"\n"
            "      CTabItem text=\"Project Explorer\" tip=\"Workspace\"\n"
            "                Tree\n"
            "                  [TreeItems=7]\n"
            "          CTabItem text=\"Debug\" tip=\"\"\n"
            "                    Tree\n"
            "                      [TreeItems=2]\n"
            "          CTabItem text=\"Registers\" tip=\"\"\n"
            "                    Tree\n"
            "                      [TreeItems=0]\n"
            "END")

    def test_counts_only_the_debug_view(self):
        self.assertEqual(case._debug_view_items(self.DUMP), 2)

    def test_absent_debug_view_is_none(self):
        dump = self.DUMP.replace('CTabItem text="Debug" tip=""', 'CTabItem text="Other" tip=""')
        self.assertIsNone(case._debug_view_items(dump))

    def test_gate_needs_both_halves(self):
        debug = "com.ti.ccstudio.TIDebugPerspective"
        edit = "com.ti.ccstudio.TICPerspective"
        self.assertTrue(case._gate_open(debug, 1))
        # The perspective alone is not enough, and the item count alone is not
        # either.  Measured 2026-10-07 (run `board-1007-final`): *one* item is what
        # the Debug view holds while the launch is still going over JTAG, so this
        # pair proves "a launch exists", never "the launch finished" -- see
        # `_gate_open`'s docstring.  No threshold above 1 is pinned here: what a
        # *finished* launch holds was never measured.
        self.assertFalse(case._gate_open(edit, 2))
        self.assertFalse(case._gate_open(debug, 0))
        self.assertFalse(case._gate_open(debug, None))


class ProbeReportTest(unittest.TestCase):
    """R8's SKIP is keyed on the XDS100 row, not on "the table has a row" (AC4).

    `xds100serial.exe` lists **every** FTDI device it can see, so a board whose
    probe is absent can still produce rows -- measured on this machine 2026-10-07,
    where a plain USB/serial converter enumerates **first** and the XDS100v2 second.
    """

    #: Verbatim from `xds100serial.exe` on this machine, 2026-10-07 (two devices).
    REAL = ("Scanning for XDS100 emulators...\n"
            "\n"
            "VID/PID    Type            Serial #    Description\n"
            "0403/6010  generic FT2232  GJBDRPSS    USB <-> Serial Converter \n"
            "0403/a6d0  XDS100v1/v2     USB100V2    Texas Instruments Inc.XDS100 Ver 2.0 \n")

    def _report(self, text):
        done = mock.Mock(returncode=0, stdout=text.encode("utf-8"), stderr=b"")
        with mock.patch.object(case.subprocess, "run", return_value=done), \
                mock.patch.object(case, "_probe_tool", return_value=__file__):
            return case._probe_report("")

    def test_only_the_xds100_row_can_stand_in_for_the_probe(self):
        out = self._report(self.REAL)
        self.assertEqual(len(out["rows"]), 2)
        self.assertEqual(len(out["probe_rows"]), 1)
        self.assertIn("XDS100", out["probe_rows"][0])
        self.assertNotIn("FT2232", out["probe_rows"][0])

    def test_a_foreign_ftdi_device_is_not_a_probe(self):
        # The tool enumerates a foreign FTDI device but no XDS100 row => `probe_rows`
        # is empty.  That reading has TWO causes (probe gone / probe held by a live
        # debug session), so it is *not* proof the board is unplugged -- the split is
        # `_pre`'s job (`_probe_present`); this test only pins the row filter.
        generic_only = self.REAL.replace(
            "0403/a6d0  XDS100v1/v2     USB100V2    "
            "Texas Instruments Inc.XDS100 Ver 2.0 \n", "")
        out = self._report(generic_only)
        self.assertEqual(len(out["rows"]), 1)
        self.assertEqual(out["probe_rows"], [])

    def test_no_rows_at_all(self):
        out = self._report("Scanning for XDS100 emulators...\n")
        self.assertEqual(out["rows"], [])
        self.assertEqual(out["probe_rows"], [])


class LoadVerdictTest(unittest.TestCase):
    """The four shapes the load gate must produce, by their own wording."""

    def _verdict(self, mutate):
        result = _result()
        mutate(result)
        return case._expect(None, result)

    def test_green(self):
        passed, detail = self._verdict(lambda result: None)
        self.assertTrue(passed, detail)
        self.assertIn("running=True", detail)
        self.assertIn("clock=INTOSC", detail)

    def test_resume_step_removed_fails_naming_not_running(self):
        def drop(result):
            load = result["load"]
            del load["resume"]
            del load["resume_probe"]
            load["resume_attempts"] = []
            load["running"] = False
        passed, detail = self._verdict(drop)
        self.assertFalse(passed)
        self.assertIn("NOT RUNNING", detail)
        self.assertIn("never ran", detail)

    def test_clock_patch_removed_fails_naming_the_clock_source(self):
        passed, detail = self._verdict(lambda result: result["clock"].update(source="XTAL"))
        self.assertFalse(passed)
        self.assertIn("clock source", detail)
        self.assertIn("XTAL", detail)

    def test_device_family_mutation_fails_naming_the_device(self):
        """`_expect` passes a producer error through to the verdict.

        The producer itself (`_pre`) is driven by
        `PreGuardTest.test_a_foreign_silicon_projectspec_is_recorded_verbatim`; this
        one only pins that the judgement layer opens with ``result["errors"]`` --
        *not* by poking the summary field `seed["device"]`, which `_expect` only
        prints (`_detail`) and never judges (measured 2026-10-07: that path stays
        GREEN).  The string fed below is `_pre`'s own message, verbatim.
        """
        # C10: the guarded device is pinned by this test's own literal, not by the
        # case's constant -- drop one from the case and this must go red.
        self.assertEqual(case._EXPECTED_DEVICE, "TMS320F280025C")
        self.assertEqual(case._spec_device('<project device="TMS320F2800137" />'),
                         "TMS320F2800137")

        def wrong_family(result):
            result["errors"].append(
                "device read-back: the located projectspec declares device=%r, expected "
                "%r (family %r) -- wrong silicon; the verdict is FAIL (the error is "
                "recorded and the build still runs, so the failure is reported rather "
                "than the run being stopped)"
                % ("TMS320F2800137", "TMS320F280025C", "f28002x"))
        passed, detail = self._verdict(wrong_family)
        self.assertFalse(passed)
        self.assertIn("device read-back", detail)
        self.assertIn("TMS320F2800137", detail)

    def test_zero_byte_syscfg_fails_naming_the_missing_mux_lines(self):
        """AC3(b): the stub `c2000.syscfg` left at 0 B generates no mux at all.

        Those three lines are the whole difference between "the pin mux came from
        the config" and "somebody wrote them by hand" (R4), so their absence has
        to be named line by line.
        """
        # C10 again: pinned by this test's own literal; push a fourth line into
        # `_MUX_LINES` and the equality below goes red.
        _MUX = ("GPIO_setPinConfig(GPIO_34_GPIO34)",
                "GPIO_setPinConfig(GPIO_6_GPIO6)",
                "GPIO_setPinConfig(GPIO_7_GPIO7)")
        self.assertEqual(tuple(case._MUX_LINES), _MUX)

        def no_mux(result):
            result["board_c"]["mux"] = []
            result["board_c"]["missing"] = list(_MUX)
        passed, detail = self._verdict(no_mux)
        self.assertFalse(passed)
        self.assertIn("the pin mux is NOT in", detail)
        for line in _MUX:
            self.assertIn(line, detail)

    def test_closed_gate_fails_naming_the_stage(self):
        def close(result):
            load = result["load"]
            load["gate"] = {"open": False, "opened_at_round": None, "debug_items": None,
                            "perspective": "com.ti.ccstudio.TICPerspective"}
            # Three rounds is *fixture shape*, not the case's round cap (that is
            # `_LOAD_WAIT_ROUNDS`): the verdict only prints this count, so quoting
            # the cap number here would be a stale snapshot the moment the cap moves
            # (measurement-hygiene §13.8 反例 B).
            load["wait"] = {"rounds": [{"round": i} for i in range(1, 4)]}
            del load["resume"]
            load["resume_attempts"] = []
            load["running"] = False
        passed, detail = self._verdict(close)
        self.assertFalse(passed)
        self.assertIn("no debug context", detail)

    def test_resume_ok_without_a_following_disabled_fails(self):
        def still_halted(result):
            load = result["load"]
            load["running"] = False
            load["resume_probe"] = Response(_RESUME_RAN)
        passed, detail = self._verdict(still_halted)
        self.assertFalse(passed)
        self.assertIn("STILL HALTED", detail)

    def test_lost_connection_is_reported_and_keeps_the_other_problems(self):
        def lose(result):
            result["clock"]["source"] = "XTAL"
            result["load"]["transport_error"] = (
                "sys.wait jobs-idle -> ConnectionResetError(10054, 'reset')")
        passed, detail = self._verdict(lose)
        self.assertFalse(passed)
        self.assertIn("bridge connection to the IDE was lost", detail)
        # the problems collected before the load stay in the verdict
        self.assertIn("clock source", detail)

    def test_every_launch_issue_is_shape_checked(self):
        def bad_second(result):
            result["load"]["launch_attempts"] = [Response(_LAUNCH_RAN),
                                                 Response("OK\nEND")]
        passed, detail = self._verdict(bad_second)
        self.assertFalse(passed)
        self.assertIn("issue 2", detail)

    def test_reissued_launch_that_worked_is_green(self):
        # a first issue with zero effect looks exactly like a good one (OK + the
        # executed line), so the verdict must not depend on which issue it was
        def two_issues(result):
            result["load"]["launch_attempts"] = [Response(_LAUNCH_RAN),
                                                 Response(_LAUNCH_RAN)]
        passed, detail = self._verdict(two_issues)
        self.assertTrue(passed, detail)


class LaunchbarWaitTest(unittest.TestCase):
    """What the launch waits for is a line the **IDE** wrote (H2/`_wait_launchbar`).

    `_seed` now writes that same preference file (the version line and one
    ``activeLaunchMode=debug`` per seeded descriptor), so the old sync --
    ``configDescList`` naming our descriptor -- stopped being proof of anything the
    IDE did: this case had written a name, and would then wait for it.  The sync is
    the LaunchBar's own ``<descriptor>/activeLaunchTarget`` line (never written here),
    plus the mode of the descriptor it names, because `run` mode accepts
    `launchActive` and creates no session at all (measured; see `_seed`).
    """

    #: The test's own literal for "our" descriptor (C10): a mutated `_LAUNCH_NAME`
    #: must make these fixtures stop being ours, and the tests go red.
    NAME = "ctl_board_chase"

    class _Ctx:
        def __init__(self):
            self.notes = []

        def note(self, line):
            self.notes.append(line)

    def _workspace(self, text):
        root = tempfile.mkdtemp(prefix="eclipse-ctl-launchbar-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        settings = os.path.join(root, ".metadata", ".plugins",
                                "org.eclipse.core.runtime", ".settings")
        os.makedirs(settings, exist_ok=True)
        if text is not None:
            with open(os.path.join(settings, "org.eclipse.launchbar.core.prefs"),
                      "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        return root

    def _wait(self, root):
        with mock.patch.object(case, "_LAUNCHBAR_WAIT_S", 0.0):
            return case._wait_launchbar(self._Ctx(), {"workspace": root})

    def test_the_ides_own_target_line_for_our_descriptor_in_debug_is_the_sync(self):
        root = self._workspace(_launchbar_prefs(self.NAME, "debug", bound=True))
        out = self._wait(root)
        self.assertTrue(out["found"])
        self.assertEqual(out["active"], self.NAME)
        # the descriptor the IDE made live is *recorded*, not assumed
        self.assertEqual(out["debug_bound"], [self.NAME])
        self.assertEqual(out["targets"][self.NAME],
                         "org.eclipse.launchbar.core.launchTargetType.local\\:Local")
        self.assertIn(self.NAME, out["desc_line"])

    def test_the_file_this_case_writes_is_not_a_sync_by_itself(self):
        """The self-written, self-waited loop: seeded state, no IDE write.

        `_seed` writes the mode lines of this file (see `SeedLaunchbarPrefsTest`); the
        list here is the shape that would appear if the case ever wrote one too, and
        it names **our** descriptor.  Neither may count as the sync: nothing in this
        file is something the IDE did, so the wait must stay ``found=False``.  Anything
        else would make the precondition mean "this case wrote its own file".
        """
        root = self._workspace(
            "eclipse.preferences.version=1\n"
            "configDescList=org.eclipse.launchbar.core.descriptorType.default\\:%s\n"
            "org.eclipse.launchbar.core.descriptorType.default\\:%s"
            "/activeLaunchMode=debug\n" % (self.NAME, self.NAME))
        out = self._wait(root)
        self.assertFalse(out["found"])
        self.assertEqual(out["names"], [self.NAME])
        self.assertEqual(out["modes"], {self.NAME: "debug"})
        self.assertEqual(out["targets"], {})

    def test_run_mode_is_not_a_sync_even_when_the_ide_bound_it(self):
        """The measured zero-effect mode, at the wait layer: `run` ⇒ no session.

        The binding is there (the IDE activated the descriptor) but its mode is `run`,
        and in `run` `LaunchActiveCommandHandler` calls `DebugUITools.launch(...)` with
        `run` -- the command is accepted and no debug session exists.  So this file is
        not the sync: `found` stays False and the note names the modes it read.
        """
        root = self._workspace(_launchbar_prefs(self.NAME, "run", bound=True))
        ctx = self._Ctx()
        with mock.patch.object(case, "_LAUNCHBAR_WAIT_S", 0.0):
            out = case._wait_launchbar(ctx, {"workspace": root})
        self.assertFalse(out["found"])
        self.assertEqual(out["bound"], [self.NAME])       # bound ...
        self.assertEqual(out["debug_bound"], [])                  # ... but not debug
        self.assertIsNone(out["active"])
        self.assertTrue(any("found=False" in line for line in ctx.notes))

    def test_an_empty_descriptor_list_is_not_a_sync(self):
        root = self._workspace("configDescList=\n")
        ctx = self._Ctx()
        with mock.patch.object(case, "_LAUNCHBAR_WAIT_S", 0.0):
            out = case._wait_launchbar(ctx, {"workspace": root})
        self.assertFalse(out["found"])
        self.assertEqual(out["desc_line"], "configDescList=")
        self.assertTrue(any("found=False" in line for line in ctx.notes))

    def test_another_configuration_is_not_a_sync(self):
        root = self._workspace(_launchbar_prefs("not_ours", "debug", bound=True))
        out = self._wait(root)
        self.assertFalse(out["found"])
        self.assertEqual(out["bound"], [])


# --------------------------------------------------------------------------- #
# Shapes for the tests that drive the **producers** (R-3/R-4/R-5/R-1/R-2/O-3)
# --------------------------------------------------------------------------- #

_PARTS_EDIT = ('OK\nperspective id=com.ti.ccstudio.TICPerspective label="CCS Edit"\n'
               "views=6\neditors=1\nEND")

#: Verbatim from `xds100serial.exe` on this machine, 2026-10-07 (see
#: `ProbeReportTest.REAL`): the row that is *not* the probe, and the probe's own.
_GENERIC_FTDI_ROW = ("0403/6010  generic FT2232  GJBDRPSS    USB <-> Serial Converter")
_XDS100_ROW = ("0403/a6d0  XDS100v1/v2     USB100V2    "
               "Texas Instruments Inc.XDS100 Ver 2.0")


class _PreCtx:
    """The smallest stand-in `_pre` touches: no IDE, no bridge, no board."""

    class _Target:
        name = "ccs12"
        install_dir = ""
        port = 0

    class _Runner:
        port = 0

    class _Paths:
        def __init__(self, workspace):
            self.workspace = workspace
            self.configuration = os.path.join(workspace, ".metadata")
            # No `endpoint.json` in the fixture workspace: `_stop_instance` really is
            # called (that is the order `_pre` now has to have) but returns before it
            # would spawn `python -m ctl uninstall`, so nothing on the machine moves.
            self.endpoint = os.path.join(workspace, "endpoint.json")
            self.run_id = "unit"

    def __init__(self, workspace):
        self.paths = self._Paths(workspace)
        self.target = self._Target()
        self.runner = self._Runner()
        self.run_id = "unit"
        self.notes = []
        self.board_plan = None

    def note(self, line):
        self.notes.append(line)


class _BridgeStub:
    """A context whose `request` answers from a table (drives `_load`)."""

    def __init__(self, answers):
        """``answers``: request-prefix -> list of raw frames; the last one repeats."""
        self._answers = answers
        self._seen = {prefix: 0 for prefix in answers}
        self.requests = []
        self.notes = []
        self.board_plan = None

    def request(self, request):
        self.requests.append(request)
        for prefix, frames in self._answers.items():
            if request.startswith(prefix):
                index = min(self._seen[prefix], len(frames) - 1)
                self._seen[prefix] += 1
                return Response(frames[index])
        raise AssertionError("no canned answer for %r" % request)

    def note(self, line):
        self.notes.append(line)


def _workspace_with_launchbar(name, mode="debug", bound=True):
    """A temp workspace whose LaunchBar state the IDE has already **made live**.

    The shape is the one three real workspaces on this machine carry (see
    `case._LAUNCHBAR_PREFS`): the version line, the IDE's own `configDescList`, and
    one `<descriptor node path>/activeLaunchMode=<mode>` per descriptor -- plus the
    `<descriptor node path>/activeLaunchTarget=…` line the LaunchBar writes when it
    *activates* a descriptor.  That last line is the sync `_wait_launchbar` waits
    for; `configDescList` alone is not enough any more, and this fixture carries both
    so the load starts from the state the real IDE leaves behind.  ``mode``/``bound``
    let a test build the *other* measured state (`run`, which creates no session).
    """
    root = tempfile.mkdtemp(prefix="eclipse-ctl-launchbar-")
    settings = os.path.join(root, ".metadata", ".plugins",
                            "org.eclipse.core.runtime", ".settings")
    os.makedirs(settings, exist_ok=True)
    with open(os.path.join(settings, "org.eclipse.launchbar.core.prefs"),
              "w", encoding="utf-8", newline="") as handle:
        handle.write(_launchbar_prefs(name, mode, bound=bound))
    return root


def _launchbar_prefs(name, mode, bound=False):
    """The LaunchBar preference file as the real workspaces spell it.

    ``configDescList=<descriptor node path>`` (the colon escaped), the descriptor's
    ``activeLaunchMode``, and -- when the LaunchBar has activated it -- its
    ``activeLaunchTarget`` line.
    """
    node = "org.eclipse.launchbar.core.descriptorType.default\\:%s" % name
    lines = ["eclipse.preferences.version=1",
             "configDescList=%s" % node,
             "%s/activeLaunchMode=%s" % (node, mode)]
    if bound:
        lines.append("%s/activeLaunchTarget=org.eclipse.launchbar.core."
                     "launchTargetType.local\\:Local" % node)
    return "\n".join(lines) + "\n"


class PreGuardTest(unittest.TestCase):
    """`_pre`'s own guards, **driven** (R-3/R-5).

    The judgement layer already had tests; those only showed that `_expect` passes
    its input through.  These drive the production step, so deleting a guard in
    `_pre` turns them red (measured 2026-10-07: a run with `_pre`/`_generated`/
    `_action` replaced by a bomb reported `Ran 22 tests … OK` -- nothing touched
    them; see `implement.md` §5.6).
    """

    #: The mutation `implement.md` §3.1 uses: the same projectspec shape, but the
    #: f280013x family's device.  Verbatim from
    #: `.../driverlib/f280013x/examples/empty_projects/CCS/empty_driverlib_project.projectspec`
    #: (identified by `_spec_device`, which only needs `<project … device="…">`).
    WRONG_DEVICE = "TMS320F2800137"

    def _spec_root(self, device):
        root = tempfile.mkdtemp(prefix="eclipse-ctl-c2000ware-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = os.path.join(root, *case._SPEC_REL.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write('<projectSpec>\n  <project name="empty_driverlib_project" '
                         'device="%s" />\n</projectSpec>\n' % device)
        return root

    @contextlib.contextmanager
    def _pre_environment(self, device, rows, probe_rows, presence=None, probe=None,
                         c2000ware=None):
        workspace = tempfile.mkdtemp(prefix="eclipse-ctl-pre-ws-")
        self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)
        root = self._spec_root(device)
        ctx = _PreCtx(workspace)
        probe = probe or {"rows": list(rows), "probe_rows": list(probe_rows),
                          "tool": "xds100serial.exe", "rc": 0, "error": ""}
        # The OS presence channel is *always* stubbed: a unit test must not run
        # `Get-PnpDevice` against the machine it happens to be on (that is how the
        # defect this fixture now pins got read backwards).  Default = absent, which
        # is the AC4/R8 shape the existing tests exercise.
        if presence is None:
            presence = {"present": False, "source": "pnp", "ids": [], "error": ""}
        # The C2000Ware root is injected by **stubbing the resolver**, not by setting
        # `ECLIPSE_CTL_BOARD_C2000WARE`: the env var goes through the production
        # derivation, so every `_pre` test would silently depend on that code, and a
        # single mutation there would redden this whole file -- `deliverable-shape.md`
        # C12 (a mutation may only redden the tests guarding its own entry point).
        # Stub the channel, exactly as the OS/tool channels above are stubbed.
        candidates = [root] if c2000ware is None else c2000ware
        with mock.patch.object(case, "_c2000ware_candidates", return_value=candidates), \
                mock.patch.object(case, "_probe_report", return_value=probe), \
                mock.patch.object(case, "_probe_present", return_value=presence), \
                mock.patch.object(case, "list_processes", return_value=[]), \
                mock.patch.object(case, "list_port_listeners", return_value=[]):
            yield ctx

    def test_a_foreign_silicon_projectspec_is_recorded_verbatim(self):
        """AC3(a) at the producer: `_pre` reads the spec and records the mismatch.

        The message is asserted **verbatim**, so removing the read-back block from
        `_pre` (or dropping `device` from it) is what this test goes red on -- not
        the case's own constants.
        """
        with self._pre_environment(self.WRONG_DEVICE, [_XDS100_ROW],
                                   [_XDS100_ROW]) as ctx:
            case._pre(ctx)
        self.assertEqual(ctx.board_plan["spec_device"], "TMS320F2800137")
        self.assertEqual(ctx.board_plan["errors"], [
            "device read-back: the located projectspec declares device="
            "'TMS320F2800137', expected 'TMS320F280025C' (family 'f28002x') -- wrong "
            "silicon; the verdict is FAIL (the error is recorded and the build still "
            "runs, so the failure is reported rather than the run being stopped)"])
        self.assertTrue(any("spec_device=TMS320F2800137" in line
                            for line in ctx.notes), ctx.notes)

    def test_only_a_foreign_ftdi_row_skips_before_anything_is_driven(self):
        """AC4 at the producer: no XDS100 row => `_pre` raises Skip (R-5).

        (`implement.md` §5.2's sketch said "a nonexistent C2000Ware root"; that
        would hit the *root* guard first -- the probe guard is only reached with a
        real root and the spec in place, which is what this builds.)
        """
        with self._pre_environment("TMS320F280025C", [_GENERIC_FTDI_ROW], []) as ctx:
            with self.assertRaises(case.Skip) as caught:
                case._pre(ctx)
            # the SKIP fired before the plan was published: nothing is half-set-up
            self.assertIsNone(ctx.board_plan)
        self.assertIn("no XDS100 probe", caught.exception.reason)
        self.assertIn(_GENERIC_FTDI_ROW, caught.exception.reason)

    #: The hardware id of the board's probe, verbatim from `Get-PnpDevice -PresentOnly`
    #: on this machine while it was invisible to `xds100serial.exe` (a live debug
    #: session held it).  Written here as this test's own literal (C10): mutate the
    #: case's needle and the fixtures below stop matching, so the test goes red.
    HWID = "USB\\VID_0403&PID_A6D0&MI_00\\8&1A7F3620&0&0000"
    HWID_NEEDLE = "VID_0403&PID_A6D0"

    def test_a_blind_tool_never_reads_as_an_absent_board(self):
        """The defect this change closes: `rows == 1` has TWO causes.

        Same tool reading (one generic FTDI row), only the OS presence value differs,
        and the verdict must follow it: attached => "held", never "gone".
        """
        held = {"present": True, "source": "pnp", "ids": [self.HWID], "error": ""}
        with self._pre_environment("TMS320F280025C", [_GENERIC_FTDI_ROW], [],
                                   presence=held) as ctx:
            with self.assertRaises(case.Skip) as caught:
                case._pre(ctx)
            self.assertTrue(any("presence source=pnp present=True" in line
                                for line in ctx.notes), ctx.notes)
            # the reading is emitted before the verdict, so a SKIP still carries the
            # evidence that produced it (the note used to sit past the gate)
            self.assertTrue(any(line.startswith("pre: probe xds100serial.exe")
                                for line in ctx.notes), ctx.notes)
        reason = caught.exception.reason
        self.assertIn(self.HWID, reason)              # the OS reading is quoted ...
        self.assertIn("holding the probe", reason)    # ... and named as the cause
        self.assertNotIn("no XDS100 probe", reason)   # never the absence wording ...
        self.assertNotIn("attach that probe", reason)  # ... and never that instruction
        # The flip: the same tool rows with the *other* presence value must NOT
        # produce this verdict.  What the absent probe's own wording is stays pinned
        # by `test_only_a_foreign_ftdi_row_skips_before_anything_is_driven` (one
        # branch, one pinning test -- so the R-5 mutation keeps reddening exactly
        # that one); here the contract is that the two causes are not conflated.
        with self._pre_environment("TMS320F280025C", [_GENERIC_FTDI_ROW], []) as ctx:
            with self.assertRaises(case.Skip) as caught:
                case._pre(ctx)
        absent_reason = caught.exception.reason
        self.assertNotIn("holding the probe", absent_reason)
        self.assertNotIn(self.HWID, absent_reason)

    def test_a_tool_that_never_ran_is_not_read_as_a_held_handle(self):
        """`rc is None` means the binary never ran: name that, never the handle.

        `_probe_report` leaves `rc` None when the tool is missing or the spawn fails.
        C14 contract 2 (`deliverable-shape.md`): the verdict must name the channel that
        actually said it -- a live-session story here would send the operator off to
        stop a CCS instance that holds nothing.
        """
        never_ran = {"tool": "xds100serial.exe", "rc": None, "rows": [],
                     "probe_rows": [],
                     "error": "probe tool not found: <tmp>/xds100serial.exe"}
        attached = {"present": True, "source": "override", "ids": [], "error": ""}
        with self._pre_environment("TMS320F280025C", [], [], presence=attached,
                                   probe=never_ran) as ctx:
            with self.assertRaises(case.Skip) as caught:
                case._pre(ctx)
        reason = caught.exception.reason
        self.assertIn("could not run", reason)
        self.assertIn("probe tool not found", reason)  # the observed cause, verbatim
        self.assertNotIn("holding the probe", reason)  # never the unsupported story
        self.assertNotIn("no XDS100 probe", reason)    # and never the absence tier

    def test_the_override_speaks_for_itself_in_the_absent_tier(self):
        """C14 contract 2: the override never queried the OS -- do not credit it.

        The absent tier is the only one allowed to say "no probe", and the sentence
        must name the channel that actually answered.  Crediting the override with a
        PnP finding reads as if the device table had been consulted.
        """
        absent = {"present": False, "source": "override", "ids": [], "error": ""}
        with self._pre_environment("TMS320F280025C", [_GENERIC_FTDI_ROW], [],
                                   presence=absent) as ctx:
            with self.assertRaises(case.Skip) as caught:
                case._pre(ctx)
        reason = caught.exception.reason
        self.assertIn("no XDS100 probe", reason)                # the absence tier
        self.assertIn("override says the board is absent", reason)
        self.assertNotIn("reports no present device", reason)   # not a PnP finding

    def test_the_c2000ware_override_wins_outright(self):
        """`ECLIPSE_CTL_BOARD_C2000WARE` short-circuits the whole derivation."""
        with mock.patch.dict(os.environ, {case._BOARD_ENV + "C2000WARE": "X:/patched"}):
            self.assertEqual(case._c2000ware_candidates("D:/anywhere/ccs/eclipse"),
                             ["X:/patched"])

    def test_the_c2000ware_root_is_derived_from_the_install_tree(self):
        """No literal default: the root comes from the target's own tree.

        Layout asserted here is the one measured 2026-10-07: `<ti>/ccs<ver>/ccs/eclipse`
        with C2000Ware beside it as `<ti>/c2000/C2000Ware_<ver>`.  The fixture builds
        its own `<ti>` (never this machine's), so the test cannot pass by accident on
        a machine that happens to have the reference layout.
        """
        ti = tempfile.mkdtemp(prefix="eclipse-ctl-ti-")
        self.addCleanup(shutil.rmtree, ti, ignore_errors=True)
        install_dir = os.path.join(ti, "ccs1281", "ccs", "eclipse")
        os.makedirs(install_dir)
        ware = os.path.join(ti, "c2000", "C2000Ware_9_99_00_00")
        os.makedirs(os.path.join(ware, *case._SPEC_REL.split("/")[:-1]))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(case._BOARD_ENV + "C2000WARE", None)
            got = case._c2000ware_candidates(install_dir)
        self.assertEqual([os.path.normpath(ware)], [os.path.normpath(g) for g in got])

    def test_several_coexisting_releases_are_collected_name_descending(self):
        """Measured 2026-10-07: **three** releases sit in ``<ti>/c2000`` and **all
        three** carry the family's ``_SPEC_REL``, so that check selects nothing here
        -- the collection order is what decides which root ``_pre`` ends up using.

        That makes the order a **rule**, not an accident, so it is pinned here
        (C10: the expected list is *this* file's own literal, never the module's).
        Flipping the sort must redden exactly this test.
        """
        ti = tempfile.mkdtemp(prefix="eclipse-ctl-ti-")
        self.addCleanup(shutil.rmtree, ti, ignore_errors=True)
        install_dir = os.path.join(ti, "ccs1281", "ccs", "eclipse")
        os.makedirs(install_dir)
        for name in ("C2000Ware_5_04_00_00", "C2000Ware_26_00_00_00",
                     "C2000Ware_26_01_00_00"):
            os.makedirs(os.path.join(ti, "c2000", name, *case._SPEC_REL.split("/")[:-1]))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(case._BOARD_ENV + "C2000WARE", None)
            got = [os.path.basename(os.path.normpath(path))
                   for path in case._c2000ware_candidates(install_dir)]
        self.assertEqual(got, ["C2000Ware_5_04_00_00", "C2000Ware_26_01_00_00",
                               "C2000Ware_26_00_00_00"])

    def test_without_an_install_tree_it_finds_nothing(self):
        """Empty input must stay empty -- never a fallback to a path nobody verified."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(case._BOARD_ENV + "C2000WARE", None)
            self.assertEqual(case._c2000ware_candidates(""), [])
            self.assertEqual(case._c2000ware_candidates("Z:/not/a/ti/root"), [])

    def test_no_c2000ware_anywhere_skips_and_names_the_knob(self):
        """The fail-closed message must carry the knob to turn, and no fake path."""
        with self._pre_environment("TMS320F280025C", [], [], c2000ware=[]) as ctx:
            with self.assertRaises(case.Skip) as caught:
                case._pre(ctx)
        reason = caught.exception.reason
        self.assertIn("ECLIPSE_CTL_BOARD_C2000WARE", reason)  # the knob, as a literal (C10)
        self.assertIn("[]", reason)                           # it looked, and found none
        self.assertIn(case._FAMILY, reason)                   # what it was looking for
        self.assertNotIn("C2000Ware_5_04_00_00", reason)      # no machine path in the message
        self.assertNotIn("D:/ti", reason)

    def test_an_unanswerable_presence_query_skips_without_claiming_absence(self):
        """A failed OS query is `None`: say "cannot tell", never "not there"."""
        blind = {"present": None, "source": "pnp", "ids": [],
                 "error": "PnP query rc=1: Get-PnpDevice : not recognized"}
        with self._pre_environment("TMS320F280025C", [_GENERIC_FTDI_ROW], [],
                                   presence=blind) as ctx:
            with self.assertRaises(case.Skip) as caught:
                case._pre(ctx)
        reason = caught.exception.reason
        self.assertIn("cannot determine", reason)
        self.assertIn("not recognized", reason)        # the query's own error, verbatim
        self.assertNotIn("no XDS100 probe", reason)
        self.assertIn(_GENERIC_FTDI_ROW, reason)

    def test_the_runs_own_instance_is_stopped_before_the_probe_is_read(self):
        """Order, recorded: freeing this run's instance is what unblinds the tool.

        An instance left by a green invocation keeps its debug session, and that
        session holds the probe's handle -- so a run that read the tool first would
        SKIP its own re-run (AC1's one-command repeat).
        """
        order = []
        probe = {"rows": [_XDS100_ROW], "probe_rows": [_XDS100_ROW],
                 "tool": "xds100serial.exe", "rc": 0, "error": ""}
        real_stop = case._stop_instance

        def record_stop(ctx, plan):
            order.append("stop")
            return real_stop(ctx, plan)

        def record_probe(install_dir):
            order.append("probe")
            return probe

        with self._pre_environment("TMS320F280025C", [_XDS100_ROW], [_XDS100_ROW]) as ctx:
            with mock.patch.object(case, "_stop_instance", record_stop), \
                    mock.patch.object(case, "_probe_report", record_probe):
                out = case._pre(ctx)
        self.assertEqual(order, ["stop", "probe"])
        self.assertIn("stop", ctx.board_plan)          # published with the plan
        self.assertTrue(any("pre: stop" in line for line in ctx.notes), ctx.notes)
        self.assertIn("xds100_rows=1", out)


class ProbePresenceTest(unittest.TestCase):
    """`_probe_present()`: the OS channel, its parse, and the override seam.

    No Win32 call runs here -- the enumeration is stubbed or the override short
    circuits it -- so the suite is machine-independent (a test that read the *host's*
    PnP state would have passed for the wrong reason on the machine where the probe
    happened to be plugged in, which is precisely how the old rule survived).
    """

    #: This test's own literals (C10), not `case._XDS100_HWID`.
    HWID_NEEDLE = "VID_0403&PID_A6D0"
    HWID = "USB\\VID_0403&PID_A6D0&MI_00\\8&1A7F3620&0&0000"
    #: The board's *other* node and a foreign FTDI device: same text stream, no match.
    BOARD_NODE = "USB\\VID_0403&PID_A6D0\\USB100V2"
    FOREIGN = "USB\\VID_0403&PID_6010\\5&2C1B4E3F&0&1"

    def test_the_pnp_answer_is_parsed_one_id_per_line(self):
        text = ("%s\r\n\r\n%s\r\n%s\r\nGet-PnpDevice : a warning on the same stream\r\n"
                % (self.HWID, self.BOARD_NODE, self.FOREIGN))
        self.assertEqual(case._pnp_ids_from_text(text),
                         [self.HWID, self.BOARD_NODE])
        self.assertEqual(case._pnp_ids_from_text(""), [])
        self.assertEqual(case._pnp_ids_from_text(self.FOREIGN + "\r\n"), [])

    def test_a_named_device_is_present(self):
        with mock.patch.object(case, "_pnp_xds100_ids",
                               return_value=([self.HWID], "")):
            out = case._probe_present()
        self.assertIs(out["present"], True)
        self.assertEqual(out["ids"], [self.HWID])
        self.assertEqual(out["error"], "")

    def test_no_named_device_is_absent_and_not_an_error(self):
        with mock.patch.object(case, "_pnp_xds100_ids", return_value=([], "")):
            out = case._probe_present()
        self.assertIs(out["present"], False)
        self.assertEqual(out["error"], "")

    def test_a_failed_query_is_none_and_carries_the_reason(self):
        with mock.patch.object(case, "_pnp_xds100_ids",
                               return_value=([], "PnP query rc=1: not recognized")):
            out = case._probe_present()
        self.assertIsNone(out["present"])
        self.assertIn("not recognized", out["error"])

    def test_the_pnp_query_asks_for_the_boards_own_hardware_id(self):
        # the needle the OS is asked about is this test's literal, not the case's
        self.assertIn(self.HWID_NEEDLE, case._PNP_QUERY)
        # `-PresentOnly` is load-bearing, not wording: without it the query also
        # lists *known-but-absent* devices, so this second channel would answer
        # "present" for a probe that is not there -- exactly the C14 failure
        # (`deliverable-shape.md`).  Pinned deliberately; do not drop as cosmetic.
        self.assertIn("Get-PnpDevice -PresentOnly", case._PNP_QUERY)

    def test_the_override_forces_the_value(self):
        with mock.patch.dict(os.environ, {case._BOARD_ENV + "PRESENCE": "absent"}):
            self.assertIs(case._probe_present()["present"], False)
        with mock.patch.dict(os.environ, {case._BOARD_ENV + "PRESENCE": "present"}):
            self.assertIs(case._probe_present()["present"], True)
        with mock.patch.dict(os.environ, {case._BOARD_ENV + "PRESENCE": "maybe"}):
            out = case._probe_present()
        self.assertIsNone(out["present"])
        self.assertIn("maybe", out["error"])

    def test_a_noisy_stream_is_not_read_as_an_absent_board(self):
        """rc=0 with text but no matching id is *unparsable*, not "none".

        The answer "no such device" is an **empty** stream (measured on this machine
        2026-10-07: the query with a needle that matches nothing writes 0 bytes,
        rc=0) -- so a stream carrying a swallowed warning/error must fail closed
        (`present=None`), never be spelled the same way as "absent".
        """
        noisy = {"killed": None, "rc": 0, "timed_out": False,
                 "text": "Get-PnpDevice : Access is denied.\r\n", "elapsed": 0.0}
        with mock.patch.object(case, "_run_capture", return_value=noisy), \
                mock.patch.object(case.shutil, "which", return_value="pwsh"):
            ids, error = case._pnp_xds100_ids()
        self.assertEqual(ids, [])
        self.assertIn("named no", error)
        self.assertIn("Access is denied", error)
        # the contrast that makes the guard meaningful: a *blank* stream is "none".
        blank = dict(noisy, text="")
        with mock.patch.object(case, "_run_capture", return_value=blank), \
                mock.patch.object(case.shutil, "which", return_value="pwsh"):
            self.assertEqual(case._pnp_xds100_ids(), ([], ""))


class GeneratedMuxTest(unittest.TestCase):
    """`_generated` computes what board.c is missing -- driven (R-4)."""

    class _Ctx:
        def __init__(self):
            self.notes = []

        def note(self, line):
            self.notes.append(line)

    #: C10: pinned by this test's own literals, never by `case._MUX_LINES`.
    _MUX = ("GPIO_setPinConfig(GPIO_34_GPIO34)",
            "GPIO_setPinConfig(GPIO_6_GPIO6)",
            "GPIO_setPinConfig(GPIO_7_GPIO7)")

    def _project(self, board_c):
        proj = tempfile.mkdtemp(prefix="eclipse-ctl-generated-")
        self.addCleanup(shutil.rmtree, proj, ignore_errors=True)
        syscfg = os.path.join(proj, "device", "syscfg")
        os.makedirs(syscfg, exist_ok=True)
        with open(os.path.join(syscfg, "board.c"), "w", encoding="utf-8",
                  newline="") as handle:
            handle.write(board_c)
        return proj

    def test_missing_lines_are_computed_from_board_c(self):
        # One of the three present: the *computed* answer is the other two, so
        # deleting `out["missing"] = …` in `_generated` leaves the initial
        # all-three value and this goes red (a 0-mux file would not tell them apart).
        out = case._generated(self._Ctx(),
                              self._project("void f(void) { %s }\n" % self._MUX[0]),
                              _NAME)
        self.assertEqual([line for line, _ in out["mux"]], [self._MUX[0]])
        self.assertEqual(out["missing"], list(self._MUX[1:]))

        # AC3(b): the stub `c2000.syscfg` left at 0 B generates no mux at all.
        out = case._generated(self._Ctx(), self._project(""), _NAME)
        self.assertEqual(out["mux"], [])
        self.assertEqual(out["missing"], list(self._MUX))

        # …and the judgement layer turns that into the named FAIL (R4).
        result = _result()
        result["board_c"] = {"path": os.path.join("device", "syscfg", "board.c"),
                             "mux": [], "missing": out["missing"]}
        passed, detail = case._expect(None, result)
        self.assertFalse(passed)
        self.assertIn("the pin mux is NOT in", detail)
        for line in self._MUX:
            self.assertIn(line, detail)

    def test_a_board_c_that_never_generated_is_missing_all_three(self):
        out = case._generated(self._Ctx(),
                              tempfile.mkdtemp(prefix="eclipse-ctl-empty-"), _NAME)
        self.assertEqual(out["path"], "")
        self.assertEqual(out["missing"], list(self._MUX))


class ResumeDialogTest(unittest.TestCase):
    """R-1: an OK that also carries a `dialog=` line is not proof the target runs.

    Driven through `_load` (the step that sets `running`), because the judgement
    layer alone cannot show that a dialog-carrying answer is refused.
    """

    #: Verbatim from the run that exposed R-1 (`runs/board-1007-chk`):
    #: `bridge.log` has
    #: ``06:04:36.036 … REQ "cmd.run org.eclipse.debug.ui.commands.Resume" -> OK (520 ms, 7 lines)``
    #: -- 7 **payload** lines -- and `shadow/manifest.jsonl` seq 5 carries
    #: ``"dialog": "dialog=appeared \"Error\""`` for that very request, whose frame
    #: is `shadow/0005-060436-Error.png` (title "Error"; the body reads
    #: `Run Control not available`).  The five handler lines are the bridge's own
    #: (`LiveBridge.java:1093/1278/1282/1239/1285`) and the `dialog_note=` line is
    #: `LiveBridge.java:567-569` verbatim.
    RESUME_BLOCKED = "\n".join([
        "OK",
        "ICommandService via IWorkbench.getService -> true",
        "IHandlerService -> true",
        "before: defined=true handled=true",
        "executeCommand returned: org.eclipse.core.runtime.Status Status OK: "
        "unknown code=0 OK",
        "OK executed org.eclipse.debug.ui.commands.Resume",
        'dialog=appeared "Error"',
        "dialog_note=the command may have FAILED, or the dialog may be the expected"
        " behaviour; close it and read back (ui.parts) before treating this call as done",
        "END"])

    #: The debug context the gate opens on: `ui.tree` with the Debug view's tree.
    DEBUG_TREE = ('OK\nroot text="limbo"\n'
                  '          CTabItem text="Debug" tip=""\n'
                  "                    Tree\n"
                  "                      [TreeItems=2]\n"
                  "END")

    def _load(self, workspace, resume_frames=None):
        """Drive `_load` with a chosen `Resume` answer sequence.

        ``resume_frames`` defaults to the R-1 live sequence; the tail frame repeats
        once the table is exhausted (``_BridgeStub``).  The clock is faked: the
        resume stage is now bounded by a **wall clock**, and with instant answers a
        real clock would either spin for real minutes or (with `sleep` stubbed to 0)
        never reach the bound at all.
        """
        if resume_frames is None:
            resume_frames = [_DISABLED, self.RESUME_BLOCKED]
        ctx = _BridgeStub({
            "ui.parts": [_PARTS_EDIT, _PARTS_DEBUG],
            "sys.wait": ["OK\nidle=true\npending=0\nEND"],
            "ui.tree": [self.DEBUG_TREE],
            "cmd.run " + case._CMD_RESUME: resume_frames,
            "cmd.run " + case._CMD_LAUNCH_ACTIVE: [_LAUNCH_RAN],
        })
        launch = os.path.join(workspace, case._LAUNCH_NAME + ".launch")
        with open(launch, "w", encoding="utf-8", newline="") as handle:
            handle.write("<launchConfiguration/>\n")
        with _fake_clock():
            return case._load(ctx, {"workspace": workspace}, launch)

    def test_a_dialog_on_the_resume_answer_is_never_running(self):
        workspace = _workspace_with_launchbar(case._LAUNCH_NAME)
        self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)
        load = self._load(workspace)

        self.assertTrue(load["gate"]["open"])
        self.assertIsNone(load["resume"])
        self.assertIsNotNone(load["resume_blocked"])
        self.assertFalse(load["running"])
        # The loop polled past the blocked answer instead of stopping at it -- and kept
        # going for the slice's wall clock, not for a fixed number of attempts.
        self.assertGreater(len(load["resume_attempts"]), 1)
        self.assertGreater(load["resume_slices"][0]["attempts"], 1)

        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertFalse(passed)
        self.assertIn("dialog", detail)
        self.assertIn("running=False", detail)

    def test_a_dialog_after_a_clean_resume_still_refuses_to_certify_running(self):
        """§6.1: the fail-closed must bind the *conclusion*, not the attempt.

        The live finding (R-1) had the dialog on the **first** ``Resume`` (that is
        the tier above).  This is the residual one: a **clean** ``Resume`` that ran,
        **then** an ``OK`` carrying ``dialog=``, **then** a bare ``ERR disabled``.
        Before the fix that sequence set ``running=True`` -- the dialog only skipped
        the *dialog* attempt, it never revoked the earlier clean one -- while the
        on-screen modal still stood between the command and the target.  Now the
        confirming branch also requires ``resume_blocked is None``, so the modal
        keeps the loop open and the verdict is FAIL naming the dialog.

        The second drive is the other half of the contract: with no dialog anywhere
        the loop must still certify ``running=True`` and PASS -- the fix must not
        fail-close the green path.
        """
        workspace = _workspace_with_launchbar(case._LAUNCH_NAME)
        self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)

        # A: clean ran -> dialog-carrying OK -> ERR disabled  => NOT certified running
        load = self._load(workspace, [_DISABLED, _RESUME_RAN, self.RESUME_BLOCKED,
                                      _DISABLED])
        self.assertTrue(load["gate"]["open"])
        self.assertIsNotNone(load["resume"], "a clean Resume did run first")
        self.assertIsNotNone(load["resume_blocked"], "then the dialog appeared")
        self.assertFalse(load["running"])
        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertFalse(passed, detail)
        self.assertIn("dialog", detail)
        self.assertIn("running=False", detail)

        # B: clean OK -> ERR disabled, no dialog anywhere  => still PASS
        clean = self._load(workspace, [_DISABLED, _RESUME_RAN, _DISABLED])
        self.assertTrue(clean["gate"]["open"])
        self.assertIsNone(clean["resume_blocked"])
        self.assertTrue(clean["running"])
        result = _result()
        result["load"] = clean
        passed, detail = case._expect(None, result)
        self.assertTrue(passed, detail)


class PerspectiveIsNotACriterionTest(unittest.TestCase):
    """R-2: the launch is judged on the reading taken **inside** the window.

    `_expect` used to re-derive a verdict from `parts_after`, a fresh `ui.parts`
    taken after the resume loop -- by which time a modal has already dropped the
    perspective back to CCS Edit (measured on `runs/board-1007-chk`: the gate
    opened on the `06:04:35.507` read, the `06:04:38.790` read is `TICPerspective`).
    The gate judges the perspective once, on the reading it opened on.
    """

    def _verdict(self, gate_open, parts_after_raw):
        result = _result()
        load = result["load"]
        if gate_open:
            load["wait"] = {"rounds": [{"round": 1}],
                            "perspective": "com.ti.ccstudio.TIDebugPerspective"}
            load["gate"] = {"open": True, "opened_at_round": 1, "debug_items": 2,
                            "perspective": "com.ti.ccstudio.TIDebugPerspective"}
        else:
            load["wait"] = {"rounds": [{"round": 1}],
                            "perspective": "com.ti.ccstudio.TICPerspective"}
            load["gate"] = {"open": False, "opened_at_round": None,
                            "debug_items": None,
                            "perspective": "com.ti.ccstudio.TICPerspective"}
            del load["resume"]
            load["resume_attempts"] = []
            load["running"] = False
        load["parts_after"] = Response(parts_after_raw)
        return case._expect(None, result)

    def test_a_collapsed_parts_after_cannot_turn_a_green_load_red(self):
        passed, detail = self._verdict(True, _PARTS_EDIT)
        self.assertTrue(passed, detail)

    def test_a_debug_parts_after_cannot_rescue_a_closed_gate(self):
        passed, detail = self._verdict(False, _PARTS_DEBUG)
        self.assertFalse(passed)
        self.assertIn("no debug context", detail)


class LoadPacingTest(unittest.TestCase):
    """O-3: the slice is ended by its own wall clock, never by the round cap.

    `sys.wait jobs-idle` answers in ~0 ms when nothing is running, so without the
    floor under one round the round cap ends the slice in about a second -- measured
    2026-10-07 (`_LOAD_ROUND_MIN_S`): 43 `ui.parts` inside one second, four
    `launchActive` issues 152/23/8 s apart.  With the floor, the live run's slices
    reported `the 150s wait budget is spent after 10 round(s)` / `after 91 round(s)`.
    """

    class _InstantCtx:
        """Every request answers instantly and the gate never opens."""

        def __init__(self):
            self.notes = []
            self.requests = []

        def request(self, request):
            self.requests.append(request)
            if request.startswith("sys.wait"):
                return Response("OK\nidle=false\npending=0\nEND")
            return Response("OK\nperspective id=com.ti.ccstudio.TICPerspective "
                            'label="CCS Edit"\nviews=6\neditors=1\nEND')

        def note(self, line):
            self.notes.append(line)

    def test_the_round_cap_cannot_end_a_slice_before_its_wall_clock(self):
        self.assertGreaterEqual(case._LOAD_WAIT_ROUNDS * case._LOAD_ROUND_MIN_S,
                                case._LOAD_WAIT_SLICE_S)

    def test_the_slice_is_ended_by_the_deadline_not_by_the_round_cap(self):
        budget = 1.6
        ctx = self._InstantCtx()
        started = time.monotonic()
        out = case._wait_for_debug_context(ctx, {}, budget)
        elapsed = time.monotonic() - started

        self.assertFalse(out["open"])
        self.assertLess(len(out["rounds"]), case._LOAD_WAIT_ROUNDS)
        self.assertGreaterEqual(len(out["rounds"]) * case._LOAD_ROUND_MIN_S, budget)
        self.assertGreaterEqual(elapsed, budget)
        self.assertTrue(any("wait budget is spent" in line for line in ctx.notes))


# --------------------------------------------------------------------------- #
# The resume stage's window + the session's liveness (2026-10-07, `board-1007-ac1`)
# --------------------------------------------------------------------------- #

_IDLE = "OK\nmode=jobs-idle\nwaited_ms=1 budget_ms=15000\nidle=true\npending=0\n" \
        "jobs_total=10 running=0 waiting=0 sleeping=10 none=0\nEND"

#: A Debug view with two items, i.e. the gate's second half satisfied.
_TREE_LIVE = ('OK\nroot text="limbo"\n'
              '          CTabItem text="Debug" tip=""\n'
              "                    Tree\n"
              "                      [TreeItems=2]\n"
              "END")


class _FakeClock:
    """Stand-in for the `time` module inside `board_led_chase`.

    A clock that moves **only** when `sleep` is called.  Both waits under test are
    wall clocks, and every request in these tests answers instantly: with the real
    module a round would take zero time, so the one thing under test -- the deadline
    ending the slice -- could only be reached by sleeping for real minutes.  The
    stamping helpers are delegated to the real module; they produce evidence text,
    never a timing input.
    """

    def __init__(self, start=1_700_000_000.0):
        self.now = start
        self.slept = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += max(0.0, float(seconds))

    def time(self):
        return self.now

    def localtime(self, seconds=None):
        return time.localtime(self.now if seconds is None else seconds)

    def strftime(self, fmt, t=None):
        return time.strftime(fmt, t if t is not None else self.localtime())


@contextlib.contextmanager
def _fake_clock(**constants):
    """Run `board_led_chase` on a `_FakeClock`, with `constants` overridden."""
    clock = _FakeClock()
    with mock.patch.object(case, "time", clock):
        with mock.patch.multiple(case, **constants) if constants else contextlib.nullcontext():
            yield clock


class _LoadStub(_BridgeStub):
    """`_BridgeStub` + a temp workspace whose LaunchBar record already names us."""

    def __init__(self, answers, mode="debug", bound=True):
        super().__init__(answers)
        self.workspace = _workspace_with_launchbar(case._LAUNCH_NAME, mode=mode,
                                                   bound=bound)
        self.launch = os.path.join(self.workspace, case._LAUNCH_NAME + ".launch")
        with open(self.launch, "w", encoding="utf-8", newline="") as handle:
            handle.write("<launchConfiguration/>\n")

    def cleanup(self):
        shutil.rmtree(self.workspace, ignore_errors=True)

    def run(self):
        return case._load(self, {"workspace": self.workspace}, self.launch)


def _live_answers(resume_frames, launch_frames=None):
    """The answers a *live* session needs: gate open at once, session staying open.

    The `Resume` table gets `_DISABLED` prepended: `_load` sends that command once
    *before* the launch as the negative control, and it must answer the disabled
    shape (the answer the control is there for), not one of the loop's frames.
    """
    return {
        "ui.parts": [_PARTS_DEBUG],
        "ui.tree": [_TREE_LIVE],
        "sys.wait": [_IDLE],
        "cmd.run " + case._CMD_RESUME: [_DISABLED] + list(resume_frames),
        "cmd.run " + case._CMD_LAUNCH_ACTIVE: list(launch_frames or [_LAUNCH_RAN]),
    }


class ResumeWindowTest(unittest.TestCase):
    """The F8 window is the slice's wall clock -- not the count it used to be.

    Measured 2026-10-07 (`board-1007-ac1`, `bridge.log`): 12 `Resume` requests from
    `06:43:49.846` to `06:44:18.316` -- **29 s**, every one `ERR disabled` -- and then
    GIVING UP, while the archived run that lit the LEDs had the launch and the
    successful `Resume` about 12 minutes apart (`run-ram-launch.md` §4.1).
    """

    def test_the_resume_window_is_the_slices_wall_clock_not_a_fixed_count(self):
        budget = 100.0
        ctx = _LoadStub(_live_answers([_DISABLED]))
        self.addCleanup(ctx.cleanup)
        with _fake_clock(_LOAD_WAIT_SLICE_S=budget):
            load = ctx.run()

        self.assertTrue(load["gate"]["open"])
        self.assertFalse(load["running"])
        first = load["resume_slices"][0]
        self.assertEqual(first["budget_s"], budget)
        # the slice held for its whole wall clock ...
        self.assertGreaterEqual(first["elapsed_s"], budget)
        # ... and the polling went on far past the 12 attempts the fixed window allowed
        self.assertGreater(first["attempts"], 12)
        self.assertGreaterEqual(
            first["attempts"] * (case._LIVENESS_STEP_S + case._LOAD_POLL_S), budget)

    def test_the_giveup_note_records_the_seconds_the_attempts_and_the_last_answer(self):
        ctx = _LoadStub(_live_answers([_DISABLED]))
        self.addCleanup(ctx.cleanup)
        with _fake_clock(_LOAD_WAIT_SLICE_S=20.0, _LOAD_RESUME_REISSUE=1):
            load = ctx.run()

        note = next(line for line in ctx.notes if "GIVING UP after" in line)
        self.assertRegex(
            note,
            r"GIVING UP after \d+ org\.eclipse\.debug\.ui\.commands\.Resume "
            r"attempt\(s\) in \d+ slice\(s\) over \d+s")
        self.assertIn("with 1 %s re-issue(s)" % case._CMD_LAUNCH_ACTIVE, note)
        self.assertIn("The last answer, verbatim:", note)
        self.assertIn(_DISABLED.splitlines()[0], note)
        # The R7 ambiguity statement stays, and it is named as the *only* reading
        # available when no abort was seen -- "could not certify it is running", never
        # "it is not running".
        self.assertIn("cannot separate", note)
        self.assertIn("No abort was observed", note)
        self.assertFalse(load["session_aborted"])


class SessionLivenessTest(unittest.TestCase):
    """A session that comes up and dies is named -- and is not resumed into.

    The AC1 frame at 06:41:11 shows the Debug view's `ctl board chase [Code Composer
    Studio - Device Debugging]` root node while the status bar still reads
    `Launching ctl_board_chase: (34%)`; the perspective then fell back to
    `TICPerspective` and 12 `Resume` answers came back `ERR disabled` because nothing
    was suspended.  The gate alone cannot tell that state from a running target.
    """

    def test_a_dead_session_is_named_aborted_and_the_launch_is_reissued(self):
        ctx = _LoadStub({
            # `ui.parts` is also asked once before the launch (the negative control),
            # so the frames line up as: [parts_before, gate round 1, liveness round 1,
            # (repeat) liveness round 2] -- the gate opens on the first read that
            # follows the control, and the very next read is CCS Edit.
            "ui.parts": [_PARTS_EDIT, _PARTS_DEBUG, _PARTS_EDIT],
            "ui.tree": [_TREE_LIVE],
            "sys.wait": [_IDLE],
            "cmd.run " + case._CMD_RESUME: [_DISABLED, _RESUME_RAN, _DISABLED],
            "cmd.run " + case._CMD_LAUNCH_ACTIVE: [_LAUNCH_RAN],
        })
        self.addCleanup(ctx.cleanup)
        with _fake_clock(_LOAD_WAIT_SLICE_S=20.0):
            load = ctx.run()

        self.assertTrue(load["gate"]["open"])
        self.assertTrue(load["session_aborted"])
        self.assertIsNone(load["resume"])
        self.assertFalse(load["running"])
        # every read-only check saw the session gone, and each one was the full pair
        self.assertTrue(load["liveness"])
        self.assertTrue(all(check["aborted"] for check in load["liveness"]))
        self.assertEqual(len(load["liveness"][0]["rounds"]), case._LIVENESS_ROUNDS)
        # never resorted to resuming a session that is not there
        self.assertEqual(load["resume_attempts"], [])
        # one re-issue per aborted slice, on top of the launch stage's own issue
        self.assertEqual(len(load["launch_attempts"]), 1 + case._LOAD_RESUME_REISSUE)
        self.assertEqual(len(load["launch_issues"]), 1 + case._LOAD_RESUME_REISSUE)
        self.assertTrue(all(row["aborted"] for row in load["launch_issues"]))

        diff = load["abort_evidence"]["diff"]
        self.assertIn(case._DEBUG_PERSPECTIVE, diff)
        self.assertIn("TICPerspective", diff)
        self.assertIn("[TreeItems=2] -> [TreeItems=no]", diff)
        self.assertIn(diff, next(line for line in ctx.notes if "ABORTED" in line))

        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertFalse(passed)
        self.assertIn("never ran", detail)
        self.assertIn("ABORTING", detail)

    def test_the_gate_must_still_be_open_on_the_second_read(self):
        """C10: the death is not "the reading said edit" -- it is the *pair* failing.

        The two round counts below are the test's **own literals** (C10): asserting
        `len(rounds) == case._LIVENESS_ROUNDS` would let a weakened
        `_LIVENESS_ROUNDS` satisfy its own test.  The claim here is independent of the
        constant: a pair that agrees at once reads exactly two rounds.
        """
        ctx = _BridgeStub({"ui.parts": [_PARTS_DEBUG], "ui.tree": [_TREE_LIVE]})
        with _fake_clock():
            alive, live = case._session_alive(ctx, {}, {"at": "t", "perspective":
                                                        case._DEBUG_PERSPECTIVE,
                                                        "debug_items": 1})
        self.assertTrue(alive)
        self.assertFalse(live["aborted"])
        self.assertEqual(len(live["rounds"]), 2)

        ctx = _BridgeStub({"ui.parts": [_PARTS_EDIT], "ui.tree": [_TREE_LIVE]})
        with _fake_clock():
            alive, live = case._session_alive(ctx, {}, {"at": "t", "perspective":
                                                        case._DEBUG_PERSPECTIVE,
                                                        "debug_items": 1})
        self.assertFalse(alive)
        self.assertTrue(live["aborted"])
        self.assertEqual(len(live["rounds"]), 2)


class ReleasedSessionTest(unittest.TestCase):
    """R7's floor: a clean `Resume` survives the session going away.

    Measured 2026-10-07 (`runs/board-1007-ac2/bridge.log` + that run's own notes): the
    clean `Resume` at 07:09:33.618 (`OK`, 7-line frame) released the target; 1.8 s
    later a *single* `ui.parts` read showed the edit perspective, and 2 s after that
    the debug perspective was back.  The case read that single frame as an ABORT,
    dropped the release, re-issued `launchActive` at 07:09:38.686 (which loads and
    HALTS at the entry point) and then reported `running=False` with
    `<no confirming call>` -- a green release destroyed by two different forbidden
    criteria (the session state, and a re-issue that killed the running program).

    These drive `_load` (the step that sets `running`), per C10/C12.
    """

    #: The pair's "before" reading (the `before` record `_session_alive` diffs against).
    GATE = {"at": "t", "perspective": case._DEBUG_PERSPECTIVE, "debug_items": 2}

    def test_a_clean_release_survives_the_session_going_away(self):
        """Clean ran -> the session is gone -> `running` on the release, verbatim.

        Behaviour (i) of the contract: the confirming `Resume` is best-effort, and
        when the session is gone (there is nothing left to ask) the stage certifies on
        the release it has -- the *floor*, never a guess.
        """
        parts = [_PARTS_EDIT, _PARTS_DEBUG, _PARTS_DEBUG,
                 _PARTS_DEBUG, _PARTS_EDIT, _PARTS_EDIT]
        answers = _live_answers([_RESUME_RAN])
        answers["ui.parts"] = parts
        ctx = _LoadStub(answers)
        self.addCleanup(ctx.cleanup)
        with _fake_clock():
            load = ctx.run()

        self.assertTrue(load["gate"]["open"])
        self.assertIsNotNone(load["resume"], "a clean Resume ran and released the target")
        self.assertIsNone(load["resume_probe"],
                          "there was no session left to ask for the confirmation")
        self.assertTrue(load["running"])
        self.assertFalse(load["session_aborted"],
                         "a session that ends after a release is not an ABORT of it")
        self.assertEqual(len(load["launch_attempts"]), 1,
                         "never re-issue launchActive -- it halts the released target")
        self.assertIsNotNone(load["resume_unconfirmed"])
        self.assertIn("GONE", load["resume_unconfirmed"]["why"])
        self.assertIsNone(load["resume_blocked"])

        note = next(line for line in ctx.notes if "is UNAVAILABLE" in line)
        self.assertIn(case._CMD_RESUME, note)
        # the release, verbatim: R7's shape (result word + line count) and the frame
        self.assertIn("%s: %r" % (case._shape(load["resume"]), load["resume"].raw), note)
        self.assertIn(case._OK_MARK + case._CMD_RESUME, note)
        # ... and the two liveness readings, so this outcome cannot be confused with
        # "the loader never released anything"
        self.assertIn("perspective=com.ti.ccstudio.TIDebugPerspective", note)
        self.assertIn("perspective=com.ti.ccstudio.TICPerspective", note)
        self.assertIn("[TreeItems=2] -> [TreeItems=no]", note)

        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertTrue(passed, detail)

    def test_a_single_closed_round_is_a_flicker_not_a_death(self):
        """R1, driven: `[open, closed, open]` must not abort, re-issue, or drop the release.

        The ac2 sequence exactly.  The pair has to keep reading until it settles (the
        third round re-opens the streak), so the confirming call is still made and the
        run is green -- a single closed frame is a perspective blink, not a death.
        """
        parts = [_PARTS_EDIT, _PARTS_DEBUG, _PARTS_DEBUG,
                 _PARTS_DEBUG, _PARTS_EDIT, _PARTS_DEBUG,
                 _PARTS_DEBUG, _PARTS_DEBUG]
        answers = _live_answers([_RESUME_RAN, _DISABLED])
        answers["ui.parts"] = parts
        ctx = _LoadStub(answers)
        self.addCleanup(ctx.cleanup)
        with _fake_clock():
            load = ctx.run()

        self.assertTrue(load["gate"]["open"])
        self.assertIsNotNone(load["resume"])
        flicker = next(rec for rec in load["liveness"]
                       if rec["rounds"] and not rec["rounds"][0]["open"])
        self.assertFalse(flicker["rounds"][0]["open"])          # the blink (edit)
        self.assertTrue(flicker["rounds"][-1]["open"])          # ... and it re-opened
        self.assertEqual(len(flicker["rounds"]), 3,
                         "the pair kept reading past the blink, it did not stop at two")
        self.assertTrue(flicker["verdict"])
        self.assertFalse(flicker["aborted"])
        self.assertFalse(load["session_aborted"])
        self.assertIsNone(load["resume_reran"])
        self.assertEqual(len(load["launch_attempts"]), 1,
                         "a flicker may not trigger a re-issue")
        self.assertTrue(load["running"])
        self.assertIsNotNone(load["resume_probe"],
                             "the confirmation was still obtainable -- and was taken")
        self.assertEqual(load["resume_probe"].status_line.split()[0], "ERR")

        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertTrue(passed, detail)

    def test_a_run_of_closed_rounds_is_a_death(self):
        """R1's other side: the death must still be judged -- and judged promptly.

        `[open, closed, closed]` is a death (the streak, `_LIVENESS_ROUNDS` = 2).  The
        three rounds are a literal (C10): pushing the streak up to 4 would need five
        rounds here, so this test goes red instead of silently weakening the rule --
        the measured blink recovered inside one `_LIVENESS_STEP_S`, and a death has to
        be detectable from the same evidence.
        """
        ctx = _BridgeStub({"ui.parts": [_PARTS_DEBUG, _PARTS_EDIT, _PARTS_EDIT],
                           "ui.tree": [_TREE_LIVE]})
        with _fake_clock():
            alive, live = case._session_alive(ctx, {}, self.GATE)

        self.assertFalse(alive)
        self.assertTrue(live["aborted"])
        self.assertIs(live["verdict"], False)
        self.assertEqual(len(live["rounds"]), 3)
        self.assertIn("[TreeItems=2] -> [TreeItems=no]", live["diff"])
        self.assertIn(case._DEBUG_PERSPECTIVE, live["diff"])

    def test_a_bare_err_disabled_without_a_release_is_never_running(self):
        """Behaviour (iii): `ERR disabled` alone is not a release, and never reads as it.

        Nothing is ever released here -- `Resume` answers `ERR disabled` every time --
        so the case must stay red naming the not-released state, and `resume_probe`
        (the *upgrade* on R7's floor) must stay unset: the confirmation only means
        something after a `Resume` has actually run.
        """
        ctx = _LoadStub(_live_answers([_DISABLED]))
        self.addCleanup(ctx.cleanup)
        with _fake_clock(_LOAD_WAIT_SLICE_S=20.0, _LOAD_RESUME_REISSUE=1):
            load = ctx.run()

        self.assertTrue(load["gate"]["open"])
        self.assertIsNone(load["resume"])
        self.assertIsNone(load["resume_probe"])
        self.assertFalse(load["running"])
        self.assertTrue(load["resume_attempts"], "the loop did issue Resume")
        self.assertTrue(all(a.status_line.startswith("ERR disabled")
                            for a in load["resume_attempts"]))

        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertFalse(passed)
        self.assertIn("never ran", detail)

    def test_a_later_ran_after_the_release_is_named_as_still_halted(self):
        """The one post-release reading that does contradict the release.

        `OK executed …Resume` means the handler was enabled, i.e. a context existed
        *again* -- so a newer reading says the target is halted again.  That is a real
        FAIL, and it is named as one (never as "the loader never released anything",
        and never by re-issuing `launchActive` over a released target).
        """
        ctx = _LoadStub(_live_answers([_RESUME_RAN, _RESUME_RAN]))
        self.addCleanup(ctx.cleanup)
        with _fake_clock(_LOAD_WAIT_SLICE_S=20.0):
            load = ctx.run()

        self.assertTrue(load["gate"]["open"])
        self.assertIsNotNone(load["resume"])
        self.assertIsNotNone(load["resume_reran"])
        self.assertFalse(load["running"])
        self.assertIsNone(load["resume_blocked"])
        self.assertIsNone(load["resume_unconfirmed"])
        self.assertEqual(len(load["launch_attempts"]), 1)
        note = next(line for line in ctx.notes if "GIVING UP" in line)
        self.assertIn("DID run", note)
        self.assertIn(case._shape(load["resume"]), note)

        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertFalse(passed)
        self.assertIn("STILL HALTED", detail)
        self.assertIn(case._shape(load["resume"]), detail)

    def test_an_abort_after_a_release_is_named_as_the_abort_not_still_halted(self):
        """R2 at the verdict layer: name the evidence that is actually in the record.

        This is the ac2 verdict shape -- `resume` set, `running` False, and a verbatim
        read-back of the session going away -- and the wording must not invent "STILL
        HALTED at its entry point" over it.
        """
        result = _result()
        load = result["load"]
        load["running"] = False
        load["session_aborted"] = True
        load["abort_evidence"] = {
            "before": {"at": "t0", "perspective": case._DEBUG_PERSPECTIVE,
                       "debug_items": 2},
            "rounds": [
                {"round": 1, "open": False, "at": "t1",
                 "perspective": "com.ti.ccstudio.TICPerspective", "debug_items": None},
                {"round": 2, "open": False, "at": "t2",
                 "perspective": "com.ti.ccstudio.TICPerspective", "debug_items": None}],
            "diff": ("perspective com.ti.ccstudio.TIDebugPerspective -> "
                     "com.ti.ccstudio.TICPerspective; Debug view [TreeItems=2] -> "
                     "[TreeItems=no]")}
        passed, detail = case._expect(None, result)
        self.assertFalse(passed)
        self.assertIn("ABORTING", detail)
        self.assertIn("verbatim diff", detail)
        self.assertNotIn("STILL HALTED", detail)


class LaunchIssueLedgerTest(unittest.TestCase):
    """Requirement 3: each `launchActive` is recorded with the read-back after it."""

    def test_every_issue_is_ledgered_with_the_readback_that_followed_it(self):
        # Issue 1 spends its whole 4 s slice on CCS Edit, and issue 2's first round is
        # the debug perspective, so the gate opens on issue 2 and the Resume that
        # follows runs and is confirmed.  `ui.parts` frames line up with the calls in
        # order: [parts_before, slice 1 round 1, round 2, round 3, slice 2 round 1,
        # (repeat)] -- the first three are the controls/rounds of issue 1, the fourth
        # is the round the gate opens on.  The slice is 4 s with the 1.5 s floor under
        # one round, which is the three rounds the sequence is cut to.
        ctx = _LoadStub({
            "ui.parts": [_PARTS_EDIT, _PARTS_EDIT, _PARTS_EDIT, _PARTS_EDIT,
                         _PARTS_DEBUG],
            "ui.tree": [_TREE_LIVE],
            "sys.wait": [_IDLE],
            "cmd.run " + case._CMD_RESUME: [_DISABLED, _RESUME_RAN, _DISABLED],
            "cmd.run " + case._CMD_LAUNCH_ACTIVE: [_LAUNCH_RAN],
        })
        self.addCleanup(ctx.cleanup)
        with _fake_clock(_LOAD_WAIT_SLICE_S=4.0):
            load = ctx.run()

        self.assertTrue(load["running"])
        ledger = [line for line in ctx.notes if "launchActive ledger --" in line]
        self.assertEqual(len(ledger), 2)
        for line in ledger:
            self.assertRegex(line, r"sent \d\d:\d\d:\d\d")
        self.assertIn("issue 1 sent", ledger[0])
        self.assertIn("no session appeared", ledger[0])
        self.assertIn("perspective=com.ti.ccstudio.TICPerspective", ledger[0])
        self.assertIn("issue 2 sent", ledger[1])
        self.assertIn("gate OPEN", ledger[1])
        self.assertIn("perspective=com.ti.ccstudio.TIDebugPerspective", ledger[1])
        self.assertIn("Debug view [TreeItems=2]", ledger[1])

        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertTrue(passed, detail)


class JobsProbeTest(unittest.TestCase):
    """The job read is a **probe**, not a wait: one request, and it decides nothing.

    What it replaced waited for a fresh instance's own startup jobs (repository
    metadata downloads) to fall silent, under a 180 s cap.  Measured 2026-10-07: with
    that cap forced to 0 the **first** `launchActive` took effect while the instance's
    own jobs were still RUNNING and the gate OPENED on it -- so the wait only ever
    cost wall clock (54.3 s of one run).  These tests pin the shape of its replacement:
    exactly one request even while the instance is busy, and a record that decides
    nothing.
    """

    #: The probe request, as **this test** spells it.  Deliberately not built from the
    #: case's constant (`deliverable-shape` C10: a gate must not take its threshold
    #: from the thing it guards) -- a loop that crept back into `_probe_jobs` would ask
    #: `sys.wait jobs-idle` instead (and any *other* `sys.wait` form added there would
    #: show up too), so the pre-launch list below would no longer be exactly
    #: `[self.PROBE]`.
    PROBE = "sys.wait 1"

    #: The busy answer, assembled from the measured path (2026-10-07): its header
    #: (`mode=jobs-idle` / `waited_ms=15000 budget_ms=15000` / `pending=2` /
    #: `jobs_total=11 running=2 waiting=0 sleeping=9 none=0`) comes from run
    #: `board-ac1-fix`, `busy name="Loading the repository {0}"` from `settle-before`,
    #: and `…/ccsv9/auto/content.jar` from `board-ac1-fix` (whose own settle line reads
    #: `quiet=True after 3 poll(s) in 47.2s`).  The header is the `jobs-idle` mode's
    #: own text and the probe does not read it -- `_jobs_reading` takes `idle=` / the
    #: counts line / `busy name=`, which the bridge emits identically in both modes
    #: (`LiveBridge.sysWait`).
    BUSY = ("OK\nmode=jobs-idle\nwaited_ms=15000 budget_ms=15000\nidle=false\n"
            "pending=2\njobs_total=11 running=2 waiting=0 sleeping=9 none=0\n"
            '  busy name="Loading the repository {0}" state=RUNNING\n'
            '  busy name="https://software-dl.ti.com/ccs/esd/device_support_ccsv9/'
            'auto/content.jar" state=RUNNING\nEND')

    def test_the_probe_asks_once_even_when_the_instance_is_busy(self):
        """A busy instance is read **once** -- never re-read, never slept on."""
        ctx = _LoadStub(dict(_live_answers([_RESUME_RAN, _DISABLED]),
                             **{"sys.wait": [self.BUSY]}))
        self.addCleanup(ctx.cleanup)
        with _fake_clock():
            load = ctx.run()

        # The probe's own window is everything asked *before* the first launch: the
        # load wait's own `sys.wait jobs-idle` rounds come later, so the window is
        # what isolates "how many times the instance was looked at".
        first_launch = next(index for index, request in enumerate(ctx.requests)
                            if "launchActive" in request)
        self.assertEqual([request for request in ctx.requests[:first_launch]
                          if request.startswith("sys.wait")], [self.PROBE])
        self.assertEqual(load["jobs"]["idle"], "false")
        self.assertEqual(load["jobs"]["running"], "2")
        self.assertTrue(load["jobs"]["busy"])
        self.assertTrue(any(line.startswith("load: jobs --") for line in ctx.notes))

    def test_a_busy_instance_is_not_a_reason_to_skip_or_fail(self):
        ctx = _LoadStub(dict(_live_answers([_RESUME_RAN, _DISABLED]),
                             **{"sys.wait": [self.BUSY]}))
        self.addCleanup(ctx.cleanup)
        with _fake_clock():
            load = ctx.run()

        self.assertEqual(load["jobs"]["idle"], "false")
        self.assertTrue(load["launch_attempts"])     # the launch went out anyway
        self.assertTrue(load["running"])

        # ... and nothing in the verdict reads it: the load still passes whole.
        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertTrue(passed, detail)

    def test_an_idle_instance_is_recorded_as_idle(self):
        ctx = _LoadStub(_live_answers([_RESUME_RAN, _DISABLED]))
        self.addCleanup(ctx.cleanup)
        with _fake_clock():
            load = ctx.run()

        self.assertEqual(load["jobs"]["idle"], "true")
        self.assertEqual(load["jobs"]["running"], "0")
        self.assertEqual(load["jobs"]["busy"], [])


# --------------------------------------------------------------------------- #
# The load stage's `#32770` shells: a question is answered, a progress shell is
# waited out (2026-10-07, `ccs12-p42` frame 114 + this round's button enumeration)
# --------------------------------------------------------------------------- #

#: This instance's pid -- the scope every window lookup in these tests is bound to.
_PID = 29912

#: Verbatim shapes from the measured path.  The question's title and its affirmative
#: button are frame 114 of run `ccs12-p42` (`python -m ctl shadow --run-id ccs12-p42
#: --seq 114`); the progress shell's title is this round's enumeration, verbatim.
_QUESTION_TITLE = "Reuse Debug Settings"
_PROGRESS_TITLE = ("Loading Program: C:\\Users\\Alice\\.eclipse-ctl\\runs\\ccs12-p42\\ws\\"
                   "board_led_chase\\CPU1_RAM\\board_led_chase.out")
_SHELL = (_PID, "SWT_Window0", "CCS Edit")
_QUESTION = (_PID, "#32770", _QUESTION_TITLE)
_PROGRESS = (_PID, "#32770", _PROGRESS_TITLE)
#: The measured press line of the question, as the tool prints it and as the case
#: records it: `BM_CLICK sent to hwnd=0xE010DA text="&Yes"`.
_CLICKED = 'BM_CLICK sent to hwnd=0xE010DA text="&Yes"'
#: The tool's own verbatim refusal when nothing matched (0 hits, §13.6/§13.7).
_NO_MATCH = "ERR no visible Button matching 'Yes'"


def _window(hwnd, meta):
    return {hwnd: meta}


class _Screen:
    """The three `ctl.screen` entry points `_answer_load_modal` uses, faked.

    ``frames`` is a list of window maps (``{hwnd: (pid, class, title)}``); the last
    one repeats.  ``button_table`` maps a window title to the ``[(hwnd, text)]`` its
    enumeration returns; ``click_output`` is the verbatim output of the press tool.
    ``seen``/``enumerated``/``clicked``/``closed`` are what the test asserts on: how
    often windows were looked at, which titles were enumerated, what was pressed, and
    what was closed (``WM_CLOSE`` -- which must never happen to a question).
    """

    def __init__(self, frames, button_table=None, click_output=_CLICKED):
        self.frames = list(frames)
        self.button_table = dict(button_table or {})
        self.click_output = click_output
        self.seen = 0
        self.enumerated = []
        self.clicked = []
        self.closed = []

    def visible_windows(self, pids=None):
        windows = self.frames[min(self.seen, len(self.frames) - 1)]
        self.seen += 1
        return dict(windows)

    def buttons(self, title_like, pids=None, timeout=60.0):
        self.enumerated.append(title_like)
        return list(self.button_table.get(title_like, []))

    def click_button(self, title_like, text, pids=None, timeout=60.0):
        self.clicked.append((title_like, text))
        return self.click_output

    def close(self, title_like, cls="", pids=None, timeout=60.0):
        self.closed.append((title_like, cls))
        return "no window matched (test)"


@contextlib.contextmanager
def _fake_screen(stub):
    """Patch the window entry points `ctl.screen` exposes, for one test."""
    with mock.patch.object(case.screen, "visible_windows", stub.visible_windows), \
            mock.patch.object(case.screen, "buttons", stub.buttons), \
            mock.patch.object(case.screen, "click_button", stub.click_button), \
            mock.patch.object(case.screen, "close", stub.close):
        yield stub


def _green_load(screen_stub, answers=None, **constants):
    """Drive `_load` to a PASSing run with `screen_stub` answering the windows."""
    ctx = _LoadStub(answers if answers is not None else
                    _live_answers([_RESUME_RAN, _DISABLED]))
    ctx.screen_pids = [_PID]
    try:
        with _fake_screen(screen_stub):
            with _fake_clock(**constants):
                return ctx, ctx.run()
    finally:
        ctx.cleanup()


class LoadModalTest(unittest.TestCase):
    """The load stage's own `#32770` shells, and the boundary that decides them.

    Two shells sit on this path and they need opposite handling (both measured):

    * the **question** ``Reuse Debug Settings`` -- body *This project has been
      debugged before…*, buttons ``&Yes`` / ``&No`` -- is **answered** by pressing the
      affirmative button.  ``WM_CLOSE`` here is *cancel*, so it would cancel the very
      load the stage is waiting for, and while it stands the SWT thread is blocked
      (frame 114: the load's own request answered ``ERR timeout UI task did not finish
      within 15000 ms``, and eight `ui.parts` reads after it all said `TICPerspective`);
    * the **progress shell** ``Loading Program: …\\board_led_chase.out`` has **no
      Button at all**: nothing is asked, it is waited out, and the zero hits are
      normal -- not a fault, and never a reason to close it.

    What is on screen is decided by the dialog's **buttons**, and the dialog itself
    is identified by **class + this instance's pid** -- never by its title.  Every
    ambiguity fails closed (nothing pressed, candidates recorded).
    """

    def test_the_question_is_answered_during_the_wait_and_the_load_still_passes(self):
        """The headline case: a clean answer plus the question ⇒ answered, then PASS.

        The box is *not* on screen at the launch issue (it appears while the load
        runs), so only the gate-wait can catch it -- which is what the recorded
        ``when`` pins, together with the press itself.
        """
        stub = _Screen(
            frames=[_window("0X0001234", _SHELL),
                    dict(_window("0X0001234", _SHELL),
                         **_window("0X13D1462", _QUESTION)),
                    _window("0X0001234", _SHELL)],
            button_table={_QUESTION_TITLE: [("0XE010DA", "&Yes"), ("0XE010DB", "&No")]})
        ctx, load = _green_load(stub)

        # pressed, by the declared text, on the dialog that was identified by class+pid
        self.assertEqual(stub.clicked, [(_QUESTION_TITLE, "Yes")])
        # ... and closed nothing: `WM_CLOSE` on a question is *cancel*
        self.assertEqual(stub.closed, [])
        rows = load["modal_answers"]
        self.assertEqual([row["action"] for row in rows], ["pressed"])
        self.assertTrue(rows[0]["when"].startswith("wait round"), rows[0]["when"])
        self.assertEqual(rows[0]["hwnd"], "0X13D1462")
        self.assertEqual(rows[0]["buttons"], ['0XE010DA "&Yes"', '0XE010DB "&No"'])
        self.assertEqual(rows[0]["output"], _CLICKED)

        note = next(line for line in ctx.notes if "load: modal answer (" in line)
        self.assertIn(_QUESTION_TITLE, note)
        self.assertIn(_CLICKED, note)
        self.assertTrue(load["running"])
        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertTrue(passed, detail)

    def test_the_question_on_screen_at_the_issue_is_answered_there_too(self):
        stub = _Screen(frames=[dict(_window("0X0001234", _SHELL),
                                    **_window("0X13D1462", _QUESTION))],
                       button_table={_QUESTION_TITLE: [("0XE010DA", "&Yes"),
                                                  ("0XE010DB", "&No")]})
        _ctx, load = _green_load(stub)
        self.assertEqual([row["when"] for row in load["modal_answers"]],
                         ["after launchActive issue 1"])
        self.assertEqual(stub.clicked, [(_QUESTION_TITLE, "Yes")])

    def test_a_clean_run_with_no_shell_at_all_is_untouched_and_still_passes(self):
        """No false red: nothing on screen ⇒ nothing enumerated, nothing pressed."""
        stub = _Screen(frames=[_window("0X0001234", _SHELL)])
        ctx, load = _green_load(stub)
        self.assertEqual(load["modal_answers"], [])
        self.assertEqual(stub.enumerated, [])
        self.assertEqual(stub.clicked, [])
        self.assertFalse(any("modal answer" in line for line in ctx.notes))
        self.assertTrue(load["running"])
        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertTrue(passed, detail)

    def test_the_progress_shell_is_waited_out_never_pressed_and_never_red(self):
        """No Button at all: `no-button`, once, and the verdict does not move.

        The measured progress shell answers the click attempt with
        ``no visible window matching 'Loading Program: …'`` -- 0 hits, which here is
        the *expected* shape.  It also shows the ledger's dedupe: the box stays on
        screen for many rounds and is recorded once (per window).
        """
        stub = _Screen(frames=[_window("0XD61210", _PROGRESS)],
                       button_table={_PROGRESS_TITLE: []})
        ctx, load = _green_load(stub)
        rows = load["modal_answers"]
        self.assertEqual(len(rows), 1, "a shell that stays on screen is recorded once")
        self.assertEqual(rows[0]["action"], "no-button")
        self.assertEqual(rows[0]["hwnd"], "0XD61210")
        self.assertEqual(rows[0]["buttons"], [])
        self.assertEqual(stub.clicked, [])
        self.assertEqual(stub.closed, [])
        self.assertTrue(any("modal answer NO BUTTON" in line for line in ctx.notes))
        self.assertTrue(load["running"])
        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertTrue(passed, detail)

    def test_both_shells_at_once_are_decided_separately(self):
        """One frame, two dialogs: the progress shell is waited out, the question answered."""
        both = dict(_window("0X0001234", _SHELL), **_window("0XD61210", _PROGRESS),
                    **_window("0X13D1462", _QUESTION))
        stub = _Screen(frames=[both],
                       button_table={_PROGRESS_TITLE: [],
                                     _QUESTION_TITLE: [("0XE010DA", "&Yes"),
                                                       ("0XE010DB", "&No")]})
        _ctx, load = _green_load(stub)
        self.assertEqual(sorted((row["hwnd"], row["action"])
                                for row in load["modal_answers"]),
                         [("0X13D1462", "pressed"), ("0XD61210", "no-button")])
        self.assertEqual(stub.clicked, [(_QUESTION_TITLE, "Yes")])

    def test_no_affirmative_button_is_a_refusal_not_a_press(self):
        """A box with buttons, none of them ours: record and press nothing."""
        stub = _Screen(frames=[_window("0X0BADBEEF", (_PID, "#32770", "Error"))],
                       button_table={"Error": [("0XE01", "&OK"), ("0XE02", "&Cancel")]})
        ctx, load = _green_load(stub)
        rows = load["modal_answers"]
        self.assertEqual([row["action"] for row in rows], ["refused"])
        self.assertIn("0 of the 2 visible Button(s)", rows[0]["refusal"])
        self.assertEqual(rows[0]["buttons"], ['0XE01 "&OK"', '0XE02 "&Cancel"'])
        self.assertEqual(stub.clicked, [])
        self.assertTrue(any("modal answer REFUSED" in line for line in ctx.notes))

    def test_two_affirmative_buttons_are_an_ambiguity_that_is_never_picked_from(self):
        stub = _Screen(frames=[_window("0X13D1462", _QUESTION)],
                       button_table={_QUESTION_TITLE: [("0XE010DA", "&Yes"),
                                                  ("0XE010DC", "&Yes to all")]})
        _ctx, load = _green_load(stub)
        rows = load["modal_answers"]
        self.assertEqual([row["action"] for row in rows], ["refused"])
        self.assertEqual(rows[0]["candidates"], ['0XE010DA "&Yes"', '0XE010DC "&Yes to all"'])
        self.assertEqual(stub.clicked, [], "no silent pick from an ambiguous set")

    def test_a_press_the_tool_did_not_make_is_not_a_press(self):
        """§13.7 at the low layer: the tool's own three states decide, not ours.

        The enumeration sees exactly one `&Yes`, but the press itself comes back with
        the tool's 0-hit refusal.  The row may then not read `pressed` -- counting it
        would be the silent wrong click the whole discipline is about.  Nothing was
        pressed, so the wait may try again (the tool is addressed the same way each
        time); the ledger keeps the refusal once.
        """
        stub = _Screen(frames=[_window("0X13D1462", _QUESTION)],
                       button_table={_QUESTION_TITLE: [("0XE010DA", "&Yes")]},
                       click_output=_NO_MATCH)
        _ctx, load = _green_load(stub)
        rows = load["modal_answers"]
        self.assertEqual([row["action"] for row in rows], ["refused"])
        self.assertIn(_NO_MATCH, rows[0]["refusal"])
        self.assertTrue(stub.clicked)
        self.assertEqual(set(stub.clicked), {(_QUESTION_TITLE, "Yes")})

    def test_a_title_that_addresses_two_windows_is_refused_before_any_press(self):
        """The address the tool uses is a title, so it has to be unique in its scope.

        Two dialogs carry the same title: the tool (`Find`) would take whichever it
        enumerates first, so the case refuses for both and never even enumerates --
        nothing is pressed on an address it cannot pin to one window.
        """
        stub = _Screen(frames=[dict(_window("0X13D1462", _QUESTION),
                                    **_window("0X13D1463", _QUESTION))],
                       button_table={_QUESTION_TITLE: [("0XE010DA", "&Yes")]})
        _ctx, load = _green_load(stub)
        rows = load["modal_answers"]
        self.assertEqual([row["action"] for row in rows], ["refused", "refused"])
        self.assertEqual(rows[0]["candidates"], ["0X13D1462", "0X13D1463"])
        self.assertEqual(stub.enumerated, [])
        self.assertEqual(stub.clicked, [])

    def test_an_unknown_instance_pid_touches_no_window_and_is_recorded_once(self):
        ctx = _LoadStub(_live_answers([_RESUME_RAN, _DISABLED]))
        self.addCleanup(ctx.cleanup)
        stub = _Screen(frames=[_window("0X13D1462", _QUESTION)],
                       button_table={_QUESTION_TITLE: [("0XE010DA", "&Yes")]})
        with _fake_screen(stub):
            with _fake_clock():
                load = ctx.run()

        rows = load["modal_answers"]
        self.assertEqual(len(rows), 1, "the same refusal is not repeated every round")
        self.assertEqual(rows[0]["action"], "refused")
        self.assertIn("pid is unknown", rows[0]["refusal"])
        self.assertEqual(stub.clicked, [])
        self.assertEqual(stub.seen, 0, "no window was even enumerated")


# --------------------------------------------------------------------------- #
# The LaunchBar mode `_seed` now seeds (2026-10-07: `run` ⇒ accepted, no session)
# --------------------------------------------------------------------------- #

class SeedLaunchbarPrefsTest(unittest.TestCase):
    """`_seed` writes the LaunchBar **mode**, and the wait still needs the IDE.

    Both halves of the measured contract (C10/C12):

    * (a) with the descriptor's ``activeLaunchMode`` seeded as ``debug`` and the IDE
      having bound it (its own ``activeLaunchTarget`` line), the descriptor is live and
      the load's gate can open -- driven to PASS;
    * (b) with ``run`` -- what the LaunchBar writes when it builds that state itself --
      the command is accepted with a clean answer and **no debug session is created**,
      so the descriptor is never made live and a run in that state stays red.

    And the sync itself must stay a line this case does **not** write (see
    `LaunchbarWaitTest.test_the_file_this_case_writes_is_not_a_sync_by_itself`), which
    is why the seeded file carries no ``configDescList``.
    """

    #: The test's own literals (C10), never `case._LAUNCHBAR_PREFS`/`case._LAUNCH_NAME`:
    #: the two descriptor names `_seed` must preset, and the file it must write.
    NAMES = ("ctl_board_chase", "board_led_chase")
    PRESET = ("eclipse.preferences.version=1\n"
              "org.eclipse.launchbar.core.descriptorType.default\\:ctl_board_chase"
              "/activeLaunchMode=debug\n"
              "org.eclipse.launchbar.core.descriptorType.default\\:board_led_chase"
              "/activeLaunchMode=debug\n")

    class _Ctx:
        class _Target:
            name = "ccs12"
            install_dir = ""
            port = 0

            @staticmethod
            def launcher_path():
                # Any existing file: only `os.path.isfile` ever sees it (`_run_capture`
                # is faked -- no IDE is started here).
                return os.path.abspath(case.__file__)

        class _Runner:
            port = 0

        class _Paths:
            def __init__(self, workspace):
                self.workspace = workspace
                self.configuration = os.path.join(workspace, ".metadata")
                self.endpoint = os.path.join(self.configuration, "endpoint.json")

        def __init__(self, workspace):
            self.paths = self._Paths(workspace)
            self.target = self._Target()
            self.runner = self._Runner()
            self.run_id = "unit"
            self.notes = []
            self.board_plan = None

        def note(self, line):
            self.notes.append(line)

    def _seed(self, stale=None):
        """Drive `_seed`, faking only the projectCreate subprocess and the clock patch."""
        workspace = tempfile.mkdtemp(prefix="eclipse-ctl-seed-")
        self.addCleanup(shutil.rmtree, workspace, ignore_errors=True)
        name = self.NAMES[1]
        settings = os.path.join(workspace, ".metadata", ".plugins",
                                "org.eclipse.core.runtime", ".settings")
        os.makedirs(settings, exist_ok=True)
        if stale is not None:
            with open(os.path.join(settings, "org.eclipse.launchbar.core.prefs"),
                      "w", encoding="utf-8", newline="") as handle:
                handle.write(stale)
        ctx = self._Ctx(workspace)
        plan = {"workspace": workspace,
                "spec": "C:/c2000ware/empty_driverlib_project.projectspec"}

        def create(argv, timeout, cwd=None):
            proj = os.path.join(workspace, argv[-1])
            os.makedirs(proj, exist_ok=True)
            written = {".project": "<projectDescription><name>%s</name></projectDescription>\n"
                                    % name,
                       ".cproject": "<cproject/>\n",
                       ".ccsproject": '<deviceVariant value="TMS320C28XX.TMS320F280025C"/>\n'}
            for entry, text in written.items():
                with open(os.path.join(proj, entry), "w", encoding="utf-8",
                          newline="") as handle:
                    handle.write(text)
            return {"rc": 0, "timed_out": False, "text": "projectCreate ok",
                    "elapsed": 1.0, "killed": None}

        clock = {"path": os.path.join(workspace, name, "device", "device.h"),
                 "line": 272, "error": ""}
        with mock.patch.object(case, "_run_capture", create), \
                mock.patch.object(case, "_patch_clock_source", return_value=clock):
            out = case._seed(ctx, plan, name, _MARKER)
        return ctx, workspace, out

    def test_seed_writes_the_debug_mode_for_both_names_over_any_stale_file(self):
        ctx, workspace, out = self._seed(
            stale="configDescList=org.eclipse.launchbar.core.descriptorType.default"
                  "\\:somebody_elses_descriptor\n"
                  "org.eclipse.launchbar.core.descriptorType.default"
                  "\\:somebody_elses_descriptor/activeLaunchMode=debug\n")
        self.assertTrue(out["ok"], out["error"])
        prefs = os.path.join(workspace, ".metadata", ".plugins",
                             "org.eclipse.core.runtime", ".settings",
                             "org.eclipse.launchbar.core.prefs")
        self.assertEqual(out["launchbar_prefs"], prefs)
        self.assertEqual(case._read_text(prefs), self.PRESET)
        self.assertNotIn("somebody_elses_descriptor", case._read_text(prefs))
        # the list stays the IDE's: a name this case wrote must not become its own sync
        self.assertNotIn("configDescList", case._read_text(prefs))
        # the design name first, the project name as the documented fallback
        self.assertEqual(out["launchbar_names"], list(self.NAMES))
        note = next(line for line in ctx.notes if line.startswith("launchbar:"))
        self.assertIn(str(self.NAMES[1]), note)

    def test_the_seeded_file_only_becomes_a_sync_when_the_ide_binds_the_descriptor(self):
        ctx, workspace, out = self._seed()
        self.assertTrue(out["ok"], out["error"])
        with mock.patch.object(case, "_LAUNCHBAR_WAIT_S", 0.0):
            before = case._wait_launchbar(ctx, {"workspace": workspace})
        self.assertFalse(before["found"], "our own write is not the IDE's signal")
        self.assertEqual(before["modes"], {self.NAMES[0]: "debug", self.NAMES[1]: "debug"})
        self.assertEqual(before["targets"], {})
        # ... then the IDE activates the descriptor: its own key, its own value
        with open(out["launchbar_prefs"], "a", encoding="utf-8", newline="") as handle:
            handle.write("org.eclipse.launchbar.core.descriptorType.default\\:%s"
                         "/activeLaunchTarget=org.eclipse.launchbar.core."
                         "launchTargetType.local\\:Local\n" % self.NAMES[0])
        with mock.patch.object(case, "_LAUNCHBAR_WAIT_S", 0.0):
            after = case._wait_launchbar(ctx, {"workspace": workspace})
        self.assertTrue(after["found"])
        self.assertEqual(after["active"], self.NAMES[0])

    def test_the_preset_debug_is_taken_and_the_load_passes(self):
        """(a) the seeded `debug`, adopted: the descriptor is live and the load is green."""
        ctx = _LoadStub(_live_answers([_RESUME_RAN, _DISABLED]), mode="debug")
        self.addCleanup(ctx.cleanup)
        with _fake_clock():
            load = ctx.run()

        self.assertTrue(load["launchbar"]["found"])
        self.assertEqual(load["launchbar"]["active"], self.NAMES[0])
        self.assertTrue(load["gate"]["open"])
        self.assertTrue(load["running"])
        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertTrue(passed, detail)

    def test_only_run_leaves_the_descriptor_not_live(self):
        """The isolated pair: the same live bridge, `debug` vs `run`.

        The *bridge* cannot see the LaunchBar mode, so this pins exactly what the case
        can observe from it: the wait makes our descriptor live in `debug` and never in
        `run`.  What `run` costs at the session level -- no debug context at all -- is
        the red drive below.
        """
        live = _live_answers([_RESUME_RAN, _DISABLED])
        on = _LoadStub(live, mode="debug")
        self.addCleanup(on.cleanup)
        off = _LoadStub(live, mode="run")
        self.addCleanup(off.cleanup)
        with _fake_clock():
            live_load = on.run()
            run_load = off.run()

        self.assertTrue(live_load["launchbar"]["found"])
        self.assertEqual(live_load["launchbar"]["active"], self.NAMES[0])
        self.assertFalse(run_load["launchbar"]["found"])
        self.assertEqual(run_load["launchbar"]["modes"], {self.NAMES[0]: "run"})
        self.assertEqual(run_load["launchbar"]["bound"], [self.NAMES[0]])
        self.assertIsNone(run_load["launchbar"]["active"])

    def test_a_run_mode_run_whose_session_never_appears_is_red(self):
        """(b) driven: `run` creates no session ⇒ the gate never opens ⇒ FAIL.

        The bridge answers are the measured shape of that state: the perspective stays
        `TICPerspective` (here: the only `ui.parts` frame), so the Debug view is never
        even asked for and the load reports the stage it failed at.
        """
        ctx = _LoadStub({"ui.parts": [_PARTS_EDIT], "ui.tree": [_TREE_LIVE],
                         "sys.wait": [_IDLE],
                         "cmd.run " + case._CMD_RESUME: [_DISABLED],
                         "cmd.run " + case._CMD_LAUNCH_ACTIVE: [_LAUNCH_RAN]},
                        mode="run")
        self.addCleanup(ctx.cleanup)
        with _fake_clock(_LOAD_WAIT_SLICE_S=4.0, _LOAD_LAUNCH_ATTEMPTS=1):
            load = ctx.run()

        self.assertFalse(load["launchbar"]["found"])
        self.assertFalse(load["gate"]["open"])
        self.assertFalse(load["running"])
        result = _result()
        result["load"] = load
        passed, detail = case._expect(None, result)
        self.assertFalse(passed)
        self.assertIn("no debug context", detail)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
