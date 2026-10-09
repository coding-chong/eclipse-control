"""board.led.chase.gs32 -- the GS32 sibling of `board.led_chase`: build OUR payload,
flash it with the vendor's CLI programmer, and let a human confirm two LEDs chase.

What is verified: a scratch copy of the GS32 SDK template project is overlaid with the
board's real LED pins and a two-LED chase payload, built by **GS32_Studio's headless
build** (a plain CLI, no Eclipse command id, no bridge), flashed by the vendor's
`GS32ProgCommand.exe`, and the machine-checkable half of that chain is judged here; the
second half (LED1/LED2 alternating) is printed as an explicit request for a human.

WHY THE JUDGEMENT IS NOT THE CCS12 ONE (the shape is copied, the criteria are not)

`board_led_chase.py` drives *CCS12* through the **bridge** (`launchActive` / `Resume`)
and judges the answers' shape.  Nothing here touches the bridge (`requires_bridge=False`):
the driver surface is two CLIs, so the machine segment is **their rc + their own success
markers + reading the artifact back**:

    build  rc=0 and the CDT summary says 0 errors   (measured: "Build Finished. 0 errors, 0 warnings.")
    elf    readelf -h says ELF32 + RISC-V, and this run's marker is IN the image
    flash  rc=0 and the log says "Programming succeeded for 1 file(s)."

`rc=0` is not "the target is running": the flash log's own `tgt-RESET mode=run.` is
**auxiliary evidence only** (a wrong clock source would leave the payload spinning before
`main()`), which is exactly why the human segment cannot be dropped.

FOUR SCOUT ANSWERS (S0 -- each a measured fact, with the command that produced it)

1. **The build base** -- `gs32_examples/gs32f035/GPIO/gpio_ex2_toggle_regs/` carries only
   project scaffolding (`.cproject`/`.project`/`debugConfigs`/`inc/board_cfg.h`), no
   `src/`; `template/gs32f035/` is the buildable one (`src/main.c` + `inc/board_cfg.h`).
   Both have an **empty** "Configuration of the LED pins" section, so the pins can only
   come from this case (the SDK gives none).
2. **The headless build** -- `GS32.exe -nosplash -application
   org.eclipse.cdt.managedbuilder.core.headlessbuild -data <ws> -import <proj> -build
   "<name>/<config>"`.  `-data`/`-import` **must be native backslash paths**: forward
   slashes are parsed as a URI scheme => `CoreException: No file system is defined for
   scheme: D` (rc=13) *and* a modal error box on the operator's desktop.  Measured
   2026-10-09: rc=13 (forward) vs rc=0 (backslash), log `research/s2*.txt`.
3. **The programmer** -- `GS32ProgCommand.exe -chip GS32F035P -elf <elf>`, measured
   rc=0 with the verbatim last line `Programming succeeded for 1 file(s).`
4. **The board's two channels, both measured in place** (C14: a negative answer needs a
   second, independent channel; the two are *mutually unblocking*, and "did not see" /
   "could not answer" / "the board is not there" are three different sentences):

   * **channel A -- OpenOCD attach** (`gs-openocd.exe ... -c init -c scan_chain
     -c shutdown`, `-c "set gs32_cfg_mode 2"` so the flash path is not entered).  The
     decisive variable is `adapter serial`: `GJBDRPSSA` (FT2232H channel A = JTAG) gives
     `tap/device found: 0x1030aa6d` + `Examined RISC-V core`, rc=0; `GJBDRPSSB` (channel
     B = the UART) gives `all ones` + `Unsupported DTM version: 15`.  D2xx enumerates B
     first, so "take the first device" is wrong; `ftdi vid_pid 0x0403 0x6010` also has to
     be pinned because a TI XDS100v2 (`PID A6D0`) and a CH340 are on the same machine.
   * **channel B -- the OS device face** (`Get-PnpDevice -PresentOnly`, the read-only PnP
     query, whose instance ids carry `VID_0403&PID_6010`), the channel a held handle
     cannot blind.

   Only both-channels-agree-ABSENT allows the word "absent"; a channel that produced no
   output at all is *could-not-tell*, never "absent".

PREREQUISITES -- none of these can be installed by the case:

    * a **GS32_Studio 1.2.5.2** install tree (the target's own `install_dir`;
      override with ``ECLIPSE_CTL_GS32_BOARD_STUDIO``);
    * the **GS32Prog** programmer install carrying `GS32ProgCommand.exe` (and, inside it,
      `openocd/bin/gs-openocd.exe` -- channel A's tool).  It is **derived** from the
      studio root -- an installer of this vendor puts its siblings beside it -- and
      ``ECLIPSE_CTL_GS32_BOARD_PROG`` short-circuits the search;
    * a **GS32F035P / H1017A** board on the desk, its USB (the on-board FT2232H) plugged
      in and **not held by a live debug session**.

Absent any of them the case **SKIPs, never FAILs**, and the verdict names *which channel
said what*.

EVERY SKIP THIS CASE CAN RAISE, so a verdict line is never a mystery

| verdict contains | means | do this |
|---|---|---|
| `skipped: not applicable to target` | wrong `--target` -- this case only runs on `gs32` | `--target gs32` |
| `no GS32_Studio install tree` | the target has no `install_dir` (or it is not there) | `ctl targets add gs32 --source-dir <...>` |
| `no SDK template project` | the install tree does not carry the example | check ``…BOARD_TEMPLATE`` |
| `no GS32Prog install carrying` | the programmer was not found beside the studio root | set ``ECLIPSE_CTL_GS32_BOARD_PROG`` |
| `no GS32 H1017A board … both channels agree the board is ABSENT` | neither channel sees the board | plug the board's USB in |
| `cannot tell whether the GS32 H1017A board is attached` | at least one channel could not be read (or they disagree) -- **not** a statement about the board | read the named channel |

RERUN (from the repo root; ~40-60 s here, most of it the build):

    python -m ctl verify --case board.led.chase.gs32 --target gs32

Read the verdict line, not `rc`: a SKIP also exits ``0`` (`--json` carries
`passed`/`skipped`).  The three detection states can be exercised with no board at all:

    ECLIPSE_CTL_GS32_BOARD_ATTACH=absent ECLIPSE_CTL_GS32_BOARD_PNP=absent …
    ECLIPSE_CTL_GS32_BOARD_ATTACH=absent ECLIPSE_CTL_GS32_BOARD_PNP=cannot …
    ECLIPSE_CTL_GS32_BOARD_ATTACH=present …
"""

from __future__ import annotations

import glob
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..runner import Case, Skip
from ._util import verdict

# --------------------------------------------------------------------------- #
# Recipe -- the board facts are constants with an environment seam, mirroring
# `board_led_chase.py`'s `ECLIPSE_CTL_BOARD_<KEY>` pattern (here
# `ECLIPSE_CTL_GS32_BOARD_<KEY>`), so the case can be pointed at another install,
# another programmer or another board's probe without editing this file.
# --------------------------------------------------------------------------- #

ENV_PREFIX = "ECLIPSE_CTL_"
_BOARD_ENV = ENV_PREFIX + "GS32_BOARD_"

#: The build configuration the SDK template declares (`parent=
#: "com.hpec.toolchains.riscv.config.elf.debug.flash"`), i.e. the name the headless
#: build is asked for: `-build "<project>/Flash_ILM"`.
_CONFIG = "Flash_ILM"

#: The project name the SDK template's `.project` declares, and the one the artifact is
#: named after (`artifactName="${ProjName}"` => `<project>.elf`).  The name that is
#: actually *used* is read back from the copied `.project` (ground truth); this constant
#: is the expectation, and `ECLIPSE_CTL_GS32_BOARD_PROJECT` overrides the expectation.
_PROJECT = "gs32f035"

#: The board's part number, as the programmer and the OpenOCD model both want it.
#: `gs32_model`'s default is `GS32F0025` (`gs32_dsp_v3.0.cfg`), which is *not* this
#: board -- so it is always passed explicitly.
_CHIP = "GS32F035P"

#: The ruling out of the other JTAG channel.  `D2xx device count: 4` on this machine is
#: two FTDI devices x two channels, and B enumerates first; the A/B measured 2026-10-09
#: is "same command line, only this suffix changed" (`GJBDRPSSA` -> idcode,
#: `GJBDRPSSB` -> `all ones`).
_SERIAL = "GJBDRPSSA"

#: The SDK template project, relative to the GS32_Studio install root.  This is the
#: buildable example (a `src/main.c` exists); the `GPIO/gpio_ex2_toggle_regs/` example is
#: scaffolding only.  Override the whole path with ``…BOARD_TEMPLATE``.
_TEMPLATE_REL = ("packages/GS32-DSPWare/gs32_examples/gs32f035/template/gs32f035")

