"""The GS32 board case's own gate: its verdict, its channel words, its overlay, its load.

Two shapes this file exists for (`deliverable-shape.md`):

* **C10** -- every literal pinned here is *this file's own*: the pin-mux statements, the
  chase's four complementary writes, the toggle idiom it forbids, and the three
  channel-state words are written out below, and the case's constants are asserted
  **equal** to them.  Reading them back (`self.assertEqual(case.MUX, case.MUX)`) would
  certify nothing: a typo in the constant would keep both sides of the comparison wrong
  together.  The command ids and the confirmation marker are pinned the same way, because
  R4's criterion is exactly "a line `OK executed <command id>` and no `dialog=` line".
* **C12** -- one mutation per predicate.  `ExpectLedgerTest` reddens exactly the
  predicate it weakens (never a neighbour's), `OverlayGateTest` does the same for the
  payload gates, `RanCriterionTest` pins the three shapes of a driven command's frame,
  and `ChannelStateTest` gives each of C14's four channel states its own wording so they
  cannot be confused for one another.

Nothing here touches a board, `GS32.exe` or the bridge.  `_expect` is driven with
synthetic results, `_overlay` with a synthetic two-file template, `_ran` with synthetic
frames, and the two hardware channels only through their `ECLIPSE_CTL_GS32_BOARD_*`
override seam (which by construction never spawns anything).
"""

from __future__ import annotations

import os
import shutil
import struct
import tempfile
import unittest
import unittest.mock as mock

from ctl.client import Response
from ctl.verify.cases import board_led_chase_gs32 as case

#: The mux datum, as this file's own literal (C10) -- **whole statements**, not the
#: `GPIO_MUX_DATA(...)` fragments: with the fragment form the mutation `GPAMUX2` ->
#: `GPAMUX1` stayed green (GPIO24/GPIO21 are not in `GPAMUX1`'s range, so the pins would
#: keep their reset peripheral function and the LEDs could never light).
_MUX = ("GpioCtrlRegs.GPAMUX2.bit.BOARD_LED1 = GPIO_MUX_DATA(BOARD_LED1_MUX);",
        "GpioCtrlRegs.GPAMUX2.bit.BOARD_LED2 = GPIO_MUX_DATA(BOARD_LED2_MUX);")
#: The chase's semantics, as this file's own literal (C10): every step drives **both**
#: pins to complementary levels, so exactly one LED is lit at any time.
_CHASE = ("GpioDataRegs.GPACLEAR.bit.BOARD_LED1 = 0x1;",
          "GpioDataRegs.GPASET.bit.BOARD_LED2 = 0x1;",
          "GpioDataRegs.GPASET.bit.BOARD_LED1 = 0x1;",
          "GpioDataRegs.GPACLEAR.bit.BOARD_LED2 = 0x1;")
#: The toggle idiom the payload must not carry, and the two command ids R4 judges.
_FORBIDDEN = "GPATOGGLE.bit.BOARD_LED"
_LAUNCH_ACTIVE = "org.eclipse.launchbar.ui.command.launchActive"
_RESUME = "org.eclipse.debug.ui.commands.Resume"


class _Ctx(object):
    """The smallest stand-in `_pre`/`_expect`/`_overlay` touch."""

    def __init__(self):
        self.notes = []
        self.run_id = "review"
        self.target = type("T", (), {"install_dir": "", "name": "gs32"})()

    def note(self, text):
        self.notes.append(text)


# --------------------------------------------------------------------------- #
# A synthetic template: the two anchors `_overlay` needs, and nothing else.
# Spelled out here rather than imported from the case (C10).
# --------------------------------------------------------------------------- #

_C_HEADER = "/**\n  * @brief Configuration of the LED pins\n  */\n"

_C_SOURCE = (
    '#include "log.h"\n'
    "\n"
    "void main(void)\n"
    "{\n"
    "    Device_init();\n"
    '    log_info("Hello DSP template!\\r\\n");\n'
    "\n"
    "    while (1) {\n"
    "if ((tickCnt % 50) == 0) {\n"
    "    GpioDataRegs.GPATOGGLE.bit.GPIO24=0x1;\n"
    '    log_info("ticks: %d\\r\\n", dspTicks);\n'
    "}\n"
    "    }\n"
    "}\n")


