"""board.led.chase.gs32 -- the GS32 sibling of `board.led_chase`: build OUR payload into
this run's own workspace, seed a launch configuration, let GS32_Studio load and run it,
and ask a human to confirm two LEDs chase.

What is verified: a copy of the GS32 SDK template project, living **in this run's
workspace**, is overlaid with the board's real LED pins and a two-LED chase payload,
built by **GS32_Studio's own Eclipse application** with `-data` pointing at that same
workspace, and loaded/run **by GS32_Studio itself** through the bridge; the
machine-checkable half of that chain is judged here, and the second half (LED1/LED2
alternating) is printed as an explicit request for a human.

WHY THIS IS NOT A "NO BRIDGE" CASE (the earlier wording of this file was wrong)
=============================================================================
This case used to build and flash with vendor CLIs only.  That throws away the point of
a board case: its value is the *drivability* of the IDE -- proving our tooling can put
this product to work.  So the driver surface is the CCS12 sibling's, spelled with GS32's
own measured command ids:

    build  `GS32.exe -nosplash -application
            org.eclipse.cdt.managedbuilder.core.headlessbuild -data <THE RUN'S ws>
            -import <proj> -build "<project>/RAM"`
    load   `cmd.run org.eclipse.launchbar.ui.command.launchActive`  (the human's F11)
    run    `cmd.run org.eclipse.debug.ui.commands.Resume`           (the human's F8)
    judged the result word **plus** a reply line `OK executed <command id>` and **no
           `dialog=` line** in that frame

`requires_bridge=False` here does **not** mean "this case does not drive the bridge" --
it means **the runner must not demand a live bridge before `pre`**.  The workspace has to
be seeded and built while the IDE is *down* (T10 below), so this case brings its own
instance up (`ctl install --keep-workspace`) and only then speaks to the bridge; the
CCS12 sibling carries the same flag for the same reason.  (`ctx.request` connects
lazily, so the unconnected `pre` is not a problem.)

`GS32ProgCommand.exe` is no longer an entry point or a criterion: it programs **flash**,
which is a different target from this RAM case.  It is kept only as a side channel -- and
only so `_prog_root` can find the install that also carries channel A's OpenOCD.

SEVEN MEASURED FACTS, and they decide the whole chain (2026-10-09/10; every one is a
reading with a rerun recipe in `research/`, not an inference)

1. **The build base** -- `gs32_examples/gs32f035/GPIO/gpio_ex2_toggle_regs/` carries only
   project scaffolding (`.cproject`/`.project`/`debugConfigs`/`inc/board_cfg.h`), no
   `src/`; `template/gs32f035/` is the buildable one (`src/main.c` + `inc/board_cfg.h`).
   Both have an **empty** "Configuration of the LED pins" section, so the pins can only
   come from this case (the SDK gives none).
2. **The workspace lock (T10)** -- a headless build with `-data <a workspace an IDE is
   running on>` answers `Workspace already in use!` (rc=-1) *and* pops a modal error box
   on the operator's desktop.  So the order is forced: **stop the instance -> seed and
   build -> start the instance**.  That is what `_stop_instance`/`_start` do, and it is
   also why the artifact must live in the run's workspace: `launchActive` only sees
   projects the running IDE has registered, and a project dropped into a live workspace
   is never registered.
3. **The build itself** -- `GS32.exe -nosplash -application
   org.eclipse.cdt.managedbuilder.core.headlessbuild -data <ws> -import <proj> -build
   "<name>/<config>"`.  `-data`/`-import` **must be native backslash paths**: forward
   slashes are parsed as a URI scheme => `CoreException: No file system is defined for
   scheme: D` (rc=13) *and* a modal error box on the operator's desktop.  Measured
   2026-10-09: rc=13 (forward) vs rc=0 (backslash), log `research/s2*.txt`.
4. **The RAM configuration has to be authored** -- the template's `.cproject` declares
   exactly one real configuration, `Flash_ILM` (`-D FLASH_TARGET`, `-T
   gs32f00xx_dsp_flashilm.ld`), and the SDK ships **no** RAM configuration for
   `gs32f035`.  The shape copied here is the vendor's own
   (`…/gs32_examples/gs32f379/adc/adc_ex01_soc_software/.cproject`, the only `.cproject`
   in the tree with a real `name="RAM"`): same `parent`, **own element ids**,
   `buildPath=${workspace_loc:/<proj>}/RAM`, `-T gs32f00xx_dsp_ram.ld` + the `_mem.ld` +
   the `_regs.ld`, **no `FLASH_TARGET`**.
   🔴 the memory map must match the **P** variant: this board is a `GS32F035P` (512K
   eFlash / 128K ILM / 32K DLM, 2 banks -- datasheet p8/p12, and the programmer reads
   back the part number `GS32F035PPN`), and the two `_mem.ld` files differ by exactly
   that (`GS32F035_mem.ld` = 256K/64K/16K).  The vendor's own 38 `gs32f035` examples all
   use the non-P script; that is their default for the non-P part, not this board.
5. **The launch must be ours, not the SDK's** -- the shipped
   `debugConfigs/gs32f035_openocd.launch` is a **flash** configuration: no
   `gs32_cfg_mode`, `gs32_model GS32F035` (no `P`),
   `PROGRAM_NAME=Flash_ILM/gs32f035.elf`, and it hard-codes the artifact path because
   **nothing on GS32 resolves `${build_artifact:…}`** (0 occurrences tree-wide).  Run as
   shipped, OpenOCD takes the flash path and dies with `Init: algorithm verification
   mismatch!` x3 -> `flash init failed` -- the `OpenOCD failed with code (1)` the
   operator sees.  So this case seeds its own `.launch` with
   `-c "set gs32_cfg_mode 2"` (no flash bank is created at all => gdb's `load` can only
   write RAM, which is the other half of fact 4) and `-c "set gs32_model GS32F035P"`,
   with `PROGRAM_NAME` naming the RAM artifact.
6. **Where LaunchBar keeps its state** -- GS32 writes
   `.metadata/…/org.eclipse.launchbar.core.prefs` itself, and a new instance records
   `activeLaunchMode=debug` *before* any `launchActive` (unlike CCS12, whose default is
   `run`, where the command answers a clean `OK` with zero effect).  CCS12's
   `DEFAULT_CCS_TARGET_CONFIGURATION` does not exist on GS32 (that string is in none of
   the 350 jars).  `_loadbar_mode` re-reads the file, so a retreat to `run` is named
   rather than silently accepted.
7. **The board's two channels, both measured in place** (C14: a negative answer needs a
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

    * a **run directory to seed** -- `--run-id <id>` (or a previously installed run for
      `gs32`, which `verify` resolves for itself).  This case owns that run's workspace
      and brings its own instance up on it; it never touches another run's project.
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
| `no run directory to seed` | `verify` resolved no run for `gs32` | add `--run-id <a fresh id>` |
| `the run's workspace registers` | that run already holds somebody else's project | use a fresh `--run-id` |
| `port N is held by another run` | another instance owns the bridge port | stop it, or `verify --port <free>` |
| `no GS32_Studio install tree` | the target has no `install_dir` (or it is not there) | `ctl targets add gs32 --source-dir <...>` |
| `no SDK template project` | the install tree does not carry the example | check ``…BOARD_TEMPLATE`` |
| `no GS32Prog install carrying` | the programmer was not found beside the studio root | set ``ECLIPSE_CTL_GS32_BOARD_PROG`` |
| `no GS32 H1017A board … both channels agree the board is ABSENT` | neither channel sees the board | plug the board's USB in |
| `cannot tell whether the GS32 H1017A board is attached` | at least one channel could not be read (or they disagree) -- **not** a statement about the board | read the named channel |

RERUN (from the repo root; ~60-120 s here: stop, seed, build, start, launch, resume).
One command from zero, exactly as the CCS12 sibling:

    python -m ctl verify --case board.led.chase.gs32 --target gs32 --run-id <fresh>

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
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ...client import Response
from ...errors import CtlError
from ...lifecycle import (REPO_ROOT, list_port_listeners, list_processes,
                          run_live_pid)
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

#: The build configuration this case **authors itself** (see `_ram_config`) and the name
#: the headless build is asked for: `-build "<project>/RAM"`.  The SDK template declares
#: only `Flash_ILM`; the vendor's own `name="RAM"` configuration (gs32f379's adc example)
#: is the shape copied, and the two edits that matter are both named constants below.
_CONFIG = "RAM"

#: The configuration the RAM one is cloned from.  Spelled out rather than assumed, so an
#: SDK that renames it is a named failure instead of a silent no-op.
_FLASH_CONFIG = "Flash_ILM"

#: The linker-script triple.  Against the template's `Flash_ILM` list, exactly **two**
#: entries change and both are here so a diff is readable:
#:   * the *segment* script: `_flashilm.ld` -> `_ram.ld` (this is what makes the image
#:     RAM-only: no flash LOAD address, and an empty copy table);
#:   * the *part* script: `GS32F035_mem.ld` -> `GS32F035P_mem.ld`.  **Not** cosmetic --
#:     `_ram.ld`'s `MEMORY` block consumes `__FLASH_SIZE/__ILM_SIZE/__DLM_SIZE`, so the
#:     part script sets the region lengths and the stack placement; the non-P file is
#:     256K/64K/16K and this board's part is 512K/128K/32K (datasheet p8/p12, and the
#:     programmer reads back `GS32F035PPN`).
#:   * the *register* script is left alone.
#: The series (`f00xx`) and the version (`3.0`) are the template's own: the vendor's
#: gs32f379 example names `gs32f3xx_dsp_ram.ld` / `GS32F379D_mem.ld` /
#: `gs32f3xx_dsp_2.2_regs.ld`, which belong to a different series and must not be copied.
_FLASHILM_SCRIPT = "gs32f00xx_dsp_flashilm.ld"
_RAM_SCRIPT = "gs32f00xx_dsp_ram.ld"
_MEM_SCRIPT = "GS32F035_mem.ld"
_MEM_SCRIPT_P = "GS32F035P_mem.ld"
_REGS_SCRIPT = "gs32f00xx_dsp_3.0_regs.ld"

#: The `-D` the flash configuration carries and the RAM configuration must not: RAM-only
#: images do not take the flash path (`_ram.ld` has no `AT>ROM`, and the flash driver
#: never runs).  Measured occurrence in the template `.cproject`: two, both
#: `<listOptionValue builtIn="false" value="FLASH_TARGET"/>` -- one in the assembler's
#: `-D` list, one in the C compiler's.
_FLASH_DEFINE = "FLASH_TARGET"

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
#: same-named `...managedbuilder.core` bundle.  `-data` is this case's **run workspace**
#: (never a scratch tree of its own): the artifact has to be inside the workspace the
#: instance then opens, or `launchActive` cannot see it.
_LAUNCHER = "GS32.exe"
_APP = "org.eclipse.cdt.managedbuilder.core.headlessbuild"

#: The launch configuration this case seeds, and the two Eclipse **command ids** the
#: bridge drives (R3/R6: every command names its identity -- these go through the
#: existing bridge method `cmd.run`, they are not bridge methods of their own).
#:  * `…launchbar.ui.command.launchActive` -- declared by `org.eclipse.launchbar.ui`; the
#:    human's F11.  Measured live: `defined=true handled=true`.
#:  * `…debug.ui.commands.Resume` -- declared by `org.eclipse.debug.ui`; the human's F8.
#:    `defined=true handled=true`.
#: The launch file is named after the project (as the SDK's own is), so whichever
#: descriptor the LaunchBar claims, it is a copy of an identical file.
_LAUNCH_SUFFIX = "_openocd"
_CMD_LAUNCH_ACTIVE = "org.eclipse.launchbar.ui.command.launchActive"
_CMD_RESUME = "org.eclipse.debug.ui.commands.Resume"

#: The bridge answer's confirmation line (R4's criterion) and the veto.  A frame counts
#: only if it carries `OK executed <command id>` for the id that was sent **and** carries
#: no `dialog=` line: measured on the CCS12 sibling, a `Resume` answered
#: `OK executed …Resume` **and** `dialog=appeared "Run Control not available"` in the
#: same frame -- the handler ran, the target was never released.
_OK_MARK = "OK executed "
_DIALOG_MARK = "dialog="

#: The LaunchBar's own state file, under the run workspace's `.metadata`, and the mode
#: this case requires of it.  GS32 writes this itself; `debug` is what makes
#: `launchActive` create a debug session (see fact 6 in the module docstring).
_LAUNCHBAR_PREFS_REL = os.path.join(
    ".metadata", ".plugins", "org.eclipse.core.runtime", ".settings",
    "org.eclipse.launchbar.core.prefs")
_LAUNCHBAR_DEBUG = "activeLaunchMode=debug"
#: `_loadbar_mode` splits the prefs line at the **last** `=` and keeps the value alone, so the
#: comparison in `_expect` must be against the bare mode word.  There is deliberately **no**
#: `activeLaunchMode=run` sibling constant: one in the file-line form compares against a bare value
#: and can never be true, which would leave a retreat to `run` green (exactly what the gate test
#: `…_retreated_to_run_mode_is_red` caught on 2026-10-11).
_LAUNCHBAR_MODE_RUN = "run"

#: The seeded `.launch`.  Modelled on the SDK's own
#: `debugConfigs/gs32f035_openocd.launch` with the four measured corrections:
#:  * `gdbServerOther` carries `-c "set gs32_cfg_mode 2"` -- with no flash bank created,
#:    gdb's `load` can only write RAM (that is why the build must be RAM too);
#:  * the model is `GS32F035P`, not the factory's `GS32F035`;
#:  * `PROGRAM_NAME` names **this** configuration's artifact (nothing on GS32 resolves
#:    `${build_artifact:…}`, measured: 0 occurrences tree-wide);
#:  * `doDebugInRam=true` and `doSecondReset=false`.  These two are the whole difference
#:    between the factory's flash口径 launch and the vendor's own **RAM** launch
#:    (`libraries/bootloader/…/ram_ex3_dsp_ramload_3.0/debugConfigs/
#:    ram_ex3_dsp_ramload_3_0_openocd.launch` -- measured: identical in every other key
#:    this file sets, `setPcRegister` still `false` in both).  A second reset *after*
#:    gdb's `load` would put the PC back on the reset vector, which for a RAM image is
#:    system flash, not our payload -- the measured "clean `OK`, zero effect" specimen.
#: `@…@` tokens are substituted verbatim (never through a regex, whose backslash escapes
#: would land a real CR/LF inside an XML attribute).
_LAUNCH_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<launchConfiguration type="ilg.gnumcueclipse.debug.gdbjtag.openocd.launchConfigurationType">
    <booleanAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.doContinue" value="true"/>
    <booleanAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.doDebugInRam" value="true"/>
    <booleanAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.doFirstReset" value="true"/>
    <booleanAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.doGdbServerAllocateConsole" value="true"/>
    <booleanAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.doGdbServerAllocateTelnetConsole" value="false"/>
    <booleanAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.doSecondReset" value="false"/>
    <booleanAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.doStartGdbCLient" value="true"/>
    <booleanAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.doStartGdbServer" value="true"/>
    <booleanAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.enableSemihosting" value="true"/>
    <stringAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.firstResetType" value="init"/>
    <stringAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.gdbClientOtherCommands" value="set mem inaccessible-by-default off"/>
    <stringAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.gdbClientOtherOptions" value=""/>
    <stringAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.gdbServerConnectionAddress" value=""/>
    <stringAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.gdbServerExecutable" value="${openocd_path}/${openocd_executable}"/>
    <intAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.gdbServerGdbPortNumber" value="3355"/>
    <stringAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.gdbServerLog" value=""/>
    <stringAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.gdbServerOther" value="@GDBOTHER@"/>
    <stringAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.gdbServerTclPortNumber" value="6666"/>
    <intAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.gdbServerTelnetPortNumber" value="4444"/>
    <stringAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.otherInitCommands" value=""/>
    <stringAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.otherRunCommands" value=""/>
    <stringAttribute key="ilg.gnumcueclipse.debug.gdbjtag.openocd.secondResetType" value="halt"/>
    <stringAttribute key="ilg.gnumcueclipse.debug.gdbjtag.svdPath" value="${GS32_FW_PATH}\\utilities\\svd\\gs32f00xx\\gs32f00xx_dsp_v3.0.svd"/>
    <stringAttribute key="org.eclipse.cdt.debug.gdbjtag.core.imageFileName" value=""/>
    <stringAttribute key="org.eclipse.cdt.debug.gdbjtag.core.imageOffset" value=""/>
    <stringAttribute key="org.eclipse.cdt.debug.gdbjtag.core.ipAddress" value="localhost"/>
    <stringAttribute key="org.eclipse.cdt.debug.gdbjtag.core.jtagDevice" value="GNU MCU OpenOCD"/>
    <booleanAttribute key="org.eclipse.cdt.debug.gdbjtag.core.loadImage" value="true"/>
    <booleanAttribute key="org.eclipse.cdt.debug.gdbjtag.core.loadSymbols" value="true"/>
    <stringAttribute key="org.eclipse.cdt.debug.gdbjtag.core.pcRegister" value=""/>
    <intAttribute key="org.eclipse.cdt.debug.gdbjtag.core.portNumber" value="3355"/>
    <booleanAttribute key="org.eclipse.cdt.debug.gdbjtag.core.setPcRegister" value="false"/>
    <booleanAttribute key="org.eclipse.cdt.debug.gdbjtag.core.setResume" value="false"/>
    <booleanAttribute key="org.eclipse.cdt.debug.gdbjtag.core.setStopAt" value="true"/>
    <stringAttribute key="org.eclipse.cdt.debug.gdbjtag.core.stopAt" value="main"/>
    <stringAttribute key="org.eclipse.cdt.debug.gdbjtag.core.symbolsFileName" value=""/>
    <stringAttribute key="org.eclipse.cdt.debug.gdbjtag.core.symbolsOffset" value=""/>
    <booleanAttribute key="org.eclipse.cdt.debug.gdbjtag.core.useFileForImage" value="false"/>
    <booleanAttribute key="org.eclipse.cdt.debug.gdbjtag.core.useFileForSymbols" value="false"/>
    <booleanAttribute key="org.eclipse.cdt.debug.gdbjtag.core.useProjBinaryForImage" value="true"/>
    <booleanAttribute key="org.eclipse.cdt.debug.gdbjtag.core.useProjBinaryForSymbols" value="true"/>
    <booleanAttribute key="org.eclipse.cdt.debug.gdbjtag.core.useRemoteTarget" value="true"/>
    <stringAttribute key="org.eclipse.cdt.dsf.gdb.DEBUG_NAME" value="${cross_prefix}gdb${cross_suffix}"/>
    <booleanAttribute key="org.eclipse.cdt.dsf.gdb.UPDATE_THREADLIST_ON_SUSPEND" value="false"/>
    <intAttribute key="org.eclipse.cdt.launch.ATTR_BUILD_BEFORE_LAUNCH_ATTR" value="2"/>
    <stringAttribute key="org.eclipse.cdt.launch.COREFILE_PATH" value=""/>
    <stringAttribute key="org.eclipse.cdt.launch.PROGRAM_NAME" value="@PROGRAM@"/>
    <stringAttribute key="org.eclipse.cdt.launch.PROJECT_ATTR" value="@PROJECT@"/>
    <booleanAttribute key="org.eclipse.cdt.launch.PROJECT_BUILD_CONFIG_AUTO_ATTR" value="false"/>
    <stringAttribute key="org.eclipse.cdt.launch.PROJECT_BUILD_CONFIG_ID_ATTR" value=""/>
    <booleanAttribute key="org.eclipse.debug.core.ATTR_FORCE_SYSTEM_CONSOLE_ENCODING" value="false"/>
    <listAttribute key="org.eclipse.debug.core.MAPPED_RESOURCE_PATHS">
        <listEntry value="/@PROJECT@"/>
    </listAttribute>
    <listAttribute key="org.eclipse.debug.core.MAPPED_RESOURCE_TYPES">
        <listEntry value="4"/>
    </listAttribute>
    <stringAttribute key="org.eclipse.dsf.launch.MEMORY_BLOCKS" value="&lt;?xml version=&quot;1.0&quot; encoding=&quot;UTF-8&quot; standalone=&quot;no&quot;?&gt;&#13;&#10;&lt;memoryBlockExpressionList context=&quot;Context string&quot;/&gt;&#13;&#10;"/>
    <stringAttribute key="process_factory_id" value="org.eclipse.cdt.dsf.gdb.GdbProcessFactory"/>
</launchConfiguration>
"""

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