#: The launcher and the application id, verbatim from the measured rerun.  The plugin
#: that *declares* this id is `org.eclipse.cdt.managedbuilder.headlessbuilderapp_*.jar`
#: (its `plugin.xml` has `point="org.eclipse.core.runtime.applications"`), **not** the
#: same-named `...managedbuilder.core` bundle.
_LAUNCHER = "GS32.exe"
_APP = "org.eclipse.cdt.managedbuilder.core.headlessbuild"

#: Where the RISC-V toolchain sits under an install root.  The `toolchain/*/bin` glob is
#: used so a differently-versioned tree still resolves.
_TOOLCHAIN_GLOB = "toolchain/*/bin"
_COMPILER = "gs-riscv-elf-gcc.exe"
_READELF = "gs-riscv-elf-readelf.exe"

#: The compiler flags the project's own build uses (harvested from a real build log,
#: `research/s2b-build-2026-10-09.txt` line 16).  Needed because the GS dialect flags
#: are not the stock RISC-V ones, and the syntax pre-check has to reproduce the build's
#: own language.
_ARCH_FLAGS = ("-march=rv32imafc_xgsdida", "-mabi=ilp32f", "-msmall-data-limit=8",
               "-mno-save-restore", "--gsdi_ext1p2h", "-mgs_aux")

#: The programmer CLI and its success line.  Measured 2026-10-09 (verbatim, rc=0):
#: `target partnumber: GS32F035PPN` / `partnumber check finished.` /
#: `wrote 32768 bytes …` / `verified 21312 bytes …` / `tgt-RESET mode=run.` /
#: **`Programming succeeded for 1 file(s).`**
_PROG_CMD = "GS32ProgCommand.exe"
_PROG_SUCCESS = "Programming succeeded for 1 file(s)."

#: The flash log's release line.  **Auxiliary evidence, never a criterion**: the one
#: thing it proves is that the programmer asked for a run, not that the payload reached
#: `main()`.  A payload whose clock source is wrong spins before `main()` while this
#: line is still printed.
_PROG_RUN = "tgt-RESET mode=run."

#: Where the vendor's programmer install lives, **relative to the studio install**: the
#: GS32_Studio root measured on this machine is `<parent>/<product>/<product>`
#: (`…\GS32_Studio_v1.2.5.2\GS32_Studio_v1.2.5.2`) and the GS32Prog install sits *beside*
#: it (`…\GS32Prog V1.1.5\GS32Prog V1.1.5`) -- the same "sits beside the target" shape
#: `board_led_chase.py`'s `_c2000ware_candidates` uses for C2000Ware.  The full measured
#: path is deliberately **not** a constant here: `ctl/__main__.py`'s
#: `_machine_path_check` gates this directory against embedded machine-local paths, and a
#: fresh machine must be able to point the case elsewhere with one variable instead of
#: editing the source.  ``ECLIPSE_CTL_GS32_BOARD_PROG`` wins outright.
_PROG_ROOT_GLOB = "*GS32Prog*/*GS32Prog*"

#: OpenOCD (channel A) lives inside the programmer install.  The scripts directory is
#: passed with `-s`; the config file is named explicitly.
_OCD_EXE_REL = os.path.join("openocd", "bin", "gs-openocd.exe")
_OCD_SCRIPTS_REL = os.path.join("openocd", "scripts")
_OCD_CFG = "cs30_ftdi_dsp.cfg"

#: The tap idcode the board's RISC-V core answers with, measured 2026-10-09 both through
#: `gs-openocd.exe` and through the programmer's own tap table
#: (`0 GS32F00xx.dsp Y 0x1030aa6d 0x1030aa6d 5 0x01 0x1f`).  A different board/chip
#: would answer a different id, so this is the *board*'s fingerprint, not a generic
#: "something answered".
_IDCODE = "0x1030aa6d"

#: The hardware id Windows binds the board's FT2232H to (channel B, the unblocking one).
#: Measured 2026-10-09: `USB\VID_0403&PID_6010\GJBDRPSS`, `…&MI_00\…`, `…&MI_01\…`, and
#: two `Ports` nodes `FTDIBUS\VID_0403+PID_6010+GJBDRPSS{A,B}\0000`.  The needle is the
#: VID/PID pair and not the serial, because the serial is the *channel* selector above.
_BOARD_HWID = "VID_0403&PID_6010"

#: The read-only PnP presence query.  Through PowerShell, matching the repo's own
#: convention for Windows-native read-only queries (`ctl/lifecycle.py`'s `_pwsh`, whose
#: user is `list_processes`).  `-match` is a regex and `&` is a literal there.
_PNP_QUERY = ("Get-PnpDevice -PresentOnly | "
              "Where-Object { $_.InstanceId -match '%s' } | "
              "Select-Object -ExpandProperty InstanceId" % _BOARD_HWID)

#: The three channel states (C14).  Words, not booleans: `_channel_words` builds a
#: sentence per channel from these, so a verdict can never confuse "not there" with
#: "could not tell".
_PRESENT = "present"
_ABSENT = "absent"
_UNKNOWN = "unknown"

#: Timeouts (seconds).  The measured costs are named so a budget can be read as a budget:
#: a headless build here took ~9.4 s warm / ~24 s cold, the flash ~2.1 s, the OpenOCD
#: attach ~0.7 s, the PnP query ~1.0-1.2 s.
_BUILD_TIMEOUT = 900.0
_FLASH_TIMEOUT = 300.0
_ATTACH_TIMEOUT = 60.0
_PNP_TIMEOUT = 60.0
_SYNTAX_TIMEOUT = 120.0

#: The run marker: `CTL-GS32-<8 hex>`, printed by the payload through `log_info` so it
#: lands in `.rodata` of *this run's* image.  The artefact is only acceptable if the
#: marker is found inside it -- a stale ELF from the previous run has the previous marker.
_MARKER_PREFIX = "CTL-GS32-"

#: The ELF identity the artifact must declare: `EM_RISCV`, 32-bit.  `readelf`'s own
#: spelling is checked too (below), so an unexpected readelf format is visible rather
#: than silently passing.
_E_MACHINE_RISCV = 243

# --------------------------------------------------------------------------- #
# Overlay fragments (the two files this case owns -- everything else is the SDK's)
# --------------------------------------------------------------------------- #

#: The already-empty LED section of `inc/board_cfg.h`, verbatim as the SDK ships it.
#: The replacement is asserted to hit exactly once, so an SDK that reworded it is a
#: named failure instead of a silently un-pinned build.
_LED_ANCHOR = "/**\n  * @brief Configuration of the LED pins\n  */\n"

#: The board truth, from `docs/gs32/H1017A-GS32F035P-原理图-资源与连接.md` (pins:
#: LED1 = RUN1 = GPIO24 = U4 pin 80; LED2 = ERR1 = GPIO21 = U4 pin 79; both **active
#: low** -- anode to `+3.3V` through 2.2K, GPIO pulled low = lit).  The file is GBK.
_LED_BLOCK = """\
/* H1017A 板上真值（docs/gs32/H1017A-GS32F035P-原理图-资源与连接.md 3.1 / 4 节）:
 *   +3.3V 阳极 -> 2.2K 限流 -> GPIO, GPIO 拉低点亮（低有效）
 *   LED1 = RUN1 : U4 pin 80 = GPIO24
 *   LED2 = ERR1 : U4 pin 79 = GPIO21
 */
#define BOARD_LED1        GPIO24
#define BOARD_LED1_MUX    GPIO_24_GPIO24
#define BOARD_LED2        GPIO21
#define BOARD_LED2_MUX    GPIO_21_GPIO21

"""

