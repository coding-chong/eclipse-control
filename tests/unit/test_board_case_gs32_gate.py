"""The GS32 board case's own gate: its verdict, its channel words, its overlay.

Two shapes this file exists for (`deliverable-shape.md`):

* **C10** -- every literal pinned here is *this file's own*: the programmer's success
  line, the pin-mux needles and the three channel-state words are written out below, and
  the case's constants are asserted **equal** to them.  Reading them back
  (`self.assertEqual(case.PROG_SUCCESS, case.PROG_SUCCESS)`) would certify nothing: a
  typo in the constant would keep both sides of the comparison wrong together.
* **C12** -- one mutation per predicate.  `ExpectLedgerTest` reddens exactly the
  predicate it weakens (never a neighbour's), and `ChannelStateTest` gives each of C14's
  four channel states its own wording so they cannot be confused for one another.

Nothing here touches a board, `GS32.exe` or `GS32ProgCommand.exe`.  `_expect` is driven
with synthetic results, `_overlay` with a synthetic two-file template, and the two
hardware channels only through their `ECLIPSE_CTL_GS32_BOARD_*` override seam (which by
construction never spawns anything).
"""

from __future__ import annotations

import os
import shutil
import struct
import tempfile
import unittest
import unittest.mock as mock

from ctl.verify.cases import board_led_chase_gs32 as case

#: The mux datum, as this file's own literal (C10).
_MUX = ("GPIO_MUX_DATA(BOARD_LED1_MUX)", "GPIO_MUX_DATA(BOARD_LED2_MUX)")
#: The programmer's verbatim success line, as this file's own literal (C10).
_SUCCESS = "Programming succeeded for 1 file(s)."


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

    def test_the_success_line_and_states_are_pinned_independently(self):
        self.assertEqual(case._PROG_SUCCESS, _SUCCESS)
        self.assertEqual(tuple(case._MUX_NEEDLES), _MUX)
        self.assertEqual((case._PRESENT, case._ABSENT, case._UNKNOWN),
                         ("present", "absent", "unknown"))

    def test_the_board_facts_and_artifact_identity_are_pinned(self):
        self.assertEqual((case._CHIP, case._SERIAL), ("GS32F035P", "GJBDRPSSA"))
        self.assertEqual(case._IDCODE, "0x1030aa6d")
        self.assertEqual(case._BOARD_HWID, "VID_0403&PID_6010")
        self.assertEqual(case._MARKER_PREFIX, "CTL-GS32-")
        self.assertEqual(case._E_MACHINE_RISCV, 243)


# --------------------------------------------------------------------------- #
# The judgement layer: one mutation per predicate (C12)
# --------------------------------------------------------------------------- #

def _green():
    """A result in which every predicate holds (the values are the measured ones)."""
    return {
        "errors": [],
        "name": "gs32f035", "config": "Flash_ILM", "chip": "GS32F035P",
        "marker": "CTL-GS32-deadbeef", "project": "<p>", "started_at": 1.0,
        "overlay": {"ok": True, "error": "", "applied": [], "missing": []},
        "syntax": {"available": True, "rc": 0, "errors": [], "tail": ""},
        "build": {"rc": 0, "timed_out": False,
                  "summary": "Build Finished. 0 errors, 0 warnings.",
                  "errors": "0", "warnings": "0", "compiler_errors": [],
                  "tail": "", "elapsed": 15.4, "argv": [], "text": "", "native": True},
        "artifact": {"path": "<ws>/Flash_ILM/gs32f035.elf", "pattern": "<glob>",
                     "size": 551060,
                     "sha256": "x", "mtime": 2.0, "stale": False,
                     "elf": {"class": 1, "endian": 1, "machine": 243},
                     "marker_offset": 32864, "marker_encoding": "ascii",
                     "readelf": {"tool": "readelf", "rc": 0, "text": "",
                                 "elf_class": "ELF32", "machine": "RISC-V", "error": ""}},
        "flash": {"rc": 0, "timed_out": False, "text": "", "success": True,
                  "reset_run": True, "tail": "", "argv": [], "elapsed": 2.7},
        "plan": {"hardware": {"attach": {"state": "present"},
                              "pnp": {"state": "present"}, "state": "present",
                              "reason": ""},
                 "killed": []},
        "blocked": [], "stopped_at": None, "flash_skipped": "",
    }


class ExpectLedgerTest(unittest.TestCase):
    """Each row weakens exactly one guard and reddens exactly that guard's predicate."""

    def _red(self, mutate):
        result = _green()
        mutate(result)
        passed, detail = case._expect(_Ctx(), result)
        self.assertFalse(passed, "the mutation left the verdict green: %s" % detail)
        return detail.split(" | FAILED: ")[-1].split("; ")

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

    def test_flash_success_line_absent(self):
        red = self._red(lambda r: r["flash"].update(success=False))
        self.assertEqual(red, ["flash: the log does not carry the verbatim success line "
                               "'%s'" % _SUCCESS])

    def test_flash_rc_nonzero(self):
        red = self._red(lambda r: r["flash"].update(rc=1))
        self.assertEqual(len(red), 1)
        self.assertIn("flash: rc=1 (expected 0)", red[0])

    def test_overlay_failure_is_named_not_summarised(self):
        red = self._red(lambda r: r["overlay"].update(ok=False, error="main.c: x"))
        self.assertEqual(red, ["overlay: main.c: x"])

    def test_a_chain_stop_names_every_step_it_did_not_reach(self):
        def mutate(r):
            r["blocked"] = ["build"]
            r["stopped_at"] = "build"
            r["artifact"].update(path="")
            r["flash"].update(rc=1)

        red = self._red(mutate)
        self.assertEqual(red, ["artifact: not reached -- the chain stopped at build",
                               "flash: not reached -- the chain stopped at build"])


# --------------------------------------------------------------------------- #
# The four channel states (C14): four word-for-word different sentences
# --------------------------------------------------------------------------- #

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
        _, out = self._overlay()
        self.assertTrue(out["ok"], out["error"])
        src = self._read("src", "main.c")
        self.assertIn("CTL-GS32-review01", src)
        for needle in _MUX:
            self.assertIn(needle, src)

    def test_the_led_block_lands_in_the_header(self):
        _, out = self._overlay()
        self.assertTrue(out["ok"], out["error"])
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