#: The programmer CLI.  **Side channel only** (PRD R3): it programs *flash*, which is not
#: this case's target, so it is not an entry point here and nothing in `_expect` reads
#: it.  It is kept because the install that carries it also carries
#: `openocd/bin/gs-openocd.exe` (channel A's tool) -- `_prog_root` finds the install by
#: looking for this file.
#: Measured 2026-10-09 (verbatim, rc=0): `target partnumber: GS32F035PPN` /
#: `partnumber check finished.` / `wrote 32768 bytes …` / `verified 21312 bytes …` /
#: `tgt-RESET mode=run.` / `Programming succeeded for 1 file(s).`
#: ⚠️ 2026-10-10: the same command failed 3/3 with `Init: algorithm verification
#: mismatch!` x3 -> `flash init failed` (reason still `未证实`), which is exactly why the
#: load path here is RAM + `gs32_cfg_mode 2` rather than this CLI.
_PROG_CMD = "GS32ProgCommand.exe"

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
#: a headless build here took ~9.4 s warm / ~24 s cold, the OpenOCD attach ~0.7 s, the
#: PnP query ~1.0-1.2 s, `install` (which starts a fresh IDE) tens of seconds.
_BUILD_TIMEOUT = 900.0
_INSTALL_TIMEOUT = 900.0
_STOP_TIMEOUT = 180.0
_ATTACH_TIMEOUT = 60.0
_PNP_TIMEOUT = 60.0
_SYNTAX_TIMEOUT = 120.0

