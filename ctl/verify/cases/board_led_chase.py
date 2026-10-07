"""board.led_chase -- the first hardware case: build OUR payload, load it, let it run.

What is verified: a real C2000 board (a DSP280025 Lite with an on-board XDS100v2
probe) is made to run a program this case builds from scratch, and the *machine
checkable* half of that chain is judged by the case; the second half (three LEDs
chasing) is printed as an explicit request for a human to confirm.

FOUR SCOUT ANSWERS (S0 -- each one is a measured fact, with the command that
produced it; nothing here is inferred)

1. **How the existing end-to-end case creates / builds** -- `cases/realflow_build_artifact.py`
   ``:_RECIPES`` (ccs12 entry) and ``:_create``/``:_build``/``:_artifact``:
   the scratch tree is ``<run_root>/<run_id>/realflow`` (``:_pre``), the project is
   produced by ``eclipsec.exe -noSplash -data <ws> -application
   com.ti.ccstudio.apps.projectCreate -ccs.projectSpec <spec>`` (``:_RECIPES``
   ``create_argv``), built by ``... -application com.ti.ccstudio.apps.projectBuild
   -ccs.projects <name> -ccs.configuration <config> -ccs.buildType full``
   (``build_argv``), judged by ``rc`` plus ``_elf_header`` / ``_find_marker``
   (``:_expect``).  This case keeps that shape (same argv spellings, same
   ELF-header and marker predicates) and adds what a board case needs: a SysConfig
   overlay, a launch configuration, a bridge-driven load, and a probe probe.
2. **The generated main file** -- run
   ``eclipsec -application com.ti.ccstudio.apps.projectCreate -ccs.projectSpec
   <.../empty_driverlib_project.projectspec>`` and the project root holds
   ``empty_driverlib_main.c`` (3001 B) + ``c2000.syscfg`` (**0 B**).  Both come from
   the spec's last two copy rows (``<file action="copy" path="../empty_driverlib_main.c"
   targetDirectory=""`` / ``../c2000.syscfg``); measured 2026-10-07 in
   ``.../runs/ccs12-e2e/probe/m1``.  ``-ccs.name <n>`` renames the project (measured).
3. **Where a ``.launch`` must live, and why the project must be in the IDE's
   workspace** -- ``<project>/.launches/<config>.launch``, and the project must be
   *registered in the workspace the IDE opened*: a project dropped into a running
   IDE's workspace is never seen (measured: no ``.metadata/.plugins/
   org.eclipse.core.resources/.projects/<name>/`` entry, no launchbar descriptor,
   after a ``.launch`` was written next to it -- ``probe/probe_vis.py``), and a
   second JVM cannot seed it either: ``projectCreate -data <live ws>`` fails with
   ``Workspace location '...' is in use or cannot be created`` (measured, rc 1).
   There is no headless import command in the registry (``cmd.list``: 807 ids;
   ``org.eclipse.e4.ui.importer.openDirectory`` / ``...configureProject`` are
   wizards, and the bridge has no text input).  => the project is seeded into the
   *run's* workspace **before** the IDE starts and the IDE is started with
   ``--keep-workspace`` -- the pattern ``ctl/lifecycle.py:install`` documents.
4. **Probe in place** -- two INDEPENDENT channels, and the *attachment* question is
   answered only by the second one:

   * ``<install_dir>/ccs_base/common/uscif/xds100serial.exe`` prints a device table.
     An ``XDS100`` row in it is evidence the tool can **see** the probe -- it is
     **not** evidence the probe is attached, and a *missing* row is not evidence it
     is gone.  Measured 2026-10-07, same machine, **driver binding unchanged across
     the A/B** (``Get-PnpDevice -PresentOnly`` reported
     ``USB\\VID_0403&PID_A6D0&MI_00\\8&1A7F3620&0&0000`` under class ``TI_Debug_Probe``
     in *both* states, so the cause is the held handle, not a rebind):

         # instance ccs12-p42 alive (pid 31160; it had run a debug session):
         VID/PID    Type            Serial #    Description
         0403/6010  generic FT2232  GJBDRPSS    USB <-> Serial Converter

         # same instance stopped via `python -m ctl uninstall --target ccs12
         #   --run-id ccs12-p42 --verify-clean`:
         VID/PID    Type            Serial #    Description
         0403/6010  generic FT2232  GJBDRPSS    USB <-> Serial Converter
         0403/a6d0  XDS100v1/v2     USB100V2    Texas Instruments Inc.XDS100 Ver 2.0

     A live **debug session** keeps the probe's FTDI handle open, so the tool cannot
     enumerate it at all.  (A fresh, session-less instance does not: measured
     2026-10-07, row present while ``ctl install --run-id <tmp>`` was live.)
   * ``_probe_present()`` asks Windows itself -- ``Get-PnpDevice``, the read-only PnP
     query -- for a present device whose hardware id contains
     ``VID_0403&PID_A6D0``.  That channel answers whether or not an instance holds
     the probe.

   So ``rows == 1`` has **two** causes -- probe physically absent, or probe held by a
   live debug session -- and the verdict is three-valued: an ``XDS100`` row => go on;
   else OS-absent => **SKIP**; else OS-present => **SKIP** naming the held handle
   (and this is why ``_pre`` stops *this run's own* leftover instance before it reads
   the tool at all); else the OS query failed => **SKIP** saying it cannot tell --
   never "absent".

PREREQUISITES -- a fresh clone has none of these.  Measured 2026-10-07 by cloning into
an empty directory and pointing ``USERPROFILE`` at an empty home (no config, no runs, no
bridge jar), i.e. a new machine's state:

    git clone <repo> eclipse-ctl && cd eclipse-ctl
    python -m ctl targets add ccs12 --source-dir <your .../ccs/eclipse>  # only when the
        # built-in reference value is not yours; `targets list` prints the value in use
    python -m ctl build --target ccs12                                   # `bridge/dist/`
        # is gitignored, so a fresh clone has no jar and `install` stops with
        # `no bridge jar built yet`

**Hardware and SDK, which no command can install** -- a fresh machine has these only if
someone plugged them in:

  * a **TMS320F280025C** (the DSP280025 Lite board) on the desk;
  * an **XDS100v2** probe, *attached and not held by another live debug session* (it is
    exclusive: a running session blanks it from the enumeration entirely);
  * a **C2000Ware** tree carrying the ``f28002x`` family, derived from the target's own
    ``install_dir`` or pointed at with ``ECLIPSE_CTL_BOARD_C2000WARE``.

Absent any of the three the case **SKIPs, never FAILs**, and the verdict line names which
one -- ``no C2000Ware root carrying the 'f28002x' family``, ``no XDS100 probe attached``,
or the probe ``IS attached but … cannot enumerate it`` (held).  A SKIP here is therefore a
statement about the bench, not about the code.

Then the RERUN below.  Measured **twice** from that exact state (2026-10-07, same machine):
``rc=0`` both times, and both stopped at the ASK THE HUMAN line (machine-checkable segment
green).  Wall clock was **113.6 s** and **229.4 s** -- a **2x spread**, so the duration is a
*stock* number: quote it with its own measurement, never use it as a threshold
(``measurement-hygiene`` 13.9).

Read the **verdict line**, not ``rc``: a SKIP -- no ``--run-id`` yet, no probe, or the
port held by another run -- also exits ``0``.  ``ctl verify`` uses ``0`` for "nothing
failed", which includes "nothing ran"; ``--json`` carries ``passed``/``skipped``.

Every SKIP this case can raise, so a verdict line is never a mystery (all exit ``0``):

| verdict begins with | means | do this |
|---|---|---|
| ``no run directory to seed`` | no ``--run-id`` passed | pass one (below) |
| ``skipped: not applicable to target`` | wrong ``--target`` -- this case only runs on ``ccs12`` | ``--target ccs12`` |
| ``no C2000Ware root carrying the 'f28002x' family`` | no C2000Ware tree reachable from the target | install C2000Ware, or point ``ECLIPSE_CTL_BOARD_C2000WARE`` at one |
| ``the run's workspace registers <project>`` | that run id already holds somebody's project | pick a run id you have not seeded into |
| ``no XDS100 probe attached`` | the OS PnP table has no ``VID_0403&PID_A6D0`` | plug the probe in |
| ``the XDS100 probe IS attached but … cannot enumerate it`` | probe present, held by a live debug session (exclusive) | stop that session |
| ``cannot determine whether the XDS100 probe is attached`` | the PnP query itself did not answer | read the named channel; this case will not call it "absent" |
| ``port <N> is held by another run`` | another instance owns the launch port | stop that run |

RERUN (from the product repo; ~2-4 min, it brings the instance up itself):

    python -m ctl verify --case board.led_chase --target ccs12 --run-id board-<ts>

The run id must name a run whose workspace registers no project yet -- you do **not**
``ctl install`` first (the case brings the instance up itself): pick a run id you have
never used, or one this case already cleaned.  A run with a foreign project
SKIPs with that instruction rather than launching somebody else's configuration.
Two more measured preconditions, both reported as an actionable SKIP instead of a
silent wrong answer:

* the launch port must be free *or* already held by this same run (the case stops
  that instance and restarts it on the wiped workspace).  A port held by *another*
  run SKIPs -- the XDS100 is exclusive and this case must own the instance that
  opens it.
* ``ctl verify --all`` needs a live bridge for the other 26 cases
  (``ENV-NOT-READY`` otherwise): ``ctl install --target ccs12 --run-id <id>``
  first.  This case itself is ``requires_bridge=False`` and will start the
  instance; the others are not.

WHY THIS CASE STARTS THE INSTANCE ITSELF (``requires_bridge=False``)
====================================================================
Everything that must be true *before* the IDE starts (the projectspec-generated
project, the SysConfig-generated pin mux, the launch configuration, the
``${build_artifact:...}`` image) can only be put in place while the workspace is
not held by a running IDE -- see scout 3, measured.  So the case owns its fixture
the way ``input.f_fixture`` owns its product: ``pre`` resolves the environment
and the preconditions (SKIP/FAIL boundary in ``design.md`` §5), ``action`` seeds
the workspace, builds, starts the instance, and only then drives the bridge.
``ctx.request`` connects lazily, so the unconnected ``pre`` is not a problem.

THE THREE HARD POINTS, MEASURED (all 2026-10-07, on this machine)
==============================================================
**H1 -- freshness.** ``${build_artifact:<project>}`` resolves inside the IDE's own
workspace, so the image has to be the one this run built *there*.  The case builds
``CPU1_RAM`` with the TI headless application **before** the instance starts (the
workspace lock is free then: ``projectBuild -data <the run's ws>``), and asserts
the artifact's path, size, mtime (inside this action's window), ``e_machine`` and a
unique marker.  The IDE's own CDT state is read back as well
(``.metadata/.plugins/org.eclipse.cdt.core/<project>.*``) so an ambiguous build
configuration is a FAIL, not a guess.

**H2 -- a launch configuration is not enough.**  Three things must be true for
``launchActive`` to reach *our* image, and each one was caught the hard way:
* the workspace must register **exactly this project** (drop a project into a
  running IDE and nothing notices it: no registry entry, no launchbar descriptor;
  and a second JVM cannot seed one -- ``projectCreate -data <live ws>`` answers
  ``Workspace location '…' is in use or cannot be created``).  Hence: seed while
  the IDE is down, then start the instance with ``--keep-workspace``.
* the **active target configuration** has to be recorded in the workspace.  With the
  ``.launch`` alone the launch stops on a modal -- "*You require a target
  configuration to start a debug session*" -- the target is never loaded and
  ``Resume`` stays ``ERR disabled`` for its whole poll window.  CCS keeps the choice
  in ``.metadata/.plugins/org.eclipse.core.runtime/.settings/
  com.ti.ccstudio.system.setup.prefs`` as
  ``DEFAULT_CCS_TARGET_CONFIGURATION=<abs path to the targetConfigs/*.ccxml>``
  (verbatim from the workspace where the same ``.launch`` shape does launch).  The
  case writes that one key before the instance comes up.
* the LaunchBar descriptor's **active launch mode** has to be ``debug``.  Measured
  2026-10-07: when the LaunchBar builds that state itself it records ``run``, and
  ``LaunchActiveCommandHandler.execute`` is
  ``DebugUITools.launch(config, getActiveLaunchMode().getIdentifier())`` -- so in
  ``run`` mode the command is accepted with a clean answer (no ``dialog=``) and **no
  debug session is ever created**: read at 2 s granularity the perspective **bounces
  back** -- baseline ``TICPerspective`` (5 views) -> ``TIDebugPerspective`` (6 views)
  at T+2 s/T+4 s -> ``TICPerspective`` again from T+6 s (measured 2026-10-07,
  ``research/cross-check-vs-successful-run.md`` §3) -- i.e. it never *settles* in
  debug.  Pre-seeded as ``debug`` (the same key, in the
  same ``_seed``), the identical command put the perspective at
  ``com.ti.ccstudio.TIDebugPerspective`` and held it for 18 s, with the Console
  carrying the target's GEL lines.  The mode is a **precondition**, never a
  criterion: the verdict is still the read-back plus the result words.
  Upstream documents the **concept**, not what this case paid for: Eclipse Help
  *Using the Launch Bar* (**``help.eclipse.org/latest`` -- CDT upstream, NOT the CDT
  doc set shipped with CCS 12.8.1: its ``org.eclipse.cdt.doc.user`` jar carries no
  ``cbs_*`` page at all**, measured 2026-10-07) names both pieces -- "*Run button, to launch a run.  This
  button will change to a Debug button in Debug mode*" and "*Launch mode selector.
  To change between Run and Debug mode*"; Eclipsepedia ``CDT/LaunchBar`` states the
  mechanism in one line -- "*Each descriptor has an active mode and active target.
  This is persisted in preference store*" (which is what `_LAUNCHBAR_PREFS` writes);
  QNX ``launch_modes`` adds "*the launch mode determines ... which perspective is
  opened*".  **None of the three records what this case needed**: that the
  LaunchBar's own default is ``run``, and that in ``run`` ``launchActive`` answers a
  clean ``OK`` with **zero** effect (no ``dialog=``, no error, no session).  The
  stored key *shape* is undocumented as well -- it was read out of three real
  workspaces, per `_LAUNCHBAR_PREFS`.

**H3 -- dialogs, and the probe.**  The XDS100 is exclusive, so the case drives the
same IDE instance that owns it and never starts a second debugger.  Two modal
classes were measured on this machine: a *stale* ``CCS Crash Report``, re-raised at
every start from the debug server's ``Unexpected CCS exit detected [10/1/26,
3:39 PM]`` record, and ``Problem Occurred`` / "*Refreshing workspace*" caused by
deleting the project directory out from under a live IDE (``ResourceException: …
The project description file (.project) for '<project>' is missing``).  So the case
(a) sweeps ``#32770`` dialogs scoped to its instance pid (class + pid, never title)
right after the instance comes up, and (b) never removes the project while an
instance is alive -- the next invocation wipes the whole workspace *after* stopping
that instance.  Leaving them stacked is not cosmetic: a modal blocks the UI thread,
which is what makes a launch hang.

A **third** class belongs to a *fresh* workspace: ``Configuring Debugger (may take a few
minutes on first launch)`` -- measured 2026-10-07 in the isolated-HOME rehearsal (empty
``USERPROFILE``, so every start was a first launch, and it appeared in **both** runs).
It offers four Buttons and none is the affirmative one, so `_modal_row` *refuses* it
(``action=refused``, never pressed); it did not block the load in either rehearsal.

That sweep is for **statements** (error boxes, crash reports), and its disposal is
``WM_CLOSE``, i.e. the window's X.  A dialog that asks a **question** is the exact
opposite case, and the load stage meets one: ``Reuse Debug Settings`` (body
verbatim: *This project has been debugged before.  Do you want to reuse the debug
settings previously set?*), whose ``WM_CLOSE`` is *cancel* and would cancel the very
load the stage is waiting for.  So the load stage answers it -- ``BM_CLICK`` on the
affirmative button -- and the criterion for "is this a question" is the dialog's own
**Button children**, not its title.  The third shape on that path has no buttons at
all: the progress shell ``Loading Program: …<project>/CPU1_RAM/*.out``, which is
waited out and never closed.  `_answer_load_modal` carries the boundary, the
fail-closed rules and the evidence (frame 114 of a run's shadow archive, replayable
with ``python -m ctl shadow --run-id <run> --seq <n>``).

COMMAND IDENTITY (R6): every command this case sends is named here verbatim.
* `org.eclipse.launchbar.ui.command.launchActive` -- an **Eclipse command id** sent
  through the bridge's ``cmd.run`` (it is *not* a bridge method: the bridge's 16
  methods are listed in ``bridge/src/ctl/bridge/LiveBridge.java:253-297``); it is
  what the human's ``F11`` invokes.  ``cmd.query`` reports it defined+handled
  ("Launch Active Launch Configuration").
* `org.eclipse.debug.ui.commands.Resume` -- an **Eclipse command id** through
  ``cmd.run`` as well (the human's ``F8``).  Measured before 2026-10-07: without a
  live debug session it answers ``ERR disabled``; with one it answers ``OK``.
  Both are *scripts over the existing protocol* -- no bridge method was added (R5).
* ``sys.wait jobs-idle`` -- a **bridge method** (read/wait;
  ``bridge/src/ctl/bridge/LiveBridge.java:262`` registers it, ``:683-685`` is the
  implementation): the launch's own completion signal, and it takes **no**
  argument (``sys.wait jobs-idle 180000`` is ``ERR badrequest``; each call uses the
  bridge's own 15 s budget).  An exhausted budget is a normal ``OK`` with
  ``idle=false`` -- never ``ERR timeout`` (``cases/read_wait.py``).
* ``ui.parts`` and ``ui.tree <depth> --shell all`` -- **bridge methods**, both
  read-only: the debug perspective and the Debug view's ``Tree`` item count are
  what the load gate is made of (see ``_wait_for_debug_context``).
* ``eclipsec.exe -application com.ti.ccstudio.apps.projectCreate|projectBuild`` --
  external processes (the TI headless applications), never the bridge.
* The ``python -m ctl uninstall|install`` calls are the CLI's own doors.

Exit-code note (M4/M5): the verdict is never a duration and never "the session came
up" -- it is the *shape of the answer* (``OK`` + 7 lines carrying
``OK executed <id>`` vs ``ERR disabled`` + 5 lines; the design text guessed 5/3
because it counted the payload only, without the status line and ``END``), a
read-back of the perspective, and the bytes of the artifact.

ENVIRONMENT FLAKE, MEASURED (not this case's bug, and not its to fix): the TI
headless applications intermittently exit ``0xFFFFFFFF`` (reported by ``rc`` as
``4294967295``) **while succeeding** -- ``projectCreate`` printed
``Done!`` and left a complete project behind, yet the launcher returned -1, which
the seed step reads as ``projectCreate rc=4294967295`` and FAILs on.  Observed
2026-10-07 on this machine four times (``04:12``, ``04:13`` twice as a seed FAIL
in this case, and ``projectCreate`` alone at ``04:10``/``04:11``), against four
back-to-back manual runs of the identical argv that all returned 0.  Adding
``-consoleLog`` makes the same run exit 0 and shows the framework saying, *after*
``Done!``:
``!ENTRY org.eclipse.core.resources 4 566 !MESSAGE Workspace was not properly
initialized or has already shutdown.`` -- i.e. a shutdown race inside the
launcher, not a refusal to do the work.  A green run therefore must not depend on
luck: if ``seed: projectCreate rc=4294967295`` appears, the create itself
succeeded -- re-run the case (each invocation wipes and reseeds its own workspace).
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

from ... import screen
from ...client import Response
from ...errors import CtlError
from ...lifecycle import REPO_ROOT, list_port_listeners, list_processes, run_live_pid
from ..runner import DIALOG_CLASSES, Case, Skip
from ._util import verdict

# --------------------------------------------------------------------------- #
# Recipe -- every value is an install-relative or a measured fact, never a
# machine-local absolute path; the environment may override each one
# (`ECLIPSE_CTL_BOARD_<KEY>`), mirroring `realflow_build_artifact.py`.
# --------------------------------------------------------------------------- #

ENV_PREFIX = "ECLIPSE_CTL_"
_BOARD_ENV = ENV_PREFIX + "BOARD_"

#: Conventional C2000Ware locations, **relative to a TI install root**.  A target's
#: ``install_dir`` is ``<ti>/ccs<ver>/ccs/eclipse`` and C2000Ware sits beside it
#: (``<ti>/c2000/C2000Ware_<ver>``), so the root is *derived* from the
#: already-resolved target -- see `_c2000ware_candidates`.  Override the whole lookup
#: with ``ECLIPSE_CTL_BOARD_C2000WARE``.  No machine-local literal belongs here: the
#: module header's rule (and `ctl/targets.py`'s `_find_ecj`, same shape) is
#: "install-relative or a measured fact".
_C2000WARE_GLOBS = ("c2000/C2000Ware_*", "C2000Ware_*")

#: Device family directory under ``<C2000Ware>/driverlib``.  Eleven same-named
#: ``empty_driverlib_project.projectspec`` files live under this tree
#: (f280013x/f280015x/f28002x/f28003x/f28004x/f2807x/f2837xd/f2837xs/f2838x/
#: f28p55x/f28p65x) -- picking the wrong one builds another silicon silently, so
#: the family is a *constant* here and the generated device is read back (R2).
_FAMILY = "f28002x"

#: The board's device: 源芯科 DSP280025 Lite (docs/dsp280025/...:8), i.e. the
#: TMS320F280025C.  Frozen on purpose -- this is the *expected* side of R2's
#: read-back, and it must not be re-derived from the file under test (C10).
_EXPECTED_DEVICE = "TMS320F280025C"

#: Where the projectspec for `_FAMILY` sits, relative to the C2000Ware root.
_SPEC_REL = ("driverlib/%s/examples/empty_projects/CCS/"
             "empty_driverlib_project.projectspec" % _FAMILY)

#: The project name we ask `projectCreate` for (``-ccs.name``); the TI spec itself
#: hard-codes ``empty_driverlib_project``.
_PROJECT = "board_led_chase"

#: The launch configuration file.  It is the only one the project declares, and
#: the project is the only one the workspace registers -- together that is the
#: identity of whatever `launchActive` runs.
_LAUNCH_NAME = "ctl_board_chase"

#: The build configuration (first of the four the TI spec declares).
_CONFIG = "CPU1_RAM"

#: Other build configurations of the same project: the case refuses to guess the
#: artifact directory if the IDE's own state names one of these instead (H1).
_OTHER_CONFIGS = ("CPU1_FLASH", "CPU1_LAUNCHXL_RAM", "CPU1_LAUNCHXL_FLASH")

#: EM_TI_C2000 -- the only machine a C2000 artifact may declare.
_MACHINE = 141

#: The unique-per-run marker: ``CTL-BOARD-<8 hex>`` (found as UTF-16LE in the
#: image -- the C2000 compiler's ``char`` is 16 bit; measured 2026-10-07).
_MARKER_PREFIX = "CTL-BOARD-"

#: Placeholder inside the payload.  A plain token, not `str.format`: the fragment
#: contains ``"${build_artifact:...}"``-style braces and C braces.
_MARKER_TOKEN = "@MARKER@"

#: The three pin-mux lines the SysConfig overlay must produce (R4).  They are the
#: gate that separates "the pin mux came from c2000.syscfg" from "somebody wrote
#: it into the payload".
_MUX_LINES = ("GPIO_setPinConfig(GPIO_34_GPIO34)",
              "GPIO_setPinConfig(GPIO_6_GPIO6)",
              "GPIO_setPinConfig(GPIO_7_GPIO7)")

#: Timeouts (seconds).  A cold CCS build compiles the driver library too.
_BUILD_TIMEOUT = 900.0
_CREATE_TIMEOUT = 300.0
_INSTALL_TIMEOUT = 900.0
_PROBE_TIMEOUT = 60.0
_WIPE_ATTEMPTS = 10

#: The launch configuration's probe key, as written in the ccxml the TI spec
#: copies (``targetConfigs/TMS320F280025C.ccxml``); the ``_0`` spelling is the
#: second variant CCS writes and is kept so the same file works either way.
_CCXML = "TMS320F280025C.ccxml"
_PROBE = "Texas Instruments XDS100v2 USB Debug Probe"
_CORE = "C28xx_CPU1"

#: Eclipse command ids driven through the bridge's `cmd.run` (R6).  Neither is a
#: bridge method: the bridge's method table is `bridge/src/ctl/bridge/LiveBridge.java:253-297`.
_CMD_LAUNCH_ACTIVE = "org.eclipse.launchbar.ui.command.launchActive"
_CMD_RESUME = "org.eclipse.debug.ui.commands.Resume"

#: Answer shapes (R7), measured on this machine 2026-10-07 (count =
#: ``raw.splitlines()``: status line + payload + terminating ``END``).
#:
#: * a command that ran: ``OK`` + 7 lines, payload carrying ``OK executed <id>``.
#:   It is 8 when the bridge appends its ``dialog=…`` line (measured: the launch
#:   itself is a modal progress shell, so the shell snapshot times out and the
#:   bridge says so on the same answer) -- hence the OK criterion is a *lower*
#:   bound plus the executed line, not an exact count.
#: * a command whose handler is disabled: ``ERR disabled`` + 5 lines, payload =
#:   the bare handler dump, no executed line.  Measured 5 in every attempt,
#:   dialogs on screen or not.
#:
#: (The design text guessed 5/3 -- payload only, without the status line and END.)
#: Every answer is printed verbatim either way, so a shape change stays visible.
_OK_LINES = 7
_ERR_LINES = 5

#: The bridge's own confirmation line for a command that ran.
_OK_MARK = "OK executed "

#: The bridge's own marker for a dialog it saw appear while a write method ran
#: (`LiveBridge.java:566` for the appeared shape, `:572` for the timed-out one).
#: It is appended *after* the handler's own lines, so one answer can carry both
#: ``OK executed <id>`` and ``dialog=…`` -- "the handler ran" is not "the command
#: took effect".  Measured 2026-10-07 (`runs/board-1007-chk`): a `Resume` answered
#: ``OK`` with ``OK executed org.eclipse.debug.ui.commands.Resume`` **and**
#: ``dialog=appeared "Error"``, and the shadow frame of that very request
#: (`shadow/0005-060436-Error.png`) is a modal whose body reads
#: ``Run Control not available`` -- the target was never released.
_DIALOG_MARK = "dialog="

#: Eclipse's **debug** perspective -- the one `ui.parts` reports once the launch
#: has taken effect.  Measured: the same read-only channel answers
#: ``perspective id=com.ti.ccstudio.TICPerspective label="CCS Edit"`` on an idle
#: instance and ``id=com.ti.ccstudio.TIDebugPerspective label="CCS Debug"`` after
#: a launch that really ran (`run-ram-launch.md` §3, reproduced by the parent's
#: live probe 2026-10-07: a launch with *zero* effect left the perspective at
#: `TICPerspective` for 120 s).
_DEBUG_PERSPECTIVE = "com.ti.ccstudio.TIDebugPerspective"

#: The view whose `Tree` is the debug context's fingerprint.  The bridge's
#: `ui.tree` dumps one line per widget, indented by depth, with a
#: ``CTabItem text="<view tab>"`` line for every view (`LiveBridge.java:836-838`);
#: a `Tree` reports only its item count -- ``[TreeItems=N]`` (`:852`) -- so the
#: count is all there is, and it is a *read-only* answer: a launch with no effect
#: leaves no Debug view at all (measured: `ui.tree 14` -> **zero** `[TreeItems=…]`
#: lines), while a live debug context gives the Debug view a non-empty tree.
_DEBUG_VIEW = "Debug"

#: Depth passed to `ui.tree`, plus `--shell all`.  The bridge's default depth is 3,
#: and its default *shell* is the largest visible shell -- both are wrong for this
#: probe, measured on this machine 2026-10-07 against the very instance this case
#: had left running:
#: * the view stack is parked in the invisible `PartRenderingEngine's limbo` shell
#:   while the editor is maximized (`ui.shells`: 3 shells, the visible workbench
#:   window is `shell=1/3`), so the default pick reached **no** `Tree` at all
#:   (`ui.tree 16` -> 147 lines, `[TreeItems=…]` count 0) -- `--shell all` is what
#:   covers both that layout and the debug perspective's layout;
#: * the Debug view's tree is first reachable at **depth 9**; raw, verbatim from
#:   `ui.tree 9 --shell all`:
#:       `          CTabItem text="Debug" tip=""`
#:       `                    [TreeItems=1]`
#:   (depth 8 prints the Debug tab but not its `Tree`; 16 is used below for margin,
#:   since deeper only costs lines that are already bounded by the bridge's 3000.)
_LOAD_TREE_DEPTH = 16

#: The wait for the launch to finish, before any `Resume` is allowed to mean
#: anything.  `sys.wait jobs-idle` takes **no** argument -- `sys.wait jobs-idle
#: 180000` is a hard `ERR badrequest` (parent's live probe 2026-10-07) -- and uses
#: the bridge's own 15 s budget (`LiveBridge.java` DEFAULT_JOBS_IDLE_WAIT_MS), so
#: the *generous* total is this loop's own wall budget.  It must be minutes, not
#: the 30 s the old poll silently assumed: the archive's own run put
#: `launchActive` at 00:24:42 and `Resume` at 00:36:17 (`run-ram-launch.md` §4.1),
#: and an exhausted wait budget is a normal `OK`/`idle=false` -- never a failure
#: by itself -- so the loop just polls again.
_LOAD_WAIT_ROUNDS = 120         # safety valve; the wall deadline must bind first
_LOAD_WAIT_BUDGET_S = 600.0

#: The floor under one round, so a slice lasts what it says even when every
#: request answers instantly.
#:
#: Measured 2026-10-07 (run `board-1007-t2`): `sys.wait jobs-idle` answers in
#: **0 ms** whenever no job is running (15 rounds at 0 ms; **43** `ui.parts`
#: calls inside one second), so the old 40-round cap -- not the wall budget --
#: ended each slice, collapsing a nominal 150 s to about a second.  The four
#: `launchActive` issues then came **152 s / 23 s / 8 s** apart, the last two
#: nearly back to back: a launch was re-issued before its predecessor had had
#: any chance to take effect.  With this floor, a 150 s slice is 100 rounds,
#: well under `_LOAD_WAIT_ROUNDS`, so the deadline is what binds.
_LOAD_ROUND_MIN_S = 1.5

#: `launchActive` is answered `OK` even when the LaunchBar's active configuration
#: is still empty -- the handler then does nothing at all (measured 2026-10-07:
#: `launchActive` 6 s after the bridge came up left the perspective at
#: `TICPerspective` for the whole 600 s budget, while the *same* command on the
#: *same* instance 2.5 min later switched it in 6 s).  So the launch is waited for
#: too: one issue per slice, and a fresh issue while nothing has happened yet.
#: The overall wait stays `_LOAD_WAIT_BUDGET_S`; the slices only bound a retry.
_LOAD_LAUNCH_ATTEMPTS = 4
_LOAD_WAIT_SLICE_S = 150.0

#: The **soft** precondition before the first `launchActive`: wait, read-only, for
#: this instance's own startup jobs to fall silent (see `_wait_jobs_quiet`).
#:
#: A *fresh* instance (every `ctl verify` builds a new `configuration`) spends its
#: first minutes downloading repository metadata; the AC1 run's own `sys.wait
#: jobs-idle` answers carry it verbatim, repeatedly:
#:
#:     idle=false
#:     pending=2
#:     jobs_total=11 running=2 waiting=0 sleeping=9 none=0
#:       busy name="Loading the repository {0}" state=RUNNING
#:       busy name="https://software-dl.ti.com/ccs/esd/device_support_ccsv9/auto/content.jar" state=RUNNING
#:
#: and its first two `launchActive` issues (`bridge.log` 06:38:26 / 06:41:09) had
#: **zero** effect while the third (06:43:41) took effect at once.  So "let the
#: instance settle" is waited for -- but *only* waited for: the cap is a wall clock
#: and the launch is issued anyway when it is spent, because a busy JobManager only
#: makes a launch less likely to take effect.  It is never a SKIP and never a FAIL.
_JOBS_QUIET_WAIT_S = 180.0
#: The floor under one settle poll, so a stub whose requests answer instantly (or a
#: real one that answers in 0 ms once the jobs are asleep) cannot hot-loop.
_JOBS_QUIET_POLL_S = 1.5

#: How long to wait, read-only, for the LaunchBar to bind a launch target to the
#: descriptor this case seeded (see `_wait_launchbar` for why that line, and not the
#: descriptor list this case no longer writes).
_LAUNCHBAR_WAIT_S = 60.0

#: The LaunchBar's preference file this case **seeds** before the instance comes up.
#:
#: ``%s`` twice: the descriptor of the launch configuration this case declares, and
#: the project's own descriptor name (see the fallback note in `_seed`).  Shape taken
#: from three real workspaces on this machine --
#: ``<…>/CCS12.8.1-Eclipse/{f2800137test,f2800157test,power_folder}/.metadata/.plugins/
#: org.eclipse.core.runtime/.settings/org.eclipse.launchbar.core.prefs`` -- which all
#: carry ``eclipse.preferences.version=1`` and one
#: ``<descriptor node path>/activeLaunchMode=<run|debug>`` line per descriptor the
#: LaunchBar has touched (the node path spells the colon escaped, as the ``.prefs``
#: format requires).
#:
#: ``configDescList`` is deliberately **not** written here: it is the LaunchBar's own
#: record of the descriptors it discovered, and it is the one signal in that file this
#: case never produces -- see `_wait_launchbar`.
_LAUNCHBAR_PREFS = ("eclipse.preferences.version=1\n"
                    "org.eclipse.launchbar.core.descriptorType.default\\:%s"
                    "/activeLaunchMode=debug\n"
                    "org.eclipse.launchbar.core.descriptorType.default\\:%s"
                    "/activeLaunchMode=debug\n")

#: `Resume`, once the read-only gate has opened.  The first `OK` proves a suspended
#: context existed, and the loop keeps resuming until a following `Resume` answers
#: `ERR disabled` (nothing suspended => the target is running).
#:
#: The polling window is a **slice of wall clock**, never a fixed attempt count.
#: Measured 2026-10-07: the run that lit the LEDs put `launchActive` at 00:24:42 and
#: the `Resume` that released the CPU at 00:36:17 (`run-ram-launch.md` §4.1) -- about
#: **12 minutes** apart -- and this file's own comment has said all along that the
#: same command on the same instance takes effect "minutes later".  A fixed
#: 12-attempt x 1.5 s (~18 s) window is an order of magnitude short of that: run
#: `board-1007-ac1` spent all 12 attempts inside **29 s** (`bridge.log`:
#: 06:43:49.846 -> 06:44:18.316, every one `ERR disabled`) and gave up while the
#: loader was still working, so the count is gone and the slice clock is what ends
#: the polling.
#:
#: `_LOAD_POLL_S` is the beat while `Resume` is still illegal (no context yet);
#: `_RUN_SETTLE_S` is the beat between a resume that ran and the confirming call.
_LOAD_POLL_S = 1.5
_RUN_SETTLE_S = 1.0

#: The resume stage's own window: it polls `Resume` for `_LOAD_WAIT_SLICE_S` seconds
#: per slice, and a slice that released nothing may re-issue `launchActive` (at most
#: `_LOAD_RESUME_REISSUE` times, under the `_LOAD_RESUME_BUDGET_S` wall deadline).
#:
#: The re-issue is needed because the read-only gate only proves a debug **session
#: exists** -- `_gate_open`'s measured limitation: one item is the launch root node
#: alone, held while the image is still going over JTAG -- never that the load
#: finished and the CPU is halted at its entry point.  Measured 2026-10-07
#: (`board-1007-ac1`): the launch took effect on the **third** issue (06:38:26 /
#: 06:41:09 / 06:43:41, the last followed by the gate opening at 06:43:49).
#:
#: This bound is spent **only by slices that released nothing**: a slice in which a
#: `Resume` ran holds the release, and `launchActive` is never issued after one (it
#: loads and halts the CPU at the entry point -- measured 2026-10-07 `board-1007-ac2`:
#: release 07:09:33.618, re-issue 07:09:38.686, which pushed a running target back to
#: its entry point).  So a run whose resume stage released something never consumes a
#: re-issue at all; a run that never did gets this many.
_LOAD_RESUME_BUDGET_S = 600.0
#: A safety valve, and the binding bound when slices end early: a slice that ends on
#: an ABORT (the session died) took only the two liveness rounds, so the wall deadline
#: would let this stage keep re-issuing for a long time.  With a live session the
#: deadline is what binds.
_LOAD_RESUME_REISSUE = 4

#: How the session that the gate opened on is **confirmed to still exist** before a
#: `Resume` answer may be read as anything (see `_session_alive`).
#:
#: The gate is not proof of a live session: the AC1 frame at 06:41:11 holds the
#: Debug view's `ctl board chase [Code Composer Studio - Device Debugging]` root
#: node while the status bar still reads `Launching ctl_board_chase: (34%)`, and the
#: session then died -- the perspective fell back to `TICPerspective` and 12
#: `Resume` answers came back `ERR disabled` because there was nothing suspended to
#: release.  So the pair the gate is made of is read back again, `_LIVENESS_STEP_S`
#: apart, and there is **no verdict until `_LIVENESS_ROUNDS` consecutive rounds
#: agree**: one read cannot tell "the UI thread is busy" (a modal progress shell holds
#: it while a launch is starting) from "the session is gone", and the measured shape on
#: this board is that a single closed round is a *flicker*, not a death --
#: `runs/board-1007-ac2/bridge.log` 07:09:38.235 reads the edit perspective exactly
#: once (a 12-line `ui.parts`, no `ui.tree`) with no write command in flight, and the
#: very next read at 07:09:40.196 is the debug perspective again (13 lines + a
#: 323-line tree).  The case read that single frame as an ABORT and re-issued
#: `launchActive` at 07:09:38.686 -- i.e. it reloaded and halted a target it had just
#: released (07:09:33.618).  Requiring the streak is what makes the promise ("a single
#: closed round must not be read as a death") true in code.
#:
#: `_LIVENESS_ROUNDS = 2` is chosen against that measurement: the flicker recovered
#: inside ~1.8 s, and two reads `_LIVENESS_STEP_S` (2.0 s) apart mean a closure has to
#: hold across the gap to be read as a death -- so what is declared dead here is a
#: session that is gone for **at least** one full step, not a perspective that blinked.
_LIVENESS_ROUNDS = 2
_LIVENESS_STEP_S = 2.0
#: The safety valve for the pair: a perspective that keeps flicking open/closed/…
#: never settles, and reading it forever would hold the whole slice.  Past this many
#: rounds the pair has **no verdict** -- ``alive`` and ``aborted`` both ``False`` --
#: and the caller must treat it as exactly that: never as a death, and never as a
#: licence to resume.
_LIVENESS_MAX_ROUNDS = 6

#: The **affirmative button text** the load stage presses when a ``#32770`` of this
#: instance offers it.  What is *declared* is the button, never the window: the
#: criterion is "does this dialog offer the affirmative button", checked against the
#: dialog's own visible Button children -- see `_answer_load_modal` (the title is
#: evidence, not a criterion).
#:
#: Where the value comes from (measured 2026-10-07, never inferred): the shadow
#: archive of run ``ccs12-p42``, frame 114 --
#:
#:     python -m ctl shadow --run-id ccs12-p42 --seq 114   # [2026-10-07 审计：该 run 目录已被 auto_gc 回收（keep_runs=3/target）⇒ 这条复跑现在回 `ERR notfound …` 且 rc=1；读数与 sha256 已内联在下面三行，现场留档在流程仓 10-07-ccs12-f280025-board-case/research/launch-handler-contract.md §3]
#:     -> outcome=timeout promoted (dialog=appeared "Reuse Debug Settings")
#:        class=#32770 hwnd=0x13D1462 pid=29912, PNG 31 142 B,
#:        sha256 b02e5225c098d0b92aa98ec641c4953e63e9092e3b93cc3d76ea627b725c671e
#:
#: That window's title reads verbatim ``Reuse Debug Settings`` and its body reads
#: verbatim *"This project has been debugged before.  Do you want to reuse the debug
#: settings previously set?"* -- the question shape, with the two buttons ``&Yes`` /
#: ``&No``.  Pressing the affirmative one (``screen.click_button("Reuse Debug
#: Settings", "Yes", pids=[29912])`` -> ``BM_CLICK sent to hwnd=0xE010DA text="&Yes"``)
#: is what let the load finish: the next `ui.parts` read
#: ``id=com.ti.ccstudio.TIDebugPerspective``, the console carried the ``board_led_chase``
#: GEL lines, and the following `Resume` was accepted (``running=True``, PASS).  Before
#: the press the same run answered ``ERR timeout UI task did not finish within 15000
#: ms`` and eight further `ui.parts` reads, 2-3 s apart, all said ``TICPerspective`` --
#: the modal held the SWT thread, so the launch never got to finish.
#:
#: The other shell on this path has **no buttons at all** and must not be answered:
#: a *progress* shell, measured the same day with the verbatim title
#: ``Loading Program: C:\…\board_led_chase\CPU1_RAM\board_led_chase.out``.  Its
#: enumeration lists no ``Button`` child, and attempting the click anyway answers
#: ``no visible window matching 'Loading Program: …'`` -- zero affirmative hits,
#: which here is **normal and expected**, not a fault.  It is waited for, never
#: closed (closing it can cancel the very load this stage is waiting for).
_LOAD_MODAL_ANSWER = "Yes"

#: The TI template's clock-source pair, verbatim from
#: `C2000Ware_5_04_00_00/device_support/f28002x/common/include/device.h:272-276`
#: (`device.h` is copied into `<project>/device/` by the spec's row 31).
_CLOCK_XTAL_ACTIVE = "#define USE_PLL_SRC_XTAL\n//#define USE_PLL_SRC_INTOSC"

#: What this board needs instead.  The DSP280025 Lite ships **without** the 20 MHz
#: crystal and without its two 0R selectors:
#: `docs/dsp280025/DSP280025-Lite-资源与连接.md:43` "符号 XTAL，20M_5032 贴片晶振 /
#: 18pF / 0Ω 选择电阻（默认不焊 R61/R51 → 用内部振荡器）", ":376" "默认不装晶振 ...
#: R51（X2 支路）/R61（X1 支路）默认不焊".  With `USE_PLL_SRC_XTAL` active the
#: payload's `Device_init()` -> `SysCtl_setClock()` reaches `SysCtl_selectXTAL()`,
#: whose X1 poll fails and then spins forever:
#:     while (status == FALSE) { ... ESTOP0; }
#: (`.../driverlib/f28002x/driverlib/sysctl.c`: "If code is stuck here, it means
#: crystal has not started") => the CPU halts before one instruction of the
#: payload runs and no LED can ever chase.  INTOSC2 is the board's real source
#: (10 MHz x IMULT30 / REFDIV1 / ODIV3 = the same 100 MHz SYSCLK --
#: `docs/dsp280025/F28002x-勘误-时钟源-基准约束.md` §2/§3 state A).
_CLOCK_INTOSC_ACTIVE = "//#define USE_PLL_SRC_XTAL\n#define USE_PLL_SRC_INTOSC"

#: The clock source the board's own device.h must activate (R2's shape, applied to
#: the board rather than the chip).
_EXPECTED_CLOCK = "INTOSC"

# --------------------------------------------------------------------------- #
# Overlay fragments (the files this case owns -- R3 + the board's clock fact)
# --------------------------------------------------------------------------- #

#: ① the SysConfig declaration: three board LEDs on GPIO34 / GPIO6 / GPIO7, all
#: starting high (= dark; the board's LEDs are active LOW).  The generated
#: ``board.c`` is what writes the pin mux.
_SYSCFG = """/**
 * eclipse-ctl board case -- three board LEDs (D400/D401/D402) on the
 * DSP280025 Lite board: GPIO34 / GPIO6 / GPIO7, active LOW.
 *
 * Declared here so SysConfig generates the pin mux into <build>/syscfg/board.c
 * (GPIO_setPinConfig(GPIO_34_GPIO34) / GPIO_6_GPIO6 / GPIO_7_GPIO7) and the
 * pad/direction/initial level into the same file.  The payload never writes a
 * pin mux.
 */