#: `src/main.c` edits, each as an (anchor, replacement) pair asserted to hit once.
#: `None` in `_SOURCE_EDITS`'s third slot means "the replacement needs the run marker".
_SOURCE_EDITS: Tuple[Tuple[str, str], ...] = (
    ('#include "log.h"\n',
     '#include "log.h"\n#include "board_cfg.h"\n'),

    ("    Device_init();\n",
     "    Device_init();\n"
     "\n"
     "    /* LED1 = RUN1 (U4 pin 80) / LED2 = ERR1 (U4 pin 79): GPIO output, low = lit */\n"
     "    GpioCtrlRegs.GPAMUX2.bit.BOARD_LED1 = GPIO_MUX_DATA(BOARD_LED1_MUX);\n"
     "    GpioCtrlRegs.GPADIR.bit.BOARD_LED1  = 0x1;\n"
     "    GpioCtrlRegs.GPAMUX2.bit.BOARD_LED2 = GPIO_MUX_DATA(BOARD_LED2_MUX);\n"
     "    GpioCtrlRegs.GPADIR.bit.BOARD_LED2  = 0x1;\n"
     "    GpioDataRegs.GPASET.bit.BOARD_LED1  = 0x1;   /* high = off (active low) */\n"
     "    GpioDataRegs.GPASET.bit.BOARD_LED2  = 0x1;\n"),

    ('    log_info("Hello DSP template!\\r\\n");\n',
     '    log_info("Hello DSP template!\\r\\n");\n'
     '    log_info("@MARKER@\\r\\n");\n'),

    ("if ((tickCnt % 50) == 0) {",
     "if ((tickCnt % 25) == 0) {   /* 25 x 10 ms = 250 ms per chase step */"),

    ("GpioDataRegs.GPATOGGLE.bit.GPIO24=0x1;",
     "if (((tickCnt / 25) & 1) == 1) {\n"
     "                    GpioDataRegs.GPATOGGLE.bit.BOARD_LED1 = 0x1;\n"
     "                } else {\n"
     "                    GpioDataRegs.GPATOGGLE.bit.BOARD_LED2 = 0x1;\n"
     "                }"),

    ('log_info("ticks: %d\\r\\n", dspTicks);',
     'log_info("gs32 chase step %d\\r\\n", tickCnt / 25);'),
)

#: The pin mux the patched payload must end up carrying -- the *datum* that turns the
#: two pins into GPIO outputs instead of whatever their reset peripheral function is.
#: Spelled independently of `_SOURCE_EDITS` on purpose: a maintainer who drops the mux
#: from the edits while leaving this literal alone gets a **named** failure instead of a
#: silently un-muxed build whose LEDs stay dark while every machine-checkable link is
#: green (PRD AC6(3): "delete the LED pin mux" must go red).
_MUX_NEEDLES = ("GPIO_MUX_DATA(BOARD_LED1_MUX)", "GPIO_MUX_DATA(BOARD_LED2_MUX)")

#: The chase's own paragraph, kept next to the edits so the shape is readable in one
#: place: each step toggles **exactly one** of the two pins, alternately.  With two
#: active-low LEDs that is a four-state cycle (LED1 -> both -> LED2 -> neither), i.e.
#: each LED is lit for 500 ms out of every 1000 ms with the two offset by 250 ms -- a
#: strict one-at-a-time alternation is **impossible** with single-bit toggles, because
#: toggling one bit of a two-bit field necessarily flips whether the two are equal.
_CHASE_COMMENT = """\
/* two-LED chase, 250 ms per step (the CPUTimer0 tick is 10 ms): each step toggles
 * exactly one pin, alternately, so the lit focus walks LED1 -> both -> LED2 -> none.
 */"""

# --------------------------------------------------------------------------- #
# Small helpers (shapes copied from `board_led_chase.py`, which measured them)
# --------------------------------------------------------------------------- #

def _override(key: str) -> Optional[str]:
    """``ECLIPSE_CTL_GS32_BOARD_<KEY>`` -- a non-empty override, or ``None``."""
    raw = os.environ.get(_BOARD_ENV + key.upper())
    return raw if raw else None


def _decode(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return raw.decode("utf-8", errors="replace")


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _read_gbk(path: str) -> str:
    """The SDK's C sources are **GBK**; read them as such or they come back mangled."""
    with open(path, "r", encoding="gbk", newline="") as handle:
        return handle.read()


def _write_gbk(path: str, text: str) -> None:
    """Write GBK with LF newlines -- the encoding the rest of the project reads."""
    with open(path, "w", encoding="gbk", newline="") as handle:
        handle.write(text)


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _elf_header(path: str) -> Optional[Dict[str, int]]:
    """``{class, endian, machine}`` off the first 20 bytes, or ``None``."""
    with open(path, "rb") as handle:
        head = handle.read(20)
    if len(head) < 20 or head[:4] != b"\x7fELF":
        return None
    return {"class": head[4], "endian": head[5],
            "machine": struct.unpack_from("<H", head, 18)[0]}


def _marker_variants(marker: str) -> List[Tuple[str, bytes]]:
    """The marker's byte forms.  RISC-V's ``char`` is 8 bit (unlike C2000's), but the
    16-bit forms are kept so the search shape is the same as the sibling case's."""
    return (("ascii", marker.encode("ascii")),
            ("u16le", marker.encode("utf-16-le")),
            ("u16be", marker.encode("utf-16-be")))


def _find_marker(blob: bytes, marker: str) -> Tuple[int, str]:
    """``(offset, encoding)`` of the first marker form found, else ``(-1, "")``."""
    for label, needle in _marker_variants(marker):
        offset = blob.find(needle)
        if offset >= 0:
            return offset, label
    return -1, ""


def _kill_tree(pid: int) -> str:
    """Kill a timed-out child and its children; returns a one-line note."""
    try:
        done = subprocess.run(["taskkill", "/F", "/T", "/PID", str(int(pid))],
                              capture_output=True, timeout=30)
        text = (_decode(done.stdout) + _decode(done.stderr)).strip().replace("\n", " ")
        return "taskkill /F /T /PID %d rc=%d %s" % (pid, done.returncode, text[:200])
    except Exception as exc:  # noqa: BLE001 - cleanup must never raise
        return "taskkill failed: %r" % exc


def _run_capture(argv: List[str], timeout: float,
                 cwd: Optional[str] = None) -> Dict[str, Any]:
    """Run one CLI, capture merged stdout, never orphan it."""
    flags: Dict[str, Any] = {}
    if sys.platform == "win32":
        flags["creationflags"] = 0x08000000          # CREATE_NO_WINDOW
    started = time.monotonic()
    try:
        proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, **flags)
    except OSError as exc:
        return {"rc": None, "timed_out": False, "text": "spawn failed: %r" % exc,
                "elapsed": 0.0, "killed": None, "argv": list(argv)}
    try:
        out, _ = proc.communicate(timeout=timeout)
        return {"rc": proc.returncode, "timed_out": False, "text": _decode(out),
                "elapsed": time.monotonic() - started, "killed": None,
                "argv": list(argv)}
    except subprocess.TimeoutExpired:
        killed = _kill_tree(proc.pid)
        try:
            out, _ = proc.communicate(timeout=15)
        except Exception:  # noqa: BLE001
            out = b""
        return {"rc": proc.returncode, "timed_out": True, "text": _decode(out),
                "elapsed": time.monotonic() - started, "killed": killed,
                "argv": list(argv)}


def _tail(text: str, lines: int = 20) -> str:
    return "\n".join((text or "").splitlines()[-lines:])


def _native(path: str) -> str:
    """A path the Eclipse EFS will read as a *path* and not as a URI.

    Measured 2026-10-09: `-data D:/x` / `-import D:/y` are parsed as a URI scheme and the
    launcher dies with `No file system is defined for scheme: D` (rc=13) *and* pops a
    modal error box on the desktop.  `os.path.abspath`/`normpath` produce native
    separators on Windows; this function is the one place that is asserted.
    """
    return os.path.abspath(os.path.normpath(path))


def _insert_once(text: str, anchor: str, replacement: str) -> Tuple[str, int]:
    """Replace `anchor` (a **literal** string -- never a regex, so the C source's own
    ``\\r\\n`` and ``%d`` cannot be re-interpreted) and report how many times it hit.

    Deliberately not `re.sub`: its *replacement* argument interprets backslash escapes,
    which is how a real CR/LF once landed inside a C string literal and turned a build
    into `error: unterminated argument list invoking macro "log_info"`.
    """
    return text.replace(anchor, replacement), text.count(anchor)


# --------------------------------------------------------------------------- #
# Channel A -- the OpenOCD attach (the JTAG tap answers, or it does not)
# --------------------------------------------------------------------------- #