def _template(root):
    project = os.path.join(root, "gs32f035")
    os.makedirs(os.path.join(project, "inc"))
    os.makedirs(os.path.join(project, "src"))
    with open(os.path.join(project, "inc", "board_cfg.h"), "w",
              encoding="gbk", newline="") as handle:
        handle.write(_C_HEADER)
    with open(os.path.join(project, "src", "main.c"), "w",
              encoding="gbk", newline="") as handle:
        handle.write(_C_SOURCE)
    return project


class CaseContractTest(unittest.TestCase):
    """What the runner and the user path are promised, asserted against literals."""

    def test_the_case_declares_its_target_and_does_not_need_the_bridge(self):
        self.assertEqual(case.CASE.targets, ("gs32",))
        self.assertIs(case.CASE.requires_bridge, False)
        self.assertIs(case.CASE.screen_guard, False)

    def test_the_payload_gates_and_channel_words_are_pinned_independently(self):
        """C15: the payload's semantics are pinned by this file's own literals, so a
        weakened payload gate reddens *here* as well as in the case."""
        self.assertEqual(tuple(case._MUX_NEEDLES), _MUX)
        self.assertEqual(tuple(case._CHASE_NEEDLES), _CHASE)
        self.assertEqual(case._CHASE_FORBIDDEN, _FORBIDDEN)
        self.assertEqual((case._PRESENT, case._ABSENT, case._UNKNOWN),
                         ("present", "absent", "unknown"))

    def test_the_driven_command_ids_and_the_confirmation_marker_are_pinned(self):
        """R4's criterion, as literals: the id that was sent, and the line that confirms
        the handler ran -- both named by the case, both checked against this file."""
        self.assertEqual(case._CMD_LAUNCH_ACTIVE, _LAUNCH_ACTIVE)
        self.assertEqual(case._CMD_RESUME, _RESUME)
        self.assertEqual(case._OK_MARK, "OK executed ")
        self.assertEqual(case._DIALOG_MARK, "dialog=")

    def test_the_board_facts_and_artifact_identity_are_pinned(self):
        self.assertEqual((case._CHIP, case._SERIAL), ("GS32F035P", "GJBDRPSSA"))
        self.assertEqual(case._IDCODE, "0x1030aa6d")
        self.assertEqual(case._BOARD_HWID, "VID_0403&PID_6010")
        self.assertEqual(case._MARKER_PREFIX, "CTL-GS32-")
        self.assertEqual(case._E_MACHINE_RISCV, 243)

    def test_the_ram_configuration_recipe_is_pinned(self):
        """R2's recipe, as literals: the clone source, the segment script it swaps in,
        the **P** part script (512K/128K/32K -- the non-P file is 256K/64K/16K), the
        register script that must not move, and the `-D` that must be dropped."""
        self.assertEqual(case._CONFIG, "RAM")
        self.assertEqual(case._FLASH_CONFIG, "Flash_ILM")
        self.assertEqual(case._FLASHILM_SCRIPT, "gs32f00xx_dsp_flashilm.ld")
        self.assertEqual(case._RAM_SCRIPT, "gs32f00xx_dsp_ram.ld")
        self.assertEqual(case._MEM_SCRIPT, "GS32F035_mem.ld")
        self.assertEqual(case._MEM_SCRIPT_P, "GS32F035P_mem.ld")
        self.assertEqual(case._REGS_SCRIPT, "gs32f00xx_dsp_3.0_regs.ld")
        self.assertEqual(case._FLASH_DEFINE, "FLASH_TARGET")
        self.assertEqual(case._APP, "org.eclipse.cdt.managedbuilder.core.headlessbuild")


# --------------------------------------------------------------------------- #
# The judgement layer: one mutation per predicate (C12)
# --------------------------------------------------------------------------- #

def _frame(*lines):
    """A bridge frame with this file's own shape: a status line, then the body."""
    return Response("\n".join(list(lines) + ["END"]))


def _ran(command_id):
    return _frame("OK", "OK executed " + command_id)


def _disabled():
    return _frame("ERR disabled")