const led  = scripting.addModule("/driverlib/board_components/led", {}, false);
const led1 = led.addInstance();
const led2 = led.addInstance();
const led3 = led.addInstance();

led1.$name                  = "myBoardLED0";
led1.gpio.writeInitialValue = true;
led1.gpio.initialValue      = 1;
led1.gpio.gpioPin.$assign   = "GPIO34";

led2.$name                  = "myBoardLED1";
led2.gpio.writeInitialValue = true;
led2.gpio.initialValue      = 1;
led2.gpio.gpioPin.$assign   = "GPIO6";

led3.$name                  = "myBoardLED2";
led3.gpio.writeInitialValue = true;
led3.gpio.initialValue      = 1;
led3.gpio.gpioPin.$assign   = "GPIO7";
"""

#: ② the payload: one-directional chase D400 -> D401 -> D402 -> loop, 200 ms per
#: step, exactly one LED lit at a time, all three dark at entry.  The pin numbers
#: are written as numbers on purpose: the *mux* is what the config owns, and a
#: payload that compiled against the generated header would turn the R4 gate into
#: a compile error instead of a "the three mux lines are missing" verdict.
_PAYLOAD = """/*
 * eclipse-ctl board case payload -- one-directional LED chase D400 -> D401 ->
 * D402, 200 ms per step, exactly one LED lit at any time, all three dark at
 * entry (the board's LEDs are active LOW: low = lit).
 *
 * The pin MUX is not here: <build>/syscfg/board.c, generated from c2000.syscfg,
 * runs GPIO_setPinConfig(GPIO_34_GPIO34 / GPIO_6_GPIO6 / GPIO_7_GPIO7) from
 * Board_init(), and lays the pad/direction/initial level from the same source.
 */

#include "driverlib.h"
#include "device.h"
#include "board.h"
#include "c2000ware_libraries.h"

/* Unique per run -- proves the image came from THIS build, not a stale one. */
volatile const char ctl_board_marker[] = "@MARKER@";

/* Referenced from main() so the linker cannot drop the marker. */
volatile unsigned long g_ctl_board_marker_live;

#define CTL_STEP_US  200000U

static const uint32_t kCtlLeds[3]= {34U, 6U, 7U};

void main(void)
{
    uint16_t i;

    Device_init();
    Device_initGPIO();
    Interrupt_initModule();
    Interrupt_initVectorTable();

    Board_init();
    C2000Ware_libraries_init();

    g_ctl_board_marker_live = (unsigned long)ctl_board_marker[0];

    EINT;
    ERTM;

    for (i = 0U; i < 3U; i++)
    {
        GPIO_writePin(kCtlLeds[i], 1U);        /* all dark */
    }

    while (1)
    {
        for (i = 0U; i < 3U; i++)
        {
            GPIO_writePin(kCtlLeds[i], 0U);    /* light this one */
            DEVICE_DELAY_US(CTL_STEP_US);
            GPIO_writePin(kCtlLeds[i], 1U);    /* dark again */
        }
    }
}

//
// End of File
//
"""

#: ③ the launch configuration.  Shape borrowed from the configuration that was
#: measured to launch on THIS board
#: (``<run>/ws/empty_driverlib_project/.launches/ccs12e2e.launch``, mtime
#: 2026-10-07 00:24); only the project name and the configuration's own name are
#: ours.  ``@NAME@`` is a plain token because the value contains ``${...}``.
#: ``MRU_PROGRAM`` and the source-locator memento are dropped -- they are
#: bookkeeping the IDE rewrites on launch; the eleven attributes that identify the
#: launch (type, debugger properties, program, project, target config, the mapped
#: resource) are kept verbatim.
_LAUNCH = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<launchConfiguration type="com.ti.ccstudio.debug.launchType.device.debugging">
    <stringAttribute key="com.ti.ccstudio.debug.debugModel.ATTR_DEBUGGER_PROPERTIES.@CCXML@.@PROBE@/@CORE@" value="@PROPS@"/>
    <stringAttribute key="com.ti.ccstudio.debug.debugModel.ATTR_DEBUGGER_PROPERTIES.@CCXML@.@PROBE@_0/@CORE@" value="@PROPS@"/>
    <stringAttribute key="com.ti.ccstudio.debug.debugModel.ATTR_PROGRAM.@CCXML@.@PROBE@/@CORE@" value="${build_artifact:@NAME@}"/>
    <stringAttribute key="com.ti.ccstudio.debug.debugModel.ATTR_PROGRAM.@CCXML@.@PROBE@_0/@CORE@" value="${build_artifact:@NAME@}"/>
    <stringAttribute key="com.ti.ccstudio.debug.debugModel.ATTR_PROJECT.@CCXML@.@PROBE@/@CORE@" value="@NAME@"/>
    <stringAttribute key="com.ti.ccstudio.debug.debugModel.ATTR_PROJECT.@CCXML@.@PROBE@_0/@CORE@" value="@NAME@"/>
    <stringAttribute key="com.ti.ccstudio.debug.debugModel.ATTR_TARGET_CONFIG" value="${target_config_active_default:@NAME@}"/>
    <listAttribute key="org.eclipse.debug.core.MAPPED_RESOURCE_PATHS">
        <listEntry value="/@NAME@"/>
    </listAttribute>
    <listAttribute key="org.eclipse.debug.core.MAPPED_RESOURCE_TYPES">
        <listEntry value="4"/>
    </listAttribute>
    <stringAttribute key="org.eclipse.debug.core.source_locator_id" value="com.ti.ccstudio.debug.sourceLocator"/>
</launchConfiguration>
"""