def _attach_probe(prog_root: str, serial: str, chip: str) -> Dict[str, Any]:
    """Ask the board's JTAG tap to identify itself, and report three-valued.

    ``state`` is one of `_PRESENT` / `_ABSENT` / `_UNKNOWN`, and the last one is its own
    sentence: the tool being missing, the spawn failing, a timeout, or an answer with no
    output at all are **not** "the board is not there" (C14's fourth state).

    ``ECLIPSE_CTL_GS32_BOARD_ATTACH=present|absent|cannot`` forces the state; an override
    never queried the probe, so it says so in its own terms.
    """
    override = (_override("attach") or "").strip().lower()
    forced = {"present": _PRESENT, "absent": _ABSENT, "cannot": _UNKNOWN}.get(override)
    if override and forced is None:
        return {"state": _UNKNOWN, "source": "override", "rc": None, "idcode": False,
                "argv": [], "text": "",
                "words": "%sATTACH=%r is not a recognized value (use present|absent|cannot)"
                         % (_BOARD_ENV, override)}
    if forced is not None:
        return {"state": forced, "source": "override", "rc": None, "idcode": False,
                "argv": [], "text": "",
                "words": "the %sATTACH override says %r -- it never queried the probe"
                         % (_BOARD_ENV, forced)}

    exe = os.path.join(prog_root, _OCD_EXE_REL)
    scripts = os.path.join(prog_root, _OCD_SCRIPTS_REL)
    cfg = os.path.join(scripts, _OCD_CFG)
    out: Dict[str, Any] = {"state": _UNKNOWN, "source": "openocd", "rc": None,
                           "idcode": False, "argv": [], "text": "", "words": ""}
    if not os.path.isfile(exe):
        out["words"] = ("the OpenOCD attach tool did not run: no %s under %s"
                        % (_OCD_EXE_REL, prog_root))
        return out
    argv = [exe, "-s", scripts,
            "-c", "set gs32_adapter_serial " + serial,
            "-c", "set gs32_cfg_mode 2",
            "-c", "set cJTAG 0",
            "-c", "set gs32_model " + chip,
            "-f", cfg,
            "-c", "init", "-c", "scan_chain", "-c", "shutdown"]
    out["argv"] = argv
    run = _run_capture(argv, _ATTACH_TIMEOUT, cwd=scripts)
    out["rc"] = run["rc"]
    out["text"] = str(run["text"])
    out["idcode"] = _IDCODE in out["text"]
    if run["killed"]:
        out["words"] = ("the OpenOCD attach tool did not answer: killed after %.0fs"
                        % _ATTACH_TIMEOUT)
    elif run["rc"] is None:
        out["words"] = "the OpenOCD attach tool did not run: %s" % _tail(out["text"], 1)
    elif not out["text"].strip():
        out["words"] = ("the OpenOCD attach tool ran (rc=%s) and produced no output at "
                        "all, so it says nothing about the board" % run["rc"])
    elif run["rc"] == 0 and out["idcode"]:
        out["state"] = _PRESENT
        out["words"] = ("the OpenOCD attach found tap idcode %s and examined the RISC-V "
                        "core (rc=0, adapter serial %s)" % (_IDCODE, serial))
    else:
        # It ran and produced text but never named the tap.  That is a *negative* from
        # this channel -- `_hardware` is what may (or may not) turn it into the word
        # "absent", and only with the second channel agreeing.
        out["state"] = _ABSENT
        out["words"] = ("the OpenOCD attach ran (rc=%s, adapter serial %s) and found no "
                        "tap idcode %s; last lines: %s"
                        % (run["rc"], serial, _IDCODE,
                           "; ".join(_tail(out["text"], 3).splitlines())))
    return out


# --------------------------------------------------------------------------- #
# Channel B -- the OS device face (a held handle cannot blind it)
# --------------------------------------------------------------------------- #