def _green():
    """A result in which every predicate holds (the values are the measured ones)."""
    return {
        "errors": [],
        "name": "gs32f035", "config": "RAM", "chip": "GS32F035P",
        "marker": "CTL-GS32-deadbeef", "project": "<p>", "run": "gs32-gate",
        "started_at": 1.0,
        "seed": {"ok": True, "error": "",
                 "overlay": {"ok": True, "error": "", "applied": [], "missing": []},
                 "ram": {"ok": True, "id": "com.hpec…flash.980314703.490272334",
                         "configs": ["Flash_ILM", "RAM"], "dropped": 2, "checks": []},
                 "launch": {"ok": True, "name": "gs32f035_openocd",
                            "files": ["<p>/.launches/gs32f035_openocd.launch"],
                            "program": "RAM/gs32f035.elf", "gdb_server_other": ""}},
        "syntax": {"available": True, "rc": 0, "errors": [], "tail": ""},
        "build": {"rc": 0, "timed_out": False,
                  "summary": "Build Finished. 0 errors, 0 warnings.",
                  "errors": "0", "warnings": "0", "compiler_errors": [],
                  "tail": "", "elapsed": 15.4, "argv": [], "text": "", "native": True},
        "artifact": {"path": "<ws>/RAM/gs32f035.elf", "pattern": "<glob>",
                     "size": 551060,
                     "sha256": "x", "mtime": 2.0, "stale": False,
                     "elf": {"class": 1, "endian": 1, "machine": 243},
                     "marker_offset": 32864, "marker_encoding": "ascii",
                     "readelf": {"tool": "readelf", "rc": 0, "text": "",
                                 "elf_class": "ELF32", "machine": "RISC-V", "error": ""}},
        "start": {"rc": 0, "text": "", "error": ""},
        "load": {"launch": _ran(_LAUNCH_ACTIVE), "resume": _ran(_RESUME),
                 "resume_before": _disabled(), "wait": ["OK (8 lines)"],
                 "attempts": 1, "resume_at": "00:00:01", "console": "", "log_tail": "",
                 "transport_error": "",
                 "loadbar": {"path": "<ws>/…/org.eclipse.launchbar.core.prefs",
                             "lines": [],
                             "modes": {"org.eclipse.launchbar.core.descriptorType"
                                       ".default\\:gs32f035_openocd": "debug"},
                             "error": ""}},
        "plan": {"hardware": {"attach": {"state": "present"},
                              "pnp": {"state": "present"}, "state": "present",
                              "reason": ""},
                 "killed": []},
        "blocked": [], "stopped_at": None, "not_run": "",
    }