#: The escaped ``<PropertyValues>`` blob (Connect on startup / installed
#: breakpoint / soft-launch failures), copied byte-for-byte from the measured
#: configuration; only the *program* is different.
_PROPS = ("&lt;?xml version=&quot;1.0&quot; encoding=&quot;UTF-8&quot; "
          "standalone=&quot;no&quot; ?&gt;&#10;&lt;PropertyValues&gt;&#10;&#10;"
          "  &lt;property id=&quot;ConnectOnStartup&quot;&gt;&#10;"
          "    &lt;curValue&gt;1&lt;/curValue&gt;&#10;  &lt;/property&gt;&#10;&#10;"
          "  &lt;property id=&quot;EnableInstalledBreakpoint&quot;&gt;&#10;"
          "    &lt;curValue&gt;1&lt;/curValue&gt;&#10;  &lt;/property&gt;&#10;&#10;"
          "  &lt;property id=&quot;IgnoreSoftLaunchFailures&quot;&gt;&#10;"
          "    &lt;curValue&gt;0&lt;/curValue&gt;&#10;  &lt;/property&gt;&#10;&#10;"
          "&lt;/PropertyValues&gt;&#10;")


# --------------------------------------------------------------------------- #
# Small helpers (the shapes are the ones `realflow_build_artifact.py` measured)
# --------------------------------------------------------------------------- #

def _override(key: str) -> Optional[str]:
    """``ECLIPSE_CTL_BOARD_<KEY>`` -- a non-empty override, or ``None``."""
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


def _write_text(path: str, text: str) -> None:
    """Write LF bytes verbatim -- never let the platform turn them into CRLF."""
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
    """The marker's byte forms: ASCII, and 16-bit chars (C2000's ``char``)."""
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
    """Kill a timed-out build and its children; returns a one-line note."""
    try:
        done = subprocess.run(["taskkill", "/F", "/T", "/PID", str(int(pid))],
                              capture_output=True, timeout=30)
        text = (_decode(done.stdout) + _decode(done.stderr)).strip().replace("\n", " ")
        return "taskkill /F /T /PID %d rc=%d %s" % (pid, done.returncode, text[:200])
    except Exception as exc:  # noqa: BLE001 - cleanup must never raise
        return "taskkill failed: %r" % exc


def _run_capture(argv: List[str], timeout: float,
                 cwd: Optional[str] = None) -> Dict[str, Any]:
    """Run a create/build command, capture merged stdout, never orphan it."""
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
                "elapsed": time.monotonic() - started, "killed": None, "argv": list(argv)}
    except subprocess.TimeoutExpired:
        killed = _kill_tree(proc.pid)
        try:
            out, _ = proc.communicate(timeout=15)
        except Exception:  # noqa: BLE001
            out = b""
        return {"rc": proc.returncode, "timed_out": True, "text": _decode(out),
                "elapsed": time.monotonic() - started, "killed": killed, "argv": list(argv)}


def _tail(text: str, lines: int = 20) -> str:
    return "\n".join((text or "").splitlines()[-lines:])


def _spec_device(spec_text: str) -> Optional[str]:
    """The ``device="..."`` attribute of a projectSpec."""
    match = re.search(r'<project\b[^>]*\bdevice="([^"]*)"', spec_text, re.S)
    return match.group(1) if match else None


def _project_device(ccsproject_text: str) -> Optional[str]:
    """``<deviceVariant value="TMS320C28XX.TMS320F280025C"/>`` -> the variant."""
    match = re.search(r'<deviceVariant\s+value="([^"]*)"', ccsproject_text)
    return match.group(1) if match else None


def _registered_projects(workspace: str) -> List[str]:
    """Project names the workspace itself registers (its own registry, on disk).

    The registry directory also holds Eclipse's own bookkeeping
    (``.org.eclipse.egit.core.cmp``, measured on this machine) and the RSE temp
    project the IDE creates for itself (``RemoteSystemsTempFiles``); neither is a
    project this case could collide with, so both are filtered out.
    """
    registry = os.path.join(workspace, ".metadata", ".plugins",
                            "org.eclipse.core.resources", ".projects")
    if not os.path.isdir(registry):
        return []
    return sorted(name for name in os.listdir(registry)
                  if not name.startswith(".")
                  and name != "RemoteSystemsTempFiles"
                  and os.path.isdir(os.path.join(registry, name)))


def _active_build_configs(workspace: str, project: str) -> List[str]:
    """Build-configuration names the IDE's own CDT state mentions for `project`.

    Eclipse keeps the project's build state under
    ``.metadata/.plugins/org.eclipse.cdt.core/<project>.<n>.pdom``; on the measured
    machine that file names the active configuration (``CPU1_RAM``, 5x, and no
    other).  This is the IDE's own record of which directory
    ``${build_artifact:<project>}`` will resolve to (H1) -- read, never assumed.
    """
    root = os.path.join(workspace, ".metadata", ".plugins", "org.eclipse.cdt.core")
    names: List[str] = []
    for path in sorted(glob.glob(os.path.join(root, project + ".*"))):
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as handle:
            blob = handle.read()
        for candidate in (_CONFIG,) + _OTHER_CONFIGS:
            if candidate.encode("ascii") in blob and candidate not in names:
                names.append(candidate)
    return names


def _c2000ware_candidates(install_dir: str) -> List[str]:
    """Every C2000Ware root reachable from ``install_dir``; ``[]`` if none.

    Resolution: ``ECLIPSE_CTL_BOARD_C2000WARE`` (a non-empty override wins outright)
    else derive from the target's own install tree -- walk up from ``install_dir``
    (``<ti>/ccs<ver>/ccs/eclipse``) to the TI root and glob `_C2000WARE_GLOBS`.
    ``[]`` means "the caller must SKIP with an actionable message"; it never means
    "fall back to a path nobody verified" (the shape `ctl/targets.py::_find_ecj`
    removed when it dropped a hard-coded sibling install).

    Candidates are **not** arbitrated here: the caller keeps the first one that
    carries the family's ``projectspec``.  What is on disk only *filters* -- the
    **order** decides, so the order is the rule: roots are collected name-descending
    (``sorted(..., reverse=True)``).

    Measured 2026-10-07 (``<ti>`` = ``D:/ti``, so the walk reaches ``D:/ti/c2000``
    from ``D:/ti/ccs1281/ccs/eclipse``): **three** releases sit there and **all three**
    (``C2000Ware_5_04_00_00`` / ``C2000Ware_26_00_00_00`` / ``C2000Ware_26_01_00_00``)
    carry
    the family's ``_SPEC_REL`` -- i.e. the projectspec check alone selects
    nothing here, and ``C2000Ware_5_04_00_00`` wins because ``"5…" > "26…"`` **as
    strings**, not because it is newer.  So this is a **deterministic tie-break, not
    a version comparison**: it keeps one machine reproducible (the same set of
    releases always yields the same root), and the caller prints the whole candidate
    list beside the chosen root so "the root it found" is never read as "the only
    root there is" (R2's rule one level up).  The accepted end-to-end recipe (AC1) is
    what re-certifies whichever release this picks; no version is pinned, and the
    device read-back (R2) stays the gate on the silicon.
    """
    override = _override("c2000ware")
    if override:
        return [override]
    out: List[str] = []
    base = install_dir or ""
    for _ in range(4):
        if not base:
            break
        for pattern in _C2000WARE_GLOBS:
            hits = sorted(glob.glob(os.path.join(base, *pattern.split("/"))),
                          reverse=True)
            for hit in hits:
                cand = os.path.normpath(hit)
                if cand not in out:
                    out.append(cand)
        parent = os.path.dirname(os.path.normpath(base))
        if parent == base:
            break
        base = parent
    return out


def _probe_tool(install_dir: str) -> str:
    """Locate ``xds100serial.exe`` under a CCS install tree.

    For ``ccs12`` the target's ``install_dir`` is the *launcher's* directory
    (``…/ccs/eclipse``, `ctl/targets.py`), not the product root, so the uscif
    tool two levels up is searched for as well.  ``ECLIPSE_CTL_BOARD_USCIF``
    overrides the whole lookup.
    """
    override = _override("uscif")
    if override:
        return override
    rel = os.path.join("ccs_base", "common", "uscif", "xds100serial.exe")
    candidates = []
    base = install_dir or ""
    for _ in range(3):
        if not base:
            break
        candidates.append(os.path.join(base, rel))
        base = os.path.dirname(base.rstrip("\\/"))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return candidates[0] if candidates else rel