def _pnp_ids_from_text(text: str) -> List[str]:
    """The hardware ids one PnP answer names: one per line, blanks and noise dropped."""
    ids: List[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line and _BOARD_HWID.lower() in line.lower():
            ids.append(line)
    return ids


def _pnp_board_ids() -> Tuple[List[str], str]:
    """``([hardware ids], "")`` or ``([], error)`` -- never a guess (fail closed).

    A *blank* stream is the answer "no such device" (measured for this query shape: a
    needle matching nothing writes 0 bytes on both streams, rc=0), so a non-empty stream
    that names no matching id is **not** an answer -- it is a warning the command
    swallowed, and it must not read as "absent".
    """
    exe = shutil.which("pwsh") or shutil.which("powershell")
    if not exe:
        return [], "no PowerShell on PATH (pwsh or powershell)"
    done = _run_capture([exe, "-NoProfile", "-NonInteractive", "-Command", _PNP_QUERY],
                        timeout=_PNP_TIMEOUT)
    if done["killed"]:
        return [], "the PnP query was killed after %ss" % _PNP_TIMEOUT
    if done["rc"] != 0:
        return [], "the PnP query rc=%s: %s" % (done["rc"], _tail(str(done["text"]), 3))
    ids = _pnp_ids_from_text(str(done["text"]))
    if not ids and str(done["text"]).strip():
        return [], ("the PnP query answered rc=0 but named no %r hardware id; the stream "
                    "carried: %s" % (_BOARD_HWID, _tail(str(done["text"]), 3)))
    return ids, ""


def _pnp_probe() -> Dict[str, Any]:
    """Does the OS see the board's FT2232H?  Three-valued, same shape as channel A."""
    override = (_override("pnp") or "").strip().lower()
    forced = {"present": _PRESENT, "absent": _ABSENT, "cannot": _UNKNOWN}.get(override)
    if override and forced is None:
        return {"state": _UNKNOWN, "source": "override", "ids": [],
                "words": "%sPNP=%r is not a recognized value (use present|absent|cannot)"
                         % (_BOARD_ENV, override)}
    if forced is not None:
        return {"state": forced, "source": "override", "ids": [],
                "words": "the %sPNP override says %r -- it never queried the OS"
                         % (_BOARD_ENV, forced)}

    ids, error = _pnp_board_ids()
    if error:
        return {"state": _UNKNOWN, "source": "pnp", "ids": [],
                "words": "the OS presence query (Get-PnpDevice) did not answer: %s" % error}
    if ids:
        return {"state": _PRESENT, "source": "pnp", "ids": ids,
                "words": ("the OS presence query (Get-PnpDevice) reports %d present "
                          "device(s) whose hardware id contains %r, first %r"
                          % (len(ids), _BOARD_HWID, ids[0]))}
    return {"state": _ABSENT, "source": "pnp", "ids": [],
            "words": ("the OS presence query (Get-PnpDevice) reports no present device "
                      "whose hardware id contains %r" % _BOARD_HWID)}


# --------------------------------------------------------------------------- #
# The two channels, combined (C14: "absent" needs both, and a channel that never
# ran is its own sentence)
# --------------------------------------------------------------------------- #

def _hardware(prog_root: str, serial: str, chip: str) -> Dict[str, Any]:
    """``{"state": present|absent|unknown, "attach": …, "pnp": …, "reason": …}``.

    The combination is deliberately asymmetric and matches C14:

    * **both present** -- and a positive from either is self-supporting, so the attach
      channel's positive short-circuits.  Nothing conclusive needs a second channel to
      back a *positive* finding;
    * **both absent** -- and only then may the word "absent" be used (the two channels
      are mutually unblocking: channel A is blinded by nothing but a broken JTAG path,
      channel B by nothing at all);
    * **anything else** -- two different states is not evidence of absence any more than
      one unreadable channel is: the verdict is *could-not-tell*, and each channel is
      quoted in its own words.
    """
    attach = _attach_probe(prog_root, serial, chip)
    pnp = _pnp_probe()
    out: Dict[str, Any] = {"attach": attach, "pnp": pnp, "state": _UNKNOWN,
                           "reason": ""}
    if attach["state"] == _PRESENT or pnp["state"] == _PRESENT:
        out["state"] = _PRESENT
        out["reason"] = ("board present -- channel A (openocd attach): %s; channel B "
                         "(OS device face): %s" % (attach["words"], pnp["words"]))
    elif attach["state"] == _ABSENT and pnp["state"] == _ABSENT:
        out["state"] = _ABSENT
        out["reason"] = (
            "no GS32 H1017A board: both channels agree the board is ABSENT -- channel A "
            "(openocd attach): %s; channel B (OS device face): %s.  Plug the board's USB "
            "(the on-board FT2232H) into this machine and retry" % (attach["words"],
                                                                    pnp["words"]))
    else:
        out["state"] = _UNKNOWN
        out["reason"] = (
            "cannot tell whether the GS32 H1017A board is attached -- this is a statement "
            "about the two queries, not about the board.  channel A (openocd attach): %s; "
            "channel B (OS device face): %s" % (attach["words"], pnp["words"]))
    return out


# --------------------------------------------------------------------------- #
# Plan (`pre`) -- the scratch copy of the SDK template, then the two channels
# --------------------------------------------------------------------------- #

def _scratch_root(ctx) -> str:
    """A per-run scratch root under the OS temp dir (PRD R9: never a user project).

    One directory per invocation, so two concurrent runs cannot collide on the shared
    workspace or on the artifact the flash step reads.  ``ctx.run_id`` is borrowed **only
    as a readable name prefix** -- this case never reads or writes a run directory (no
    bridge, no ``--run-id``); uniqueness comes from the uuid suffix, so a run id that is
    days old is only a label.
    """
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", str(ctx.run_id or "adhoc"))
    return os.path.join(tempfile.gettempdir(), "eclipse-ctl-gs32",
                        "%s-%s" % (safe, uuid.uuid4().hex[:6]))


def _studio_root(ctx) -> str:
    override = _override("studio")
    if override:
        return _native(override)
    return _native((getattr(ctx.target, "install_dir", "") or "").strip())


def _toolchain_tool(studio: str, name: str) -> str:
    """``<studio>/toolchain/<ver>/bin/<name>`` -- the first hit of the version glob."""
    override = _override("tool_" + os.path.splitext(name)[0].replace("gs-riscv-elf-", ""))
    if override:
        return override
    hits = sorted(glob.glob(os.path.join(studio, _TOOLCHAIN_GLOB, name)))
    return hits[-1] if hits else os.path.join(studio, _TOOLCHAIN_GLOB, name)


def _prog_root(ctx) -> str:
    """The GS32Prog install carrying `GS32ProgCommand.exe`, derived from the target.

    Two bases are tried, both **relative to the studio root the target already
    resolved** -- the parent of the studio root (where an installer of this vendor puts
    its siblings) and the studio root itself -- so nothing here is a machine-local
    literal; ``ECLIPSE_CTL_GS32_BOARD_PROG`` short-circuits the search.  Returns ``""``
    when nothing is found; `_pre` turns that into its own sentence.
    """
    override = _override("prog")
    if override:
        return _native(override)
    studio = _studio_root(ctx)
    out: List[str] = []
    for base in (os.path.dirname(os.path.dirname(studio)), os.path.dirname(studio)):
        if not base or not os.path.isdir(base):
            continue
        for hit in sorted(glob.glob(os.path.join(base, _PROG_ROOT_GLOB))):
            if (os.path.isfile(os.path.join(hit, _PROG_CMD))
                    and os.path.normpath(hit) not in out):
                out.append(os.path.normpath(hit))
    return out[0] if out else ""


def _prog_candidates_text(ctx) -> str:
    """What the programmer search actually looked at, for the verdict line."""
    studio = _studio_root(ctx)
    bases = [base for base in (os.path.dirname(os.path.dirname(studio)),
                               os.path.dirname(studio)) if base]
    return ", ".join(os.path.join(base, _PROG_ROOT_GLOB) for base in bases) or "<none>"


def _template_dir(ctx, studio: str) -> str:
    return _native(_override("template") or os.path.join(studio, _TEMPLATE_REL))


def _project_name(project_dir: str) -> Optional[str]:
    """The name the copied template's own `.project` declares (ground truth)."""
    path = os.path.join(project_dir, ".project")
    if not os.path.isfile(path):
        return None
    match = re.search(r"<name>([^<]*)</name>", _read_text(path))
    return match.group(1) if match else None


def _pre(ctx):
    plan: Dict[str, Any] = {"errors": [], "killed": []}
    ctx.board_plan = plan

    studio = _studio_root(ctx)
    plan["studio"] = studio
    if not studio or not os.path.isdir(studio):
        raise Skip("no GS32_Studio install tree: the target's install_dir is %r and it "
                   "is not a directory; set %sSTUDIO=<the GS32_Studio root>"
                   % (studio, _BOARD_ENV))

    template = _template_dir(ctx, studio)
    plan["template"] = template
    if not os.path.isfile(os.path.join(template, ".project")):
        raise Skip("no SDK template project at %s (no .project): the GS32_Studio tree "
                   "does not carry %s; set %sTEMPLATE=<the template project dir>"
                   % (template, _TEMPLATE_REL, _BOARD_ENV))

    chip = _override("chip") or _CHIP
    config = _override("config") or _CONFIG
    serial = _override("serial") or _SERIAL
    prog = _prog_root(ctx)
    if not prog:
        # A prerequisite sentence of its own -- never phrased as a statement about the
        # board: channel A lives inside this install, so a missing programmer would
        # otherwise hide behind "the attach channel did not run".
        raise Skip("no GS32Prog install carrying %s: the search (derived from the "
                   "studio root %s) looked at %s; set %sPROG=<the GS32Prog root>"
                   % (_PROG_CMD, studio, _prog_candidates_text(ctx), _BOARD_ENV))
    plan.update({"chip": chip, "config": config, "serial": serial, "prog": prog})

    scratch = _scratch_root(ctx)
    ws = os.path.join(scratch, "ws")
    name = _project_name(template) or _PROJECT
    project = os.path.join(scratch, "proj", name)
    plan.update({"scratch": scratch, "workspace": ws, "project": project,
                 "project_name": name})
    os.makedirs(os.path.join(scratch, "proj"), exist_ok=True)
    os.makedirs(ws, exist_ok=True)
    shutil.copytree(template, project)
    expected = _override("project") or _PROJECT
    if name != expected:
        plan["errors"].append(
            "project read-back: the SDK template's .project declares %r, expected %r -- "
            "this case builds the template as shipped (the ELF is named after it), so a "
            "renamed example is a wrong input, not a wrong expectation"
            % (name, expected))
    ctx.note("pre: studio=%s template=%s scratch=%s project=%s (name read back from "
             ".project) config=%s chip=%s prog=%s"
             % (studio, template, scratch, project, config, chip, prog))

    hardware = _hardware(prog, serial, chip)
    plan["hardware"] = hardware
    attach, pnp = hardware["attach"], hardware["pnp"]
    ctx.note("pre: channel A (openocd attach) state=%s source=%s rc=%s idcode=%s -- %s"
             % (attach["state"], attach["source"], attach.get("rc"),
                attach.get("idcode"), attach["words"]))
    ctx.note("pre: channel B (OS device face) state=%s source=%s ids=%s -- %s"
             % (pnp["state"], pnp["source"], pnp.get("ids") or "<none>", pnp["words"]))
    if attach.get("text"):
        for line in _tail(attach["text"], 12).splitlines():
            ctx.note("attach| " + line)

    if hardware["state"] != _PRESENT:
        # A SKIP raised from `pre` never reaches `post` (the runner treats it as
        # "cannot be exercised here"), so the scratch tree this case just made is
        # removed on this path too -- R9's "clean up after yourself" has no exception.
        shutil.rmtree(scratch, ignore_errors=True)
        plan["scratch"] = ""
        ctx.note("pre: %s -- scratch tree removed (%s)"
                 % (hardware["state"], not os.path.isdir(scratch)))
        raise Skip(hardware["reason"])

    ctx.note("pre: %s" % hardware["reason"])
    return "scratch=%s project=%s attach=%s pnp=%s" % (
        scratch, project, attach["state"], pnp["state"])


# --------------------------------------------------------------------------- #
# Overlay (the only writes; both files are GBK)
# --------------------------------------------------------------------------- #

def _overlay(ctx, project: str, marker: str) -> Dict[str, Any]:
    """Fill the LED section and patch the payload.

    Three things are asserted, each by its own literal: every anchor hits exactly once,
    the run marker is in the patched source, and the pin mux (`_MUX_NEEDLES`) is in it
    (PRD AC6(3) -- deleting the mux must redden this case, not just the human segment).
    """
    out: Dict[str, Any] = {"ok": False, "error": "", "applied": [], "missing": [],
                           "header": os.path.join(project, "inc", "board_cfg.h"),
                           "source": os.path.join(project, "src", "main.c")}

    header = out["header"]
    source = out["source"]
    if not os.path.isfile(header) or not os.path.isfile(source):
        out["missing"] = [p for p in (header, source) if not os.path.isfile(p)]
        out["error"] = "the template project has no %s" % "; ".join(out["missing"])
        return out

    led_block = _LED_BLOCK
    text = _read_gbk(header)
    text, hits = _insert_once(text, _LED_ANCHOR, _LED_ANCHOR + led_block)
    if hits != 1:
        out["error"] = ("board_cfg.h: the LED-pins anchor was found %d time(s), expected "
                        "1 -- the SDK template's LED section changed" % hits)
        return out
    if _LED_ANCHOR + led_block not in text:
        out["error"] = "board_cfg.h: the LED block was not inserted"
        return out
    try:
        text.encode("gbk")
    except UnicodeEncodeError as exc:
        out["error"] = "board_cfg.h: the LED block is not GBK-encodable: %r" % exc
        return out
    _write_gbk(header, text)
    out["applied"].append("board_cfg.h: LED section filled")

    src = _read_gbk(source)
    for anchor, replacement in _SOURCE_EDITS:
        # Plain literal substitution (never a regex replacement, whose backslash
        # escapes would land a real CR/LF inside the C string literal).
        replacement = replacement.replace("@MARKER@", marker)
        new, hits = _insert_once(src, anchor, replacement)
        if hits != 1:
            out["missing"].append(anchor)
            continue
        src = new
        out["applied"].append("main.c: %r -> %r" % (anchor[:48], replacement[:48]))
    if out["missing"]:
        out["error"] = ("main.c: %d anchor(s) were not found exactly once: %s"
                        % (len(out["missing"]),
                           "; ".join(repr(a[:60]) for a in out["missing"])))
        return out
    if marker not in src:
        out["error"] = "main.c: the run marker %r is not in the patched source" % marker
        return out
    absent = [needle for needle in _MUX_NEEDLES if needle not in src]
    if absent:
        # AC6(3).  Without the mux the pins stay on their reset peripheral function, so
        # the LEDs cannot light -- yet the build, the ELF, the marker and the programmer
        # would all still be green (the human segment is the only other place that would
        # notice, and it is not a verdict).  Named here so the red is machine-checkable.
        out["error"] = ("main.c: the LED pin mux is not in the patched source -- missing "
                        "%s (the pins would not be GPIO outputs)" % "; ".join(absent))
        return out
    _write_gbk(source, src)
    out["ok"] = True
    ctx.note("overlay: board_cfg.h LED section + main.c (%d edit(s)); mux=%d/%d marker=%s"
             % (len(out["applied"]), len(_MUX_NEEDLES) - len(absent), len(_MUX_NEEDLES),
                marker))
    return out


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #

def _cproject_flags(project: str, studio: str) -> Dict[str, Any]:
    """The project's own `-I` and `-D` sets, read from its `.cproject`.

    Read rather than invented: the IDE's own answer is the only defensible set for a
    syntax pre-check, and it is what makes "10 include dirs" a measurement.  Values
    carry Eclipse macros (`${GS32_DRIVER_PATH}`, `${ProjDirPath}`, `${eclipse_home}`),
    expanded here against the `.cproject`'s own `stringMacro` table.
    """
    path = os.path.join(project, ".cproject")
    out: Dict[str, Any] = {"includes": [], "defs": [], "error": ""}
    if not os.path.isfile(path):
        out["error"] = "no .cproject at %s" % path
        return out
    text = _read_text(path)
    macros = dict(re.findall(r'<stringMacro name="([^"]+)"[^>]*value="([^"]*)"', text))
    macros.update({"ProjDirPath": project, "eclipse_home": studio,
                   "ECLIPSE_HOME": studio})

    def options(fragment: str) -> List[str]:
        values: List[str] = []
        for block in re.finditer(r'<option[^>]*superClass="([^"]*)"[^>]*>(.*?)</option>',
                                 text, re.S):
            if fragment not in block.group(1):
                continue
            values += re.findall(r'<listOptionValue[^>]*value="([^"]*)"', block.group(2))
        return values

    def expand(value: str) -> str:
        value = value.replace("&quot;", "").strip()
        for _ in range(4):
            value = re.sub(r"\$\{([^}]+)\}",
                           lambda m: macros.get(m.group(1), m.group(0)), value)
        return os.path.normpath(value)

    out["defs"] = [value.strip() for value in
                   options("option.c.compiler.defs") if value.strip()]
    out["includes"] = [expand(value) for value in
                       options("option.c.compiler.include.paths")]
    if not out["includes"]:
        out["error"] = "the .cproject declares no c-compiler include paths"
    return out


def _syntax_check(ctx, plan: Dict[str, Any], project: str) -> Dict[str, Any]:
    """The pre-flight gate that runs *before* the launcher is ever invoked.

    A deliberately broken payload must be caught here, because the GS32 launcher pops a
    **modal error dialog on the operator's desktop** whenever the JVM exits non-zero --
    so a wrong payload that only failed inside the build would interrupt the person at
    the keyboard.  `available=False` is a *reported* limitation (the tool or the flag set
    could not be produced), not a silent pass: the build's own error summary is still a
    hard gate after it.
    """
    out: Dict[str, Any] = {"available": False, "rc": None, "error": "", "argv": [],
                           "errors": [], "tail": ""}
    studio = plan["studio"]
    compiler = _toolchain_tool(studio, _COMPILER)
    if not os.path.isfile(compiler):
        out["error"] = "no %s under %s" % (_COMPILER, os.path.join(studio, _TOOLCHAIN_GLOB))
        ctx.note("syntax: unavailable -- %s" % out["error"])
        return out
    flags = _cproject_flags(project, studio)
    if flags["error"]:
        out["error"] = flags["error"]
        ctx.note("syntax: unavailable -- %s" % out["error"])
        return out
    main_c = os.path.join(project, "src", "main.c")
    argv = ([compiler] + list(_ARCH_FLAGS)
            + ["-D" + value for value in flags["defs"]]
            + ["-I" + value for value in flags["includes"]]
            + ["-fsyntax-only", main_c])
    out["available"] = True
    out["argv"] = argv
    run = _run_capture(argv, _SYNTAX_TIMEOUT, cwd=project)
    out["rc"] = run["rc"]
    out["tail"] = _tail(str(run["text"]), 12)
    out["errors"] = [line.strip() for line in str(run["text"]).splitlines()
                     if re.search(r":\d+:\d+:\s*error:", line)]
    ctx.note("syntax: rc=%s include_dirs=%d defs=%d errors=%d"
             % (run["rc"], len(flags["includes"]), len(flags["defs"]), len(out["errors"])))
    for line in out["tail"].splitlines():
        ctx.note("syntax| " + line)
    return out


def _build(ctx, plan: Dict[str, Any], project: str, name: str) -> Dict[str, Any]:
    """The headless build.  `-data`/`-import` are asserted native (see `_native`)."""
    out: Dict[str, Any] = {"argv": [], "rc": None, "timed_out": False, "text": "",
                           "elapsed": 0.0, "summary": None, "errors": None,
                           "warnings": None, "compiler_errors": [], "tail": "",
                           "native": True}
    launcher = os.path.join(plan["studio"], _LAUNCHER)
    data = _native(plan["workspace"])
    imported = _native(project)
    if "/" in data or "/" in imported:
        out["native"] = False
        out["text"] = ("refusing to run the headless build with forward slashes in "
                       "-data/-import: Eclipse's EFS reads them as a URI scheme "
                       "(`No file system is defined for scheme`) and the launcher pops a "
                       "modal error box on the desktop")
        ctx.note("build: REFUSED -- %s" % out["text"])
        return out
    argv = [launcher, "-nosplash", "-application", _APP, "-data", data,
            "-import", imported, "-build", "%s/%s" % (name, plan["config"])]
    out["argv"] = argv
    ctx.note("build: %s" % " ".join(argv))
    run = _run_capture(argv, _BUILD_TIMEOUT, cwd=plan["workspace"])
    if run["killed"]:
        plan["killed"].append(run["killed"])
    out["rc"] = run["rc"]
    out["timed_out"] = run["timed_out"]
    out["elapsed"] = run["elapsed"]
    out["text"] = str(run["text"])
    out["tail"] = _tail(out["text"], 25)
    # The CDT summary is the build's own verdict; `Build Failed. 3 errors, …` and
    # `Build Finished. 0 errors, 0 warnings.` are both this shape.  The compiler's own
    # `path:line:col: error:` lines are scanned too, because a summary is a claim while
    # the error lines are the evidence -- and `MEM_CANAERROR_REGS` proves the bare word
    # "error" cannot be grepped for.
    match = re.search(r"(Build Finished|Build Failed)\.\s*(\d+)\s+errors?,\s*"
                      r"(\d+)\s+warnings?", out["text"])
    if match:
        out["summary"] = match.group(0).strip()
        out["errors"] = match.group(2)
        out["warnings"] = match.group(3)
    out["compiler_errors"] = [line.strip() for line in out["text"].splitlines()
                              if re.search(r":\d+:\d+:\s*error:", line)]
    ctx.note("build: rc=%s timed_out=%s elapsed=%.1fs summary=%r compiler_error_lines=%d"
             % (out["rc"], out["timed_out"], out["elapsed"], out["summary"],
                len(out["compiler_errors"])))
    for line in out["tail"].splitlines():
        ctx.note("build| " + line)
    return out


def _readelf(ctx, plan: Dict[str, Any], elf: str) -> Dict[str, Any]:
    """`readelf -h` on the artifact: the R4 criterion that names ELF32 + RISC-V."""
    out: Dict[str, Any] = {"tool": "", "rc": None, "text": "", "elf_class": None,
                           "machine": None, "error": ""}
    tool = _toolchain_tool(plan["studio"], _READELF)
    out["tool"] = tool
    if not os.path.isfile(tool):
        out["error"] = "no %s under %s" % (_READELF,
                                           os.path.join(plan["studio"], _TOOLCHAIN_GLOB))
        return out
    run = _run_capture([tool, "-h", elf], 60.0)
    out["rc"] = run["rc"]
    out["text"] = str(run["text"])
    # `[^ \r\n]+` (not `\S+`/`.+?`) so a CRLF readelf puts on the end of every line
    # (measured: `Machine:                           RISC-V\r`) is not captured as part
    # of the value.
    found = re.search(r"^ *Class: *([^ \r\n]+)", out["text"], re.M)
    out["elf_class"] = found.group(1) if found else None
    found = re.search(r"^ *Machine: *([^ \r\n]+)", out["text"], re.M)
    out["machine"] = found.group(1) if found else None
    ctx.note("readelf: %s -h %s -> rc=%s Class=%s Machine=%s"
             % (os.path.basename(tool), os.path.basename(elf), out["rc"],
                out["elf_class"], out["machine"]))
    return out


def _artifact(ctx, plan: Dict[str, Any], project: str, name: str,
              marker: str, started_at: float) -> Dict[str, Any]:
    """The linked image: this run's ELF, this run's marker, read back from the bytes."""
    out: Dict[str, Any] = {"path": "", "pattern": "", "size": 0, "sha256": "",
                           "mtime": 0.0, "elf": None, "marker_offset": -1,
                           "marker_encoding": "", "readelf": None, "stale": False}
    pattern = os.path.join(project, plan["config"], "*.elf")
    out["pattern"] = pattern
    hits = sorted(glob.glob(pattern))
    if not hits:
        ctx.note("artifact: no file matched %s" % pattern)
        return out
    path = hits[0]
    out["path"] = path
    out["size"] = os.path.getsize(path)
    out["mtime"] = os.path.getmtime(path)
    out["sha256"] = _sha256(path)
    out["elf"] = _elf_header(path)
    out["stale"] = bool(out["mtime"] and out["mtime"] < started_at)
    with open(path, "rb") as handle:
        blob = handle.read()
    offset, encoding = _find_marker(blob, marker)
    out["marker_offset"] = offset
    out["marker_encoding"] = encoding
    out["readelf"] = _readelf(ctx, plan, path)
    elf = out["elf"] or {}
    ctx.note("artifact: %s size=%d mtime=%s sha256=%s class=%s endian=%s e_machine=%s "
             "(expected %d) stale=%s"
             % (path, out["size"],
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(out["mtime"])),
                out["sha256"], elf.get("class"), elf.get("endian"), elf.get("machine"),
                _E_MACHINE_RISCV, out["stale"]))
    ctx.note("artifact: marker %r %s"
             % (marker, ("found at offset %d (%s)" % (offset, encoding))
                if offset >= 0 else "NOT FOUND in any encoding (ascii/u16le/u16be)"))
    return out