class ExpectLedgerTest(unittest.TestCase):
    """Each row weakens exactly one guard and reddens exactly that guard's predicate.

    The red list is captured where it is *built*, not parsed back out of the verdict
    string: `verdict` joins the problems with `"; "`, and a message of its own may
    contain that sequence (the chase complaint does), so splitting the prose would
    miscount one problem as two.
    """

    def _red(self, mutate):
        result = _green()
        mutate(result)
        captured = []
        original = case.verdict

        def record(problems, detail):
            captured.extend(problems)
            return original(problems, detail)

        with mock.patch.object(case, "verdict", record):
            passed, detail = case._expect(_Ctx(), result)
        self.assertFalse(passed, "the mutation left the verdict green: %s" % detail)
        return list(captured)

    def test_the_unmutated_result_is_green(self):
        passed, detail = case._expect(_Ctx(), _green())
        self.assertTrue(passed, detail)

    def test_build_summary_missing(self):
        red = self._red(lambda r: r["build"].update(summary=None))
        self.assertEqual(len(red), 1)
        self.assertIn("carries no 'Build Finished", red[0])

    def test_build_rc_nonzero(self):
        self.assertEqual(self._red(lambda r: r["build"].update(rc=1)),
                         ["build: rc=1 (expected 0)"])

    def test_build_compiler_error_line(self):
        red = self._red(lambda r: r["build"].update(compiler_errors=["m.c:1:1: error: x"]))
        self.assertEqual(len(red), 1)
        self.assertIn("compiler error line(s)", red[0])

    def test_artifact_missing(self):
        red = self._red(lambda r: r["artifact"].update(path=""))
        self.assertEqual(len(red), 1)
        self.assertIn("no file matched", red[0])

    def test_artifact_not_an_elf(self):
        red = self._red(lambda r: r["artifact"].update(elf=None))
        self.assertEqual(len(red), 1)
        self.assertIn("is not an ELF", red[0])

    def test_artifact_wrong_machine(self):
        red = self._red(lambda r: r["artifact"]["elf"].update(machine=244))
        self.assertEqual(len(red), 1)
        self.assertIn("e_machine=244", red[0])

    def test_artifact_readelf_disagrees(self):
        red = self._red(lambda r: r["artifact"]["readelf"].update(machine="ARM"))
        self.assertEqual(len(red), 1)
        self.assertIn("readelf -h says", red[0])

    def test_artifact_stale(self):
        red = self._red(lambda r: r["artifact"].update(stale=True))
        self.assertEqual(len(red), 1)
        self.assertIn("is older than this case's start", red[0])

    def test_artifact_marker_absent(self):
        red = self._red(lambda r: r["artifact"].update(marker_offset=-1))
        self.assertEqual(len(red), 1)
        self.assertIn("is not in the image in any encoding", red[0])

    def test_resume_confirmation_line_absent(self):
        """R4's criterion: the result word alone is not it -- the frame must carry
        `OK executed <id>`.  A bare `ERR disabled` cannot separate "no usable session"
        from "already running", which is why the failure says exactly that."""
        red = self._red(lambda r: r["load"].update(resume=_disabled(), attempts=3))
        self.assertEqual(len(red), 1)
        self.assertIn("did not run in 3 attempt(s)", red[0])
        self.assertIn("could not certify the target was released", red[0])

    def test_launch_confirmation_line_absent(self):
        red = self._red(lambda r: r["load"].update(launch=_disabled()))
        self.assertEqual(len(red), 1)
        self.assertIn(_LAUNCH_ACTIVE, red[0])
        self.assertIn(case._OK_MARK + _LAUNCH_ACTIVE, red[0])

    def test_a_dialog_line_vetoes_a_confirmation_line(self):
        """Measured on the sibling: `OK executed …Resume` and `dialog=appeared "Run
        Control not available"` arrive in the *same frame* -- the handler ran, the target
        was never released."""
        red = self._red(lambda r: r["load"].update(
            resume=_frame("OK", "OK executed " + _RESUME,
                          'dialog=appeared "Run Control not available"')))
        self.assertEqual(len(red), 1)
        self.assertIn(case._DIALOG_MARK, red[0])

    def test_a_dead_bridge_conversation_is_named(self):
        red = self._red(lambda r: r["load"].update(
            transport_error="cmd.run X -> ConnectionResetError(10054)"))
        self.assertEqual(len(red), 1)
        self.assertIn("the bridge conversation died", red[0])

    def test_a_launchbar_that_retreated_to_run_mode_is_red(self):
        """Fact 6: in `run` mode `launchActive` is accepted with a clean answer and no
        session is ever created, so the confirmation line above cannot be read as a load."""
        red = self._red(lambda r: r["load"]["loadbar"].update(
            modes={"…descriptorType.default\\:gs32f035_openocd": "run"}))
        self.assertEqual(len(red), 1)
        self.assertIn("active mode is `run`", red[0])

    def test_a_launchbar_with_no_descriptor_is_red(self):
        red = self._red(lambda r: r["load"]["loadbar"].update(modes={}))
        self.assertEqual(len(red), 1)
        self.assertIn("names no descriptor", red[0])

    def test_a_launchbar_that_could_not_be_read_is_not_red(self):
        """C14's shape at the judgement layer: "could not tell" is its own answer, and it
        never becomes a failure -- the load's own criterion still stands."""
        result = _green()
        result["load"]["loadbar"].update(modes={}, error="the file was never written")
        passed, detail = case._expect(_Ctx(), result)
        self.assertTrue(passed, detail)

    def test_a_seed_failure_is_named_not_summarised(self):
        red = self._red(lambda r: r["seed"].update(ok=False, error="main.c: x"))
        self.assertEqual(red, ["seed: main.c: x"])

    def test_a_chain_stop_names_every_step_it_did_not_reach(self):
        def mutate(r):
            r["blocked"] = ["build"]
            r["stopped_at"] = "build"
            r["artifact"].update(path="")
            r["load"].update(resume=_disabled())

        red = self._red(mutate)
        self.assertEqual(red, ["artifact: not reached -- the chain stopped at build",
                               "load: not reached -- the chain stopped at build"])