def _probe_report(install_dir: str) -> Dict[str, Any]:
    """Ask the CCS debug-service tool which FTDI devices it can **see**.

    ``xds100serial.exe`` enumerates **every** FTDI device it can see -- not only
    XDS100s -- so the table's first row need not be the probe at all.  Measured on
    this machine 2026-10-07:

    ```
    0403/6010  generic FT2232  GJBDRPSS    USB <-> Serial Converter
    0403/a6d0  XDS100v1/v2     USB100V2    Texas Instruments Inc.XDS100 Ver 2.0
    ```

    Row 1 is a *different* FTDI device (a USB/serial converter); row 2 is the
    XDS100v2 this case's launch configuration names (``_PROBE``).  So "the table
    has a row" is not "the probe is attached": keying R8's SKIP on any row would
    let a board with no probe attached run the whole case (the AC4 hole).

    The converse is true as well, and it is the trap this channel used to fall into:
    a row carrying ``XDS100`` is evidence of **visibility**, not of **attachment**.
    While a live debug session holds the probe the tool enumerates **one** row and
    the XDS100 is invisible (A/B on run ``ccs12-p42``, verbatim in the module
    docstring under "Probe in place"), so ``probe_rows == []`` has two causes and
    this function cannot tell them apart.  ``_probe_present()`` is the channel that
    can, and ``_pre`` decides on the pair.

    RERUN (either state, ~0.1 s; the A/B is the presence of a live debug session
    holding the probe).  The path is *derived*, never hardcoded -- `_probe_tool`
    walks up from the target's `install_dir`, and `_pre` records the result on its
    `probe` line:

        python -c "from ctl.verify.cases.board_led_chase import _probe_tool as f; print(f('<install_dir>'))"

    i.e. ``<install_dir>/ccs_base/common/uscif/xds100serial.exe`` (measured
    2026-10-07 with ``install_dir`` = ``D:/ti/ccs1281/ccs/eclipse``).
    """
    tool = _probe_tool(install_dir)
    out: Dict[str, Any] = {"tool": tool, "rc": None, "rows": [], "probe_rows": [],
                           "error": ""}
    if not os.path.isfile(tool):
        out["error"] = "probe tool not found: %s" % tool
        return out
    try:
        done = subprocess.run([tool], capture_output=True, timeout=_PROBE_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        out["error"] = "probe tool failed: %r" % exc
        return out
    text = (_decode(done.stdout) + "\n" + _decode(done.stderr))
    out["rc"] = done.returncode
    out["rows"] = [line.strip() for line in text.splitlines()
                   if re.match(r"^\s*[0-9a-fA-F]{4}/[0-9a-fA-F]{4}\b", line)]
    #: The rows this case can actually connect through.  The tool puts its own
    #: classification in the `Type` column, so an `XDS100` row is the tool's own
    #: semantic answer -- more robust than hard-coding a VID/PID.  `_PROBE` names
    #: an XDS100v2, and that is what R8 has to be keyed on.
    out["probe_rows"] = [row for row in out["rows"] if "XDS100" in row]
    return out


#: The hardware id Windows binds the TI XDS100 driver to **on this machine**,
#: verbatim from the PnP database while the probe was invisible to
#: ``xds100serial.exe`` (an instance holding it) -- ``Get-PnpDevice -PresentOnly``
#: reports it under class ``TI_Debug_Probe`` in *both* states of the A/B, which is
#: why presence is keyed on the id and not on any driver state:
#:
#:     USB\VID_0403&PID_A6D0&MI_00\8&1A7F3620&0&0000
#:
#: The unqualified ``USB\VID_0403&PID_A6D0\USB100V2`` node comes first in the query
#: and is matched by the same needle (it is the same board).
_XDS100_HWID = "VID_0403&PID_A6D0"

#: The read-only PnP presence query.  Through PowerShell, matching the repo's own
#: convention for Windows-native read-only queries -- ``ctl/lifecycle.py:213-217``
#: (``_pwsh``), whose user is ``list_processes`` (``Get-CimInstance Win32_Process``).
#: ``-match`` is a regex and ``&`` is a literal there, so the needle is passed as-is.
_PNP_QUERY = ("Get-PnpDevice -PresentOnly | "
              "Where-Object { $_.InstanceId -match '%s' } | "
              "Select-Object -ExpandProperty InstanceId" % _XDS100_HWID)

#: The PnP query's wall budget.  Measured cost on this machine 2026-10-07:
#: **1.0-1.2 s** per invocation (three runs: 1.07 s / 1.13 s / 1.00 s), so 60 s is
#: a valve, not a race.
_PNP_TIMEOUT = 60.0


def _pnp_ids_from_text(text: str) -> List[str]:
    """The hardware ids one PnP answer names: one per line, blanks and noise dropped.

    Only lines carrying the needle are kept, so a stray warning line on the same
    stream cannot be read as a device (the query already filters, and this is the
    second, cheaper gate).
    """
    ids: List[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line and _XDS100_HWID.lower() in line.lower():
            ids.append(line)
    return ids


def _pnp_xds100_ids() -> Tuple[List[str], str]:
    """``([hardware ids], "")`` or ``([], error)`` -- never a guess (fail closed).

    Every failure mode (no PowerShell, spawn failure, non-zero exit, timeout, and a
    non-empty stream that names no matching id) comes back as the second element,
    never as an empty list: an unanswerable question must not be spelled the same
    way as the answer "none".

    The last one is why a *blank* stream and a *noisy* one are told apart: the
    answer "no such device" is an **empty** stream (measured 2026-10-07: the query
    with a needle that matches nothing writes 0 bytes on both streams, rc=0), so a
    stream that carries text but yields no id is not an answer at all -- it is a
    warning/error the command swallowed (stderr is merged into stdout by
    ``_run_capture``) and must not read as "absent".
    """
    exe = shutil.which("pwsh") or shutil.which("powershell")
    if not exe:
        return [], "no PowerShell on PATH (pwsh or powershell)"
    done = _run_capture([exe, "-NoProfile", "-NonInteractive", "-Command", _PNP_QUERY],
                        timeout=_PNP_TIMEOUT)
    if done["killed"]:
        return [], "PnP query killed after %ss" % _PNP_TIMEOUT
    if done["rc"] != 0:
        return [], "PnP query rc=%s: %s" % (done["rc"], _tail(str(done["text"]), 3))
    ids = _pnp_ids_from_text(str(done["text"]))
    if not ids and str(done["text"]).strip():
        return [], ("PnP query rc=0 but named no %r hardware id; the stream carried: %s"
                    % (_XDS100_HWID, _tail(str(done["text"]), 3)))
    return ids, ""


def _probe_present() -> Dict[str, Any]:
    """Is an XDS100 probe attached?  The channel a held handle cannot blind.

    ``xds100serial.exe`` answers "can this tool enumerate the probe", which a live
    debug session can turn into ``False`` while the probe sits plugged in (A/B in the
    module docstring: the XDS100 is exclusive, `design.md` H3).  This asks the OS,
    which the held handle does not change -- that is the whole reason it exists; if it
    merely re-asked ``xds100serial.exe`` it would be a second name for one answer.  It
    is what separates the two causes of ``probe_rows == []``:

    * ``present is True``  -- attached, but the tool cannot see it => a held handle;
    * ``present is False`` -- genuinely not attached (that is R8/AC4's case);
    * ``present is None``  -- the query itself did not answer => say *that*.

    ``ECLIPSE_CTL_BOARD_PRESENCE=present|absent`` forces the value (the case's usual
    override seam, `_override`); an unrecognised value is ``None`` + an error, never
    a guess.  RERUN on this machine (~1.0-1.2 s, prints the matched hardware ids):

        python -c "from ctl.verify.cases import board_led_chase as c; print(c._probe_present())"
    """
    override = _override("presence")
    if override:
        value = {"present": True, "absent": False}.get(override.strip().lower())
        if value is None:
            return {"present": None, "source": "override", "ids": [],
                    "error": "%sPRESENCE=%r is not a recognized value "
                             "(use present|absent)" % (_BOARD_ENV, override)}
        return {"present": value, "source": "override", "ids": [], "error": ""}

    ids, error = _pnp_xds100_ids()
    if error:
        return {"present": None, "source": "pnp", "ids": [], "error": error}
    return {"present": bool(ids), "source": "pnp", "ids": ids, "error": ""}


def _run_ctl(args: List[str], timeout: float) -> Dict[str, Any]:
    """One `python -m ctl …` door, from the repo root (never a shell string)."""
    argv = [sys.executable, "-m", "ctl"] + args
    return _run_capture(argv, timeout, cwd=REPO_ROOT)


def _shape(response) -> str:
    return "%s (%d lines)" % (response.status_line, len(response.lines))


def _stamp() -> str:
    """``HH:MM:SS`` wall clock -- so a note can be put next to a frame capture.

    Every driven command in this case is answered `OK` whether or not it did
    anything, so the load's notes are the material a later root-cause pass has to
    work from; the run's own frame captures are stamped to the second, and a
    monotonic offset cannot be lined up with them.
    """
    return time.strftime("%H:%M:%S", time.localtime())


def _reading(read: Dict[str, Any]) -> str:
    """One read-back of the gate's pair, verbatim: ``at … perspective=… [TreeItems=…]``."""
    return ("at %s perspective=%s, Debug view [TreeItems=%s]"
            % (read.get("at"), read.get("perspective"),
               "no" if read.get("debug_items") is None else read["debug_items"]))


def _readback(live: Optional[Dict[str, Any]]) -> str:
    """A whole read-only session check, verbatim: the two readings and every round.

    The note for a missing confirmation has to say *what the liveness readings were*
    -- they are both the evidence that R7's forbidden criterion was actually read and
    the reason the confirming call could not be made -- so this prints them in the
    same verbatim form the ABORT note uses (the reading the pair started from, the
    first one that closed, and the verbatim diff between them), plus the open/closed
    shape of every round the pair took.
    """
    if not live:
        return "no liveness read-back was recorded"
    rounds = live.get("rounds") or []
    shape = " / ".join("open" if r["open"] else "closed" for r in rounds) \
        or "<none answered>"
    closed = next((r for r in rounds if not r["open"]), None)
    if closed is None:
        return ("the read-back was %s; the pair read %s (%.1fs apart) and never settled"
                % (_reading(live.get("before") or {}), shape, _LIVENESS_STEP_S))
    return ("the read-back was %s, the next one is %s (verbatim diff: %s); the pair read "
            "%s (%.1fs apart)"
            % (_reading(live.get("before") or {}), _reading(closed),
               live.get("diff") or "<no diff recorded>", shape, _LIVENESS_STEP_S))


def _note_unconfirmed(ctx, out: Dict[str, Any], why: str,
                      live: Optional[Dict[str, Any]]) -> None:
    """Record **verbatim** that the confirming `Resume` was unavailable (R7's floor).

    R7's criterion is the result word plus the `OK executed <command id>` line; the
    confirming `Resume` (`ERR disabled`) is the upgrade on top of it, and when it
    cannot be had the stage still reads the floor -- so the note has to carry the
    floor's own evidence (the clean `Resume`, its shape and its frame), the reason the
    upgrade is missing, and the two liveness readings it was reading.  Nothing here is
    a criterion: the session/perspective state is R7's *forbidden* one, and the note
    exists so the next reader can tell "released, confirmation unavailable" apart from
    "the loader never released anything".
    """
    ctx.note("load: the confirming %s is UNAVAILABLE -- %s.  The release: a clean %s "
             "ran at %s -- %s: %r.  The read-back that ended the window: %s.  R7 makes "
             "this readable off the floor rather than a guess: the criterion is the "
             "result word plus the %r line (a `dialog=` line vetoes; the line count is "
             "only an auxiliary threshold), and the session/perspective state is a "
             "FORBIDDEN criterion -- so the release stands and the missing confirmation "
             "is recorded verbatim instead of being filled in with a story."
             % (_CMD_RESUME, why, _CMD_RESUME, out.get("resume_at"),
                _shape(out["resume"]), out["resume"].raw, _readback(live),
                _OK_MARK + _CMD_RESUME))


# --------------------------------------------------------------------------- #
# Plan (`pre`) -- resolve the environment, then the two preconditions
# --------------------------------------------------------------------------- #

def _pre(ctx):
    if ctx.paths is None:
        raise Skip("no run directory to seed; retry with --run-id <id> (the case "
                   "writes only inside <run_root>/<run_id>)")

    plan: Dict[str, Any] = {"errors": [], "killed": []}

    candidates = _c2000ware_candidates(ctx.target.install_dir or "")
    root = next((c for c in candidates
                 if os.path.isfile(os.path.join(c, _SPEC_REL))), None)
    if root is None:
        raise Skip("no C2000Ware root carrying the %r family: looked at %s, derived "
                   "from target %r's install tree (%r); set %sC2000WARE=<the "
                   "C2000Ware directory>" % (
                       _FAMILY, candidates or "[]", ctx.target.name,
                       ctx.target.install_dir or "<unset>", _BOARD_ENV))
    plan["c2000ware"] = root
    spec = os.path.join(root, _SPEC_REL)
    plan["spec"] = spec

    spec_text = _read_text(spec)
    plan["spec_device"] = _spec_device(spec_text)
    if plan["spec_device"] != _EXPECTED_DEVICE:
        # Not a SKIP: the file was *found* and it is the wrong chip -- that is the
        # silent-error case R2 exists for.  The error is *recorded*, not thrown:
        # `_action` still builds that project (it has already wiped and seeded the
        # workspace), and the verdict is FAIL because `_expect` opens with these
        # errors.  So the wording says what happens -- no promise of a short circuit.
        plan["errors"].append(
            "device read-back: the located projectspec declares device=%r, expected "
            "%r (family %r) -- wrong silicon; the verdict is FAIL (the error is "
            "recorded and the build still runs, so the failure is reported rather "
            "than the run being stopped)"
            % (plan["spec_device"], _EXPECTED_DEVICE, _FAMILY))

    workspace = ctx.paths.workspace
    registered = _registered_projects(workspace)
    plan["workspace"] = workspace
    plan["registered_before"] = registered
    ours = _override("project") or _PROJECT
    foreign = [name for name in registered if name != ours]
    if foreign:
        raise Skip("the run's workspace registers %s -- this case owns its workspace "
                   "(it seeds the project before the IDE starts, so a foreign project "
                   "would make the launch configuration ambiguous) and will not delete "
                   "another session's project; retry on a fresh instance: "
                   "python -m ctl install --target %s --run-id %s"
                   % (", ".join(repr(n) for n in foreign), ctx.target.name,
                      ctx.run_id + "-2"))

    # The run's OWN leftover instance is stopped **before** the probe is read, and
    # the order is the point: an instance left behind by a green invocation of this
    # case still has the debug session it ended with, and a live debug session holds
    # the probe's FTDI handle -- while it is held, `xds100serial.exe` enumerates ONE
    # row and the XDS100 is invisible (A/B in the module docstring, run `ccs12-p42`).
    # Reading the tool first would make the case read "the tool is blind" as "the
    # board is gone" and SKIP its own re-run -- the one thing AC1's one-command
    # repeat cannot afford, because AC5 deliberately leaves that instance running.
    # (Measured 2026-10-07: a *session-less* live instance does not blind the tool --
    # 2 rows with `ctl install` live -- so what has to be freed is the debug session.)
    #
    # `_stop_instance` is defined further down this module; the name is resolved when
    # this function runs, so the forward reference is fine.
    stop = _stop_instance(ctx, plan)
    plan["stop"] = stop
    ctx.note("pre: stop %s (rc=%s) before the probe is read -- this run's own leftover "
             "instance would hold the probe's handle"
             % ("ran" if stop["needed"] else "not needed", stop["rc"]))

    probe = _probe_report(ctx.target.install_dir or "")
    plan["probe"] = probe
    tool = os.path.basename(probe["tool"])
    rows = " | ".join(probe["rows"]) or "<none>"
    # Emitted before any SKIP below, so a skipped run still carries the reading that
    # produced the verdict (`prd.md` R7: the evidence is the reading, not the story).
    ctx.note("pre: probe %s rc=%s ftdi_rows=%d xds100_rows=%d xds100=%r others=%r"
             % (tool, probe["rc"], len(probe["rows"]), len(probe["probe_rows"]),
                probe["probe_rows"][0] if probe["probe_rows"] else "",
                [row for row in probe["rows"] if row not in probe["probe_rows"]]))
    if not probe["probe_rows"]:
        # Three-valued, and the order carries the meaning:
        # * `XDS100` in a row is a positive proof of ATTACHMENT (the tool could only
        #   put that row there by enumerating the device) -- so a row short-circuits
        #   the whole question, above this branch;
        # * no row is NOT proof of absence.  `rows == 1` has two causes: the probe is
        #   physically gone, or a live debug session holds it (A/B in the module
        #   docstring).  `_probe_present()` asks the OS, which the held handle does
        #   not change, and this is where the two are told apart.
        presence = _probe_present()
        plan["presence"] = presence
        ids = ", ".join(presence["ids"]) or "<none>"
        ctx.note("pre: presence source=%s present=%s ids=%s error=%r"
                 % (presence["source"], presence["present"], ids, presence["error"]))
        # What answered, in words -- the same two messages have to read correctly
        # whether the OS answered or the override forced the value.
        where = ("the %sPRESENCE override" % _BOARD_ENV
                 if presence["source"] == "override"
                 else "the OS presence query (Get-PnpDevice)")
        if presence["present"] is False:
            # R8/AC4's genuine case: nothing is attached.  SKIP, never FAIL.
            # C14 contract 2 (`deliverable-shape.md`): name the channel that actually
            # said this.  The override never queried the OS, so it must not be credited
            # with a PnP finding -- it answers in its own terms.
            absent_why = ("%s says the board is absent" % where
                          if presence["source"] == "override"
                          else "%s reports no present device whose hardware id "
                               "contains %r" % (where, _XDS100_HWID))
            raise Skip("no XDS100 probe attached: %s enumerated %d FTDI device(s) "
                       "(rc=%s, %s) and none of them carries 'XDS100', and %s; this "
                       "case drives %r, so attach that probe -- rows: %s"
                       % (tool, len(probe["rows"]), probe["rc"],
                          probe["error"] or "no emulator row", absent_why,
                          _PROBE, rows))
        if presence["present"] is True:
            # The tool is blind; the board is not.  The message must name that cause,
            # because "attach the probe" would send the operator to the wrong end.
            held = (" -- %s reports hardware id %s" % (where, ids)
                    if presence["ids"] else " -- %s says so" % where)
            if probe["rc"] is None:
                # The binary never ran at all: `_probe_report` leaves `rc` None when the
                # tool is missing or the spawn failed.  Blaming a live debug session
                # here would send the operator to stop an instance that holds nothing
                # -- name the cause that was actually observed (C14 contract 2).
                raise Skip("the XDS100 probe IS attached%s but %s could not run (%s), so "
                           "this channel says nothing about the board: fix the tool, not "
                           "the probe -- rows: %s"
                           % (held, tool, probe["error"] or "no error recorded", rows))
            raise Skip("the XDS100 probe IS attached%s but %s cannot enumerate it -- it "
                       "listed only %d FTDI device(s) (rc=%s, %s): a live CCS debug "
                       "session is holding the probe's handle, so the tool cannot see "
                       "it.  The board is not missing: stop the instance holding it "
                       "(python -m ctl uninstall --target %s --run-id <that run>) and "
                       "retry -- rows the tool could see: %s"
                       % (held, tool, len(probe["rows"]), probe["rc"],
                          probe["error"] or "no emulator row", ctx.target.name, rows))
        raise Skip("cannot determine whether the XDS100 probe is attached: %s listed %d "
                   "FTDI device(s) and none of them carries 'XDS100' (rc=%s, %s), and %s "
                   "did not answer (%s).  This is a statement about the query, not "
                   "about the board -- %r may well be attached -- rows: %s"
                   % (tool, len(probe["rows"]), probe["rc"],
                      probe["error"] or "no emulator row", where,
                      presence["error"] or "no error recorded", _PROBE, rows))

    # The target's port must end up ours: this case starts the instance itself, and
    # `install` refuses a port another run holds.  Same predicate as
    # `lifecycle.install` (a listener whose command line names THIS run's
    # configuration area or workspace is ours, anything else is foreign).
    port = ctx.runner.port or ctx.target.port
    conf_norm = ctx.paths.configuration.replace("\\", "/")
    ws_norm = workspace.replace("\\", "/")
    mine = set()
    for row in list_processes():
        cmdline = (row.get("cmdline") or "").replace("\\", "/")
        if conf_norm in cmdline or ws_norm in cmdline:
            try:
                mine.add(int(row["pid"]))
            except (TypeError, ValueError):
                continue
    holders = list_port_listeners(port)
    foreign = [pid for pid in holders if pid not in mine]
    plan["port"] = port
    plan["port_holders"] = holders
    if foreign:
        raise Skip("port %d is held by another run (pid %s) and this case must start "
                   "the instance itself; stop it first (python -m ctl uninstall "
                   "--target %s --run-id <that run>) or re-run on a free port"
                   % (port, ", ".join(str(pid) for pid in foreign), ctx.target.name))
    ctx.note("pre: port %d holders=%s (ours=%s)"
             % (port, holders or "<none>", sorted(mine) or "<none>"))

    ctx.board_plan = plan
    ctx.note("pre: c2000ware=%s (chosen from %d candidate(s): %s) spec=%s "
             "spec_device=%s expected=%s"
             % (root, len(candidates), ", ".join(candidates) or "[]", spec,
                plan["spec_device"], _EXPECTED_DEVICE))
    ctx.note("pre: workspace=%s registered_projects=%s"
             % (workspace, registered or "<none>"))
    return "workspace=%s probe_rows=%d xds100_rows=%d" % (
        workspace, len(probe["rows"]), len(probe["probe_rows"]))


# --------------------------------------------------------------------------- #
# The steps
# --------------------------------------------------------------------------- #

def _stop_instance(ctx, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Free the workspace's lock and the port before seeding the project.

    Called twice in a run: from ``_pre`` -- before the probe is read, so the case's
    own leftover instance cannot blind the tool (C14 contract 3) -- and again from
    the action, which re-stops whatever the pre-phase left behind.  The second call
    is harmless: `uninstall` returns 0 when there is nothing to stop, and it does
    not delete the run.

    A live IDE holds ``<ws>/.metadata/.lock``, and both `projectCreate` and the
    seeding step need the workspace to itself (measured: the second JVM is refused
    with "Workspace location '…' is in use or cannot be created").  `uninstall` is
    the CLI's own door for that; it stops the run's pid and any process still
    holding its port or configuration area, and it does *not* delete the run.
    """
    out: Dict[str, Any] = {"needed": False, "rc": None, "text": ""}
    endpoint = ctx.paths.endpoint
    if not os.path.isfile(endpoint):
        ctx.note("stop: no endpoint.json in %s -- no live instance to stop"
                 % ctx.paths.run_id)
        return out
    out["needed"] = True
    run = _run_ctl(["uninstall", "--target", ctx.target.name,
                    "--run-id", ctx.run_id], timeout=180.0)
    out["rc"] = run["rc"]
    out["text"] = run["text"]
    for line in _tail(run["text"], 12).splitlines():
        ctx.note("stop| " + line)
    if run["rc"] != 0:
        out["error"] = "uninstall rc=%s" % run["rc"]
    return out


def _wipe_workspace(ctx, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Make the run's workspace empty, so the seed starts from nothing.

    A workspace is not just its project directories: Eclipse keeps a serialized
    resource tree under ``.metadata/.plugins/org.eclipse.core.resources/.root/``,
    and a project that is still listed there makes ``projectCreate`` answer
    ``!ERROR: A resource with name '<name>' already exists in the workspace!`` and
    then *hang* (measured 2026-10-07: 900 s until the case's own timeout killed
    it).  Deleting the whole workspace is what ``ctl install`` does by default for
    exactly this reason; this case does it itself because the seed has to happen
    while the IDE is not running.  A foreign project is never reached here: ``pre``
    skips first.
    """
    workspace = plan["workspace"]
    out: Dict[str, Any] = {"path": workspace, "removed": False,
                           "had": sorted(os.listdir(workspace))
                           if os.path.isdir(workspace) else [], "error": ""}
    last: Optional[Exception] = None
    for attempt in range(_WIPE_ATTEMPTS):
        try:
            if os.path.isdir(workspace):
                shutil.rmtree(workspace)
            os.makedirs(workspace, exist_ok=True)
            out["removed"] = True
            break
        except OSError as exc:               # a JVM still letting go of a lock
            last = exc
            time.sleep(1.0)
    if not out["removed"]:
        out["error"] = ("could not empty %s after %d attempts: %r"
                        % (workspace, _WIPE_ATTEMPTS, last))
    ctx.note("wipe: %s removed=%s (had %s)%s"
             % (workspace, out["removed"], out["had"] or "<nothing>",
                "" if out["removed"] else " ERROR " + out["error"]))
    return out


def _seed(ctx, plan: Dict[str, Any], name: str, marker: str) -> Dict[str, Any]:
    """Step 1 -- projectCreate the TI project into the run's workspace + overlay."""
    out: Dict[str, Any] = {"ok": False, "error": "", "argv": [], "overlay": [],
                           "device": None, "project_name": None, "log_tail": ""}
    workspace = plan["workspace"]
    os.makedirs(workspace, exist_ok=True)
    proj = os.path.join(workspace, name)
    out["path"] = proj

    launcher = _override("launcher") or ctx.target.launcher_path()
    if not launcher or not os.path.isfile(launcher):
        out["error"] = "IDE launcher not found: %r (override with %sLAUNCHER=<abs path>)" \
                       % (launcher, _BOARD_ENV)
        return out
    plan["launcher"] = launcher

    argv = [launcher, "-noSplash", "-data", workspace,
            "-application", "com.ti.ccstudio.apps.projectCreate",
            "-ccs.projectSpec", plan["spec"], "-ccs.name", name]
    out["argv"] = argv
    run = _run_capture(argv, _CREATE_TIMEOUT, cwd=workspace)
    out["rc"] = run["rc"]
    out["log_tail"] = _tail(run["text"])
    for line in out["log_tail"].splitlines():
        ctx.note("create| " + line)
    if run["timed_out"]:
        out["error"] = "projectCreate timed out after %.0fs (%s)" % (run["elapsed"], run["killed"])
        return out
    if run["rc"] != 0:
        out["error"] = "projectCreate rc=%s" % run["rc"]
        return out
    landed = [entry for entry in (".project", ".cproject", ".ccsproject")
              if os.path.isfile(os.path.join(proj, entry))]
    if len(landed) != 3:
        out["error"] = "projectCreate rc=0 but the project description did not land: %s" % landed
        return out

    # -- R2: identity read-back, verbatim --------------------------------- #
    ccsproject = os.path.join(proj, ".ccsproject")
    out["device"] = _project_device(_read_text(ccsproject))
    project_xml = _read_text(os.path.join(proj, ".project"))
    match = re.search(r"<projectDescription>\s*<name>([^<]*)</name>", project_xml)
    out["project_name"] = match.group(1) if match else None
    ctx.note("readback: .ccsproject deviceVariant=%r (expected %r); .project name=%r "
             "(asked %r)" % (out["device"], "TMS320C28XX." + _EXPECTED_DEVICE,
                             out["project_name"], name))

    # -- the overlay (R3): the three files this case owns ------------------ #
    stage = os.path.join(os.path.dirname(ctx.paths.endpoint), "board")
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(os.path.join(stage, ".launches"), exist_ok=True)
    syscfg = os.path.join(proj, "c2000.syscfg")
    payload = os.path.join(proj, "empty_driverlib_main.c")
    launch_dir = os.path.join(proj, ".launches")
    launch = os.path.join(launch_dir, _LAUNCH_NAME + ".launch")
    os.makedirs(launch_dir, exist_ok=True)
    _write_text(syscfg, _SYSCFG)
    _write_text(payload, _PAYLOAD.replace(_MARKER_TOKEN, marker))
    _write_text(launch, (_LAUNCH
                         .replace("@PROPS@", _PROPS)
                         .replace("@CCXML@", _CCXML)
                         .replace("@PROBE@", _PROBE)
                         .replace("@CORE@", _CORE)
                         .replace("@NAME@", name)))
    for path in (syscfg, payload, launch):
        out["overlay"].append("%s (%d B)" % (os.path.relpath(path, workspace),
                                             os.path.getsize(path)))
    ctx.note("overlay: %s" % "; ".join(out["overlay"]))

    # -- the launch configuration's other half: the ACTIVE TARGET CONFIG ------ #
    # Measured 2026-10-07: a `.launch` with
    # ``ATTR_TARGET_CONFIG=${target_config_active_default:<project>}`` does NOT
    # resolve on its own.  On a workspace that has never been told which ccxml to
    # use, the launch stops with the modal "You require a target configuration to
    # start a debug session" (screenshot + the dialog's own text), the target is
    # never loaded, and `Resume` stays disabled for its whole poll window.  CCS
    # keeps that choice in the workspace preference
    # ``.metadata/.plugins/org.eclipse.core.runtime/.settings/
    # com.ti.ccstudio.system.setup.prefs``:
    #
    #     DEFAULT_CCS_TARGET_CONFIGURATION=C\:\\...\\targetConfigs\\TMS320F280025C.ccxml
    #
    # (verbatim from the workspace where the same `.launch` shape *does* launch --
    # `<runs>/ccs12-e2e/ws/.../empty_driverlib_project`).  This case owns its
    # workspace and starts the IDE itself, so it writes that one key before the
    # instance comes up; without it the `.launch` is only half a launch
    # configuration.
    ccxml = os.path.join(proj, "targetConfigs", _CCXML)
    settings = os.path.join(workspace, ".metadata", ".plugins",
                            "org.eclipse.core.runtime", ".settings")
    os.makedirs(settings, exist_ok=True)
    setup = os.path.join(settings, "com.ti.ccstudio.system.setup.prefs")
    escaped = ccxml.replace("\\", "\\\\").replace(":", "\\:")
    _write_text(setup, "DEFAULT_CCS_TARGET_CONFIGURATION=%s\n"
                       "eclipse.preferences.version=1\n" % escaped)
    out["ccxml"] = ccxml
    out["ccxml_exists"] = os.path.isfile(ccxml)
    out["setup_prefs"] = setup
    ctx.note("target-config: %s exists=%s; DEFAULT_CCS_TARGET_CONFIGURATION=%s (%s)"
             % (ccxml, out["ccxml_exists"], escaped, setup))

    # -- the LaunchBar's own state: written from scratch, ours in `debug` mode --- #
    # The IDE reads this file at startup, and it carries two different things:
    #
    # * the descriptors the LaunchBar has **discovered** (`configDescList`).  A stale
    #   list from another run would make `launchActive` drive somebody else's
    #   configuration while still answering OK (the archive's "OK with zero effect"),
    #   which is why this file used to be deleted outright.  Writing it from scratch
    #   covers the same hazard, and `configDescList` is deliberately **not** written
    #   here at all: it stays the IDE's own record (`_wait_launchbar`).
    # * the **mode** `launchActive` uses (`<descriptor>/activeLaunchMode`).  Measured
    #   2026-10-07: when a fresh instance builds that state itself it records `run`,
    #   and `LaunchActiveCommandHandler.execute` is
    #   `DebugUITools.launch(config, getActiveLaunchMode().getIdentifier())` -- so in
    #   `run` mode the command is **accepted with a clean answer and no `dialog=`** and
    #   no debug session is ever created: the perspective **bounces back** (read at 2 s
    #   granularity: TICPerspective -> TIDebugPerspective at T+2/T+4 s -> TIC again from
    #   T+6 s; `research/cross-check-vs-successful-run.md` §3) instead of *settling*.
    #   Pre-seeded as `debug`
    #   (and kept across the instance's restart, measured), the same command put the
    #   perspective at `com.ti.ccstudio.TIDebugPerspective` and it held for 18 s, with
    #   the console carrying the target's GEL lines.  The mode is therefore a
    #   **precondition the load needs**, never a criterion of its own: the verdict is
    #   still the read-back plus the result words (`_expect`).
    #
    # Two descriptor names are written.  The **design is one of them**:
    # `_LAUNCH_NAME`, the only launch configuration this case's project declares.  The
    # project name goes in too as a **fallback**, not by design: the three real
    # workspaces above spell the default descriptor after the *project*
    # (`…descriptorType.default\:gpio_ex2_toggle`), and the measured rebuild of this
    # very case produced a second, project-named descriptor while `configDescList`
    # kept both.  Which of the two ends up active is **read back**, never assumed --
    # `_wait_launchbar` records the file's own lines, and the load's note names them.
    prefs = os.path.join(settings, "org.eclipse.launchbar.core.prefs")
    out["launchbar_prefs"] = prefs
    out["launchbar_stale"] = os.path.isfile(prefs)
    out["launchbar_names"] = [_LAUNCH_NAME, name]
    _write_text(prefs, _LAUNCHBAR_PREFS % (_LAUNCH_NAME, name))
    ctx.note("launchbar: wrote %s (a stale file was %s) -- activeLaunchMode=debug for "
             "%s; `configDescList` is left unwritten so `_wait_launchbar` still waits on "
             "a line this case does not produce"
             % (prefs, "there" if out["launchbar_stale"] else "absent",
                out["launchbar_names"]))

    # -- overlay (5): the board's real clock source (see `_patch_clock_source`) - #
    # This is a *board* fact, not a chip fact: R1 keeps the base for everything the
    # chip needs, and the board overrides the controlCARD's 20 MHz-crystal
    # assumption.  It is written before the build, so the built image's clock setup
    # is the board's; `_clock_readback` re-reads it from the built project so a
    # missing patch is a FAIL naming the clock source, not a silent XTAL build.
    clock = _patch_clock_source(ctx, proj)
    out["clock_patch"] = clock
    if clock["error"]:
        out["error"] = "clock source: " + clock["error"]
        return out
    out["overlay"].append("%s (%s)" % (os.path.relpath(clock["path"], workspace),
                                       clock["line"]))

    out["ok"] = True
    return out


def _build(ctx, plan: Dict[str, Any], proj: str, name: str) -> Dict[str, Any]:
    """Step 2 -- the headless build of `CPU1_RAM` in the seeded workspace."""
    out: Dict[str, Any] = {"argv": [], "rc": None, "timed_out": False,
                           "logs": {}, "errors_line": ""}
    for config in (_CONFIG,):
        argv = [plan["launcher"], "-noSplash", "-data", plan["workspace"],
                "-application", "com.ti.ccstudio.apps.projectBuild",
                "-ccs.projects", name, "-ccs.configuration", config,
                "-ccs.buildType", "full"]
        out["argv"].append(argv)
        ctx.note("build: %s" % " ".join(argv))
        run = _run_capture(argv, _BUILD_TIMEOUT, cwd=plan["workspace"])
        if run["killed"]:
            plan["killed"].append(run["killed"])
        # Measured shape (m4/build.log): "CCS headless build complete! 0 out of 1
        # projects have errors." -- the summary is prefixed, so no `^` anchor.
        match = re.search(r"(\d+) out of (\d+) projects have errors", run["text"])
        out["logs"][config] = {"rc": run["rc"], "timed_out": run["timed_out"],
                              "elapsed": run["elapsed"],
                              "errors": match.group(1) if match else None,
                              "total": match.group(2) if match else None,
                              "tail": _tail(run["text"])}
        out["rc"] = run["rc"]
        out["timed_out"] = run["timed_out"]
        if match:
            out["errors_line"] = match.group(0).strip()
        ctx.note("build %s: rc=%s timed_out=%s elapsed=%.1fs %s"
                 % (config, run["rc"], run["timed_out"], run["elapsed"],
                    out["errors_line"] or "<no 'errors' summary line>"))
        for line in _tail(run["text"], 25).splitlines():
            ctx.note("build| " + line)
    return out


def _generated(ctx, proj: str, name: str) -> Dict[str, Any]:
    """Step 3 -- the SysConfig-generated board.c and the three mux lines (R4)."""
    out: Dict[str, Any] = {"path": "", "mux": [], "missing": list(_MUX_LINES),
                           "build_started": 0.0, "mtime": 0.0}
    hits = sorted(glob.glob(os.path.join(proj, "**", "syscfg", "board.c"),
                            recursive=True))
    if not hits:
        ctx.note("board.c: no <project>/**/syscfg/board.c was generated")
        return out
    path = hits[0]
    out["path"] = path
    text = _read_text(path)
    out["mux"] = [(line, text[:text.index(line)].count("\n") + 1)
                  for line in _MUX_LINES if line in text]
    out["missing"] = [line for line in _MUX_LINES if line not in text]
    ctx.note("board.c: %s (%d B); mux lines %s"
             % (os.path.relpath(path, proj), os.path.getsize(path),
                "; ".join("%s @%d" % (line, line_no) for line, line_no in out["mux"])
                or "<none>"))
    if out["missing"]:
        ctx.note("board.c: MISSING %s" % "; ".join(out["missing"]))
    return out


def _artifact(ctx, proj: str, name: str, marker: str) -> Dict[str, Any]:
    """Step 4 -- the linked image: C2000 ELF + this run's marker."""
    out: Dict[str, Any] = {"path": "", "pattern": "", "size": 0, "sha256": "",
                           "mtime": 0.0, "elf": None, "marker_offset": -1,
                           "marker_encoding": ""}
    pattern = os.path.join(proj, _CONFIG, "*.out")
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
    with open(path, "rb") as handle:
        blob = handle.read()
    offset, encoding = _find_marker(blob, marker)
    out["marker_offset"] = offset
    out["marker_encoding"] = encoding
    elf = out["elf"] or {}
    ctx.note("artifact: %s size=%d mtime=%s sha256=%s class=%s endian=%s e_machine=%s "
             "(expected %d)"
             % (path, out["size"],
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(out["mtime"])),
                out["sha256"], elf.get("class"), elf.get("endian"),
                elf.get("machine"), _MACHINE))
    ctx.note("artifact: marker %r %s"
             % (marker, ("found at offset %d (%s)" % (offset, encoding))
                if offset >= 0 else "NOT FOUND in any encoding (ascii/u16le/u16be)"))
    return out


def _start(ctx, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Step 5 -- bring the instance up on the seeded workspace (`--keep-workspace`).

    The port is passed through when one was requested (``ctl verify --port N``):
    without it the install would fall back to the target's default while ``pre``
    checked the requested one, so the case would guard one port and open another --
    and on a machine where several sessions share the default port that is not
    isolation (measured 2026-10-07: `ctl uninstall` kills *every* pid listening on
    the run's port, so two runs on the same default port kill each other).
    """
    out: Dict[str, Any] = {"rc": None, "text": "", "error": ""}
    argv = ["install", "--target", ctx.target.name, "--run-id", ctx.run_id]
    port = getattr(ctx.runner, "port", None)
    if port:
        argv += ["--port", str(port)]
    argv.append("--keep-workspace")
    run = _run_ctl(argv, timeout=_INSTALL_TIMEOUT)
    out["rc"] = run["rc"]
    out["text"] = run["text"]
    for line in _tail(run["text"], 12).splitlines():
        ctx.note("install| " + line)
    if run["rc"] != 0:
        out["error"] = "install rc=%s" % run["rc"]
    return out


def _instance_pids(ctx) -> Optional[List[int]]:
    """This instance's pid set, or ``None`` when it cannot be resolved (fail closed).

    The pid the runner recorded for the case is filled in by ``ctl verify`` before
    ``_load`` runs; when it is not there yet, the runner resolves it (the recorded
    pid, widened by command line when the launcher handed the workbench to a child
    JVM).  ``None`` means **unknown**, and unknown is never widened to "every
    process": the window tools take a single ``-ProcId``, so an unscoped press or
    ``WM_CLOSE`` could land on another application's dialog (``A4-1a``,
    ``Runner.clean_room``).
    """
    pids = list(getattr(ctx, "screen_pids", None) or [])
    if pids:
        return pids
    resolve = getattr(getattr(ctx, "runner", None), "screen_pids", None)
    if not callable(resolve):
        return None
    try:
        resolved = resolve()
    except (screen.ScreenError, OSError):
        # An unknown pid is the fail-closed answer, and it must never abort the load:
        # the modal answering is an aid, not a stage of its own.
        return None
    if not resolved:
        return None
    ctx.screen_pids = list(resolved)
    return list(resolved)


def _load_dialogs(windows: screen.WindowMap) -> List[Tuple[str, str]]:
    """The ``#32770`` windows of THIS instance: ``[(hwnd, title)]``.

    Identification is the Win32 dialog class plus the instance's pid (the pid scope is
    already in ``windows``) -- **never a title** (``ui.open`` retitles the main shell,
    so a title is not an identity).  The titles come *out of* a window that was already
    identified that way: they are only used to choose an answer, never to find the
    window.  One implementation, so `_sweep_dialogs` and the load stage's answering
    cannot drift apart on what counts as a dialog.
    """
    return sorted((hwnd, meta[2]) for hwnd, meta in windows.items()
                  if meta[1] in DIALOG_CLASSES)


def _modal_row(ctx, pids: List[int], windows: screen.WindowMap, hwnd: str,
               title: str, when: str) -> Dict[str, Any]:
    """Decide -- and, when the criterion says so, perform -- one ``#32770``'s answer.

    The criterion is the dialog's own **visible Button children**, never its title:

    * the affirmative button is offered exactly once -> press it (``BM_CLICK``, what a
      user's click does) and let the caller keep waiting;
    * **no Button child at all** -> the *progress* shell (`Loading Program: …`): it
      asks nothing, so nothing is pressed and nothing is decided against it -- it is
      waited out.  Zero hits here is normal, not a fault, and closing it could cancel
      the load;
    * buttons, but not the affirmative one -> refuse: nothing here was measured to be
      a question this case may answer;
    * the affirmative twice or more -> refuse and name the candidates (text addressing
      must resolve to exactly one control, §13.7).

    ``action`` is ``pressed`` / ``no-button`` / ``refused``; every other field is
    verbatim evidence.
    """
    row: Dict[str, Any] = {"when": when, "at": _stamp(), "hwnd": hwnd, "title": title,
                           "button": _LOAD_MODAL_ANSWER, "buttons": [], "candidates": [],
                           "action": "", "refusal": "", "output": ""}
    # ``win-click-button.ps1`` addresses its window by **title substring over every
    # visible window of the pid scope** (``Find``), not by the class+pid pair this
    # dialog was identified with.  The address is therefore the title *read off an
    # already-identified window*, and it has to be unique in that same scope -- and
    # matched the same way (case-insensitively) -- or the tool walks into whichever
    # window it enumerates first.
    addressed = sorted(h for h, meta in windows.items()
                       if title.lower() in meta[2].lower())
    if addressed != [hwnd]:
        row["action"] = "refused"
        row["candidates"] = addressed
        row["refusal"] = ("the title %r addresses %d window(s) of this instance "
                          "(%s), so the button tool cannot be pointed at one of them"
                          % (title, len(addressed),
                             "; ".join('%s "%s"' % (h, windows[h][2])
                                       for h in addressed) or "<none>"))
        return row
    buttons = screen.buttons(title, pids=pids)   # `-ListOnly` semantics: it presses nothing
    row["buttons"] = ['%s "%s"' % (h, t) for h, t in buttons]
    if not buttons:
        row["action"] = "no-button"
        row["refusal"] = ("no visible Button under this dialog -- the progress shell; "
                          "nothing to answer, so it is waited out (never closed, and "
                          "never a failure)")
        return row
    hits = [(h, t) for h, t in buttons if _LOAD_MODAL_ANSWER.lower() in t.lower()]
    if len(hits) != 1:
        row["action"] = "refused"
        row["candidates"] = ['%s "%s"' % (h, t) for h, t in hits]
        row["refusal"] = ("%d of the %d visible Button(s) are the affirmative %r -- text "
                          "addressing must resolve to exactly one, and picking one of "
                          "several is a silent wrong press"
                          % (len(hits), len(buttons), _LOAD_MODAL_ANSWER))
        return row
    output = screen.click_button(title, _LOAD_MODAL_ANSWER, pids=pids)
    presses = [line.strip() for line in output.splitlines() if "BM_CLICK" in line]
    if not presses:
        # §13.7: the tool's three states, all in its own verbatim output --
        # `ERR no visible Button matching '…'` (0 hits) or `ERR ambiguous: N …` plus
        # the candidate lines (>1 hits).  Both mean "nothing was pressed", and
        # counting either as the press is the silent wrong click.
        row["action"] = "refused"
        row["refusal"] = ("the button tool pressed nothing -- its verbatim output is %r"
                          % output.strip()[:400])
        return row
    row["action"] = "pressed"
    row["output"] = presses[0]
    return row


def _record_modal(ctx, rows: List[Dict[str, Any]],
                  row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Append one modal ledger row unless that window already told the same story.

    The key is the window (its ``hwnd``) *plus* what was decided about it.  A shell
    that stays on screen is met again every round, and re-recording "no Button" each
    time would be noise, not evidence; a shell that goes away and comes back is a new
    window (new hwnd) and is recorded again.  The note is written here, so the ledger
    line sits at the point in the trace where the decision was taken.
    """
    key = (row.get("hwnd") or row["refusal"], row["action"])
    if any((other.get("hwnd") or other["refusal"], other["action"]) == key
           for other in rows):
        return None
    rows.append(row)
    if row["action"] == "pressed":
        ctx.note("load: modal answer (%s) -- #32770 %s \"%s\": buttons %s; pressed "
                 "%r -> %s" % (row["when"], row["hwnd"], row["title"],
                               row["buttons"] or "<none>", row["button"], row["output"]))
    else:
        ctx.note("load: modal answer %s (%s) at %s -- #32770 %s \"%s\": buttons %s; %s%s"
                 % ("NO BUTTON" if row["action"] == "no-button" else "REFUSED",
                    row["when"], row["at"], row["hwnd"], row["title"],
                    row["buttons"] or "<none>", row["refusal"],
                    ("; candidates: " + "; ".join(row["candidates"]))
                    if row["candidates"] else ""))
    return row


def _answer_load_modal(ctx, out: Dict[str, Any], when: str) -> List[Dict[str, Any]]:
    """Answer the load stage's modal **question** by pressing its button, not by closing it.

    The boundary between answering and closing, with the criterion for each:

    * an **error box** is a *statement* -- nothing is being asked, and the only
      disposal is ``WM_CLOSE`` (the window's X).  That is `_sweep_dialogs` here, and
      `Runner.clean_room` for the other cases;
    * a **yes/no question** is the exact opposite: ``WM_CLOSE`` on it is *cancel*, so
      "closing" it cancels the very load this stage is waiting for.  Measured, not
      theorised: while the ``Reuse Debug Settings`` window stands the SWT thread is
      blocked, ``launchActive`` never finishes, and the gate reads ``TICPerspective``
      for the whole budget (frame 114 of run ``ccs12-p42``; the load's own request
      answered ``ERR timeout UI task did not finish within 15000 ms``).  So a question
      is **answered by its button text** and the wait continues;
    * a **progress shell** (`Loading Program: …`) is neither: it has no Button at all,
      asks nothing, and is waited out (see `_modal_row`).

    Which one is on screen is decided by the dialog's **buttons**, not by its title
    (`_modal_row`); the dialog itself is identified by **class + this instance's pid**
    (`_load_dialogs`), never by a title.  Any refusal -- an unknown pid, a failed
    enumeration, a title address that is not unique in the scope the button tool
    itself uses, no affirmative button, or a press the tool's own three states
    rejected -- records the reason and the candidates and presses **nothing**
    (§13.2/§13.7): picking a target out of an ambiguous set is the silent wrong press
    this refuses.

    Returns the ledger rows this call added (usually none: no ``#32770`` on screen).
    """
    rows: List[Dict[str, Any]] = out.setdefault("modal_answers", [])
    added: List[Dict[str, Any]] = []
    pids = _instance_pids(ctx)
    if not pids:
        row = _record_modal(ctx, rows, {
            "when": when, "at": _stamp(), "hwnd": "", "title": "",
            "button": _LOAD_MODAL_ANSWER, "buttons": [], "candidates": [],
            "action": "refused", "output": "",
            "refusal": ("the instance's pid is unknown, so no window can be addressed "
                        "and a press could reach another application")})
        return [row] if row is not None else []
    try:
        windows = screen.visible_windows(pids)
    except screen.ScreenError as exc:
        row = _record_modal(ctx, rows, {
            "when": when, "at": _stamp(), "hwnd": "", "title": "",
            "button": _LOAD_MODAL_ANSWER, "buttons": [], "candidates": [],
            "action": "refused", "output": "",
            "refusal": "the window enumeration failed: %s" % exc})
        return [row] if row is not None else []
    for hwnd, title in _load_dialogs(windows):
        if any(row["hwnd"] == hwnd and row["action"] == "pressed" for row in rows):
            # Already answered in this run.  The wait keeps polling (that is the
            # caller's job), but the same question is not pressed twice: a shell that
            # survives the press is evidence the press did not take, and sending the
            # same BM_CLICK again would act twice on one question.
            continue
        try:
            row = _modal_row(ctx, pids, windows, hwnd, title, when)
        except screen.ScreenError as exc:
            row = {"when": when, "at": _stamp(), "hwnd": hwnd, "title": title,
                   "button": _LOAD_MODAL_ANSWER, "buttons": [], "candidates": [],
                   "action": "refused", "output": "",
                   "refusal": "the window tools failed: %s" % exc}
        recorded = _record_modal(ctx, rows, row)
        if recorded is not None:
            added.append(recorded)
    return added


def _sweep_dialogs(ctx) -> Dict[str, Any]:
    """Dismiss stale modal shells of THIS instance before driving the launch.

    Measured 2026-10-07 (window enumeration of the run's own pid, right after the
    instance came up): a freshly started CCS already carries ``#32770`` modals --
    ``CCS Crash Report``, re-raised from a stale
    ``Unexpected CCS exit detected [10/1/26, 3:39 PM]`` record the debug server
    keeps -- and they stack across runs.  The bridge-requiring cases get this
    sweep for free through ``Runner.clean_room``; a case that brings its own
    instance up does not, so it does it itself.  Scope is the Win32 dialog class
    plus this instance's pid, **never a title**: a dialog is identified by class +
    pid, and for the *stale shells* this sweep is for (error boxes, crash reports)
    ``WM_CLOSE`` -- the window's X -- is the right disposal.

    That last sentence is **not** the rule for a dialog that asks a question:
    ``WM_CLOSE`` on a yes/no box means *cancel*, so the load stage answers the one
    question it was measured on by button text instead -- see `_answer_load_modal`
    for the boundary and its evidence.
    """
    out: Dict[str, Any] = {"pids": None, "before": [], "after": [], "problems": []}
    try:
        pids = _instance_pids(ctx)
        out["pids"] = list(pids or [])
        if not pids:
            # Same fail-safe `clean_room` uses: without the instance's pid the only
            # scope left is "every process", and closing other applications'
            # windows is not this case's business.
            out["problems"] = ["instance pid unknown; not touching any window"]
        else:
            out["before"] = _load_dialogs(screen.visible_windows(pids))
            out["problems"] = ctx.runner.clean_room(ctx)
            out["after"] = _load_dialogs(screen.visible_windows(pids))
    except screen.ScreenError as exc:
        out["problems"] = ["could not enumerate windows: %s" % exc]
    ctx.note("dialogs: instance pids=%s; #32770 before=%s after=%s%s"
             % (out["pids"], out["before"] or "<none>", out["after"] or "<none>",
                (" problems=" + "; ".join(out["problems"])) if out["problems"] else ""))
    return out


def _fingerprint(path: str) -> str:
    if not os.path.isfile(path):
        return "absent"
    return "%s/size=%d/mtime=%.0f" % (_sha256(path)[:12], os.path.getsize(path),
                                      os.path.getmtime(path))


def _clock_source(text: str) -> Optional[str]:
    """Which PLL source a ``device.h`` activates: ``"XTAL"``/``"INTOSC"``/``None``.

    The template flips between the two by *commenting one out* and uncommenting
    the other, so the active one is the bare ``#define`` and the inactive one is
    ``//#define``.  A file with both or neither is deliberately *neither* here --
    the caller treats that as a failure to name, not as a default to assume.
    """
    active: Optional[str] = None
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped == "#define USE_PLL_SRC_XTAL":
            if active is not None:
                return None
            active = "XTAL"
        elif stripped == "#define USE_PLL_SRC_INTOSC":
            if active is not None:
                return None
            active = "INTOSC"
    return active


def _patch_clock_source(ctx, proj: str) -> Dict[str, Any]:
    """Overlay (5) -- make the board's real clock source the effective one.

    The five overlay items this case owns are the three files of R3 plus this
    board fact: TI's template assumes the controlCARD's 20 MHz crystal
    (``#define USE_PLL_SRC_XTAL``), this board has no crystal at all -- Y1 is
    ``20M_5032`` and the 0R selectors R61/R51 are deliberately left unsoldered
    (see ``_CLOCK_INTOSC_ACTIVE``).  R1 ("the base supplies everything, we do not
    rewrite") is about the *chip* base; the board overrides the template's clock
    assumption, and without this flip the CPU halts in ``SysCtl_selectXTAL()``
    before the payload's ``main()`` runs.

    Only the two define lines change -- the INTOSC branch in the same file already
    carries the matching 100 MHz ``DEVICE_SETCLOCK_CFG``.  The read-back happens
    twice: here (immediately, so a failed write is named as such) and again in
    ``_clock_readback`` from the built project (so removing the patch is a FAIL,
    not a silent XTAL build).
    """
    out: Dict[str, Any] = {"path": "", "error": "", "source_before": None,
                           "source": None, "line": ""}
    path = os.path.join(proj, "device", "device.h")
    out["path"] = path
    if not os.path.isfile(path):
        out["error"] = ("the TI template's device/device.h was not generated at %s, "
                        "so the board's INTOSC clock source cannot be selected and "
                        "the payload would halt in SysCtl_selectXTAL()" % path)
        return out
    text = _read_text(path)
    out["source_before"] = _clock_source(text)
    # Line-oriented, EOL-preserving: the template is LF, but never assume it.
    patched, xtal_hits = re.subn(r"(?m)^#define USE_PLL_SRC_XTAL(\r?)$",
                                 r"//#define USE_PLL_SRC_XTAL\1", text)
    patched, intosc_hits = re.subn(r"(?m)^//#define USE_PLL_SRC_INTOSC(\r?)$",
                                   r"#define USE_PLL_SRC_INTOSC\1", patched)
    if xtal_hits != 1 or intosc_hits != 1:
        out["error"] = ("device/device.h does not carry the clock-source pair "
                        "verbatim (%d XTAL line(s), %d INTOSC line(s) found), so the "
                        "PLL source cannot be flipped to the board's INTOSC"
                        % (xtal_hits, intosc_hits))
        return out
    _write_text(path, patched)
    out["source"] = _clock_source(_read_text(path))
    if out["source"] != _EXPECTED_CLOCK:
        out["error"] = ("device/device.h still activates the %r PLL source after the "
                        "patch, expected %r" % (out["source"], _EXPECTED_CLOCK))
        return out
    out["line"] = ("now #define USE_PLL_SRC_INTOSC (was %s)"
                   % (out["source_before"] or "<no active define>"))
    ctx.note("clock: %s -- %s; the board has no 20 MHz crystal (R61/R51 unsoldered), "
             "so the template's XTAL branch would spin in SysCtl_selectXTAL()'s "
             "unbounded ESTOP0 loop and the payload would never execute"
             % (path, out["line"]))
    return out


def _clock_readback(ctx, proj: str) -> Dict[str, Any]:
    """Read-only: the PLL source the *built* project's own device.h activates.

    Same shape as R2's device read-back, one level down: read the file the
    compiler will read, name the active define, and let ``_expect`` compare it
    with the board's real source.  Deliberately independent of the patch step --
    with the patch removed this still reports the XTAL build, so the failure names
    the clock source instead of hiding behind "no image".
    """
    out: Dict[str, Any] = {"path": "", "source": None, "line": ""}
    path = os.path.join(proj, "device", "device.h")
    out["path"] = path
    if not os.path.isfile(path):
        ctx.note("clock: %s does not exist, so the PLL source is unknown" % path)
        return out
    text = _read_text(path)
    out["source"] = _clock_source(text)
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip() == "#define USE_PLL_SRC_INTOSC":
            out["line"] = "%d: %s" % (number, line.strip())
    ctx.note("clock: %s activates PLL source %s (%s); this board's real source is "
             "INTOSC2, so anything but that halts the CPU in SysCtl_selectXTAL()"
             % (path, out["source"], out["line"] or "<no active define>"))
    return out


def _ask(ctx, request: str, out: Dict[str, Any]):
    """One bridge request whose loss is *recorded*, never raised.

    A mid-conversation socket reset -- the IDE dies, the port closes -- arrives as
    a bare `OSError`: ``Client.talk`` wraps only the connect, not the read
    (measured 2026-10-07: ``unexpected: ConnectionResetError(10054)`` aborted a
    whole case run, and the verdict never named the stage that failed).  The load
    stage must *report* that state, so the failure becomes a not-ok ``Response``
    plus a ``transport_error`` on the load record, and the case's verdict names it.
    """
    try:
        return ctx.request(request)
    except (CtlError, OSError) as exc:
        out["transport_error"] = "%s -> %r" % (request, exc)
        ctx.note("load: %s failed at the transport level: %r" % (request, exc))
        return Response("ERR internal load transport (%r)" % (exc,))


def _debug_view_items(text: str) -> Optional[int]:
    """``Tree`` item count of the **Debug** view's tree, or ``None`` if absent.

    `ui.tree` prints the widget tree depth-first, with the view tab as a
    ``CTabItem text="…"`` line and the view's own control subtree indented under
    it (`LiveBridge.java:836-838`/`:852`).  So the Debug view's count is the first
    ``[TreeItems=N]`` after its ``CTabItem`` line and before the next view tab --
    attributing it by position is what keeps "some other view's tree" from
    standing in for the debug context.  `None` means the view is not in the dump
    at all (which is what an idle IDE looks like).
    """
    items: Optional[int] = None
    inside = False
    for line in (text or "").splitlines():
        if re.match(r"\s*CTabItem\b", line):
            inside = ('text="%s"' % _DEBUG_VIEW) in line
            continue
        if not inside:
            continue
        match = re.search(r"\[TreeItems=(\d+)\]", line)
        if match:
            items = int(match.group(1))
            break
    return items


def _gate_open(perspective: Optional[str], items: Optional[int]) -> bool:
    """The read-only gate of Part 2, in one place.

    Both halves are required and both are read-only: the active perspective is the
    CCS **debug** perspective, and the Debug view's tree holds at least one item.
    Neither channel can move the target, so a *closed* gate is silence -- never an
    answer that may be read as "resume anyway".

    **Measured (2026-10-07, run `board-1007-final`, shadow frame
    ``0003-053306-ws_board_led_chase_device_device_c_Code_.png``, captured 1 s after
    ``launchActive``):** *one* item is the launch root node alone --
    ``ctl_board_chase [Code Composer Studio - Device Debugging]`` with no child --
    and that is what the view holds **while the launch is still going over JTAG**
    (the same frame's status bar reads ``Launching ctl_board_chase: (23%)``).  So
    this half proves "a launch exists", **not** "the launch finished": `True` here
    can be returned while the image is still loading.

    What a *finished* launch's view holds is **not established by any measurement
    we have** -- ``bridge/src/ctl/bridge/LiveBridge.java:852`` shows ``[TreeItems=N]``
    is ``((Tree) w).getItems().length``, i.e. the tree's **top-level** rows, not a
    walked hierarchy, and the archive's only green run (`run-ram-launch.md` §3)
    recorded ``ui.parts`` (perspective + view list), never an item count.  Do not
    invent a threshold for it; measure it first (C6).

    **Measured limitation (2026-10-07, board-show):** the gate is a *precondition*,
    not a proof of a session.  A launch that ERRORED (the probe was busy) still
    switched the perspective to `TIDebugPerspective` with the Debug view at
    `[TreeItems=1]` (the launch node alone) -- the gate opened on wait round 1 --
    and then `Resume` stayed `ERR disabled` for all 12 attempts, with the
    perspective falling back to `TICPerspective` once the launch died.  So the
    perspective/`TreeItems` pair cannot certify "a debug context exists"; that is
    what the closed loop in `_load` is for, and why its first step requires a
    `Resume` that actually RAN (`OK` + `OK executed <id>`) before `ERR disabled`
    is allowed to mean "running".
    """
    return perspective == _DEBUG_PERSPECTIVE and items is not None and items >= 1


def _wait_jobs_quiet(ctx, load_out: Dict[str, Any]) -> Dict[str, Any]:
    """Read-only: wait for this instance's **own startup jobs** to fall silent.

    A *fresh* instance (every `ctl verify` builds a new `configuration`) spends its
    first minutes downloading repository metadata -- the AC1 run's own
    `sys.wait jobs-idle` answers carry it verbatim, repeatedly:

        idle=false
        pending=2
        jobs_total=11 running=2 waiting=0 sleeping=9 none=0
          busy name="Loading the repository {0}" state=RUNNING
          busy name="https://software-dl.ti.com/ccs/esd/device_support_ccsv9/auto/content.jar" state=RUNNING

    and its first two `launchActive` issues (`bridge.log` 06:38:26 / 06:41:09) had
    **zero** effect while the third (06:43:41), issued after the downloads were
    done, took effect at once.  So the first launch waits for the instance to
    settle.

    This is a **soft** precondition, on purpose: the cap is a wall clock and the
    launch is issued anyway when it is spent.  A busy JobManager makes a launch
    *less likely* to take effect -- it is never a reason to SKIP or FAIL, and
    nothing here is a criterion (`_expect` never reads this record).  Only
    `sys.wait jobs-idle` -- a bridge method -- is called; it takes no argument and
    nothing here moves the target.
    """
    out: Dict[str, Any] = {"quiet": False, "rounds": 0, "waited_s": 0.0,
                           "idle": None, "jobs_total": None, "running": None,
                           "waiting": None, "pending": None, "busy": [],
                           "end_idle": None, "last": ""}
    started = time.monotonic()
    deadline = started + _JOBS_QUIET_WAIT_S
    first_busy: Optional[Dict[str, Any]] = None
    reading: Dict[str, Any] = {}
    while True:
        out["rounds"] += 1
        wait = _ask(ctx, "sys.wait jobs-idle", load_out)
        if load_out.get("transport_error"):
            break
        out["last"] = wait.status_line
        reading = _jobs_reading(wait.text)
        if first_busy is None and reading["idle"] != "true":
            first_busy = reading
        out["end_idle"] = reading["idle"]
        if reading["idle"] == "true":
            out["quiet"] = True
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(_JOBS_QUIET_POLL_S)
    # "Then" -- the state to line up against "what was still running while the launch
    # did nothing": the **first** busy reading, or the last one when the instance never
    # went quiet at all.
    then = first_busy or reading
    for key in ("idle", "jobs_total", "running", "waiting", "pending", "busy"):
        out[key] = then.get(key)
    out["waited_s"] = round(time.monotonic() - started, 1)
    ctx.note("load: settle -- the instance's own jobs are quiet=%s after %d poll(s) "
             "in %.1fs; then: idle=%s jobs_total=%s running=%s waiting=%s pending=%s "
             "busy=%s; at the end: idle=%s (a fresh instance downloads repository "
             "metadata, and the first `launchActive` issues of the AC1 run took no "
             "effect until that was over)"
             % (out["quiet"], out["rounds"], out["waited_s"], out["idle"],
                out["jobs_total"], out["running"], out["waiting"], out["pending"],
                out["busy"] or "<none>", out["end_idle"]))
    if not out["quiet"]:
        ctx.note("load: settle -- the instance was still busy after %.0fs (last "
                 "answer %r); the launch is issued ANYWAY -- this is a soft "
                 "precondition, never a SKIP and never a FAIL"
                 % (_JOBS_QUIET_WAIT_S, out["last"]))
    return out


def _jobs_reading(text: str) -> Dict[str, Any]:
    """The JobManager fields of one `sys.wait jobs-idle` answer, verbatim.

    (`idle=`, `pending=`, and the counts line -- the bridge prints
    ``jobs_total=11 running=2 waiting=0 sleeping=9 none=0`` **on one line**, so the
    keys are searched for, not line-anchored -- plus the `busy name=` lines.  Nothing
    here derives a value; every field is the bridge's own text.)
    """
    read: Dict[str, Any] = {"idle": None, "jobs_total": None, "running": None,
                            "waiting": None, "pending": None, "busy": []}
    for key in ("idle", "jobs_total", "running", "waiting", "pending"):
        found = re.search(r"\b%s=(\w+)" % key, text)
        read[key] = found.group(1) if found else None
    read["busy"] = [line.strip() for line in text.splitlines()
                    if line.strip().startswith("busy name=")]
    return read


def _descriptor_name(node_path: str) -> str:
    """``…descriptorType.default\\:ctl_board_chase`` -> ``ctl_board_chase``.

    The ``.prefs`` file spells a descriptor as its preference node path, with the
    colon escaped (three real workspaces on this machine; see `_LAUNCHBAR_PREFS`), so
    the name is the last colon-separated segment.
    """
    return node_path.strip().rsplit(":", 1)[-1].strip()


def _launchbar_state(path: str) -> Dict[str, Any]:
    """The LaunchBar's preference file, read **verbatim** (no window, no IDE).

    ``{"desc": <the configDescList line>, "names": [<descriptor name>, …],
    "modes": {<descriptor name>: <run|debug>}, "targets": {<descriptor name>:
    <activeLaunchTarget line>}}`` -- every field is the file's own text, so "which
    descriptor is active, and with which mode" is *read*, never assumed.
    """
    text = _read_text(path) if os.path.isfile(path) else ""
    out: Dict[str, Any] = {"desc": "", "names": [], "modes": {}, "targets": {}}
    for line in text.splitlines():
        if line.startswith("configDescList="):
            out["desc"] = line.strip()
            out["names"] = [_descriptor_name(item)
                            for item in line.split("=", 1)[1].split(",")
                            if _descriptor_name(item)]
        elif "/activeLaunchMode=" in line:
            node, _sep, mode = line.partition("/activeLaunchMode=")
            out["modes"][_descriptor_name(node)] = mode.strip()
        elif "/activeLaunchTarget=" in line:
            node, _sep, target = line.partition("/activeLaunchTarget=")
            out["targets"][_descriptor_name(node)] = target.strip()
    return out


def _wait_launchbar(ctx, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Read-only: wait for the LaunchBar to make OUR descriptor live.

    `launchActive` drives the LaunchBar's **active** descriptor, and the LaunchBar
    builds that state asynchronously after startup -- while it is still empty the
    command answers `OK` and does nothing (measured 2026-10-07, see
    ``_LOAD_LAUNCH_ATTEMPTS``).

    **The signal is the IDE's own ``<descriptor>/activeLaunchTarget`` line**, not the
    ``configDescList``: `_seed` now *writes* that same file (the version line and one
    ``activeLaunchMode=debug`` per seeded descriptor), so a name in the list it wrote
    is no longer proof of anything the IDE did -- waiting on it would be a
    self-written, self-waited loop.  The LaunchBar writes ``activeLaunchTarget`` when
    it *activates* a descriptor, which is a step after discovering it, and this case
    never writes that key; so its appearance for a descriptor this case seeded is the
    IDE telling us that descriptor is live.  Which descriptor that is, is precisely
    what the line names -- recorded, not assumed (`_launchbar_state`).

    The descriptors that count as "ours" are the launch configuration this case
    declares plus whatever project the workspace actually registers (the descriptor
    is named after the project -- the real workspaces above -- while the launch
    configuration has its own name, and the measured rebuild kept both).

    A timeout is not a verdict: it is recorded and the caller proceeds (the launch
    is then re-issued on its own budget, and the gate decides).
    """
    workspace = plan.get("workspace") or ""
    path = os.path.join(workspace, ".metadata", ".plugins",
                        "org.eclipse.core.runtime", ".settings",
                        "org.eclipse.launchbar.core.prefs")
    ours = {_LAUNCH_NAME} | set(_registered_projects(workspace))
    out: Dict[str, Any] = {"path": path, "found": False, "waited_s": 0.0,
                           "desc_line": "", "target_line": "", "rounds": 0,
                           "ours": sorted(ours), "names": [], "modes": {},
                           "targets": {}, "bound": [], "debug_bound": [],
                           "active": None}
    started = time.monotonic()
    deadline = started + _LAUNCHBAR_WAIT_S
    while True:
        out["rounds"] += 1
        state = _launchbar_state(path)
        out["desc_line"] = state["desc"]
        out["names"] = state["names"]
        out["modes"] = state["modes"]
        out["targets"] = state["targets"]
        out["bound"] = sorted(set(state["targets"]) & ours)
        # Both halves are needed to say the launch can do anything: the IDE must have
        # *activated* our descriptor (its own `activeLaunchTarget` line) **and** that
        # descriptor's mode must be `debug` -- in `run` the command is accepted and no
        # debug session is created (measured, see `_seed`).  The mode is our own seeded
        # value read back, not something waited for: the loop's progress comes from the
        # IDE's line, so this is a guard on the premise, never a self-written loop.
        out["debug_bound"] = [name for name in out["bound"]
                              if state["modes"].get(name) == "debug"]
        if out["debug_bound"]:
            out["found"] = True
            out["active"] = out["debug_bound"][0]
            out["target_line"] = state["targets"][out["active"]]
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(2.0)
    out["waited_s"] = round(time.monotonic() - started, 1)
    ctx.note("load: launchbar %s -> found=%s after %d poll(s) in %.1fs; the IDE's "
             "list is %s; descriptor modes %s; activeLaunchTarget lines %s; bound to "
             "ours=%s (debug=%s), so the descriptor the IDE made LIVE is %s%s"
             % (path, out["found"], out["rounds"], out["waited_s"],
                out["desc_line"] or "<no configDescList line>",
                out["modes"] or "<none>", out["targets"] or "<none>",
                out["bound"] or "<none>", out["debug_bound"] or "<none>",
                out["active"] or "<none>",
                "" if out["found"] else
                " (a `launchActive` issued before the LaunchBar makes our descriptor "
                "live answers OK and does nothing -- see _LOAD_LAUNCH_ATTEMPTS; the "
                "launch is then re-issued on its own budget and the gate decides)"))
    return out


def _wait_for_debug_context(ctx, load_out: Dict[str, Any],
                            budget_s: float) -> Dict[str, Any]:
    """Parts 1+2 -- wait for the launch to finish, then for a debug context.

    One round is: answer the load stage's modal question if one is on screen
    (`_answer_load_modal` -- the box blocks the SWT thread, so this is what lets the
    launch finish), then `sys.wait jobs-idle` (the bridge's own JobManager wait, the
    launch's own completion signal) plus the two read-only probes of Part 2.  The
    rounds are bounded by ``budget_s`` (the caller's slice of the overall budget,
    so a launch that had no effect can be re-issued between slices); an exhausted
    `jobs-idle` budget is a normal `OK`/`idle=false` and simply means "poll again",
    and a read that times out while a modal progress shell holds the UI thread is
    recorded and retried rather than trusted.  Every request goes through `_ask`,
    so a lost connection lands on ``load_out["transport_error"]`` and the loop ends
    instead of raising.
    """
    out: Dict[str, Any] = {"rounds": [], "opened_at_round": None, "open": False,
                           "idle_seen": False, "perspective": None,
                           "tree_items": None, "parts": None, "tree": None,
                           "budget_s": budget_s}
    deadline = time.monotonic() + max(0.0, budget_s)
    for round_no in range(1, _LOAD_WAIT_ROUNDS + 1):
        round_started = time.monotonic()
        # A modal *question* blocks the SWT thread, and no bridge read can finish
        # while it stands.  Measured 2026-10-07 (frame 114 of run `ccs12-p42`): the
        # load's own request answered `ERR timeout UI task did not finish within
        # 15000 ms` and eight further `ui.parts` reads said `TICPerspective`, while
        # the modal waited for an answer nobody gave.  So it is answered at the top
        # of the round, *before* the reads: answering it is what lets the launch
        # finish.  `_answer_load_modal` has the boundary -- a question is answered by
        # its button's text, `WM_CLOSE` would be *cancel* and would cancel the load.
        _answer_load_modal(ctx, load_out, "wait round %d" % round_no)
        wait = _ask(ctx, "sys.wait jobs-idle", load_out)
        if load_out.get("transport_error"):
            break
        match = re.search(r"^idle=(\w+)", wait.text, re.M)
        idle = match.group(1) if match else None
        pending = re.search(r"^pending=(\d+)", wait.text, re.M)
        out["idle_seen"] = out["idle_seen"] or idle == "true"
        parts = _ask(ctx, "ui.parts", load_out)
        perspective = _perspective(parts)
        # The tree only costs a call (and a large dump) once the perspective half of
        # the gate is satisfied -- the gate needs both halves, so this loses nothing.
        tree = None
        items = None
        if perspective == _DEBUG_PERSPECTIVE:
            tree = _ask(ctx, "ui.tree %d --shell all" % _LOAD_TREE_DEPTH, load_out)
            items = _debug_view_items(tree.text)
        out["rounds"].append({"round": round_no, "at": _stamp(),
                              "wait": _shape(wait), "idle": idle,
                              "pending": pending.group(1) if pending else None,
                              "parts": _shape(parts), "perspective": perspective,
                              "tree": _shape(tree) if tree is not None else "<skipped>",
                              "debug_items": items})
        ctx.note("load: wait round %d/%d -- sys.wait jobs-idle -> %s (idle=%s "
                 "pending=%s); ui.parts -> %s (perspective=%s); ui.tree %d --shell all "
                 "-> %s (Debug view [TreeItems=%s])"
                 % (round_no, _LOAD_WAIT_ROUNDS, wait.status_line, idle,
                    pending.group(1) if pending else "?", _shape(parts), perspective,
                    _LOAD_TREE_DEPTH,
                    _shape(tree) if tree is not None else "not asked (perspective is "
                    "not the debug one)", items))
        out["perspective"] = perspective
        out["tree_items"] = items
        out["parts"] = parts
        out["tree"] = tree
        if load_out.get("transport_error"):
            ctx.note("load: wait round %d aborted -- the bridge connection was lost "
                     "(%s); the load cannot be judged further"
                     % (round_no, load_out["transport_error"]))
            break
        if _gate_open(perspective, items):
            out["opened_at_round"] = round_no
            out["open"] = True
            ctx.note("load: the read-only gate opened on round %d -- perspective %s, "
                     "Debug view [TreeItems=%d]; a debug context exists, so a Resume "
                     "answer can now mean something" % (round_no, perspective, items))
            break
        # Hold the pace: a round whose requests all answered instantly must not let
        # the loop burn `_LOAD_WAIT_ROUNDS` and end the slice in about a second
        # (see `_LOAD_ROUND_MIN_S` for the measurement that made this necessary).
        busy = time.monotonic() - round_started
        if busy < _LOAD_ROUND_MIN_S:
            time.sleep(_LOAD_ROUND_MIN_S - busy)
        if time.monotonic() >= deadline:
            # `budget_s`, not `_LOAD_WAIT_BUDGET_S`: the caller passes a *slice*, so
            # reporting the constant here would print a number 4x the real one.
            ctx.note("load: the %.0fs wait budget is spent after %d round(s)"
                     % (budget_s, round_no))
            break
    if not out["open"]:
        ctx.note("load: the read-only gate NEVER opened in %d round(s) over %.0fs -- "
                 "the last ui.parts said perspective=%s and the Debug view's tree "
                 "held %s item(s); no debug context exists, so the image is not "
                 "loaded (or the launch took no effect) and the program cannot be "
                 "running"
                 % (len(out["rounds"]), _LOAD_WAIT_BUDGET_S, out["perspective"],
                    "no" if out["tree_items"] is None else out["tree_items"]))
    return out


def _gate_pair(ctx, load_out: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One read-only reading of the pair the gate is made of, or ``None``.

    `ui.parts` for the active perspective and `ui.tree <depth> --shell all` for the
    Debug view's `Tree` item count -- the same two channels `_wait_for_debug_context`
    uses, so a reading here is directly comparable with the one the gate opened on.
    The tree is only asked for once the perspective half is satisfied (it costs a
    large dump, and the gate needs both halves anyway).  ``None`` means the bridge
    connection died; the caller reads `load_out["transport_error"]` and stops.
    """
    parts = _ask(ctx, "ui.parts", load_out)
    if load_out.get("transport_error"):
        return None
    perspective = _perspective(parts)
    tree = None
    items = None
    if perspective == _DEBUG_PERSPECTIVE:
        tree = _ask(ctx, "ui.tree %d --shell all" % _LOAD_TREE_DEPTH, load_out)
        if load_out.get("transport_error"):
            return None
        items = _debug_view_items(tree.text)
    return {"at": _stamp(), "perspective": perspective, "debug_items": items,
            "parts": _shape(parts),
            "tree": _shape(tree) if tree is not None else "<not asked>",
            "open": _gate_open(perspective, items)}


def _session_alive(ctx, load_out: Dict[str, Any],
                   before: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """Is the session the gate opened on **still there**?  Read-only, N-round.

    The gate only proves that a debug session *exists* -- `_gate_open`'s measured
    limitation, and the AC1 run shows what it is worth: the frame at 06:41:11 held
    the Debug view's launch root node while the status bar still read
    `Launching ctl_board_chase: (34%)`, and the session then died.  So the gate's
    own pair is read back `_LIVENESS_STEP_S` apart until `_LIVENESS_ROUNDS`
    **consecutive** rounds agree, and only then is there a verdict.

    Consecutive, not "one closed round is a death": one failed read cannot separate
    "the UI thread is busy" (a modal progress shell holds it during a launch; the
    gate's own loop tolerates that and polls on) from "the session is gone", and the
    measured shape on this board is that a single closed round is a *flicker* --
    `runs/board-1007-ac2/bridge.log` 07:09:38.235 reads the edit perspective once,
    with no write in flight, and 07:09:40.196 is the debug perspective again.  So
    ``[open, closed, open]`` is **not** a death (the pair keeps reading until it
    settles), while ``[open, closed, closed]`` is.  The same holds the other way:
    a single open read is not life until a second one says the same.

    **What this reading is allowed to decide belongs to the caller, and it is
    bounded by R7.**  It has verdict force only while the slice has released nothing
    yet -- and there it is the one thing that can tell the two readings of
    `Resume`'s `ERR disabled` apart ("no session" vs "the target is already
    running").  Once a clean `Resume` has run, the session going away is the
    *expected end state* of a release on CCS (the target keeps executing the RAM
    image), and R7 lists the session/perspective state as a **forbidden criterion**
    -- so the caller records the reading and certifies on the release, never the
    other way round, and never re-issues `launchActive` because of it.

    Returns ``(alive, record)``.  ``alive`` is ``True`` only for a run of
    ``_LIVENESS_ROUNDS`` open rounds; ``record["aborted"]`` is ``True`` only for a run
    of closed rounds.  ``alive`` *and* ``aborted`` both ``False`` is **no verdict**
    (the pair never settled inside ``_LIVENESS_MAX_ROUNDS``, or the transport died)
    and the caller must not read a session verdict out of either flag.
    ``record["diff"]`` is the verbatim two-reading difference (the perspective and the
    item count, before -> after) that names a death; the caller puts it in the note.
    A transport failure leaves ``alive`` ``False`` with ``record["aborted"]`` ``False``
    -- that is the caller's business, not a session verdict.
    """
    readings: List[Dict[str, Any]] = []
    streak = 0                      # consecutive rounds agreeing with the last one
    verdict: Optional[bool] = None  # None until the streak reaches _LIVENESS_ROUNDS
    for index in range(1, _LIVENESS_MAX_ROUNDS + 1):
        read = _gate_pair(ctx, load_out)
        if read is None:
            break                   # transport failure: not a session verdict
        read["round"] = index
        streak = streak + 1 if readings and readings[-1]["open"] == read["open"] else 1
        readings.append(read)
        if streak >= _LIVENESS_ROUNDS:
            verdict = read["open"]
            break
        time.sleep(_LIVENESS_STEP_S)
    out: Dict[str, Any] = {"alive": verdict is True, "aborted": False,
                           "verdict": verdict, "streak": streak,
                           "rounds": readings, "before": before, "diff": "",
                           "at": _stamp()}
    if verdict is False:
        closed = next(r for r in readings if not r["open"])
        out["aborted"] = True
        out["diff"] = ("perspective %s -> %s; Debug view [TreeItems=%s] -> "
                       "[TreeItems=%s]"
                       % (before.get("perspective"), closed["perspective"],
                          "no" if before.get("debug_items") is None
                          else before["debug_items"],
                          "no" if closed["debug_items"] is None
                          else closed["debug_items"]))
    return out["alive"], out


def _load(ctx, plan: Dict[str, Any], launch: str) -> Dict[str, Any]:
    """Step 6 -- make the target run OUR image, and *prove* that it is running.

    What stood here before broke on the first `OK` from `Resume`, on the theory
    that the handler is disabled until the target is halted.  That theory is
    false, and it is exactly the false green this step closes:

    * `launchActive` answers as soon as the launch *starts*, while the image is
      still going over JTAG.  A `Resume` issued then runs against the in-flight
      launch; the loader then halts the CPU at the entry point and nothing ever
      resumes it -- the LEDs stay dark while the case said PASS (measured
      2026-10-07: the case's own shadow frames put `launchActive` at 03:19:49 and
      `Resume` 3 s later, and the frame at the `Resume` moment still reads
      "Launching ctl_board_chase: (100%)" with the Debug view holding the launch
      root node only).
    * `Resume`'s result word alone cannot separate the states: `ERR disabled`
      means "nothing is suspended", which is true both when no session exists and
      when the target is already running (`run-ram-launch.md` §4.2), and a launch
      that took no effect leaves it `ERR disabled` for minutes on end.

    So there are three stages, each resting on a *read-only* answer:

    0. the launch itself is waited for -- the LaunchBar records our launch
       configuration asynchronously, and `launchActive` answers `OK` **with zero
       effect** while that record is still empty (measured 2026-10-07: `launchActive`
       6 s after the bridge came up left the perspective at `TICPerspective` for the
       whole 600 s budget; the same command on the same instance 2.5 min later
       switched it in 6 s).  So the instance's own startup jobs are given a bounded,
       read-only chance to settle (`_wait_jobs_quiet` -- a *soft* precondition, never
       a criterion), the workspace's own LaunchBar record is waited for, and a launch
       that shows no effect in its slice is issued again, bounded;
    1. wait for the launch to finish -- `sys.wait jobs-idle` under a generous
       budget (`_wait_for_debug_context`), never a sleep.  Every round of that wait
       first answers the load stage's modal **question** if one is on screen
       (`_answer_load_modal`): the box blocks the SWT thread, so nothing the wait could
       read would change until it is answered -- measured 2026-10-07, frame 114 of run
       `ccs12-p42`, where `Reuse Debug Settings` held the load and only pressing its
       `&Yes` let the session appear;
    2. open the gate: the debug perspective AND a non-empty Debug-view tree.  A
       gate that never opens is a FAIL naming the stage, never a fall-through.
       The perspective is only ever a *trigger* here (for stage 0's re-issue), never
       a criterion -- see `_gate_open`'s measured limitation;
    3. resume, then close the loop: R7's criterion is the **result word plus the
       `OK executed <command id>` line** (a `dialog=` line vetoes; the line count is
       only an auxiliary threshold; the forbidden criteria are `null`, the duration,
       and the session/perspective state).  So a `Resume` that ran -- `OK` with
       `OK executed …Resume`, **no** `dialog=` -- is this stage's **floor**: the
       suspended context existed and the target was released.  A following `Resume`
       answering `ERR disabled` (nothing suspended, therefore the target is
       **running**) is the **upgrade** on top of that floor, and a `Resume` is
       certified only when the upgrade arrives.  A **second** ran `Resume` means a
       context existed *again* (the resume was premature, or the loader halted the
       CPU at the entry point again) -- a newer reading that contradicts the release
       -- so the loop resumes again rather than concluding anything.  The polling
       runs for the slice's **wall clock** (`_LOAD_WAIT_SLICE_S`), never for a fixed
       number of attempts -- the measured scale is minutes (`_LOAD_POLL_S`), and a
       count would give up while the loader is still working.  A whole slice that
       released nothing re-issues `launchActive` (bounded by `_LOAD_RESUME_REISSUE`
       under `_LOAD_RESUME_BUDGET_S`), because the gate only proves that a debug
       *session exists* -- the launch may still be in flight or may have produced no
       resumable context at all.  A slice that DID release something is never
       re-issued: `launchActive` loads and halts at the entry point, so issuing it
       after a release is how the ac2 run pushed a running target back to its entry
       point (measured 2026-10-07: release 07:09:33.618, re-issue 07:09:38.686).

       **When the upgrade cannot be had** -- the session is gone by the time the
       confirming `Resume` would be sent, or no usable answer arrives -- the stage
       still certifies `running` on the release and records **verbatim** why the
       confirming call was unavailable, with the two liveness readings it was
       reading.  On CCS the debug session going away right after a release is this
       step's expected end state (the target keeps executing the RAM image) and R7
       makes the session/perspective state a forbidden criterion, so it cannot take
       the release away.  The stage never invents a "still halted" story for a run
       that has a clean release; the only two things that can keep it from
       certifying are the dialog veto (R-1) and a newer ran `Resume` that says a
       context existed again.  If nothing ever ran, the case FAILS naming the real
       state -- and the note says explicitly that a bare `ERR disabled` **cannot**
       separate "the launch produced no usable session" from "the target is already
       running" (R7), so the FAIL is "could not certify the program is running",
       never "the program is not running".  An answer that carries the bridge's
       `dialog=` line does **not** count as "ran" even when it carries
       `OK executed <id>` (R-1): the handler ran, the IDE raised a dialog, and "the
       handler ran" is not "the target was released".

    The three stages are judged on readings taken *inside* the observation window.
    The perspective, in particular, is not a criterion at all: it is the gate's
    input, read once, and the `ui.parts` recorded as `parts_after` is that same
    in-window answer -- never a fresh request after the loop (R-2).
    """
    out: Dict[str, Any] = {"launch_file": launch,
                           "launch_before": _fingerprint(launch),
                           "modal_answers": []}

    # The negative control first (C10): with no session yet, Resume must be
    # *disabled*.  Recording that shape is what makes the OK below meaningful.
    out["parts_before"] = _ask(ctx, "ui.parts", out)
    out["resume_before"] = _ask(ctx, "cmd.run " + _CMD_RESUME, out)
    ctx.note("load: cmd.run %s (before the launch) -> %s"
             % (_CMD_RESUME, _shape(out["resume_before"])))

    # -- the launch: let the instance settle, and let the LaunchBar know us ---- #
    # Two read-only waits before the first F11, both for the *same* reason: the
    # command is answered `OK` whether or not it did anything.  A fresh instance is
    # still downloading repository metadata (soft, `_wait_jobs_quiet`), and the
    # LaunchBar only records our configuration asynchronously (H2/`_wait_launchbar`).
    out["settle"] = _wait_jobs_quiet(ctx, out)
    out["launchbar"] = _wait_launchbar(ctx, plan)

    # F11's command: it launches the ACTIVE launch configuration, which is the one
    # this case installed into the workspace (its only project).  The debug
    # perspective below is only the *trigger* for re-issuing it (a no-effect launch
    # leaves no session to disturb); the verdict stays the closed loop below.
    #
    # Every issue is recorded as a ledger row (`launch_issues`): when it was sent, the
    # shape of its answer, and the pair read back after it.  The command is answered
    # `OK` whether or not it did anything, and the AC1 run needed three issues before
    # one took effect -- so "which issue did it" is the one thing a later root-cause
    # pass needs and cannot re-derive from anywhere else (requirement 3).
    out["launch_attempts"] = []
    out["launch_issues"] = []
    out["wait"] = None
    deadline = time.monotonic() + _LOAD_WAIT_BUDGET_S
    for attempt in range(1, _LOAD_LAUNCH_ATTEMPTS + 1):
        issued_at = _stamp()
        out["launch"] = _ask(ctx, "cmd.run " + _CMD_LAUNCH_ACTIVE, out)
        out["launch_attempts"].append(out["launch"])
        # The launch is what raises the modal question, and the wait below is where it
        # is answered -- but this site answers it too, because the question can be on
        # screen the moment the issue returns (the measured `Reuse Debug Settings`
        # appeared while the load was running) and the requirement is "answer it after
        # the issue as well as while waiting".  `_answer_load_modal` presses nothing
        # when there is nothing on screen, and never closes a question.
        _answer_load_modal(ctx, out, "after launchActive issue %d" % attempt)
        slice_s = max(0.0, min(_LOAD_WAIT_SLICE_S, deadline - time.monotonic()))
        out["wait"] = _wait_for_debug_context(ctx, out, slice_s)
        out["wait"]["issue"] = attempt
        last_round = (out["wait"]["rounds"] or [{}])[-1]
        out["launch_issues"].append(
            {"issue": attempt, "at": issued_at, "shape": _shape(out["launch"]),
             "rounds": len(out["wait"]["rounds"]), "reissued": False,
             "perspective": out["wait"]["perspective"],
             "debug_items": out["wait"]["tree_items"],
             "opened": bool(out["wait"]["open"]), "aborted": False})
        ctx.note("load: cmd.run %s (Eclipse command id, = the human's F11) issue "
                 "%d/%d, sent %s -> %s; read back after %.0fs at %s: perspective=%s, "
                 "Debug view [TreeItems=%s] -- %s"
                 % (_CMD_LAUNCH_ACTIVE, attempt, _LOAD_LAUNCH_ATTEMPTS, issued_at,
                    _shape(out["launch"]), slice_s, last_round.get("at", "?"),
                    out["wait"]["perspective"],
                    "no" if out["wait"]["tree_items"] is None
                    else out["wait"]["tree_items"],
                    "the gate OPENED" if out["wait"]["open"]
                    else "no session appeared in this slice"))
        if out["wait"]["open"] or out.get("transport_error"):
            break
        if time.monotonic() >= deadline:
            ctx.note("load: the %.0fs budget is spent; not re-issuing %s"
                     % (_LOAD_WAIT_BUDGET_S, _CMD_LAUNCH_ACTIVE))
            break
        ctx.note("load: the launch shows NO effect in the %.0fs slice (perspective "
                 "still %s, Debug view [TreeItems=%s]) -- issuing %s again; a "
                 "no-effect launch leaves no session to disturb, and the same command "
                 "on the same instance has been measured to take effect minutes later"
                 % (slice_s, out["wait"]["perspective"],
                    out["wait"]["tree_items"], _CMD_LAUNCH_ACTIVE))
    out["gate"] = {"open": out["wait"]["open"],
                   "opened_at_round": out["wait"]["opened_at_round"],
                   "perspective": out["wait"]["perspective"],
                   "debug_items": out["wait"]["tree_items"],
                   "issue": out["wait"].get("issue"),
                   "at": (out["wait"]["rounds"] or [{}])[-1].get("at", "")}

    # -- stage 3: the release, then whatever confirmation can be had -------------- #
    # R7 verbatim: the criterion is the **result word** plus a reply that carries
    # `OK executed <command id>`; a `dialog=` line vetoes; the line count is only an
    # auxiliary threshold; and the *forbidden* criteria are `null`, the duration, and
    # "the session came up / the perspective changed".  So the floor of this stage is
    # a `Resume` that ran cleanly -- `OK`, the `OK executed …Resume` line, no
    # `dialog=` line -- and the confirming `Resume` (`ERR disabled`: nothing
    # suspended, therefore the target is running) is the upgrade on top of that floor.
    # When the upgrade cannot be had, the stage certifies on the floor and records
    # verbatim *why* the confirming call was unavailable; it never guesses a "still
    # halted" story out of the session state.
    #
    # The read-only pair the gate is made of is what tells the two readings of a bare
    # `ERR disabled` apart ("no session" vs "the target is already running") -- but
    # **only before this slice has released anything**.  Once a clean `Resume` has
    # run, the session going away is the release's expected end state (the target
    # keeps executing the RAM image) and R7 forbids the session/perspective state as a
    # criterion, so the reading may not revoke the release and may not lead to a
    # re-issue of `launchActive` (`_session_alive`'s scope note).
    out["resume_attempts"] = []
    out["resume"] = None            # the Resume that RAN (the R7 shape subject)
    out["resume_at"] = None         # when that clean Resume ran (wall clock)
    out["resume_probe"] = None      # the confirming Resume -- must be ERR disabled
    out["resume_blocked"] = None    # a Resume that ran *and* raised a dialog (R-1)
    out["resume_reran"] = None      # a later Resume that ran again after the release
    out["resume_unconfirmed"] = None  # why the confirming call could not be had
    out["running"] = False
    out["resume_slices"] = []       # one record per slice: attempts, last answer
    out["resume_reissues"] = 0      # this stage's re-issues of `launchActive`
    out["liveness"] = []            # one record per read-only session check
    out["liveness_unsettled"] = None  # the pair's last "no verdict" reading, if any
    out["session_aborted"] = False  # sticky: came up, died, nothing released here
    out["abort_evidence"] = None    # the verbatim two-reading diff of the first one
    out["parts_at_giveup"] = None   # evidence only -- never a criterion (R-2)
    last_ran = None
    if not out["gate"]["open"]:
        # Never resume on silence: without a debug context a `Resume` answer has
        # no meaning at all (see the docstring), and this is the state AC3(c) must
        # turn red on.
        ctx.note("load: no debug context -- NOT sending %s; the program is not "
                 "running" % _CMD_RESUME)
    else:
        resume_started = time.monotonic()
        resume_deadline = resume_started + _LOAD_RESUME_BUDGET_S
        # The reading the gate opened on is the "before" of the first liveness pair.
        last_open: Dict[str, Any] = {"at": out["gate"]["at"],
                                     "perspective": out["gate"]["perspective"],
                                     "debug_items": out["gate"]["debug_items"],
                                     "open": True}
        pending_reissue: Optional[Dict[str, Any]] = None
        while True:
            # A slice is a **wall window**, never a number of attempts: an answer is
            # cheap (`sys.wait jobs-idle` came back in 0 ms 15 times in a row on
            # `board-1007-t2`), so a count would end the window while the loader is
            # still minutes from being resumable -- the measured scale is minutes.
            slice_s = max(0.0, min(_LOAD_WAIT_SLICE_S,
                                   resume_deadline - time.monotonic()))
            slice_started = time.monotonic()
            slice_deadline = slice_started + slice_s
            slice_attempts = 0
            aborted = False
            slice_last = "<no Resume was sent in this slice>"
            while True:
                # 1. Is the session still there?  Read-only, `_LIVENESS_ROUNDS`
                #    consecutive rounds (`_session_alive`).  What the reading is
                #    allowed to *decide* depends on whether this slice has released
                #    anything yet:
                #
                #    * nothing released yet -- a death is the one thing that can tell
                #      the two readings of `Resume`'s `ERR disabled` apart ("no
                #      session" vs "already running"), and resuming into a session that
                #      is not there would only buy more meaningless answers.  This is
                #      the reading's fail-closed job, and it decides ABORT only;
                #    * a clean `Resume` has already run -- R7 lists the session /
                #      perspective state as a *forbidden criterion*, and the session
                #      going away right after a release is this step's expected end
                #      state (the target keeps executing the RAM image).  So the
                #      reading is recorded, ends the slice, and the release is
                #      certified on R7's floor at the bottom of the slice; it may NOT
                #      revoke the release and may NOT lead to a re-issue of
                #      `launchActive`.
                alive, live = _session_alive(ctx, out, last_open)
                out["liveness"].append(live)
                if pending_reissue is not None and live["rounds"]:
                    first = live["rounds"][0]
                    pending_reissue.update({"perspective": first["perspective"],
                                            "debug_items": first["debug_items"],
                                            "opened": first["open"]})
                    pending_reissue = None
                if out.get("transport_error"):
                    break
                if not alive and not live["aborted"]:
                    # No verdict at all: the pair never settled (a perspective that
                    # keeps flicking), or the transport died.  That is neither
                    # evidence of a death -- a single closed round is not a death --
                    # nor a licence to resume into it, so look again; the slice's own
                    # wall clock bounds the retry.
                    out["liveness_unsettled"] = live
                    ctx.note("load: the session read-back did NOT settle in %d round(s) "
                             "(%s) -- no run of %d agreeing round(s) %.1fs apart, so "
                             "there is no session verdict here.  Not a death (a single "
                             "closed round must not be read as one) and not a licence "
                             "to resume: reading the pair again."
                             % (len(live["rounds"]),
                                " / ".join("open" if r["open"] else "closed"
                                           for r in live["rounds"])
                                or "<no round answered>",
                                _LIVENESS_ROUNDS, _LIVENESS_STEP_S))
                    if time.monotonic() >= slice_deadline:
                        break
                    time.sleep(_LOAD_POLL_S)
                    continue
                if not alive:
                    closed = next(r for r in live["rounds"] if not r["open"])
                    if last_ran is None:
                        aborted = True
                        out["session_aborted"] = True
                        if out["abort_evidence"] is None:
                            out["abort_evidence"] = live
                        if out["launch_issues"]:
                            out["launch_issues"][-1]["aborted"] = True
                        ctx.note("load: the debug session ABORTED -- the read-back was "
                                 "%s, the next one is %s (verbatim diff: %s).  No "
                                 "`Resume` has run in this slice, so nothing was "
                                 "released here and the slice is abandoned (resuming "
                                 "into a session that is not there would only buy more "
                                 "`ERR disabled`, which means nothing is suspended and "
                                 "is NOT evidence that the target is running, R7).  "
                                 "What this reading licenses is exactly 'the session "
                                 "is not there' -- it is not a reading that the target "
                                 "is not running, and it may not veto a release this "
                                 "stage has already made."
                                 % (_reading(last_open), _reading(closed),
                                    live["diff"]))
                        break
                    # A clean `Resume` ran in this slice: R7's floor stands, and this
                    # reading may not take it away.  The confirming `Resume` -- the
                    # upgrade -- is unavailable here (there is no session left to
                    # ask), so the unavailability is recorded verbatim now and the
                    # slice ends; the release is certified at the bottom of the slice.
                    why = ("the session read-back is GONE (%d closed round(s) %.1fs "
                           "apart)" % (_LIVENESS_ROUNDS, _LIVENESS_STEP_S))
                    out["resume_unconfirmed"] = {"why": why, "liveness": live}
                    _note_unconfirmed(ctx, out, why, live)
                    break
                last_open = live["rounds"][-1]
                # 2. The session is alive, so a `Resume` answer can now mean something.
                response = _ask(ctx, "cmd.run " + _CMD_RESUME, out)
                if out.get("transport_error"):
                    ctx.note("load: aborting the resume loop after %d attempt(s) -- "
                             "the bridge connection was lost" % (slice_attempts + 1))
                    break
                slice_attempts += 1
                slice_last = response.status_line
                out["resume_attempts"].append(response)
                ctx.note("load: cmd.run %s (Eclipse command id, = the human's F8) "
                         "attempt %d (%d in this %.0fs slice; session alive at %s) "
                         "-> %s"
                         % (_CMD_RESUME, len(out["resume_attempts"]), slice_attempts,
                            slice_s, last_open.get("at", "?"), _shape(response)))
                ran = response.ok and any(
                    line.startswith(_OK_MARK + _CMD_RESUME)
                    for line in response.payload)
                dialog = _dialog_line(response)
                if ran and dialog is not None:
                    # R-1: the handler reached the executed line, but the *same*
                    # answer carries the bridge's dialog line -- "the handler ran" is
                    # NOT "the target was released".  Fail closed
                    # (`measurement-hygiene` §13.2): record it, never let it stand in
                    # for `running`, and keep polling in case a later Resume answers
                    # cleanly.
                    out["resume_blocked"] = response
                    ctx.note("load: %s answered OK **with** %r but the same answer "
                             "also carries %r -- the IDE raised a dialog, so this does "
                             "not prove the target was released; NOT counting it as "
                             "'ran' (fail closed)"
                             % (_CMD_RESUME, _OK_MARK + _CMD_RESUME, dialog))
                elif ran:
                    if last_ran is not None:
                        # A *later* `Resume` ran: `OK executed` says the handler was
                        # enabled, i.e. a suspended context existed **again** -- a
                        # newer reading that contradicts the release.  Recorded (the
                        # FAIL wording names it) and the loop keeps resuming; it never
                        # becomes a release reading of its own.
                        out["resume_reran"] = response
                        ctx.note("load: %s ran AGAIN -- a suspended context existed "
                                 "again after the release at %s (%s), so a newer "
                                 "reading contradicts it; keeping the loop open rather "
                                 "than concluding that nothing is suspended"
                                 % (_CMD_RESUME, out["resume_at"],
                                    _shape(out["resume"])))
                    last_ran = response
                    out["resume"] = response
                    out["resume_at"] = _stamp()
                    ctx.note("load: %s ran -- a suspended context existed; confirming "
                             "that nothing is suspended any more" % _CMD_RESUME)
                    time.sleep(_RUN_SETTLE_S)
                    if time.monotonic() >= slice_deadline:
                        # The slice's wall clock has to be able to end a session that
                        # keeps answering `OK` too: `continue`-ing past this check
                        # (which the earlier shape did) lets a target that is halted
                        # and released over and over -- exactly the premature-launch
                        # shape -- keep the loop alive past every budget it has.
                        break
                    continue                # the next call is the confirmation
                elif (last_ran is not None and out["resume_blocked"] is None
                      and response.status_line.startswith("ERR disabled")):
                    out["resume_probe"] = response
                    out["running"] = True
                    ctx.note("load: confirmed -- %s answered %r after a Resume that "
                             "ran, so nothing is suspended: the target IS RUNNING"
                             % (_CMD_RESUME, response.status_line))
                    break
                # Not legal yet (no context), or a Resume that did not carry the
                # confirmation line: keep polling until this **slice's wall clock** is
                # spent -- never until a fixed number of attempts.
                if time.monotonic() >= slice_deadline:
                    break
                time.sleep(_LOAD_POLL_S)
            out["resume_slices"].append(
                {"slice": len(out["resume_slices"]) + 1, "budget_s": round(slice_s, 1),
                 "attempts": slice_attempts, "aborted": aborted,
                 "elapsed_s": round(time.monotonic() - slice_started, 1),
                 "last": slice_last})
            if out["running"] or out.get("transport_error"):
                break
            if last_ran is not None:
                # A clean `Resume` ran in this slice: the release is R7's floor, and
                # exactly two things keep the stage from certifying it -- the dialog
                # veto (R-1: bound to the *conclusion*, so it survives the whole
                # slice) and a newer ran `Resume` that says a context existed again.
                # Anything else means the confirming `Resume` -- the upgrade -- could
                # not be had, and the stage then certifies `running` on the release
                # itself, recording verbatim why the call was unavailable (the two
                # liveness readings included).  It never invents a "still halted" story
                # for a run that has a clean release.
                #
                # `launchActive` is NEVER re-issued here: it loads and HALTS at the
                # entry point, so re-issuing it after a release is how the ac2 run
                # pushed a running target back to its entry point (measured 2026-10-07
                # `board-1007-ac2/bridge.log`: release 07:09:33.618, re-issue
                # 07:09:38.686).  The re-issue below is for the slices that released
                # nothing.
                if out["resume_blocked"] is None and out["resume_reran"] is None:
                    unconfirmed = out["resume_unconfirmed"]
                    if unconfirmed is None:
                        why = ("no usable answer to the confirming %s arrived (the last "
                               "answer in the slice was %r)" % (_CMD_RESUME, slice_last))
                        unconfirmed = {"why": why,
                                       "liveness": (out["liveness_unsettled"]
                                                    or (out["liveness"][-1]
                                                        if out["liveness"] else None))}
                        out["resume_unconfirmed"] = unconfirmed
                        _note_unconfirmed(ctx, out, why, unconfirmed["liveness"])
                    out["running"] = True
                    ctx.note("load: certified on R7's floor -- the target IS RUNNING on "
                             "the release that ran at %s (%s); the confirming %s was "
                             "unavailable (%s) and is recorded above, not assumed"
                             % (out["resume_at"], _shape(out["resume"]), _CMD_RESUME,
                                unconfirmed["why"]))
                break
            if out["resume_reissues"] >= _LOAD_RESUME_REISSUE:
                break
            if time.monotonic() >= resume_deadline:
                break
            # The slice is over and **nothing was released in it** (a slice in which a
            # clean `Resume` ran never reaches here -- see above): either the session
            # died, or the launch had no usable effect (the read-only gate only proves a
            # session exists, never that the load finished and the CPU is halted at the
            # entry point).  Either way the launch is issued again, and `last_ran` is
            # cleared for the record: from here on a bare `ERR disabled` may not be read
            # as "running" until a Resume belonging to *this* launch has actually run
            # (fail closed).  This is R7's cause 3 shape and it stays red until it is
            # understood.
            out["resume_reissues"] += 1
            last_ran = None
            out["launch"] = _ask(ctx, "cmd.run " + _CMD_LAUNCH_ACTIVE, out)
            out["launch_attempts"].append(out["launch"])
            # Same site rule as the first issue above: the re-issue is answered too, so
            # a modal it raises cannot hold the thread through the next slice.
            _answer_load_modal(ctx, out, "after launchActive re-issue %d"
                               % out["resume_reissues"])
            pending_reissue = {"issue": len(out["launch_attempts"]), "at": _stamp(),
                               "shape": _shape(out["launch"]), "rounds": 0,
                               "reissued": True, "perspective": None,
                               "debug_items": None, "opened": None, "aborted": False}
            out["launch_issues"].append(pending_reissue)
            ctx.note("load: re-issuing %s (%d/%d) at %s -- %s"
                     % (_CMD_LAUNCH_ACTIVE, out["resume_reissues"],
                        _LOAD_RESUME_REISSUE, pending_reissue["at"],
                        "the session ABORTED (it came up and then went away), and a "
                        "launch that leaves no session behind has to be started "
                        "again" if aborted else
                        "%.0fs of %s polling released nothing (last answer %r); the "
                        "read-only gate only proves a debug session exists, never "
                        "that the load finished.  Measured 2026-10-07 "
                        "(`board-1007-ac1`): the launch took effect on the third "
                        "issue." % (slice_s, _CMD_RESUME, slice_last)))
            if out.get("transport_error"):
                break
        if out["resume_blocked"] is not None:
            ctx.note("load: an %s answer that carried %r also carried %r -- an "
                     "IDE dialog (measured 2026-10-07: a modal reading 'Run Control "
                     "not available') stood between the command and the target, so "
                     "that answer is not evidence the target is running"
                     % (_CMD_RESUME, _OK_MARK + _CMD_RESUME,
                        _dialog_line(out["resume_blocked"])))
        if not out["running"]:
            # Evidence for the next run, read through a dict of its own so that a
            # failed read cannot land on `load["transport_error"]` -- `_expect` turns
            # that into a hard FAIL about the whole conversation, and the load is
            # already being failed on its own terms here.  It is never a criterion:
            # the perspective is judged once, by `gate` (R-2).
            giveup: Dict[str, Any] = {}
            out["parts_at_giveup"] = _ask(ctx, "ui.parts", giveup)
            if out["resume"] is None:
                ctx.note("load: GIVING UP after %d %s attempt(s) in %d slice(s) over "
                         "%.0fs, with %d %s re-issue(s) -- no %s ever *ran* (a Resume "
                         "counts as ran only when it answers OK **with** the %r line), so "
                         "there was no suspended context to release.  A bare 'ERR "
                         "disabled' cannot separate 'the launch produced no usable "
                         "session' from 'the target is already running' (R7): this note "
                         "claims only that the case could not CERTIFY the program is "
                         "running.  The measured shape on this board is that the loader "
                         "halts the CPU at the entry point, so a live session answers OK.  "
                         "%sThe perspective at give-up: %s%s.  The last answer, verbatim: "
                         "%r"
                         % (len(out["resume_attempts"]), _CMD_RESUME,
                            len(out["resume_slices"]), time.monotonic() - resume_started,
                            out["resume_reissues"], _CMD_LAUNCH_ACTIVE,
                            _CMD_RESUME, _OK_MARK,
                            ("A session was caught ABORTING (see the verbatim diff "
                             "above) -- that is a dead session, whose `ERR disabled` is "
                             "not the 'already running' reading.  "
                             if out["session_aborted"] else
                             "No abort was observed: the session never fell back, so "
                             "the two readings stay indistinguishable here.  "),
                            _perspective(out["parts_at_giveup"]) or "<no perspective line>",
                            "" if not giveup.get("transport_error")
                            else " (that read failed: %s)" % giveup["transport_error"],
                            out["resume_attempts"][-1].raw
                            if out["resume_attempts"] else ""))
            else:
                # A release DID happen (this is *not* the "nothing was released" shape
                # above), and the two ways it can still end without a certification are
                # named here rather than assumed: the dialog veto (R-1) and a newer ran
                # `Resume` that says a context existed again.
                if out["resume_blocked"] is not None:
                    why = ("the %s answer that ran also carried a dialog line (R-1: the "
                           "handler ran, the IDE raised a dialog, and 'the handler ran' "
                           "is not 'the target was released'), so the release was never "
                           "closed" % _CMD_RESUME)
                elif out["resume_reran"] is not None:
                    why = ("a later %s ran again (%s) -- a suspended context existed "
                           "again, so a newer reading contradicts the release"
                           % (_CMD_RESUME, _shape(out["resume_reran"])))
                else:
                    why = ("the confirming %s never answered 'ERR disabled' and none of "
                           "the same-slice evidence was recorded"
                           % _CMD_RESUME)
                ctx.note("load: GIVING UP after %d %s attempt(s) in %d slice(s) over "
                         "%.0fs, with %d %s re-issue(s) -- a clean %s DID run at %s "
                         "(%s: %r), so something WAS released, and the loop still never "
                         "closed on 'ERR disabled': %s.  The release is R7's floor but "
                         "this run is NOT certified running -- the floor alone is only "
                         "certified when the confirming call is *unavailable*, which is "
                         "not the case here.  The perspective at give-up: %s%s.  The "
                         "last answer, verbatim: %r"
                         % (len(out["resume_attempts"]), _CMD_RESUME,
                            len(out["resume_slices"]), time.monotonic() - resume_started,
                            out["resume_reissues"], _CMD_LAUNCH_ACTIVE, _CMD_RESUME,
                            out["resume_at"], _shape(out["resume"]),
                            out["resume"].raw, why,
                            _perspective(out["parts_at_giveup"]) or "<no perspective line>",
                            "" if not giveup.get("transport_error")
                            else " (that read failed: %s)" % giveup["transport_error"],
                            out["resume_attempts"][-1].raw
                            if out["resume_attempts"] else ""))
    # The per-issue ledger (requirement 3): one line per `launchActive`, with the
    # shape of its answer and the read-back that followed it.  "Which issue did it"
    # cannot be re-derived from anything else after the fact.
    for record in out["launch_issues"]:
        if record["opened"] and record["aborted"]:
            verdict_words = ", gate OPEN, then judged ABORTED (the session died)"
        elif record["opened"]:
            verdict_words = ", gate OPEN"
        elif record["aborted"]:
            verdict_words = ", judged ABORTED (the session was already gone)"
        else:
            verdict_words = ", no session appeared"
        ctx.note("load: launchActive ledger -- issue %d sent %s%s -> %s; read back: "
                 "perspective=%s, Debug view [TreeItems=%s]%s"
                 % (record["issue"], record["at"],
                    " (re-issue)" if record.get("reissued") else "",
                    record["shape"], record["perspective"],
                    "no" if record["debug_items"] is None else record["debug_items"],
                    verdict_words))

    # The modal ledger (this file's second ledger): every `#32770` the load stage met,
    # with the buttons it saw and what was done about it.  The per-decision note above
    # puts the same fact at the point in the trace where it was taken; this is the
    # stable place to read the whole sequence -- and it is the record a later
    # root-cause pass needs, because "was the box a question or a progress shell" is
    # exactly what `ui.parts` alone can never say.
    for record in out["modal_answers"]:
        ctx.note("load: modal ledger -- %s at %s: #32770 %s \"%s\" buttons=%s -> %s%s"
                 % (record["when"], record["at"], record["hwnd"] or "<none>",
                    record["title"], record["buttons"] or "<none>", record["action"],
                    ("; " + (record["output"] or record["refusal"]))))

    # Read-back of the observed change (never "the session came up"): the active
    # perspective, and the launch configuration file the IDE touched while
    # launching (it persists the resolved program into it).  This is *auxiliary*
    # evidence (R7): the gate above is what makes it mean anything.
    #
    # R-2 -- the perspective read is taken from **inside** the observation window:
    # it is the `ui.parts` answer of the round the gate opened on (already recorded
    # by `_wait_for_debug_context`), never a fresh request here.  A fresh read is a
    # sample taken *after* the window, and by then a modal that killed the session
    # has dropped the perspective back to CCS Edit (measured 2026-10-07,
    # `runs/board-1007-chk/bridge.log`: `06:04:35.507 ui.parts -> TIDebugPerspective`
    # -- that is the frame the gate opened on -- then `06:04:36.036 Resume -> OK`
    # with a dialog, then `06:04:38.790 ui.parts -> TICPerspective`).  Judging the
    # launch by the second read judges the aftermath, not the launch; and the
    # perspective is not a criterion at all (`_gate_open`; `_expect` judges it once,
    # through `gate`).
    #
    # NEVER revert this to a fresh `ui.parts` issued after the loop: that request
    # goes through `_ask`, so a failure would write `load["transport_error"]`, and
    # `_expect` treats a transport_error as a hard FAIL -- an already-completed load
    # would then be judged "the bridge connection to the IDE was lost".  Reading the
    # in-window answer keeps that impossible.
    out["parts_after"] = (out.get("wait") or {}).get("parts")
    for label, response in (("parts_before", out["parts_before"]),
                            ("parts_after", out["parts_after"])):
        if response is None:
            ctx.note("load: %s -> <no in-window reading>" % label)
            continue
        ctx.note("load: %s -> %s | %s" % (label, response.status_line,
                                          " / ".join(response.payload[:6])))
    out["launch_after"] = _fingerprint(launch)
    ctx.note("load: launch configuration %s was %s before the launch and is %s after"
             % (os.path.basename(launch) if launch else "<none>",
                out["launch_before"], out["launch_after"]))
    return out


def _action(ctx):
    plan = ctx.board_plan
    name = _override("project") or _PROJECT
    token = uuid.uuid4().hex[:8]
    marker = _MARKER_PREFIX + token
    proj = os.path.join(plan["workspace"], name)
    result: Dict[str, Any] = {"errors": list(plan["errors"]), "plan": plan,
                              "name": name, "marker": marker, "project": proj,
                              "started_at": time.time()}
    ctx.note("action: project=%s marker=%s" % (name, marker))

    result["stop"] = _stop_instance(ctx, plan)
    if result["stop"].get("error"):
        result["errors"].append("stop: " + result["stop"]["error"])
        return result

    result["wipe"] = _wipe_workspace(ctx, plan)
    if result["wipe"].get("error"):
        result["errors"].append("wipe: " + result["wipe"]["error"])
        return result

    seed = _seed(ctx, plan, name, marker)
    result["seed"] = seed
    if not seed["ok"]:
        result["errors"].append("seed: " + (seed["error"] or "failed"))
        return result
    if seed["device"] != "TMS320C28XX." + _EXPECTED_DEVICE:
        result["errors"].append(
            "device read-back: the generated .ccsproject declares deviceVariant=%r, "
            "expected %r" % (seed["device"], "TMS320C28XX." + _EXPECTED_DEVICE))
    if seed["project_name"] != name:
        result["errors"].append("project name read-back: .project says %r, asked %r"
                                % (seed["project_name"], name))

    result["build"] = _build(ctx, plan, proj, name)
    # R2's shape, applied to the board: read back the clock source the built
    # project's own device.h activates, so a missing patch is a named FAIL.
    result["clock"] = _clock_readback(ctx, proj)
    result["board_c"] = _generated(ctx, proj, name)
    result["artifact"] = _artifact(ctx, proj, name, marker)

    # Identity of what the launch may reach: the workspace now registers exactly
    # this project (the wipe + create above), and the project declares exactly one
    # launch configuration -- so an `OK` from `launchActive` cannot be somebody
    # else's configuration.
    result["registered_after"] = _registered_projects(plan["workspace"])
    result["launch_files"] = sorted(glob.glob(os.path.join(proj, ".launches", "*.launch")))
    ctx.note("identity: workspace registers %s; %s declares %s"
             % (result["registered_after"],
                name, [os.path.basename(p) for p in result["launch_files"]] or "<none>"))

    if not result["errors"]:
        result["start"] = _start(ctx, plan)
        if result["start"].get("error"):
            result["errors"].append("start: " + result["start"]["error"])
            return result
        # A stale modal blocks the UI thread and would poison the launch itself
        # (`design-obs-ux.md`: a modal left behind costs the whole rest of a run).
        result["dialogs"] = _sweep_dialogs(ctx)
        # H1: `${build_artifact:<project>}` resolves against the configuration the
        # IDE's own CDT state names; that file only exists once the IDE has opened
        # the project, so it is read at load time, not before the install.
        result["cdt_configs"] = _active_build_configs(plan["workspace"], name)
        ctx.note("h1: the IDE's CDT state names build config(s) %s for %s"
                 % (result["cdt_configs"] or "<none>", name))
        result["load"] = _load(ctx, plan, result["launch_files"][0]
                               if result["launch_files"] else "")
        # The one link no tool on this machine can read back -- say so out loud,
        # and only once every machine-checkable link is green (AC2/R8), including
        # the closed-loop proof that the target is actually RUNNING.
        load = result["load"]
        resumed = load.get("resume")
        if (not result["errors"] and load["launch"].ok and load.get("running")
                and resumed is not None and resumed.ok):
            ctx.note("ASK THE HUMAN: every machine-checkable link is green (device %s "
                     "read back, clock source %s, 3/3 mux lines generated, %s built "
                     "and carrying %s, launchActive + Resume answered OK and a "
                     "following Resume answered ERR disabled = the target is running) "
                     "-- now look at the board: D400/D401/D402 must light one at a "
                     "time in one direction, 200 ms apart, looping.  That is the one "
                     "thing this case cannot read back."
                     % (_EXPECTED_DEVICE,
                        (result.get("clock") or {}).get("source"),
                        os.path.basename(result["artifact"].get("path") or "<missing>"),
                        marker))
    return result


# --------------------------------------------------------------------------- #
# Judgement
# --------------------------------------------------------------------------- #

def _expect(ctx, result) -> Tuple[bool, str]:
    problems: List[str] = list(result.get("errors") or [])
    plan = result["plan"]
    name = result["name"]
    marker = result["marker"]

    seed = result.get("seed") or {}
    build = result.get("build") or {}
    board_c = result.get("board_c") or {}
    art = result.get("artifact") or {}

    # -- the board's clock source (R2's shape, applied to the board) --------- #
    # Before the "seed did not complete" early return, so a failed patch still
    # names the clock source instead of hiding behind a generic seed failure.
    clock = result.get("clock") or {}
    clock_patch = seed.get("clock_patch") or {}
    if clock_patch.get("error"):
        problems.append("clock source: " + clock_patch["error"])
    elif clock.get("source") != _EXPECTED_CLOCK:
        observed = ("the %r PLL source" % clock["source"] if clock.get("source")
                    else "no readable PLL source (device.h was not there to read back)")
        problems.append(
            "clock source: %s activates %s, expected %r -- this board has no 20 MHz "
            "crystal (Y1/R61/R51 are not fitted), so an XTAL build spins in "
            "SysCtl_selectXTAL()'s unbounded ESTOP0 loop and the CPU halts before the "
            "payload's main() runs: no LED can chase"
            % (clock.get("path") or "device/device.h", observed, _EXPECTED_CLOCK))

    if not seed.get("ok"):
        return verdict(problems + ["seed did not complete"],
                       "project=%s seed=FAILED" % name)
    if not seed.get("ccxml_exists"):
        problems.append("target-config: the spec-copied %s is missing, so the launch "
                        "configuration cannot resolve a target" % seed.get("ccxml"))

    # -- build ------------------------------------------------------------- #
    log = (build.get("logs") or {}).get(_CONFIG) or {}
    if log.get("timed_out"):
        problems.append("build: killed by the %.0fs timeout (%s)"
                        % (_BUILD_TIMEOUT, "; ".join(plan.get("killed") or [])))
    elif log.get("rc") != 0:
        problems.append("build %s: rc=%s (expected 0)" % (_CONFIG, log.get("rc")))
    if log.get("errors") is None:
        problems.append("build %s: the log carries no 'N out of M projects have "
                        "errors' line" % _CONFIG)
    elif log.get("errors") != "0":
        problems.append("build %s: %s" % (_CONFIG, build.get("errors_line")))

    # -- R4: the pin mux is generated, not written -------------------------- #
    if not board_c.get("path"):
        problems.append("board.c: SysConfig generated no board.c under %s" % name)
    elif board_c.get("missing"):
        problems.append("board.c: the pin mux is NOT in %s -- missing %s"
                        % (board_c["path"], "; ".join(board_c["missing"])))

    # -- artifact ----------------------------------------------------------- #
    elf = art.get("elf")
    if not art.get("path"):
        problems.append("artifact: no file matched %s" % art.get("pattern"))
    else:
        if art.get("size", 0) <= 0:
            problems.append("artifact: %s is empty" % art["path"])
        if elf is None:
            problems.append("artifact: %s is not an ELF" % art["path"])
        elif elf["machine"] != _MACHINE:
            problems.append("artifact: e_machine=%d, expected %d (EM_TI_C2000)"
                            % (elf["machine"], _MACHINE))
        if art.get("marker_offset", -1) < 0:
            problems.append("artifact: the unique marker %r is not in the image in "
                            "any encoding (ascii/u16le/u16be) -- stale artifact, or "
                            "the marker was optimized out" % marker)
        if art.get("mtime", 0) and art["mtime"] < result.get("started_at", 0):
            problems.append("artifact: %s is older than this case's start (mtime %.0f "
                            "< %.0f) -- it is not this run's build"
                            % (art["path"], art["mtime"], result["started_at"]))
    configs = result.get("cdt_configs") or []
    if len(configs) > 1:
        problems.append("h1: the IDE's CDT state names several build configurations "
                        "%s, so ${build_artifact:%s} is ambiguous" % (configs, name))

    # Identity of the launch vehicle: the workspace this IDE started on registers
    # exactly the project this case seeded, and that project declares exactly one
    # launch configuration -- so an OK from `launchActive` cannot be a config
    # belonging to something else.
    registered = result.get("registered_after") or []
    if registered != [name]:
        problems.append("identity: the workspace registers %s, expected exactly [%r]"
                        % (registered, name))
    launches = result.get("launch_files") or []
    if len(launches) != 1:
        problems.append("identity: the project declares %d launch configurations, "
                        "expected exactly 1: %s" % (len(launches), launches))
    elif os.path.basename(launches[0]) != _LAUNCH_NAME + ".launch":
        problems.append("identity: the only launch configuration is %r, expected %r"
                        % (os.path.basename(launches[0]), _LAUNCH_NAME + ".launch"))

    # -- the load (R6/R7): answer shape, not a duration and not "it came up" - #
    load = result.get("load")
    if load is None:
        problems.append("load: never reached")
        return verdict(problems, _detail(result, log, board_c, art, load))

    # A lost connection is not a verdict about the *program* -- it is the load
    # chain ending mid-flight.  Name it, and stop: the shape checks below would be
    # judging a conversation that no longer exists, and the problems collected so
    # far (the clock source above all) stay in the verdict.
    transport = load.get("transport_error")
    if transport:
        problems.append(
            "load: the bridge connection to the IDE was lost while the load was being "
            "driven (%s) -- the download/resume chain can no longer be judged, so the "
            "program is NOT RUNNING and the LEDs cannot chase" % transport)
        return verdict(problems, _detail(result, log, board_c, art, load))

    before = load["resume_before"]
    if before.ok:
        problems.append("load: Resume answered OK *before* the launch -- a debug "
                        "session was already live, so the OK after the launch would "
                        "not prove anything")
    elif not before.status_line.startswith("ERR disabled"):
        problems.append("load: Resume before the launch -> %r, expected 'ERR disabled'"
                        % before.status_line)
    if len(before.lines) > _ERR_LINES:
        problems.append("load: the disabled Resume answered %d lines, expected the "
                        "bare %d: %s" % (len(before.lines), _ERR_LINES, before.raw))
    if any(line.startswith(_OK_MARK + _CMD_RESUME) for line in before.payload):
        problems.append("load: the pre-launch Resume answered with %r although no "
                        "debug session exists yet: %s" % (_OK_MARK + _CMD_RESUME,
                                                          before.raw))

    # -- stage 1/2 of the load: the launch finished and a debug context exists - #
    # Read-only, and reported before the command shapes: without a debug context a
    # `Resume` answer has no meaning at all, so this is the stage that must be
    # named when it is what failed.
    gate = load.get("gate") or {}
    if not gate.get("open"):
        problems.append(
            "load: no debug context ever appeared -- after %d wait round(s) and %s "
            "launchActive issue(s) the active perspective was %s and the Debug view's "
            "tree held %s item(s), so the image was never loaded (or the launch had no "
            "effect): the program CANNOT be running and the LEDs cannot chase"
            % (len((load.get("wait") or {}).get("rounds") or []),
               len(load.get("launch_attempts") or []), gate.get("perspective"),
               "no" if gate.get("debug_items") is None else gate.get("debug_items")))

    launches = load.get("launch_attempts") or (
        [load["launch"]] if load.get("launch") is not None else [])
    if not launches:
        problems.append("load: launchActive was never issued")
    for issue, response in enumerate(launches, 1):
        if not response.ok:
            problems.append("load: launchActive issue %d -> %r -- nothing was launched "
                            "(the LaunchBar's active configuration was still empty, or "
                            "the probe is busy)" % (issue, response.status_line))
            continue
        if len(response.lines) < _OK_LINES:
            problems.append("load: launchActive issue %d answered OK in only %d lines, "
                            "expected at least %d: %s"
                            % (issue, len(response.lines), _OK_LINES, response.raw))
        if not any(line.startswith(_OK_MARK + _CMD_LAUNCH_ACTIVE)
                   for line in response.payload):
            problems.append("load: launchActive issue %d answered OK without the %r "
                            "confirmation line: %s" % (issue, _OK_MARK + _CMD_LAUNCH_ACTIVE,
                                                       response.payload))

    # -- stage 3 of the load: the target is RUNNING, proven in a closed loop --- #
    resume = load.get("resume")
    blocked = load.get("resume_blocked")
    if resume is None:
        attempts_ = load.get("resume_attempts") or []
        problems.append(
            "load: %s never ran (%d attempt(s), last answer %r) -- without a Resume the "
            "program is never released from its entry point, so it is NOT RUNNING and "
            "the LEDs cannot chase (AC3(c): with this step removed the case must be red, "
            "and it is).  A bare 'ERR disabled' cannot separate 'the launch produced no "
            "usable session' from 'the target is already running' (R7), so it is never "
            "read as 'running' here."
            % (_CMD_RESUME, len(attempts_),
               attempts_[-1].status_line if attempts_ else "<step absent>"))
        # Requirement 2: `Resume`'s `ERR disabled` has two sources -- a session that
        # died, and a target that is already running.  The liveness read-back in
        # `_load` makes the first one decidable, so name it when it was seen.  It is
        # *not* a second criterion (this branch already failed): it is the difference
        # between "we could not certify it is running" and "we watched it die".
        if load.get("session_aborted"):
            evidence = load.get("abort_evidence") or {}
            rounds_ = evidence.get("rounds") or []
            closed = next((r for r in rounds_ if not r["open"]), {})
            problems.append(
                "load: the read-only read-back caught the debug session ABORTING -- "
                "the gate was open on %s and the session was gone by %s (verbatim "
                "diff: %s) -- so the `ERR disabled` above is a session that came up "
                "and died, NOT the 'target is already running' reading of the same "
                "word"
                % (_reading(evidence.get("before") or {}), _reading(closed),
                   evidence.get("diff") or "<no diff recorded>"))
    else:
        if len(resume.lines) < _OK_LINES:
            problems.append("load: Resume answered OK in only %d lines, expected at "
                            "least %d: %s" % (len(resume.lines), _OK_LINES, resume.raw))
        if not any(line.startswith(_OK_MARK + _CMD_RESUME) for line in resume.payload):
            problems.append("load: Resume answered OK without the %r confirmation line: "
                            "%s" % (_OK_MARK + _CMD_RESUME, resume.payload))
        if not load.get("running"):
            probe = load.get("resume_probe")
            reran = load.get("resume_reran")
            # R2: this branch used to assert "the target is STILL HALTED" whenever a
            # release had run -- including for a run whose own record holds a verbatim
            # read-back of the session going away, and for the ac2 shape where the
            # abort was the *false* one.  Name the evidence that is actually in the
            # record, strongest first, and never assert a state the record does not
            # contain.
            if reran is not None:
                problems.append(
                    "load: Resume answered OK (the release: %s) but a later %s ran "
                    "again (%s) -- `OK executed` means the handler was enabled, i.e. a "
                    "suspended context existed again, so a newer reading contradicts "
                    "the release: the target is STILL HALTED at its entry point (the "
                    "resume was premature, or the loader halted the CPU again), the "
                    "program is NOT RUNNING and the LEDs cannot chase"
                    % (_shape(resume), _CMD_RESUME, _shape(reran)))
            elif load.get("session_aborted"):
                evidence = load.get("abort_evidence") or {}
                rounds_ = evidence.get("rounds") or []
                closed = next((r for r in rounds_ if not r["open"]), {})
                problems.append(
                    "load: Resume answered OK (the release: %s) but the loop never "
                    "closed it, and the read-only read-back caught the debug session "
                    "ABORTING -- the pair was open on %s and closed by %s (verbatim "
                    "diff: %s).  A session that came up and went away is not a target "
                    "confirmed to be running (R7 forbids reading the session state as "
                    "either verdict), so the case cannot certify the release: the "
                    "program is NOT certified RUNNING and the LEDs cannot be claimed "
                    "to chase"
                    % (_shape(resume), _reading(evidence.get("before") or {}),
                       _reading(closed), evidence.get("diff") or "<no diff recorded>"))
            elif blocked is None:
                problems.append(
                    "load: Resume answered OK but the confirming Resume did not answer "
                    "'ERR disabled' (%s) after %d attempt(s) -- the target is STILL "
                    "HALTED at its entry point (the resume was premature, or the loader "
                    "halted the CPU again), so the program is NOT RUNNING and the LEDs "
                    "cannot chase"
                    % (probe.status_line if probe else "<no confirming call>",
                       len(load.get("resume_attempts") or [])))
            # (`blocked` is named by its own problem below; that is the R-1 veto and
            # it is what keeps this run red.)

    # R-1: a handler that ran is not a target that was released.  The IDE can raise a
    # dialog on the *same* answer (measured 2026-10-07: a modal whose body reads 'Run
    # Control not available'), and it can do so *after* an earlier clean-looking
    # resume -- so the dialog has to be named both for `resume is None` (never ran)
    # and for the case above (one resume ran, then a dialog, then a bare 'ERR
    # disabled' that must NOT be allowed to close the loop).  It is not a criterion:
    # it is a name for why the run is not certified.
    if blocked is not None:
        problems.append(
            "load: the %s answer that carried %r also carried the bridge's dialog "
            "line %r -- the handler ran, but the IDE raised a dialog on the same "
            "answer (measured 2026-10-07: a modal whose body reads 'Run Control "
            "not available'), so the target state is not certified: it is NOT "
            "RUNNING and the LEDs cannot chase.  An OK from a handler is not "
            "proof the target was released (fail closed)"
            % (_CMD_RESUME, _OK_MARK + _CMD_RESUME, _dialog_line(blocked)))

    # The perspective is judged **once**, by `gate` above, on the reading the gate
    # actually opened on.  R-2: a second verdict here would be a second truth from
    # the same source (C10), and it used to be derived from a *fresh* `ui.parts`
    # taken after the observation window -- exactly the sample that reads the
    # aftermath of a modal (see `_load`) rather than the launch.  `parts_after` (now
    # the in-window reading) stays in the summary line (`_detail`) as evidence,
    # never as a criterion.
    return verdict(problems, _detail(result, log, board_c, art, load))


def _perspective(response) -> Optional[str]:
    match = re.search(r"^perspective id=(\S+)", "\n".join(response.payload), re.M)
    return match.group(1) if match else None


def _dialog_line(response) -> Optional[str]:
    """The bridge's ``dialog=…`` line of an answer, or ``None`` (R-1).

    The bridge appends it to any *write* method's answer when it saw a window
    appear (`LiveBridge.java:566`) or when its own shell snapshot timed out
    (`:572`) -- **after** the handler's own lines.  So an answer can carry both
    ``OK executed <id>`` and ``dialog=…``, and the second one says the handler's
    result cannot be trusted as the effect (measured 2026-10-07: a `Resume`
    answered exactly that shape while the on-screen modal read `Run Control not
    available`).
    """
    for line in response.payload or ():
        if line.startswith(_DIALOG_MARK):
            return line
    return None


def _detail(result, log, board_c, art, load) -> str:
    name = result["name"]
    parts_after = load.get("parts_after") if load else None
    persp = _perspective(parts_after) if parts_after is not None else None
    gate = (load or {}).get("gate") or {}
    launch_touched = ""
    if load and load.get("launch_after") and load.get("launch_before"):
        launch_touched = ("rewritten" if load["launch_after"] != load["launch_before"]
                          else "untouched")
    return ("target=ccs12 project=%s device=%s clock=%s build=%s mux=%d/%d artifact=%s "
            "size=%s e_machine=%s marker=%s perspective=%s debug_items=%s "
            "running=%s launch_config=%s"
            % (name, result["seed"].get("device"),
               (result.get("clock") or {}).get("source"),
               (result.get("build") or {}).get("errors_line") or "<no summary>",
               len(board_c.get("mux") or []), len(_MUX_LINES),
               os.path.basename(art["path"]) if art.get("path") else "<missing>",
               art.get("size"),
               (art.get("elf") or {}).get("machine"),
               ("%s@%s" % (art.get("marker_encoding"), art.get("marker_offset")))
               if art.get("marker_offset", -1) >= 0 else False,
               persp,
               "n/a" if gate.get("debug_items") is None else gate["debug_items"],
               bool((load or {}).get("running")),
               launch_touched or "<reached>"))


# --------------------------------------------------------------------------- #
# Cleanup (`post`)
# --------------------------------------------------------------------------- #

def _cleanup(ctx, label: str) -> str:
    """Remove the case's own footprint, but **never under a live IDE**.

    Measured 2026-10-07, the hard way: deleting ``<ws>/board_led_chase`` while the
    instance that opened it is still running leaves the workspace's serialized
    resource tree pointing at a project whose ``.project`` is gone, and the *next*
    startup raises a modal error --

        org.eclipse.core.internal.resources.ResourceException: Errors occurred while
        refreshing resources with the local file system.
        Contains: The project description file (.project) for 'board_led_chase' is
        missing.  ...                                    (<ws>/.metadata/.log)

    which surfaces as a ``Problem Occurred`` / "Refreshing workspace" dialog that
    blocks the UI thread: the next launch then never completes and ``Resume`` stays
    disabled for its whole poll window, and the dialogs pile up across runs.

    So: with a live instance the directory is left as it is (it *is* the image the
    debug session is showing, and the running program lives in target RAM) and the
    next invocation's ``_wipe_workspace`` -- which runs only after that instance
    has been stopped -- removes the whole workspace.  With no live instance the
    footprint is removed here, verbatim.
    """
    plan = getattr(ctx, "board_plan", None)
    if not plan:
        return "nothing was created"
    if getattr(ctx, "board_cleaned", False):
        return "already cleaned"
    ctx.board_cleaned = True
    name = _override("project") or _PROJECT
    workspace = plan.get("workspace") or ""
    proj = os.path.join(workspace, name)
    run_dir = os.path.dirname(ctx.paths.endpoint) if ctx.paths else ""
    live = run_live_pid(run_dir) if run_dir else None
    if live:
        ctx.note("%s instance pid %s is still running on this workspace, so the seeded "
                 "project is left in place (deleting it under a live IDE leaves the "
                 "workspace tree inconsistent and makes the next startup raise a "
                 "blocking 'Refreshing workspace' modal); the next invocation stops "
                 "that instance and empties the whole workspace"
                 % (label, live))
    else:
        shutil.rmtree(proj, ignore_errors=True)
        registry = os.path.join(workspace, ".metadata", ".plugins",
                                "org.eclipse.core.resources", ".projects", name)
        shutil.rmtree(registry, ignore_errors=True)
        ctx.note("%s no live instance: seeded project removed=%s (%s)"
                 % (label, not os.path.isdir(proj), proj))
    stage = run_dir
    if stage:
        board_dir = os.path.join(stage, "board")
        if os.path.isdir(board_dir):
            shutil.rmtree(board_dir, ignore_errors=True)
            ctx.note("%s staging dir removed (%s)" % (label, board_dir))
    if plan.get("killed"):
        ctx.note("%s timed-out build process trees killed: %s"
                 % (label, "; ".join(plan["killed"])))
    return "live=%s" % (live or "none")


def _rollback(ctx):
    """A failed case cleans up the same way (never under a live instance)."""
    return _cleanup(ctx, "rollback:")


def _post(ctx):
    return _cleanup(ctx, "post:")


CASE = Case(
    name="board.led_chase",
    group="realflow",
    targets=("ccs12",),
    description=("the first hardware case: seed the run workspace with a TI "
                 "projectspec project + a three-LED SysConfig overlay, build CPU1_RAM, "
                 "start the instance, load through the launch configuration and Resume; "
                 "the LED chase itself is confirmed by a human"),
    pre=_pre,
    action=_action,
    expect=_expect,
    post=_post,
    rollback=_rollback,
    # No bridge before `pre`: this case seeds the workspace and starts the instance
    # itself (a project cannot be imported into a running IDE).  Same shape as the
    # `input` group's fixture case.
    requires_bridge=False,
    # Nothing here is judged by the screen: the verdict is the build log, the
    # generated board.c, the artifact's bytes and the shape of the bridge answers.
    screen_guard=False,
    evidence=("raw:action", "build:log", "artifact:probe"),
)
