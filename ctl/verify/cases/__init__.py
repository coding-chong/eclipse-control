"""Case registry.  One case per file (`design.md` §2); this module only aggregates.

Groups follow `design-obs-ux.md` §14.3: the read surface is ``read``, the write
surface (always screen-guarded) is ``write``, and the negative/error-contract
probes are ``errors``.  ``resilience`` holds the two cases that do not verify a
happy path but a *failure mode*: what a modal dialog costs the connection that
opened it (and what it does **not** cost the others), and what a write that
answered ``ERR timeout`` is allowed to have done.  Both drive their own window
snapshots instead of the runner's guard, because the modal has to be observed
*while it is on screen*.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..runner import Case
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
from .resilience_modal_reset import CASE as RESILIENCE_MODAL_RESET
from .resilience_timeout_applied import CASE as RESILIENCE_TIMEOUT_APPLIED
from .write_close_view import CASE as WRITE_CLOSE_VIEW
from .write_open_editor import CASE as WRITE_OPEN_EDITOR
from .write_run_toggle import CASE as WRITE_RUN_TOGGLE
from .write_runp_show_view import CASE as WRITE_RUNP_SHOW_VIEW

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
    ERRORS_UNKNOWN_METHOD,
    ERRORS_BAD_PARAM,
    ERRORS_MISSING_ID,
    ERRORS_UNHANDLED,
    ERRORS_BAD_RUNP_PARAM,
    ERRORS_CONSOLE_ABSENT,
    ERRORS_PLUGIN_ID_AS_VIEW,
    RESILIENCE_MODAL_RESET,
    RESILIENCE_TIMEOUT_APPLIED,
]


def by_name(name: str) -> Optional[Case]:
    for case in ALL_CASES:
        if case.name == name:
            return case
    return None


def by_group(group: str) -> List[Case]:
    return [case for case in ALL_CASES if case.group == group]


def registry() -> Dict[str, str]:
    return {case.name: case.group for case in ALL_CASES}