# --------------------------------------------------------------------------- #
# R4's criterion, on the frame itself: the confirmation line, and the dialog veto
# --------------------------------------------------------------------------- #

class RanCriterionTest(unittest.TestCase):
    """The three shapes of a driven command's frame, as this file's own literals."""

    def test_a_confirmation_line_with_no_dialog_is_a_run(self):
        self.assertTrue(case._ran(_frame("OK", "OK executed " + _RESUME), _RESUME))
        self.assertTrue(case._ran(_frame("OK", "OK executed " + _LAUNCH_ACTIVE),
                                  _LAUNCH_ACTIVE))

    def test_the_wrong_command_id_does_not_count(self):
        """A frame that confirms a *different* command is not this command's proof."""
        self.assertFalse(case._ran(_frame("OK", "OK executed " + _RESUME),
                                   _LAUNCH_ACTIVE))
        self.assertFalse(case._ran(_frame("OK", "OK executed  " + _RESUME), _RESUME))

    def test_a_dialog_line_vetoes_even_with_the_confirmation_line(self):
        self.assertFalse(case._ran(
            _frame("OK", "OK executed " + _RESUME,
                   'dialog=appeared "Run Control not available"'), _RESUME))

    def test_a_disabled_answer_never_runs(self):
        self.assertFalse(case._ran(_disabled(), _RESUME))




def _attach(forced):
    with mock.patch.dict(os.environ, {"ECLIPSE_CTL_GS32_BOARD_ATTACH": forced}):
        return case._attach_probe("<root>", "GJBDRPSSA", "GS32F035P")


def _pnp(forced):
    with mock.patch.dict(os.environ, {"ECLIPSE_CTL_GS32_BOARD_PNP": forced}):
        return case._pnp_probe()


class ChannelStateTest(unittest.TestCase):
    """A channel that never ran is its own sentence, and it never speaks for the board."""

    def test_the_four_channel_sentences_are_all_different(self):
        present = _attach("present")["words"]
        absent = _attach("absent")["words"]
        cannot = _attach("cannot")["words"]
        never = _attach("bogus")["words"]
        self.assertEqual(len({present, absent, cannot, never}), 4)
        # The "never ran" pair: the override did not query anything, and says so.
        self.assertIn("never queried the probe", absent)
        self.assertIn("never queried the probe", present)
        self.assertIn("not a recognized value", never)
        self.assertIn("unknown", cannot)

    def test_the_os_channel_says_it_never_queried_the_os(self):
        self.assertIn("never queried the OS", _pnp("absent")["words"])
        self.assertIn("not a recognized value", _pnp("bogus")["words"])

    def test_the_states_the_overrides_produce(self):
        self.assertEqual((_attach("present")["state"], _attach("absent")["state"],
                          _attach("cannot")["state"], _attach("bogus")["state"]),
                         ("present", "absent", "unknown", "unknown"))
        self.assertEqual((_pnp("present")["state"], _pnp("absent")["state"],
                          _pnp("cannot")["state"]), ("present", "absent", "unknown"))

    def _hardware(self, attach, pnp):
        env = {"ECLIPSE_CTL_GS32_BOARD_ATTACH": attach,
               "ECLIPSE_CTL_GS32_BOARD_PNP": pnp}
        with mock.patch.dict(os.environ, env):
            return case._hardware("<root>", "GJBDRPSSA", "GS32F035P")

    def test_only_two_reals_absence_and_neither_is_needed_for_presence(self):
        self.assertEqual(self._hardware("present", "absent")["state"], "present")
        self.assertEqual(self._hardware("absent", "present")["state"], "present")
        self.assertEqual(self._hardware("absent", "absent")["state"], "absent")
        # A channel that could not answer never lets the word "absent" through.
        self.assertEqual(self._hardware("absent", "cannot")["state"], "unknown")
        self.assertEqual(self._hardware("cannot", "cannot")["state"], "unknown")

    def test_the_absent_reason_says_it_is_about_the_queries_not_the_board(self):
        out = self._hardware("absent", "cannot")
        self.assertIn("cannot tell whether the GS32 H1017A board is attached", out["reason"])
        self.assertIn("not about the board", out["reason"])

    def test_the_absent_reason_names_both_channels(self):
        out = self._hardware("absent", "absent")
        self.assertIn("both channels agree", out["reason"])
        self.assertIn("channel A (openocd attach)", out["reason"])
        self.assertIn("channel B (OS device face)", out["reason"])