def _flash(ctx, plan: Dict[str, Any], elf: str) -> Dict[str, Any]:
    """Hand the artifact to the vendor's programmer CLI."""
    out: Dict[str, Any] = {"argv": [], "rc": None, "timed_out": False, "text": "",
                           "elapsed": 0.0, "success": False, "reset_run": False,
                           "tail": ""}
    exe = os.path.join(plan["prog"], _PROG_CMD)
    if not os.path.isfile(exe):
        out["text"] = "no %s under %s" % (_PROG_CMD, plan["prog"])
        out["tail"] = out["text"]
        ctx.note("flash: NOT RUN -- %s" % out["text"])
        return out
    argv = [exe, "-chip", plan["chip"], "-elf", elf]
    out["argv"] = argv
    ctx.note("flash: %s" % " ".join(argv))
    run = _run_capture(argv, _FLASH_TIMEOUT, cwd=plan["prog"])
    out["rc"] = run["rc"]
    out["timed_out"] = run["timed_out"]
    out["elapsed"] = run["elapsed"]
    out["text"] = str(run["text"])
    out["success"] = _PROG_SUCCESS in out["text"]
    out["reset_run"] = _PROG_RUN in out["text"]
    out["tail"] = _tail(out["text"], 35)
    ctx.note("flash: rc=%s timed_out=%s elapsed=%.1fs success_line=%s reset_run=%s "
             "(auxiliary only)"
             % (out["rc"], out["timed_out"], out["elapsed"], out["success"],
                out["reset_run"]))
    for line in out["tail"].splitlines():
        ctx.note("flash| " + line)
    return out