#: The load stage's budget.  `launchActive` answers `OK` as soon as the launch *starts*
#: (measured on the sibling: it answers a clean `OK` with zero effect while the LaunchBar
#: is still recording the configuration), so the Resume is only issued after the
#: instance's own jobs go idle.  `sys.wait jobs-idle` is a bridge **method** (read/wait)
#: and takes no argument; each call uses the bridge's own 15 s budget and an exhausted
#: budget is a normal `OK` with `idle=false`, never `ERR timeout`.
_LOAD_LAUNCH_WAIT_ROUNDS = 20
_LOAD_RESUME_ATTEMPTS = 6
_LOAD_RESUME_POLL_S = 2.0
_LOAD_CONSOLE_TAIL = 60

#: How many times to try emptying the run's workspace before giving up.  A JVM that has
#: just been asked to exit can still hold a file in it for a moment (measured on the
#: sibling target: 1 s apart, a handful of attempts).
_WIPE_ATTEMPTS = 10

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
     "                    GpioDataRegs.GPACLEAR.bit.BOARD_LED1 = 0x1;  /* LED1 lit  */\n"
     "                    GpioDataRegs.GPASET.bit.BOARD_LED2 = 0x1;    /* LED2 dark */\n"
     "                } else {\n"
     "                    GpioDataRegs.GPASET.bit.BOARD_LED1 = 0x1;    /* LED1 dark */\n"
     "                    GpioDataRegs.GPACLEAR.bit.BOARD_LED2 = 0x1;  /* LED2 lit  */\n"
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
#:
#: **Whole statements**, not fragments (`deliverable-shape.md` C15): with the substring
#: form `GPIO_MUX_DATA(BOARD_LED1_MUX)` the mutation `GPAMUX2` -> `GPAMUX1` stayed green
#: while being exactly the same defect -- GPIO24/GPIO21 are not in `GPAMUX1`'s range, so
#: the pins would never leave their reset peripheral function and the LEDs could not
#: light.  The register is the vendor's own choice (their `src/main.c` writes
#: `GpioCtrlRegs.GPAMUX2.bit.GPIO24 = GPIO_MUX_DATA(GPIO_24_GPIO24);`), so pinning the
#: whole statement is pinning a measured fact, not a style.
_MUX_NEEDLES = (
    "GpioCtrlRegs.GPAMUX2.bit.BOARD_LED1 = GPIO_MUX_DATA(BOARD_LED1_MUX);",
    "GpioCtrlRegs.GPAMUX2.bit.BOARD_LED2 = GPIO_MUX_DATA(BOARD_LED2_MUX);",
)

#: The chase's *semantics*: every step must DRIVE both pins to complementary levels
#: (one `GPACLEAR` = lit, one `GPASET` = dark), so **exactly one LED is lit at any
#: time**.  Spelled out as four literals so a payload that merely *toggles one pin per
#: step* -- which necessarily walks through the "both lit" and "both dark" states --
#: is caught by name instead of being left to the human segment.
#:
#: MEASURED FAILURE this guards (2026-10-10, the operator's own eyes): the first
#: payload toggled one pin per 250 ms step, alternating which pin.  With two active-low
#: LEDs that is a four-state cycle (LED2 lit -> both -> LED1 -> neither): the two LEDs
#: were lit TOGETHER for 250 ms out of every 1000 ms.  Build, ELF, marker and the
#: programmer were all green -- nothing on the toolchain can see it
#: (`deliverable-shape.md` C15).  The vendor's own example uses the complementary
#: idiom (`gs32_examples/examples_src/gpio/GS32F035_Regs/gpio_ex2_toggle_regs/`:
#: `GPASET.all = 0xAAAAAAAA; GPACLEAR.all = 0x55555555;`), so "strict alternation is
#: impossible with single-bit toggles" was never true: it was a false constraint that
#: the payload had been designed around.
_CHASE_NEEDLES = (
    "GpioDataRegs.GPACLEAR.bit.BOARD_LED1 = 0x1;",
    "GpioDataRegs.GPASET.bit.BOARD_LED2 = 0x1;",
    "GpioDataRegs.GPASET.bit.BOARD_LED1 = 0x1;",
    "GpioDataRegs.GPACLEAR.bit.BOARD_LED2 = 0x1;",
)

#: ...and the toggle idiom must be **gone**: toggling one LED pin per step is exactly
#: the shape that produces the both-lit state this case's criterion forbids.
_CHASE_FORBIDDEN = "GPATOGGLE.bit.BOARD_LED"

#: The chase's own paragraph, kept next to the edits so the shape is readable in one
#: place: every step drives **both** pins to complementary levels, so exactly one LED is
#: lit at any time and the two alternate every 250 ms -- never both, never neither.
_CHASE_COMMENT = """\
/* two-LED chase, 250 ms per step (the CPUTimer0 tick is 10 ms): both pins are driven
 * to complementary levels every step, so exactly one LED is lit at a time and the two
 * alternate -- never both, never neither.  GPASET/GPACLEAR act on a written 1 (reading
 * them is meaningless), which is why the pair is written out rather than toggled.
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


def _write_text(path: str, text: str) -> None:
    """Write UTF-8 with the newlines as given (`.cproject`/`.launch` are UTF-8)."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
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
# The CLI's own doors, and the LaunchBar's state file
# --------------------------------------------------------------------------- #

def _run_ctl(args: List[str], timeout: float) -> Dict[str, Any]:
    """One `python -m ctl …` door, from the repo root (never a shell string).

    The case drives the *same* CLI the operator does -- `install --keep-workspace` to
    bring the instance up on the workspace this case just seeded, `uninstall` to free it
    again.  No capability is added to `ctl` or the bridge (R10); these are existing
    doors, exactly as the CCS12 sibling calls them.
    """
    argv = [sys.executable, "-m", "ctl"] + args
    return _run_capture(argv, timeout, cwd=REPO_ROOT)


def _loadbar_mode(workspace: str) -> Dict[str, Any]:
    """Read back the LaunchBar's active launch mode for this workspace.

    GS32 writes `<ws>/.metadata/.../org.eclipse.launchbar.core.prefs` itself, and its own
    new instance records `activeLaunchMode=debug` *before* any `launchActive` (measured
    2026-10-10; CCS12 is the mirror image and records `run`, in which `launchActive`
    answers a clean `OK` with zero effect).  This is a **pin**, not a criterion: the
    verdict still rests on the result words, but a future retreat to `run` gets named
    instead of passing silently.

    Returns `{"path", "lines", "modes", "error"}`; `modes` is `descriptor -> mode`.
    """
    path = os.path.join(workspace, _LAUNCHBAR_PREFS_REL)
    out: Dict[str, Any] = {"path": path, "lines": [], "modes": {}, "error": ""}
    if not os.path.isfile(path):
        out["error"] = "the LaunchBar state file was never written (%s)" % path
        return out
    text = _read_text(path)
    out["lines"] = [line for line in text.splitlines() if line.strip()]
    for line in out["lines"]:
        # `rpartition`, matching this function's note: the *last* `=` separates the key
        # from the value (a descriptor id that carried an `=` of its own would otherwise
        # shift the split and the mode would be read off the wrong end).
        key, _, value = line.rpartition("=")
        if key.endswith("/activeLaunchMode"):
            out["modes"][key[: -len("/activeLaunchMode")]] = value
    return out


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
# Plan (`pre`) -- resolve the environment, then the run's own state
# --------------------------------------------------------------------------- #