# --------------------------------------------------------------------------- #
# The OS-device filter: "no output" and "output with no match" must not look alike
# --------------------------------------------------------------------------- #

class PnpFilterTest(unittest.TestCase):
    """C14's sub-shape: a filtered-to-empty channel is not the same as a silent one."""

    def test_matching_lines_are_kept_verbatim(self):
        text = ("USB\\VID_0403&PID_6010&MI_00\\7&2C069F25&0&0000\n"
                "USB\\VID_0403&PID_A6D0&MI_00\\6&1&0\n"
                "USB\\VID_0403&PID_6010\\GJBDRPSS\n")
        self.assertEqual(case._pnp_ids_from_text(text),
                         ["USB\\VID_0403&PID_6010&MI_00\\7&2C069F25&0&0000",
                          "USB\\VID_0403&PID_6010\\GJBDRPSS"])

    def test_no_output_and_no_match_are_both_empty_here(self):
        """Both are `[]` at this level -- which is why the *stream* (not the list) is
        what `_pnp_board_ids` splits on."""
        self.assertEqual(case._pnp_ids_from_text(""), [])
        self.assertEqual(case._pnp_ids_from_text("Get-PnpDevice : warning\n"), [])


# --------------------------------------------------------------------------- #
# The overlay: the anchors, the marker, and the pin mux (PRD AC6(3))
# --------------------------------------------------------------------------- #