def _stop(result: Dict[str, Any], ctx, link: str, why: str) -> Dict[str, Any]:
    """Record that `link` is red and that everything after it was deliberately not run.

    Short-circuiting (rather than running on and gating only the flash) is load-bearing:
    the launcher must not be invoked for a payload that cannot compile, because
    GS32_Studio raises a **modal error box on the operator's desktop** whenever its JVM
    exits non-zero.
    """
    result["blocked"] = (result.get("blocked") or []) + [link]
    result["stopped_at"] = link
    result["flash_skipped"] = ("%s is red -- the steps after it were NOT run (%s)"
                               % (link, why))
    ctx.note("chain: %s is red; stops here -- %s" % (link, why))
    return result


# --------------------------------------------------------------------------- #
# The action
# --------------------------------------------------------------------------- #

def _action(ctx):
    plan = ctx.board_plan
    name = plan["project_name"]
    marker = _MARKER_PREFIX + uuid.uuid4().hex[:8]
    project = plan["project"]
    result: Dict[str, Any] = {"errors": list(plan["errors"]), "plan": plan,
                              "name": name, "marker": marker, "project": project,
                              "config": plan["config"], "chip": plan["chip"],
                              "started_at": time.time(), "flash": None,
                              "flash_skipped": ""}
    ctx.note("action: project=%s config=%s chip=%s marker=%s"
             % (name, plan["config"], plan["chip"], marker))

    overlay = _overlay(ctx, project, marker)
    result["overlay"] = overlay
    if not overlay["ok"]:
        # No gate is reached at all; `_expect` names the overlay failure explicitly.
        result["blocked"] = ["overlay"]
        result["flash_skipped"] = "the overlay did not apply"
        return result

    # The chain is strictly ordered and each link gates the next: a failed link must
    # never let the artefact of a *previous* run reach the programmer, and a payload the
    # syntax pre-check catches must never reach the **launcher** either -- GS32_Studio
    # pops a modal error box on the operator's desktop whenever its JVM exits non-zero.
    # The gate is a local list, deliberately **not** `result["errors"]`: `_expect` is the
    # single place that words each failed predicate, so nothing is reported twice.
    result["syntax"] = _syntax_check(ctx, plan, project)
    syntax = result["syntax"]
    if syntax["available"] and syntax["rc"] != 0:
        return _stop(result, ctx, "syntax",
                     "the syntax pre-check is red, so the launcher is NOT invoked (a "
                     "payload that fails here would otherwise pop a modal error box on "
                     "the operator's desktop)")

    result["build"] = _build(ctx, plan, project, name)
    build = result["build"]
    if (build["rc"] != 0 or build["timed_out"] or build["summary"] is None
            or build["errors"] != "0" or build["compiler_errors"]):
        return _stop(result, ctx, "build",
                     "the build is red, so its output is not this run's image")

    result["artifact"] = _artifact(ctx, plan, project, name, marker,
                                   result["started_at"])
    art = result["artifact"]
    if not art["path"] or art["stale"] or art["marker_offset"] < 0:
        return _stop(result, ctx, "artifact",
                     "the linked image is missing, older than this run, or does not "
                     "carry this run's marker (%s@%s)"
                     % (art["marker_encoding"] or "-", art["marker_offset"]))

    result["flash"] = _flash(ctx, plan, art["path"])
    flash = result["flash"]
    if flash["rc"] != 0 or flash["timed_out"] or not flash["success"]:
        result["blocked"] = ["flash"]
        return result

    # The one link no tool here can read back.  It is a REQUEST, not a criterion: it is
    # emitted only once every machine-checkable link is green, and it is never allowed to
    # stand in for one.
    ctx.note("ASK THE HUMAN: every machine-checkable link is green (the SDK template "
             "overlaid with LED1=GPIO24/U4 pin 80 and LED2=GPIO21/U4 pin 79, %s built "
             "with 0 errors, %s carrying this run's marker %s, and the programmer's own "
             "rc=0 with %r) -- now look at the board: LED1 (RUN1) and LED2 (ERR1) must "
             "alternate, each changing state every ~250 ms, and they are ACTIVE LOW (lit "
             "= driven low).  The flash log's %r is auxiliary evidence only and proves "
             "nothing about the payload having reached main().  This is the one thing "
             "this case cannot read back."
             % (os.path.basename(art["path"]), os.path.basename(art["path"]), marker,
                _PROG_SUCCESS, _PROG_RUN))
    return result


# --------------------------------------------------------------------------- #
# Judgement
# --------------------------------------------------------------------------- #

