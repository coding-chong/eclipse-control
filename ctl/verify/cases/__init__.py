"""Case registry.  One case per file (`design.md` §2); this module only aggregates.

Groups follow `design-obs-ux.md` §14.3: the read surface is ``read``, the write
surface (always screen-guarded) is ``write``, and the negative/error-contract
probes are ``errors``.  ``resilience`` holds the two cases that do not verify a
happy path but a *failure mode*: what a modal dialog costs the connection that
opened it (and what it does **not** cost the others), and what a write that
answered ``ERR timeout`` is allowed to have done.  Both drive their own window
snapshots instead of the runner's guard, because the modal has to be observed
*while it is on screen*.  ``input`` holds the one case that judges **the target
product's SWT**, not the bridge: it starts its own fixture and never connects,
so it runs without ``install``.  ``realflow`` holds the one case that runs the
**whole real workflow** end to end: it needs a live instance for the editor step
(``ui.open`` + read-back), then shells out to the target's own headless build
entry point in a separate JVM with its own scratch workspace.
"""

from __future__ import annotations

from typing import Dict

from .board_led_chase import CASE as BOARD_LED_CHASE
from .board_led_chase_gs32 import CASE as BOARD_LED_CHASE_GS32
from .errors_bad_param import CASE as ERRORS_BAD_PARAM
from .errors_bad_runp_param import CASE as ERRORS_BAD_RUNP_PARAM
from .errors_console_absent import CASE as ERRORS_CONSOLE_ABSENT
from .errors_missing_id import CASE as ERRORS_MISSING_ID
from .errors_plugin_id_as_view import CASE as ERRORS_PLUGIN_ID_AS_VIEW
from .errors_unhandled import CASE as ERRORS_UNHANDLED
from .errors_unknown_method import CASE as ERRORS_UNKNOWN_METHOD
from .read_cmd_list import CASE as READ_CMD_LIST
from .read_cmd_query import CASE as READ_CMD_QUERY
from .read_console import CASE as READ_CONSOLE
from .read_env import CASE as READ_ENV
from .read_parts import CASE as READ_PARTS
from .read_persp import CASE as READ_PERSP
from .read_ping import CASE as READ_PING
from .read_shells import CASE as READ_SHELLS
from .read_tree import CASE as READ_TREE
from .read_viewids import CASE as READ_VIEWIDS
from .read_wait import CASE as READ_WAIT
from .realflow_build_artifact import CASE as REALFLOW_BUILD_ARTIFACT
from .resilience_modal_reset import CASE as RESILIENCE_MODAL_RESET
from .resilience_timeout_applied import CASE as RESILIENCE_TIMEOUT_APPLIED
from .write_close_view import CASE as WRITE_CLOSE_VIEW
from .write_open_editor import CASE as WRITE_OPEN_EDITOR
from .write_run_toggle import CASE as WRITE_RUN_TOGGLE
from .write_runp_show_view import CASE as WRITE_RUNP_SHOW_VIEW
from .input_fixture import CASE as INPUT_FIXTURE

#: Every registered case, in execution order: read surface, write surface
#: (screen-guarded), then the error contract.
ALL_CASES = [
    READ_PING,
    READ_ENV,
    READ_SHELLS,
    READ_PARTS,
    READ_VIEWIDS,
    READ_PERSP,
    READ_TREE,
    READ_CMD_LIST,
    READ_CMD_QUERY,
    READ_WAIT,
    READ_CONSOLE,
    WRITE_OPEN_EDITOR,
    WRITE_CLOSE_VIEW,
    WRITE_RUNP_SHOW_VIEW,
    WRITE_RUN_TOGGLE,
    INPUT_FIXTURE,
    ERRORS_UNKNOWN_METHOD,
    ERRORS_BAD_PARAM,
    ERRORS_MISSING_ID,
    ERRORS_UNHANDLED,
    ERRORS_BAD_RUNP_PARAM,
    ERRORS_CONSOLE_ABSENT,
    ERRORS_PLUGIN_ID_AS_VIEW,
    RESILIENCE_MODAL_RESET,
    RESILIENCE_TIMEOUT_APPLIED,
    # `realflow` last: it is the slowest case (a real headless build) and it is the
    # only one that leaves a scratch project tree behind for `post` to remove.
    REALFLOW_BUILD_ARTIFACT,
    # The hardware case is the slowest of all (it brings its own instance up), and
    # it is the only one that needs the run's workspace to itself before the IDE
    # starts; it therefore runs last and skips on a run that already has a project.
    BOARD_LED_CHASE,
    # The GS32 sibling of the hardware case: it drives the *other* toolchain (GS32_Studio
    # 1.2.5.2 + the H1017A board) through the **same shape** as its CCS12 sibling --
    # build via that IDE's own Eclipse application entry (`-data` onto THIS run's live
    # workspace), then let the IDE itself load and run the image through the bridge
    # (`cmd.run` of `launchActive` -> `Resume`).  That manipulability is the whole point
    # of a board case; only the ids differ from the CCS12 one.  It builds into and loads
    # a scratch copy (project copied out of the SDK package, RAM configuration, no
    # flash), so it runs last as well.
    # (Corrected 2026-10-11: this comment read "entirely through CLIs -- no bridge, no
    # Eclipse command id", which R3 superseded on 2026-10-10 -- a CLI-only board case
    # would not prove the IDE can be driven at all.)
    BOARD_LED_CHASE_GS32,
]


def registry() -> Dict[str, str]:
    return {case.name: case.group for case in ALL_CASES}