class OverlayGateTest(unittest.TestCase):
    """What `_overlay` writes, and what it refuses to call a success."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="eclipse-ctl-gs32-gate-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.project = _template(self.root)

    def _overlay(self, marker="CTL-GS32-review01"):
        ctx = _Ctx()
        out = case._overlay(ctx, self.project, marker)
        return ctx, out

    def _read(self, *parts):
        with open(os.path.join(self.project, *parts), "r", encoding="gbk",
                  newline="") as handle:
            return handle.read()

    def test_the_marker_and_the_mux_land_in_the_patched_source(self):
        """Asserts its own subject only (C12: one mutation, one predicate).  Whether the
        overlay as a whole succeeded is the *next* test's subject."""
        _, out = self._overlay()
        src = self._read("src", "main.c")
        self.assertIn("CTL-GS32-review01", src)
        for needle in _MUX:
            self.assertIn(needle, src)
        self.assertTrue(out["applied"])

    def test_the_led_block_lands_in_the_header(self):
        """Same rule: the header's content, not the overlay's verdict."""
        self._overlay()
        header = self._read("inc", "board_cfg.h")
        self.assertIn("#define BOARD_LED1        GPIO24", header)
        self.assertIn("#define BOARD_LED2        GPIO21", header)

    def test_a_missing_anchor_is_named(self):
        with open(os.path.join(self.project, "src", "main.c"), "w",
                  encoding="gbk", newline="") as handle:
            handle.write(_C_SOURCE.replace("    Device_init();\n", ""))
        _, out = self._overlay()
        self.assertFalse(out["ok"])
        self.assertIn("Device_init();", out["error"])

    def test_deleting_the_pin_mux_is_a_named_failure(self):
        """AC6(3): the case must go red when the mux is gone -- the build, the ELF, the
        marker and the programmer would all still be green without it."""
        edits = tuple((a, r) for (a, r) in case._SOURCE_EDITS
                      if "GPAMUX2.bit.BOARD_LED" not in r)
        with mock.patch.object(case, "_SOURCE_EDITS", edits):
            _, out = self._overlay()
        self.assertFalse(out["ok"])
        for needle in _MUX:
            self.assertIn(needle, out["error"])

    def test_the_chase_lines_land_and_the_toggle_idiom_does_not(self):
        _, out = self._overlay()
        self.assertTrue(out["ok"], out["error"])
        src = self._read("src", "main.c")
        for needle in _CHASE:
            self.assertIn(needle, src)
        self.assertNotIn(_FORBIDDEN, src)

    def _edits_without(self, needle):
        """`_SOURCE_EDITS` with every payload line carrying `needle` dropped."""
        edits = []
        for anchor, replacement in case._SOURCE_EDITS:
            edits.append((anchor, "".join(
                line for line in replacement.splitlines(keepends=True)
                if needle not in line)))
        return tuple(edits)

    def test_dropping_one_chase_line_is_a_named_failure(self):
        """C15 at the payload layer: one of the four complementary writes is gone, so a
        step leaves the other LED where it was -- the both-lit / both-dark states R1
        forbids.  The named missing line is what says so, and it is the *chase* complaint
        (not the mux one)."""
        needle = _CHASE[2]
        with mock.patch.object(case, "_SOURCE_EDITS", self._edits_without(needle)):
            _, out = self._overlay()
        self.assertFalse(out["ok"])
        self.assertIn(needle, out["error"])
        self.assertIn("does not drive the two LED pins complementarily", out["error"])
        self.assertNotIn("pin mux", out["error"])

    def test_the_toggle_idiom_is_a_named_failure(self):
        """The first payload toggled one pin per step -- a four-state cycle whose
        "both lit" quarter is exactly the phenomenon R1 forbids -- while every machine
        predicate stayed green.  `_CHASE_FORBIDDEN` names that shape."""
        edits = tuple(
            (anchor, repl + "\n                    GpioDataRegs." + _FORBIDDEN + "1 = 0x1;")
            if anchor == "GpioDataRegs.GPATOGGLE.bit.GPIO24=0x1;" else (anchor, repl)
            for (anchor, repl) in case._SOURCE_EDITS)
        with mock.patch.object(case, "_SOURCE_EDITS", edits):
            _, out = self._overlay()
        self.assertFalse(out["ok"])
        self.assertIn(_FORBIDDEN, out["error"])
        self.assertIn("toggling one pin per step", out["error"])

    def test_the_mux_must_be_the_whole_statement(self):
        """C15: with a *substring* needle (`GPIO_MUX_DATA(BOARD_LED1_MUX)`) this mutation
        stayed green -- same defect, because GPIO24/GPIO21 are not in `GPAMUX1`'s range,
        so the pins would keep their reset peripheral function and no LED could light."""
        edits = tuple((anchor, repl.replace("GPAMUX2.bit.BOARD_LED",
                                            "GPAMUX1.bit.BOARD_LED"))
                      for (anchor, repl) in case._SOURCE_EDITS)
        with mock.patch.object(case, "_SOURCE_EDITS", edits):
            _, out = self._overlay()
        self.assertFalse(out["ok"])
        self.assertIn("GPAMUX2.bit.BOARD_LED1", out["error"])
        self.assertIn("pin mux", out["error"])

    def test_a_missing_marker_is_a_named_failure(self):
        edits = tuple((anchor, repl.replace('    log_info("@MARKER@\\r\\n");\n', ""))
                      for (anchor, repl) in case._SOURCE_EDITS)
        with mock.patch.object(case, "_SOURCE_EDITS", edits):
            _, out = self._overlay()
        self.assertFalse(out["ok"])
        self.assertIn("run marker", out["error"])


# --------------------------------------------------------------------------- #
# The artifact readers
# --------------------------------------------------------------------------- #