def _registered_projects(workspace: str) -> List[str]:
    """The project names the run's workspace has registered, as Eclipse serializes them."""
    root = os.path.join(workspace, ".metadata", ".plugins",
                        "org.eclipse.core.resources", ".projects")
    if not os.path.isdir(root):
        return []
    return sorted(entry for entry in os.listdir(root)
                  if os.path.isdir(os.path.join(root, entry)))


def _foreign_projects(registered: List[str], name: str) -> List[str]:
    """The registered entries that are **not** this case's project.

    Eclipse registers projects of its own in any workspace it has ever started on: a
    brand-new `ctl install` workspace already carries `.org.eclipse.egit.core.cmp` the
    moment EGit loads -- measured 2026-10-11, `_registered_projects(<fresh run ws>)`
    returned **exactly** `['.org.eclipse.egit.core.cmp']`.  Dot-prefixed names are
    Eclipse-reserved, so counting them as "somebody else's" made the ownership guard
    SKIP on *every* workspace and put AC1 out of reach.
    """
    return [entry for entry in registered
            if entry != name and not entry.startswith(".")]


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
    """Resolve the environment, then the preconditions that live on the run.

    No bridge is connected at this point (`requires_bridge=False`): this case seeds and
    builds the run's workspace **while the IDE is down**, which is what fact 2 forces.
    So the thing that must exist is `ctx.paths` -- a run to own -- not a live bridge.

    Nothing of this run is written here: the seed happens in `action`, after the
    instance that holds the workspace has been stopped.
    """
    if ctx.paths is None:
        raise Skip("no run directory to seed: `verify` resolved no run for target %r and "
                   "none was given; retry with --run-id <a fresh id> -- this case seeds "
                   "<run>/ws and starts its own instance on it" % ctx.target.name)
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
    # The build configuration is **authored** by this case (`_ram_config`), not a board
    # fact, so it is deliberately not an environment seam: a variable could rename it in
    # the build request while the `.cproject` behind it still said `RAM`.
    config = _CONFIG
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

    workspace = ctx.paths.workspace
    name = _project_name(template) or _PROJECT
    project = os.path.join(workspace, name)
    plan.update({"workspace": workspace, "project": project, "project_name": name})
    expected = _override("project") or _PROJECT
    if name != expected:
        plan["errors"].append(
            "project read-back: the SDK template's .project declares %r, expected %r -- "
            "this case builds the template as shipped (the ELF is named after it), so a "
            "renamed example is a wrong input, not a wrong expectation"
            % (name, expected))
    ctx.note("pre: studio=%s template=%s run=%s workspace=%s project=%s (name read back "
             "from .project) config=%s chip=%s prog=%s"
             % (studio, template, ctx.run_id, workspace, project, config, chip, prog))

    # A workspace that already registers somebody else's project makes the launch
    # configuration ambiguous -- and this case is about to start an IDE on that same
    # workspace.  Nothing is deleted to resolve that: it SKIPs.
    #
    # Eclipse's **own** bookkeeping projects are not "somebody else's".  A brand-new
    # workspace gets `.org.eclipse.egit.core.cmp` the moment EGit loads: measured
    # 2026-10-11 on a fresh `ctl install`, `_registered_projects(<run ws>)` returned
    # exactly `['.org.eclipse.egit.core.cmp']` -- counting that as foreign made this
    # guard SKIP on *every* workspace, which put AC1 out of reach.  Dot-prefixed
    # names are Eclipse-reserved, so they are not evidence of another session.
    registered = _registered_projects(workspace)
    plan["registered_before"] = registered
    foreign = _foreign_projects(registered, name)
    if foreign:
        raise Skip("the run's workspace registers %s -- this case owns its workspace (it "
                   "seeds the project before the IDE starts, so a foreign project would "
                   "make the launch configuration ambiguous) and will not delete another "
                   "session's project; retry on a fresh instance: python -m ctl install "
                   "--target %s --run-id %s-2"
                   % (", ".join(repr(entry) for entry in foreign), ctx.target.name,
                      ctx.run_id))

    # The instance that holds this workspace has to go before anything is read or
    # written: a live IDE holds `<ws>/.metadata/.lock` (fact 2), and its debug session
    # would hold the probe's FTDI handle -- the very handle channel A needs.
    stop = _stop_instance(ctx, plan)
    ctx.note("pre: stop %s (rc=%s) before the probe is read -- this run's own leftover "
             "instance would hold the workspace lock and the probe's handle"
             % ("ran" if stop["needed"] else "not needed", stop["rc"]))
    if stop["error"]:
        plan["errors"].append("stop: %s" % stop["error"])

    port = ctx.runner.port or ctx.target.port
    holders = list_port_listeners(port)
    ours = _own_pids(ctx, plan)
    foreign_holders = [pid for pid in holders if pid not in ours]
    plan.update({"port": port, "port_holders": holders})
    ctx.note("pre: port %d holders=%s (ours=%s)"
             % (port, holders or "<none>", sorted(ours) or "<none>"))
    if foreign_holders:
        raise Skip("port %d is held by another run (pid %s) and this case must start the "
                   "instance itself; stop it first (python -m ctl uninstall --target %s "
                   "--run-id <that run>) or pass --port <free>"
                   % (port, ", ".join(str(pid) for pid in foreign_holders),
                      ctx.target.name))

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
        # Nothing of this run has been written yet (the seed happens in `action`), so
        # there is nothing to undo here -- R9's "clean up after yourself" is about the
        # workspace the case *did* seed, and it names that state below.
        ctx.note("pre: %s -- nothing of this run was written (the workspace is seeded in "
                 "`action`) and the instance this run had was stopped (rc=%s)"
                 % (hardware["state"], stop["rc"]))
        raise Skip(hardware["reason"])

    ctx.note("pre: %s" % hardware["reason"])
    return "run=%s workspace=%s attach=%s pnp=%s" % (
        ctx.run_id, workspace, attach["state"], pnp["state"])


# --------------------------------------------------------------------------- #
# Freeing the run: stop the instance that holds the workspace and the probe
# --------------------------------------------------------------------------- #