def _expect(ctx, result) -> Tuple[bool, str]:
    problems: List[str] = list(result.get("errors") or [])

    overlay = result.get("overlay") or {}
    syntax = result.get("syntax") or {}
    build = result.get("build") or {}
    art = result.get("artifact") or {}
    flash = result.get("flash")
    marker = result["marker"]

    if not overlay.get("ok"):
        return verdict(problems + ["overlay: %s" % (overlay.get("error") or "did not apply")],
                       "project=%s marker=%s overlay=FAILED" % (result["name"], marker))

    if syntax.get("available") is False:
        # A *reported* limitation, named so it is never mistaken for a silent pass.
        ctx.note("VERDICT NOTE: the syntax pre-check could not run (%s); the build's own "
                 "error summary is the gate that did." % syntax.get("error"))
    elif syntax.get("rc") != 0:
        problems.append(
            "syntax pre-check: %s exited %s (%d error line(s)): %s"
            % (os.path.basename(_COMPILER), syntax.get("rc"), len(syntax.get("errors")),
               "; ".join(syntax.get("errors", [])[:3]) or _tail(syntax.get("tail", ""), 3)))

    blocked = result.get("blocked") or []

    def reached(link: str) -> bool:
        """Was `link` run at all?  The chain stops at the first red link, so a step is
        reached only when nothing before it is in `blocked` (or was never run)."""
        order = ("overlay", "syntax", "build", "artifact", "flash")
        return not any(step in blocked for step in order[:order.index(link)])

    if not reached("build"):
        problems.append("build: not reached -- the chain stopped at %s"
                        % (result.get("stopped_at") or "<no chain stop recorded>"))
    else:
        build = result.get("build") or {}
        if build.get("timed_out"):
            problems.append("build: killed by the %.0fs timeout (%s)"
                            % (_BUILD_TIMEOUT,
                               "; ".join(result["plan"].get("killed") or [])))
        elif build.get("rc") != 0:
            problems.append("build: rc=%s (expected 0)" % build.get("rc"))
        if build.get("summary") is None:
            problems.append("build: the log carries no 'Build Finished./Build Failed.' "
                            "summary line, so the build's own verdict is unknown")
        elif build.get("errors") != "0":
            problems.append("build: %s" % build.get("summary"))
        if build.get("compiler_errors"):
            problems.append("build: %d compiler error line(s): %s"
                            % (len(build["compiler_errors"]),
                               "; ".join(build["compiler_errors"][:3])))

    if not reached("artifact"):
        problems.append("artifact: not reached -- the chain stopped at %s"
                        % result.get("stopped_at"))
    elif not art.get("path"):
        problems.append("artifact: no file matched %s" % art.get("pattern"))
    else:
        if art.get("size", 0) <= 0:
            problems.append("artifact: %s is empty" % art["path"])
        elf = art.get("elf")
        if elf is None:
            problems.append("artifact: %s is not an ELF" % art["path"])
        elif elf["class"] != 1 or elf["machine"] != _E_MACHINE_RISCV:
            problems.append("artifact: class=%s e_machine=%d, expected class=1 (ELF32) "
                            "and e_machine=%d (EM_RISCV)"
                            % (elf["class"], elf["machine"], _E_MACHINE_RISCV))
        readelf = art.get("readelf") or {}
        if readelf.get("error"):
            problems.append("artifact: readelf could not be run (%s), so the R4 "
                            "criterion 'readelf -h says ELF32 + RISC-V' was not "
                            "evaluated" % readelf["error"])
        elif readelf.get("elf_class") != "ELF32" or readelf.get("machine") != "RISC-V":
            problems.append("artifact: readelf -h says Class=%r Machine=%r, expected "
                            "'ELF32' and 'RISC-V' (rc=%s)"
                            % (readelf.get("elf_class"), readelf.get("machine"),
                               readelf.get("rc")))
        if art.get("stale"):
            problems.append("artifact: %s is older than this case's start (mtime %.0f < "
                            "%.0f) -- it is not this run's build"
                            % (art["path"], art["mtime"], result["started_at"]))
        if art.get("marker_offset", -1) < 0:
            problems.append("artifact: this run's marker %r is not in the image in any "
                            "encoding (ascii/u16le/u16be) -- stale artifact, or the "
                            "marker was optimized out" % marker)

    if not reached("flash") or flash is None:
        problems.append("flash: not reached -- the chain stopped at %s"
                        % (result.get("stopped_at") or "<no chain stop recorded>"))
    else:
        if flash.get("timed_out"):
            problems.append("flash: killed by the %.0fs timeout" % _FLASH_TIMEOUT)
        elif flash.get("rc") != 0:
            problems.append("flash: rc=%s (expected 0) -- last lines: %s"
                            % (flash.get("rc"), _tail(flash.get("tail", ""), 3)))
        if not flash.get("success"):
            problems.append("flash: the log does not carry the verbatim success line %r"
                            % _PROG_SUCCESS)
    # `tgt-RESET mode=run.` is deliberately NOT here: it is auxiliary evidence only
    # (PRD R4).  It is reported in the detail line instead.

    return verdict(problems, _detail(result))


def _detail(result) -> str:
    art = result.get("artifact") or {}
    build = result.get("build") or {}
    flash = result.get("flash") or {}
    readelf = art.get("readelf") or {}
    plan = result.get("plan") or {}
    hardware = plan.get("hardware") or {}
    return ("target=gs32 project=%s config=%s chip=%s | machine: build=%r rc=%s "
            "readelf=%s/%s elf=%s size=%s e_machine=%s marker=%s flash_success=%s "
            "flash_rc=%s | auxiliary: reset_run=%s channels=A:%s/B:%s | human="
            "awaiting-operator (LED1/LED2 alternating is NOT machine-checkable here and "
            "is not part of this verdict)"
            % (result["name"], result["config"], result["chip"],
               build.get("summary"), build.get("rc"),
               readelf.get("elf_class"), readelf.get("machine"),
               os.path.basename(art["path"]) if art.get("path") else "<missing>",
               art.get("size"), (art.get("elf") or {}).get("machine"),
               ("%s@%s" % (art.get("marker_encoding"), art.get("marker_offset")))
               if art.get("marker_offset", -1) >= 0 else False,
               bool(flash.get("success")), flash.get("rc"),
               bool(flash.get("reset_run")) if flash else False,
               (hardware.get("attach") or {}).get("state"),
               (hardware.get("pnp") or {}).get("state")))


# --------------------------------------------------------------------------- #
# Cleanup
# --------------------------------------------------------------------------- #

def _cleanup(ctx, label: str) -> str:
    """Remove the case's own scratch tree (PRD R9/AC5).

    Unlike the CCS12 sibling there is no live IDE to protect: this case never starts
    GS32_Studio, so the whole scratch root is simply removed.  Because the scratch is
    under the OS temp dir, no user project and nothing in this repository is touched.
    """
    plan = getattr(ctx, "board_plan", None)
    if not plan:
        return "nothing was created"
    if getattr(ctx, "board_cleaned", False):
        return "already cleaned"
    ctx.board_cleaned = True
    scratch = plan.get("scratch") or ""
    if scratch and os.path.isdir(scratch):
        shutil.rmtree(scratch, ignore_errors=True)
        ctx.note("%s scratch tree removed=%s (%s)"
                 % (label, not os.path.isdir(scratch), scratch))
    if plan.get("killed"):
        ctx.note("%s timed-out child process trees killed: %s"
                 % (label, "; ".join(plan["killed"])))
    return "scratch=%s removed=%s" % (scratch or "<none>",
                                      bool(scratch) and not os.path.isdir(scratch))


def _rollback(ctx):
    """A failed case cleans up the same way."""
    return _cleanup(ctx, "rollback:")


def _post(ctx):
    return _cleanup(ctx, "post:")


CASE = Case(
    name="board.led.chase.gs32",
    group="realflow",
    targets=("gs32",),
    description=("the GS32 sibling of board.led_chase: overlay a scratch copy of the SDK "
                 "template with LED1=GPIO24 / LED2=GPIO21 and a two-LED chase, build it "
                 "with GS32_Studio's headless build, flash it with the vendor's "
                 "GS32ProgCommand.exe, and ask a human to confirm the LEDs alternate -- "
                 "this case never touches the bridge"),
    pre=_pre,
    action=_action,
    expect=_expect,
    post=_post,
    rollback=_rollback,
    # Nothing here touches the bridge: the driver surface is two CLIs (`GS32.exe
    # -application …headlessbuild` and `GS32ProgCommand.exe`) and the two hardware
    # channels are the OS device face and OpenOCD.
    requires_bridge=False,
    # Nothing is judged by a window: the verdict is the two CLIs' rc + their own success
    # markers + reading the artifact's bytes back.
    screen_guard=False,
    evidence=("raw:action", "build:log", "flash:log", "artifact:probe"),
)