class ArtifactReaderTest(unittest.TestCase):
    """`_elf_header` and `_find_marker` are read from bytes, not from a tool's claim."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="eclipse-ctl-gs32-bytes-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _write(self, blob):
        path = os.path.join(self.root, "a.bin")
        with open(path, "wb") as handle:
            handle.write(blob)
        return path

    def test_the_elf_header_yields_class_endian_and_machine(self):
        blob = bytearray(20)
        blob[:4] = b"\x7fELF"
        blob[4] = 1
        blob[5] = 1
        struct.pack_into("<H", blob, 18, 243)
        self.assertEqual(case._elf_header(self._write(bytes(blob))),
                         {"class": 1, "endian": 1, "machine": 243})

    def test_a_non_elf_is_refused(self):
        self.assertIsNone(case._elf_header(self._write(b"MZ\x90\x00" + b"\x00" * 16)))

    def test_the_marker_is_found_in_each_of_its_three_encodings(self):
        marker = "CTL-GS32-abcd1234"
        for label, blob in (("ascii", b"\x00" * 7 + marker.encode("ascii")),
                            ("u16le", b"\x00" * 7 + marker.encode("utf-16-le")),
                            ("u16be", b"\x00" * 7 + marker.encode("utf-16-be"))):
            offset, found = case._find_marker(blob, marker)
            self.assertEqual((offset, found), (7, label))

    def test_an_absent_marker_is_minus_one_not_zero(self):
        self.assertEqual(case._find_marker(b"nothing here", "CTL-GS32-abcd1234"),
                         (-1, ""))


# --------------------------------------------------------------------------- #
# R2/R3's *executors*, not just their constants (C10/C15).  These drive the two
# steps against the SDK's own template; a machine without that SDK skips them --
# the same shape the case itself uses for "no hardware" (R6).
# --------------------------------------------------------------------------- #

_SDK_TEMPLATE = ("D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2/packages/"
                 "GS32-DSPWare/gs32_examples/gs32f035/template/gs32f035")


class RamConfigAndLaunchSeedTest(unittest.TestCase):
    """`_ram_config` / `_seed_launch` really do what R2/R3 promise.

    Until now only their *constants* were pinned, so a regression inside them (this
    case already hit one there -- the CRLF / `FLASH_TARGET`-drop bug) reached the
    board before anything here noticed.  A directory copy of the vendor's own
    template is the input they are written against, so these rows use exactly that.
    """

    def _copy(self):
        if not os.path.isdir(_SDK_TEMPLATE):
            self.skipTest("no GS32 SDK template at %s" % _SDK_TEMPLATE)
        root = tempfile.mkdtemp(prefix="gs32-gate-")
        self.addCleanup(shutil.rmtree, root, True)
        project = os.path.join(root, "gs32f035")
        shutil.copytree(_SDK_TEMPLATE, project)
        return project

    def test_the_ram_configuration_is_authored_on_a_directory_copy(self):
        """R2: swap the segment and part scripts, keep the register script, drop
        `FLASH_TARGET`, repoint `buildPath` -- and leave the flash configuration
        alone.  Asserted per configuration block, never by whole-file greps."""
        project = self._copy()
        out = case._ram_config(_Ctx(), project, "gs32f035")
        self.assertTrue(out["ok"], out["error"])
        back = case._read_text(os.path.join(project, ".cproject"))
        ram = case._config_block(back, case._CONFIG)
        flash = case._config_block(back, case._FLASH_CONFIG)
        self.assertTrue(ram and flash)
        self.assertIn(case._RAM_SCRIPT, ram)
        self.assertNotIn(case._FLASHILM_SCRIPT, ram)
        self.assertIn(case._MEM_SCRIPT_P, ram)
        self.assertNotIn(case._MEM_SCRIPT, ram)
        self.assertIn(case._REGS_SCRIPT, ram)
        self.assertNotIn(case._FLASH_DEFINE, ram)
        self.assertIn(case._FLASHILM_SCRIPT, flash)
        self.assertIn(case._MEM_SCRIPT, flash)
        self.assertIn(case._FLASH_DEFINE, flash)
        self.assertIn("${workspace_loc:/gs32f035}/%s" % case._CONFIG, back)

    def test_the_seeded_launch_carries_the_four_measured_corrections(self):
        """R3: the two OpenOCD `set` commands, the two reset booleans (the whole
        difference from the factory flash-shaped launch) and the RAM artifact."""
        project = self._copy()
        plan = {"project": project, "workspace": os.path.dirname(project),
                "config": case._CONFIG, "serial": case._SERIAL, "chip": case._CHIP}
        out = case._seed_launch(_Ctx(), plan, "gs32f035")
        self.assertTrue(out["ok"], out["error"])
        self.assertEqual(out["program"], "RAM/gs32f035.elf")
        text = "\n".join(case._read_text(path) for path in out["files"])
        for needle in ("set gs32_cfg_mode 2", "set gs32_model GS32F035P",
                       'doDebugInRam" value="true', 'doSecondReset" value="false'):
            self.assertIn(needle, text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