def _stop_instance(ctx, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Free the workspace's lock and the port before anything is read or seeded.

    `uninstall` is the CLI's own door: it stops the run's pid and anything still holding
    its port or configuration area, and it does **not** delete the run.  It returns 0
    when there is nothing to stop, so this is safe to call twice (once from `pre`, once
    from the action).  Measured on the sibling target: a live IDE holds
    `<ws>/.metadata/.lock`, and a second JVM on that workspace is refused with
    `Workspace already in use!` (fact 2).
    """
    out: Dict[str, Any] = {"needed": False, "rc": None, "text": "", "error": ""}
    if not os.path.isfile(ctx.paths.endpoint):
        ctx.note("stop: no endpoint.json in run %s -- no live instance to stop"
                 % ctx.run_id)
        return out
    out["needed"] = True
    run = _run_ctl(["uninstall", "--target", ctx.target.name, "--run-id", ctx.run_id],
                   timeout=_STOP_TIMEOUT)
    out["rc"] = run["rc"]
    out["text"] = str(run["text"])
    for line in _tail(out["text"], 12).splitlines():
        ctx.note("stop| " + line)
    if run["rc"] != 0:
        out["error"] = "uninstall rc=%s" % run["rc"]
    return out


def _own_pids(ctx, plan: Dict[str, Any]) -> set:
    """The pids that belong to **this run** -- the same predicate `lifecycle.install`
    uses to decide whether a port listener is ours: the recorded instance, widened by
    command line over this run's configuration area and workspace.  Anything else on the
    port is another run's, and this case SKIPs rather than killing it.
    """
    pids = set()
    run_dir = os.path.dirname(ctx.paths.endpoint)
    live = run_live_pid(run_dir)
    if live:
        pids.add(int(live))
    conf = ctx.paths.configuration.replace("\\", "/")
    workspace = (plan.get("workspace") or "").replace("\\", "/")
    for row in list_processes():
        cmdline = (row.get("cmdline") or "").replace("\\", "/")
        if (conf and conf in cmdline) or (workspace and workspace in cmdline):
            try:
                pids.add(int(row["pid"]))
            except (TypeError, ValueError):
                continue
    return pids


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
                        "%s (the pins would not be GPIO outputs)" % " ".join(absent))
        return out
    # AC6(4) + `deliverable-shape.md` C15.  The mux says "the pins are GPIO *outputs*"; it
    # says nothing about what the payload DOES with them.  The first version toggled one
    # pin per step -- a four-state cycle whose "both lit" quarter is exactly the
    # phenomenon R1 forbids -- and every machine predicate stayed green (build, ELF,
    # marker, programmer all fine).  Named here so that red is machine-checkable too.
    absent_chase = [needle for needle in _CHASE_NEEDLES if needle not in src]
    toggling = _CHASE_FORBIDDEN in src
    if absent_chase or toggling:
        out["error"] = (
            "main.c: the chase does not drive the two LED pins complementarily -- missing "
            "%s%s (toggling one pin per step walks through the both-lit and both-dark "
            "states, so the LEDs do not alternate; the criterion is exactly one lit at a "
            "time)" % (" ".join(absent_chase) or "none",
                       "; and the toggle idiom %r is still present" % _CHASE_FORBIDDEN
                       if toggling else ""))
        return out
    _write_gbk(source, src)
    out["ok"] = True
    ctx.note("overlay: board_cfg.h LED section + main.c (%d edit(s)); mux=%d/%d chase=%d/%d "
             "marker=%s"
             % (len(out["applied"]), len(_MUX_NEEDLES) - len(absent), len(_MUX_NEEDLES),
                len(_CHASE_NEEDLES) - len(absent_chase), len(_CHASE_NEEDLES),
                marker))
    return out


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #

def _wipe_workspace(ctx, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Empty the run's **own** workspace, so the seed starts from nothing.

    A workspace is not just its project directories: Eclipse serializes a resource tree
    under `.metadata/…/org.eclipse.core.resources/.root/`, and a project still listed
    there makes the next import land in a half-there tree.  `ctl install` empties the
    workspace by default; this case does it itself because the seed has to happen while
    the IDE is *not* running (fact 2).  The workspace is the run's own -- `pre` refused a
    workspace that registers somebody else's project, and stopped the instance holding it.
    """
    workspace = plan["workspace"]
    out: Dict[str, Any] = {"path": workspace, "removed": False, "error": "",
                           "had": sorted(os.listdir(workspace))
                           if os.path.isdir(workspace) else []}
    last: Optional[Exception] = None
    for _attempt in range(_WIPE_ATTEMPTS):
        try:
            if os.path.isdir(workspace):
                shutil.rmtree(workspace)
            os.makedirs(workspace, exist_ok=True)
            out["removed"] = True
            break
        except OSError as exc:               # the JVM may still be letting go of the lock
            last = exc
            time.sleep(1.0)
    if not out["removed"]:
        out["error"] = ("could not empty %s after %d attempts: %r"
                        % (workspace, _WIPE_ATTEMPTS, last))
    ctx.note("wipe: %s removed=%s (had %s)%s"
             % (workspace, out["removed"], out["had"] or "<nothing>",
                "" if out["removed"] else " ERROR " + out["error"]))
    return out


def _ram_config(ctx, project: str, name: str) -> Dict[str, Any]:
    """Author the RAM build configuration the SDK does not ship for this part (fact 4).

    Clones the template's `Flash_ILM` `<cconfiguration>` -- both halves of CDT's pair,
    which share one id -- under a fresh id, and applies exactly the edits the vendor's own
    RAM configuration (`gs32f379/adc/adc_ex01_soc_software/.cproject`) shows are needed:

        name          Flash_ILM -> RAM      (2 places: the cconfiguration's storageModule
                                             and the embedded <configuration>)
        buildPath     .../<foreign proj>/Flash -> ${workspace_loc:/<this proj>}/RAM
        segment .ld   gs32f00xx_dsp_flashilm.ld -> gs32f00xx_dsp_ram.ld
        part .ld      GS32F035_mem.ld -> GS32F035P_mem.ld    (this board is the **P** part)
        -D            FLASH_TARGET dropped   (2 list entries: assembler and C compiler)

    The register script is deliberately untouched.  The toolChain and builder ids get
    fresh values too: two configurations sharing one element id is what the vendor's own
    file avoids, and an id collision is the kind of thing that shows up as "the build ran
    the *other* configuration".

    Nothing is assumed: the clone source must be present exactly once, every replacement
    is counted, and the written file is read back and re-checked.  A `.cproject` that
    still names the flash segment script, still defines `FLASH_TARGET`, or has lost the
    `_mem.ld` swap is a **named failure** rather than a build that silently links flash.
    """
    path = os.path.join(project, ".cproject")
    out: Dict[str, Any] = {"ok": False, "error": "", "path": path, "id": "",
                           "configs": [], "dropped": 0, "checks": []}
    if not os.path.isfile(path):
        out["error"] = "no .cproject at %s" % path
        return out
    text = _read_text(path)
    block = _config_block(text, _FLASH_CONFIG)
    if not block:
        out["error"] = ("the .cproject declares no %r configuration -- the clone source "
                        "moved, so this case will not guess what to clone" % _FLASH_CONFIG)
        return out
    end = text.find(block) + len(block)

    found = re.search(r'<cconfiguration [^>]*id="([^"]+)"', block)
    flash_id = found.group(1) if found else ""
    if not flash_id:
        out["error"] = "the <cconfiguration> declares no id"
        return out
    out["id"] = flash_id
    for script, label in ((_FLASHILM_SCRIPT, "segment"), (_MEM_SCRIPT, "part"),
                          (_REGS_SCRIPT, "registers")):
        if script not in block:
            out["error"] = ("the %s linker script %r is not in the %r configuration"
                            % (label, script, _FLASH_CONFIG))
            return out
    if ('value="%s"' % _FLASH_DEFINE) not in block:
        out["error"] = ("%r is not among the %r configuration's -D entries, so there is "
                        "nothing to drop" % (_FLASH_DEFINE, _FLASH_CONFIG))
        return out

    # The template's `.cproject` is **CRLF** (measured: 189 CRLF, 0 bare LF), so the
    # line-drop below tolerates it and the clone is separated with the file's own
    # newline -- `.cproject` is XML and does not care, but a file that mixes the two
    # makes every later diff fight the reader.
    newline = "\r\n" if "\r\n" in text else "\n"
    ram_id = flash_id + ".ram"
    clone = block.replace(flash_id, ram_id)
    clone = clone.replace('name="%s"' % _FLASH_CONFIG, 'name="%s"' % _CONFIG)
    clone = clone.replace(_FLASHILM_SCRIPT, _RAM_SCRIPT)
    clone = clone.replace(_MEM_SCRIPT, _MEM_SCRIPT_P)
    clone, dropped = re.subn(
        r'[ \t]*<listOptionValue builtIn="false" value="%s"/>\r?\n' % _FLASH_DEFINE, "",
        clone)
    out["dropped"] = dropped
    if dropped != 2:
        out["error"] = ("dropping %r hit %d list entr(y/ies), expected 2 (assembler + C "
                        "compiler)" % (_FLASH_DEFINE, dropped))
        return out

    # -- fresh element ids for the tool chain and the builder --------------------
    for tag, key in (("toolChain", "toolchain"), ("builder", "builder")):
        found = re.search(r'<%s [^>]*id="([^"]+)"' % tag, clone)
        if not found:
            out["error"] = "the cloned configuration carries no <%s> id" % tag
            return out
        clone = clone.replace(found.group(1), found.group(1) + ".ram")
        out["checks"].append("%s id -> %s.ram" % (key, found.group(1)))

    # -- the builder's output directory ------------------------------------------
    clone, patched = re.subn(r'(<builder buildPath=")[^"]*(")',
                             lambda found: found.group(1) + "${workspace_loc:/%s}/%s"
                             % (name, _CONFIG) + found.group(2), clone, count=1)
    if patched != 1:
        out["error"] = ("the cloned configuration's builder buildPath was patched %d "
                        "time(s), expected 1" % patched)
        return out
    out["checks"].append("buildPath -> ${workspace_loc:/%s}/%s" % (name, _CONFIG))

    _write_text(path, text[:end] + newline + "\t\t" + clone + text[end:])

    # -- read the written file back, and check it --------------------------------
    back = _read_text(path)
    out["configs"] = re.findall(r'<configuration [^>]*name="([^"]+)"', back)
    ram_block = _config_block(back, _CONFIG)
    flash_block = _config_block(back, _FLASH_CONFIG)
    checks = (("%r is a configuration of its own" % _CONFIG, bool(ram_block)),
              ("the RAM configuration carries %r" % _RAM_SCRIPT,
               _RAM_SCRIPT in ram_block and _FLASHILM_SCRIPT not in ram_block),
              ("the RAM configuration carries the P part script %r" % _MEM_SCRIPT_P,
               _MEM_SCRIPT_P in ram_block and _MEM_SCRIPT not in ram_block),
              ("the RAM configuration keeps %r" % _REGS_SCRIPT, _REGS_SCRIPT in ram_block),
              ("the RAM configuration defines no %r" % _FLASH_DEFINE,
               _FLASH_DEFINE not in ram_block),
              ("the flash configuration is untouched (still %r, %r, %r)"
               % (_FLASHILM_SCRIPT, _MEM_SCRIPT, _FLASH_DEFINE),
               bool(flash_block) and _FLASHILM_SCRIPT in flash_block
               and _MEM_SCRIPT in flash_block and _FLASH_DEFINE in flash_block),
              ("%r is declared twice (storageModule + configuration)" % _CONFIG,
               back.count('name="%s"' % _CONFIG) == 2))
    for label, ok in checks:
        out["checks"].append("%s: %s" % (label, "ok" if ok else "NO"))
        if not ok:
            out["error"] = "read-back: %s" % label
            return out
    out["ok"] = True
    ctx.note("ram: %s -> %s (id %s.ram); configs now %s; dropped %d %r entr(y/ies)"
             % (_FLASH_CONFIG, _CONFIG, flash_id, out["configs"], dropped, _FLASH_DEFINE))
    ctx.note("ram: %s" % "; ".join(out["checks"]))
    return out


def _seed_launch(ctx, plan: Dict[str, Any], name: str) -> Dict[str, Any]:
    """Seed this case's own launch configuration, in the project **and** over the SDK's.

    Two things are written, with identical content, on purpose:

    * `<project>/.launches/<name>_openocd.launch` -- the CCS12 sibling's shape, and where
      a launch configuration belongs;
    * every `<project>/debugConfigs/*.launch` -- the SDK's own flash口径 files, inside
      *this case's copy* of the project.  Measured (T8): `debugConfigs/*.launch` **is**
      registered by the LaunchBar, and which of two same-named files wins was never
      measured -- so leaving the factory's flash口径 file live is a coin flip that would
      hand `launchActive` a launch with no `gs32_cfg_mode` (measured failure:
      `flash init failed`).  Both copies identical removes the coin flip.

    The `gdbServerOther` is built from the measured working argv of the IDE's own
    OpenOCD, and `PROGRAM_NAME` names this configuration's artifact -- nothing on GS32
    resolves `${build_artifact:…}` (fact 5).
    """
    out: Dict[str, Any] = {"ok": False, "error": "", "files": [], "program": "",
                           "gdb_server_other": "", "name": name + _LAUNCH_SUFFIX}
    project = plan["project"]
    program = "%s/%s.elf" % (plan["config"], name)
    gdb_other = ("-c &quot;set dsp_gport 3355&quot; -c &quot;set gs32_telnet_port 4444&quot; "
                 "-c &quot;set gs32_tcl_port 6666&quot; -c &quot;set cJTAG 0&quot; "
                 "-c &quot;set gs32_adapter_serial %s&quot; -c &quot;set gs32_model %s&quot; "
                 "-c &quot;set gs32_cfg_mode 2&quot; -f &quot;%s&quot;"
                 % (plan["serial"], plan["chip"], _OCD_CFG))
    text = (_LAUNCH_TEMPLATE.replace("@GDBOTHER@", gdb_other)
            .replace("@PROGRAM@", program)
            .replace("@PROJECT@", name))
    out["program"] = program
    out["gdb_server_other"] = gdb_other

    targets = [os.path.join(project, ".launches", out["name"] + ".launch")]
    debug_configs = os.path.join(project, "debugConfigs")
    if os.path.isdir(debug_configs):
        targets += sorted(os.path.join(debug_configs, entry)
                          for entry in os.listdir(debug_configs)
                          if entry.endswith(".launch"))
    for path in targets:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _write_text(path, text)
        out["files"].append(path)

    # Read one written file back: a launch that lost its model or its cfg mode is the
    # exact defect this seeding exists for.
    back = _read_text(targets[0])
    for needle, label in (("gs32_cfg_mode 2", "the RAM cfg mode"),
                          ("set gs32_model %s" % plan["chip"], "the part number"),
                          ('value="%s"' % program, "PROGRAM_NAME"),
                          ('key="ilg.gnumcueclipse.debug.gdbjtag.openocd.doDebugInRam" '
                           'value="true"', "doDebugInRam=true"),
                          ('key="ilg.gnumcueclipse.debug.gdbjtag.openocd.doSecondReset" '
                           'value="false"', "doSecondReset=false")):
        if needle not in back:
            out["error"] = "the seeded launch does not carry %s (%r)" % (label, needle)
            return out
    if re.search(r'set gs32_model GS32F03[0-9]+"', back):
        out["error"] = ("the seeded launch still carries a model without the P suffix "
                        "(%r)" % re.search(r'set gs32_model ([A-Z0-9]+)', back).group(1))
        return out
    out["ok"] = True
    ctx.note("launch: seeded %d file(s): %s; PROGRAM_NAME=%s"
             % (len(out["files"]),
                ", ".join(os.path.relpath(path, plan["workspace"])
                          for path in out["files"]), program))
    return out


def _seed_project(ctx, plan: Dict[str, Any], name: str,
                  marker: str) -> Dict[str, Any]:
    """Step 1 -- everything that has to exist while the IDE is **down** (fact 2).

    Wipe the run's own workspace, copy the SDK template into it, apply the R1 overlay,
    author the RAM configuration and seed the launch configuration.  All of it before
    `ctl install`: a project dropped into a live workspace is never registered, and a
    live IDE holds the workspace lock.
    """
    out: Dict[str, Any] = {"ok": False, "error": "", "wipe": None, "overlay": None,
                           "ram": None, "launch": None}
    wipe = _wipe_workspace(ctx, plan)
    out["wipe"] = wipe
    if wipe["error"]:
        out["error"] = wipe["error"]
        return out
    try:
        shutil.copytree(plan["template"], plan["project"])
    except OSError as exc:
        out["error"] = ("could not copy %s -> %s: %r"
                        % (plan["template"], plan["project"], exc))
        return out
    ctx.note("seed: workspace=%s project=%s (copied from %s)"
             % (plan["workspace"], plan["project"], plan["template"]))

    overlay = _overlay(ctx, plan["project"], marker)
    out["overlay"] = overlay
    if not overlay["ok"]:
        out["error"] = "overlay: %s" % overlay["error"]
        return out

    ram = _ram_config(ctx, plan["project"], name)
    out["ram"] = ram
    if not ram["ok"]:
        out["error"] = "RAM configuration: %s" % ram["error"]
        return out

    launch = _seed_launch(ctx, plan, name)
    out["launch"] = launch
    if not launch["ok"]:
        out["error"] = "launch configuration: %s" % launch["error"]
        return out

    out["ok"] = True
    return out


def _config_block(text: str, config: str) -> str:
    """The `<cconfiguration>` element whose embedded `<configuration>` is `config`.

    CDT writes one such element per configuration, and after `_ram_config` the file
    declares two: the callers below must not mix their `-D`/`-I` sets, nor clone the
    wrong one.  `""` means no element declares that configuration.
    """
    for found in re.finditer(r'<cconfiguration [^>]*id="([^"]+)"', text):
        end = text.find("</cconfiguration>", found.start())
        if end < 0:
            continue
        end += len("</cconfiguration>")        # the element, closer included: a slice
        block = text[found.start():end]        # that stopped short of the closer would
        if re.search(r'<configuration [^>]*name="%s"' % re.escape(config), block):
            return block
    return ""


def _cproject_flags(project: str, studio: str, config: str) -> Dict[str, Any]:
    """The *built configuration's* own `-I` and `-D` sets, read from the `.cproject`.

    Read rather than invented: the IDE's own answer is the only defensible set for a
    syntax pre-check, and it is what makes "10 include dirs" a measurement.  Values
    carry Eclipse macros (`${GS32_DRIVER_PATH}`, `${ProjDirPath}`, `${eclipse_home}`),
    expanded here against the `.cproject`'s own `stringMacro` table.

    Scoped to the configuration that will be built, not to the whole file: after
    `_ram_config` the file declares **two** configurations, and reading both would hand
    the pre-check a superset -- including the flash configuration's `-D FLASH_TARGET`,
    which the RAM build does not define.  A pre-check that compiles the wrong `#ifdef`
    branch is worse than no pre-check.
    """
    path = os.path.join(project, ".cproject")
    out: Dict[str, Any] = {"includes": [], "defs": [], "error": "", "scope": config}
    if not os.path.isfile(path):
        out["error"] = "no .cproject at %s" % path
        return out
    text = _read_text(path)
    scoped = _config_block(text, config)
    if not scoped:
        out["error"] = ("the .cproject declares no %r configuration, so the pre-check "
                        "cannot read the flags it would be built with" % config)
        return out
    text = scoped
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
    flags = _cproject_flags(project, studio, plan["config"])
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
    ctx.note("syntax: config=%s rc=%s include_dirs=%d defs=%d errors=%d"
             % (flags.get("scope"), run["rc"], len(flags["includes"]),
                len(flags["defs"]), len(out["errors"])))
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


def _shape(response) -> str:
    return "%s (%d lines)" % (response.status_line, len(response.lines))


def _ran(response, command_id: str) -> bool:
    """Did the frame carry `OK executed <command id>` **and** no `dialog=` line?

    That pair is R4's criterion.  The confirmation line says the handler ran; the
    absence of a `dialog=` line says the IDE did not raise a modal on the way.
    Measured on the sibling target: a `Resume` answered `OK executed …Resume` **and**
    `dialog=appeared "Run Control not available"` in the same frame -- the handler ran,
    the target was never released, and the frame's own words are what says so.
    """
    lines = [line.strip() for line in (response.raw or "").splitlines()]
    if any(line.startswith(_DIALOG_MARK) for line in lines):
        return False
    return any(line.startswith(_OK_MARK + command_id) for line in lines)


def _ask(ctx, request: str, out: Dict[str, Any]):
    """One bridge request whose loss is *recorded*, never raised.

    A mid-conversation socket reset -- the IDE dies, the port closes -- arrives as a
    bare `OSError`: `Client.talk` wraps only the connect, not the read (measured on the
    sibling target: `unexpected: ConnectionResetError(10054)` aborted a whole case run,
    and the verdict never named the stage that failed).  The load stage must *report*
    that state, so the failure becomes a not-ok `Response` plus a `transport_error` on
    the load record, and the verdict names it.
    """
    try:
        return ctx.request(request)
    except (CtlError, OSError) as exc:
        out["transport_error"] = "%s -> %r" % (request, exc)
        ctx.note("load: %s failed at the transport level: %r" % (request, exc))
        return Response("ERR internal load transport (%r)" % (exc,))


def _start(ctx, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Step 5 -- bring the instance up on the workspace this case just seeded.

    `--keep-workspace` is the whole point: `ctl install` empties the workspace by
    default, and the seed has to survive into the IDE (a project dropped into a live
    workspace is never registered -- fact 2).  The requested port is passed through, so
    the port `pre` guarded is the port opened: on a machine where several runs share the
    default port, letting `install` pick its own is not isolation.
    """
    out: Dict[str, Any] = {"rc": None, "text": "", "error": ""}
    argv = ["install", "--target", ctx.target.name, "--run-id", ctx.run_id]
    port = getattr(ctx.runner, "port", None)
    if port:
        argv += ["--port", str(port)]
    argv.append("--keep-workspace")
    run = _run_ctl(argv, _INSTALL_TIMEOUT)
    out["rc"] = run["rc"]
    out["text"] = str(run["text"])
    for line in _tail(out["text"], 15).splitlines():
        ctx.note("install| " + line)
    if run["rc"] != 0:
        out["error"] = "install rc=%s" % run["rc"]
    return out


def _load(ctx, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Step 6 -- make GS32_Studio load and run OUR image, and judge the answer's shape.

    The three readings, in this order (each one is a measured requirement):

    1. **the negative control**: a `Resume` *before* any launch has nothing suspended
       (measured on the sibling: `ERR disabled`), so recording that shape is what makes
       the `OK` below mean anything;
    2. **`launchActive`** -- it answers `OK` as soon as the launch *starts*, and the
       answer is identical whether the IDE moved or not (fact 5's T1).  So the Resume is
       held until the instance's own jobs go idle (`sys.wait jobs-idle`, a bridge
       **method** taking no argument; an exhausted budget is a normal `OK` with
       `idle=false`, never `ERR timeout`);
    3. **`Resume`** -- R4's criterion is the result word **plus** `OK executed
       <command id>` and **no `dialog=` line** (`_ran`).  `ERR disabled` after the launch
       means nothing was suspended (the launch produced no usable session, or it is still
       in flight), so it is retried for a bounded window and then fails naming that state
       -- the case never invents "still halted".

    The **effect side** is recorded, never judged: the IDE's own console and its
    `.metadata/.log` are read back, because that is where the measured "clean `OK`, zero
    effect" specimen shows itself (image written to RAM, CPU never entering it).  The
    LaunchBar's mode is re-read for the same reason: a retreat to `run` answers a clean
    `OK` and creates no session at all.
    """
    out: Dict[str, Any] = {"launch": None, "resume": None, "resume_before": None,
                           "wait": [], "console": "", "log_tail": "", "loadbar": None,
                           "transport_error": "", "resume_at": "", "attempts": 0}
    out["loadbar"] = _loadbar_mode(plan["workspace"])
    if out["loadbar"]["error"]:
        ctx.note("load: LaunchBar state not readable -- %s" % out["loadbar"]["error"])
    else:
        ctx.note("load: LaunchBar state %s -> %s (mode %r is required: `run` answers a "
                 "clean OK and creates no session)"
                 % (os.path.basename(out["loadbar"]["path"]),
                    out["loadbar"]["modes"] or "<no descriptor claimed>",
                    _LAUNCHBAR_DEBUG))

    out["resume_before"] = _ask(ctx, "cmd.run " + _CMD_RESUME, out)
    ctx.note("load: %s (before the launch, the negative control) -> %s"
             % (_CMD_RESUME, _shape(out["resume_before"])))

    out["launch"] = _ask(ctx, "cmd.run " + _CMD_LAUNCH_ACTIVE, out)
    ctx.note("load: cmd.run %s (Eclipse command id, = the human's F11) -> %s"
             % (_CMD_LAUNCH_ACTIVE, _shape(out["launch"])))

    for _round in range(_LOAD_LAUNCH_WAIT_ROUNDS):
        wait = _ask(ctx, "sys.wait jobs-idle", out)
        out["wait"].append(_shape(wait))
        if "idle=true" in (wait.raw or ""):
            break
    ctx.note("load: waited for the launch's own jobs: %s"
             % " / ".join(out["wait"]))

    resume = None
    for attempt in range(_LOAD_RESUME_ATTEMPTS):
        resume = _ask(ctx, "cmd.run " + _CMD_RESUME, out)
        out["attempts"] = attempt + 1
        ctx.note("load: cmd.run %s (Eclipse command id, = the human's F8) attempt %d -> %s"
                 % (_CMD_RESUME, attempt + 1, _shape(resume)))
        if _ran(resume, _CMD_RESUME):
            break
        time.sleep(_LOAD_RESUME_POLL_S)
    out["resume"] = resume
    out["resume_at"] = time.strftime("%H:%M:%S", time.localtime())

    # -- the effect side, read back (evidence, never a criterion) ----------------
    console = _ask(ctx, "ui.console --tail %d" % _LOAD_CONSOLE_TAIL, out)
    out["console"] = console.raw or ""
    for line in out["console"].splitlines():
        if line.strip():
            ctx.note("console| " + line.strip())
    log = os.path.join(plan["workspace"], ".metadata", ".log")
    if os.path.isfile(log):
        # Read the bytes and decode leniently: Eclipse's `.log` carries whatever the
        # plugins wrote, and a single undecodable byte must not turn the verdict into an
        # exception (this read is evidence, not a gate).
        with open(log, "rb") as handle:
            blob = handle.read()
        out["log_tail"] = _tail(blob.decode("utf-8", errors="replace"), 25)
        for line in out["log_tail"].splitlines():
            if line.strip():
                ctx.note("ide.log| " + line.strip())
    else:
        ctx.note("load: the IDE wrote no %s -- the launch left no log either way" % log)
    return out


def _stop(result: Dict[str, Any], ctx, link: str, why: str) -> Dict[str, Any]:
    """Record that `link` is red and that everything after it was deliberately not run.

    Short-circuiting is load-bearing twice over: the launcher must not be invoked for a
    payload that cannot compile (GS32_Studio pops a **modal error box on the operator's
    desktop** whenever its JVM exits non-zero), and the launch must not be issued against
    an image that is not this run's -- `launchActive` would happily load whatever is
    registered, and a stale artifact would make the human segment about the wrong payload.
    """
    result["blocked"] = (result.get("blocked") or []) + [link]
    result["stopped_at"] = link
    result["not_run"] = ("%s is red -- the steps after it were NOT run (%s)" % (link, why))
    ctx.note("chain: %s is red; stops here -- %s" % (link, why))
    return result


# --------------------------------------------------------------------------- #
# The action
# --------------------------------------------------------------------------- #

def _action(ctx):
    plan = ctx.board_plan
    name = plan["project_name"]
    marker = _MARKER_PREFIX + uuid.uuid4().hex[:8]
    result: Dict[str, Any] = {"errors": list(plan["errors"]), "plan": plan,
                              "name": name, "marker": marker, "run": ctx.run_id,
                              "project": plan["project"],
                              "config": plan["config"], "chip": plan["chip"],
                              "started_at": time.time(), "seed": None, "not_run": ""}
    ctx.note("action: run=%s project=%s config=%s chip=%s marker=%s (workspace=%s)"
             % (ctx.run_id, name, plan["config"], plan["chip"], marker,
                plan["workspace"]))

    # The seed below needs the workspace to itself.  `pre` already stopped this run's
    # leftover instance; this second call is harmless (`uninstall` returns 0 when there
    # is nothing to stop) and covers the case where something came up in between.
    result["stop"] = _stop_instance(ctx, plan)

    result["seed"] = _seed_project(ctx, plan, name, marker)
    seed = result["seed"]
    if not seed["ok"]:
        # No gate is reached at all; `_expect` names the seed failure explicitly.
        result["blocked"] = ["seed"]
        result["not_run"] = "the seed did not land: %s" % seed["error"]
        ctx.note("chain: seed is red; stops here -- %s" % seed["error"])
        return result

    # The chain is strictly ordered and each link gates the next: a payload the syntax
    # pre-check catches must never reach the **launcher** (modal error box on the
    # operator's desktop), and an artifact that is not this run's must never reach the
    # **launch**.  The gate is a local list, deliberately **not** `result["errors"]`:
    # `_expect` is the single place that words each failed predicate, so nothing is
    # reported twice.
    result["syntax"] = _syntax_check(ctx, plan, plan["project"])
    syntax = result["syntax"]
    if syntax["available"] and syntax["rc"] != 0:
        return _stop(result, ctx, "syntax",
                     "the syntax pre-check is red, so the launcher is NOT invoked (a "
                     "payload that fails here would otherwise pop a modal error box on "
                     "the operator's desktop)")

    result["build"] = _build(ctx, plan, plan["project"], name)
    build = result["build"]
    if (build["rc"] != 0 or build["timed_out"] or build["summary"] is None
            or build["errors"] != "0" or build["compiler_errors"]):
        return _stop(result, ctx, "build",
                     "the build is red, so its output is not this run's image")

    result["artifact"] = _artifact(ctx, plan, plan["project"], name, marker,
                                   result["started_at"])
    art = result["artifact"]
    if not art["path"] or art["stale"] or art["marker_offset"] < 0:
        return _stop(result, ctx, "artifact",
                     "the linked image is missing, older than this run, or does not "
                     "carry this run's marker (%s@%s)"
                     % (art["marker_encoding"] or "-", art["marker_offset"]))

    # The workspace has been seeded and built with the IDE down (fact 2); only now does
    # an instance come up on it, and only then is the bridge spoken to.
    result["start"] = _start(ctx, plan)
    start = result["start"]
    if start["error"]:
        return _stop(result, ctx, "start",
                     "the instance did not come up, so there is no IDE to drive (%s)"
                     % start["error"])

    result["load"] = _load(ctx, plan)
    load = result["load"]
    if load["transport_error"]:
        return _stop(result, ctx, "load",
                     "the bridge conversation died (%s) -- the load stage's transport "
                     "failure is reported, never raised" % load["transport_error"])
    if not _ran(load["launch"], _CMD_LAUNCH_ACTIVE):
        return _stop(result, ctx, "load",
                     "the launch command did not carry the confirmation line %r"
                     % (_OK_MARK + _CMD_LAUNCH_ACTIVE))
    if not _ran(load["resume"], _CMD_RESUME):
        return _stop(result, ctx, "load",
                     "the Resume did not carry the confirmation line %r after %d "
                     "attempt(s)" % (_OK_MARK + _CMD_RESUME, load["attempts"]))

    # The one link no tool here can read back.  It is a REQUEST, not a criterion: it is
    # emitted only once every machine-checkable link is green, and it is never allowed to
    # stand in for one.  The measured caveat is stated in the note itself, because the
    # "clean OK, zero effect" specimen had every machine link green.
    ctx.note("ASK THE HUMAN: every machine-checkable link is green -- the run's project "
             "(LED1=GPIO24/U4 pin 80, LED2=GPIO21/U4 pin 79) was built as %s with 0 "
             "errors, %s carries this run's marker %s, and GS32_Studio's own launch "
             "answered %r then %r with no dialog -- now look at the board: LED1 (RUN1) "
             "and LED2 (ERR1) must ALTERNATE -- exactly ONE lit at a time, switching "
             "every ~250 ms -- and they are ACTIVE LOW (lit = driven low).  Both lit at "
             "once, or neither, means the payload is wrong (not the board).  The bridge "
             "answer alone is NOT proof the CPU entered the payload: a clean OK with zero "
             "effect is a measured shape (the image lands in RAM and the PC stays in "
             "flash), so the console/ide.log lines above are the effect side and the "
             "human segment is the only thing that closes it.  This case cannot read back "
             "whether the LEDs are chasing."
             % (plan["config"], os.path.basename(art["path"]), marker,
                _OK_MARK + _CMD_LAUNCH_ACTIVE, _OK_MARK + _CMD_RESUME))
    return result


# --------------------------------------------------------------------------- #
# Judgement
# --------------------------------------------------------------------------- #

def _expect(ctx, result) -> Tuple[bool, str]:
    problems: List[str] = list(result.get("errors") or [])

    seed = result.get("seed") or {}
    syntax = result.get("syntax") or {}
    build = result.get("build") or {}
    art = result.get("artifact") or {}
    load = result.get("load") or {}
    marker = result["marker"]

    if not seed.get("ok"):
        # The seed is this case's own fixture: nothing downstream ran at all, so this is
        # the one place its failure is worded (the chain stopped and said so as well).
        return verdict(problems + ["seed: %s" % (seed.get("error") or "did not land")],
                       "project=%s marker=%s seed=FAILED" % (result["name"], marker))

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
        order = ("seed", "syntax", "build", "artifact", "start", "load")
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

    if not reached("load") or not load:
        problems.append("load: not reached -- the chain stopped at %s"
                        % (result.get("stopped_at") or "<no chain stop recorded>"))
    else:
        if load.get("transport_error"):
            problems.append("load: the bridge conversation died (%s)"
                            % load["transport_error"])
        if not _ran(load.get("launch") or Response(""), _CMD_LAUNCH_ACTIVE):
            problems.append(
                "load: cmd.run %s came back %s, and R4's criterion is a line %r with no "
                "%r line in the same frame"
                % (_CMD_LAUNCH_ACTIVE,
                   _shape(load["launch"]) if load.get("launch") else "<not sent>",
                   _OK_MARK + _CMD_LAUNCH_ACTIVE, _DIALOG_MARK))
        if not _ran(load.get("resume") or Response(""), _CMD_RESUME):
            problems.append(
                # This text is prose; the problems are counted where the list is built
                # (`ExpectLedgerTest._red` captures them), so an internal `"; "` is
                # harmless -- it is only the human-readable join that would blur.
                "load: cmd.run %s did not run in %s attempt(s) -- last answer %s.  The "
                "criterion is a line %r with no %r line in the same frame.  A bare "
                "`ERR disabled` cannot separate 'the launch produced no usable session' "
                "from 'the target is already running', so this reads as 'could not "
                "certify the target was released', never 'the target is not running'"
                % (_CMD_RESUME, load.get("attempts", 0),
                   _shape(load["resume"]) if load.get("resume") else "<not sent>",
                   _OK_MARK + _CMD_RESUME, _DIALOG_MARK))
        modes = (load.get("loadbar") or {}).get("modes") or {}
        # NB: `modes` values are the bare mode word (`_loadbar_mode` keeps only the text after
        # the last `=`) -- a comparison against the `activeLaunchMode=run` file-line spelling
        # would always be False and would leave a retreat to `run` green (caught 2026-10-11).
        ran_mode = sorted(name for name, mode in modes.items()
                          if mode == _LAUNCHBAR_MODE_RUN)
        if ran_mode:
            # Fact 6: in `run` mode `launchActive` answers a clean `OK` and creates no
            # debug session at all, so a confirmation line cannot be read as a load.
            problems.append(
                "load: the LaunchBar's active mode is `run` for %s -- in run mode "
                "`launchActive` is accepted with a clean answer and no session is ever "
                "created (measured), so the answer above cannot be read as a load"
                % ", ".join(ran_mode))
        elif not modes and not (load.get("loadbar") or {}).get("error"):
            problems.append(
                "load: the LaunchBar state file was read and names no descriptor, so its "
                "active mode could not be pinned to %r (fact 6) -- the file is %s"
                % (_LAUNCHBAR_DEBUG, (load.get("loadbar") or {}).get("path")))

    return verdict(problems, _detail(result))


def _detail(result) -> str:
    art = result.get("artifact") or {}
    build = result.get("build") or {}
    seed = result.get("seed") or {}
    ram = seed.get("ram") or {}
    launch = seed.get("launch") or {}
    load = result.get("load") or {}
    readelf = art.get("readelf") or {}
    plan = result.get("plan") or {}
    hardware = plan.get("hardware") or {}
    modes = (load.get("loadbar") or {}).get("modes") or {}
    return ("target=gs32 project=%s config=%s chip=%s run=%s | machine: ram_config=%s "
            "launch=%s build=%r rc=%s readelf=%s/%s elf=%s size=%s e_machine=%s "
            "marker=%s launchActive=%s resume=%s loadbar_mode=%s | auxiliary: "
            "channels=A:%s/B:%s | human=awaiting-operator (LED1/LED2 alternating is NOT "
            "machine-checkable here and is not part of this verdict)"
            % (result["name"], result["config"], result["chip"],
               result.get("run") or "<unknown>",
               ("%s cfgs=%s" % (ram.get("id") or "<not cloned>",
                                ",".join(ram.get("configs") or []) or "-"))
               if ram else "<not reached>",
               ("%s" % ", ".join(os.path.basename(path)
                                 for path in launch.get("files") or []))
               if launch else "<not reached>",
               build.get("summary"), build.get("rc"),
               readelf.get("elf_class"), readelf.get("machine"),
               os.path.basename(art["path"]) if art.get("path") else "<missing>",
               art.get("size"), (art.get("elf") or {}).get("machine"),
               ("%s@%s" % (art.get("marker_encoding"), art.get("marker_offset")))
               if art.get("marker_offset", -1) >= 0 else False,
               _ran(load["launch"], _CMD_LAUNCH_ACTIVE) if load.get("launch") else "n/a",
               _ran(load["resume"], _CMD_RESUME) if load.get("resume") else "n/a",
               ",".join("%s=%s" % (name.split(":")[-1], mode)
                        for name, mode in sorted(modes.items())) or "<unread>",
               (hardware.get("attach") or {}).get("state"),
               (hardware.get("pnp") or {}).get("state")))


# --------------------------------------------------------------------------- #
# Cleanup
# --------------------------------------------------------------------------- #

def _cleanup(ctx, label: str) -> str:
    """Remove this case's footprint from the run -- but **never under a live IDE**.

    Measured on the sibling target, the hard way: deleting the project directory while
    the instance that opened the workspace is still running leaves Eclipse's serialized
    resource tree pointing at a project whose `.project` is gone, and the *next* startup
    raises a blocking `Refreshing workspace` / `Problem Occurred` modal -- which blocks
    the UI thread, so the next launch never completes.

    So: with a live instance the project is left where it is (it *is* what the debug
    session is showing, and the running program lives in target RAM), and the next
    invocation wipes the whole workspace -- after having stopped that instance (`pre`).
    With no live instance the seed is removed here, together with its workspace registry
    entry.  The run itself is never deleted: `ctl uninstall` is the operator's door, and
    this case leaves its instance up so `verify --all` can keep going.
    """
    plan = getattr(ctx, "board_plan", None)
    if not plan:
        return "nothing was created"
    if getattr(ctx, "board_cleaned", False):
        return "already cleaned"
    ctx.board_cleaned = True
    name = plan.get("project_name") or _PROJECT
    workspace = plan.get("workspace") or ""
    project = os.path.join(workspace, name) if workspace else ""
    run_dir = os.path.dirname(ctx.paths.endpoint) if ctx.paths else ""
    live = run_live_pid(run_dir) if run_dir else None
    if live:
        ctx.note("%s instance pid %s is still running on this workspace, so the seeded "
                 "project is left in place (deleting it under a live IDE makes the next "
                 "startup raise a blocking 'Refreshing workspace' modal); the next "
                 "invocation stops that instance and empties the whole workspace; the "
                 "run is removed with `python -m ctl uninstall --target %s --run-id %s`"
                 % (label, live, ctx.target.name, ctx.run_id))
    elif project:
        shutil.rmtree(project, ignore_errors=True)
        registry = os.path.join(workspace, ".metadata", ".plugins",
                                "org.eclipse.core.resources", ".projects", name)
        shutil.rmtree(registry, ignore_errors=True)
        ctx.note("%s no live instance: seeded project removed=%s (%s)"
                 % (label, not os.path.isdir(project), project))
    if plan.get("killed"):
        ctx.note("%s timed-out child process trees killed: %s"
                 % (label, "; ".join(plan["killed"])))
    return "live=%s project=%s removed=%s" % (
        live or "none", project or "<none>",
        bool(project) and not os.path.isdir(project))


def _rollback(ctx):
    """A failed case cleans up the same way (never under a live instance)."""
    return _cleanup(ctx, "rollback:")


def _post(ctx):
    return _cleanup(ctx, "post:")


CASE = Case(
    name="board.led.chase.gs32",
    group="realflow",
    targets=("gs32",),
    description=("the GS32 sibling of board.led_chase: seed the run's own workspace with "
                 "the SDK template overlaid (LED1=GPIO24 / LED2=GPIO21) and a RAM build "
                 "configuration, build it through GS32_Studio's own Eclipse application "
                 "with -data pointing at that workspace, bring the instance up on it, then "
                 "load and run it through the bridge (launchActive -> Resume); the LED "
                 "chase itself is confirmed by a human"),
    pre=_pre,
    action=_action,
    expect=_expect,
    post=_post,
    rollback=_rollback,
    # NOT "this case does not drive the bridge": it drives it for the load and the run.
    # The flag means the runner must not *require* a live bridge before `pre` -- this
    # case seeds and builds the workspace with the IDE down (fact 2) and brings its own
    # instance up, exactly like the CCS12 sibling.  `ctx.request` connects lazily.
    requires_bridge=False,
    # Nothing here is judged by the screen: the verdict is the build log, the linked
    # image's bytes, and the shape of the bridge's own answers.  The IDE is driven, but
    # never through the screen.
    screen_guard=False,
    evidence=("raw:action", "build:log", "artifact:probe"),
)
