"""Case registry.  One case per file (`design.md` §2); this module only aggregates.

Groups follow `design-obs-ux.md` §14.3: the read surface is ``read`` and the
negative/error-contract probes are ``errors``.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..runner import Case
from .errors_console_absent import CASE as ERRORS_CONSOLE_ABSENT
from .errors_missing_id import CASE as ERRORS_MISSING_ID
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

#: Every registered case, in execution order (read surface, then error contract).
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
    ERRORS_UNKNOWN_METHOD,
    ERRORS_MISSING_ID,
    ERRORS_CONSOLE_ABSENT,
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
