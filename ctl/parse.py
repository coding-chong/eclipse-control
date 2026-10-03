"""The one authoritative reader for a ``cmd.list`` payload.

Two callers read the bridge's command table: the ``commands`` subcommand
(``ctl/__main__.py:_fetch_command_ids``) and the ``ctl run`` script door
(``ctl/run.py``'s ``commands()``).  Before this module each carried its own copy
of the parsing rules, and that is how the same defect shipped twice -- the
second copy still filtered ids with ``"." in token``, silently dropping the two
ids CCS registers without a dot (``undo`` / ``redo``) while the bridge reported
``returned=807`` and the library said 805.

Keeping the rules here makes a third divergent copy structurally impossible:
one framing rule, in one place, pinned by one test file that needs no IDE
(``tests/unit/test_command_id_framing.py``).
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

__all__ = ["CommandIds", "command_ids"]

#: ``(ids, handler_only)`` -- see :func:`command_ids`.
CommandIds = Tuple[List[str], List[str]]

#: The id block is framed by these two signature lines: ``ICommandService ...``
#: opens it, ``definedCommandIds ...`` closes it.
_HEAD_MARKER = "ICommandService"
_TAIL_MARKER = "definedCommandIds"

#: ``handlerOnly`` entries look like ``  + <id>`` -- the bridge's one
#: ``out.add("  + " + id)`` site.
_HANDLER = re.compile(r"^\s*\+\s*(\S+)")

#: Degenerate-payload form: ``id=<x>`` (optionally ``cmd id=<x>``).
_LABELLED = re.compile(r"^\s*(?:cmd )?id=(\S+)")


def command_ids(payload: Sequence[str]) -> CommandIds:
    """Split one ``cmd.list`` payload into ``(ids, handler_only)``.

    ``payload`` is the already-split body (``Response.payload``: the lines
    between the status line and the terminator), so this function never splits
    or joins text -- a caller's line boundaries are honoured and a test can hand
    it a synthetic payload directly.

    The rules, each with the reason it is a rule:

    * **The id block is framed by the two signature lines.**  The head is the
      line containing ``ICommandService``; the tail is the line containing
      ``definedCommandIds``.  Every line strictly between them *is* an id,
      copied verbatim (only surrounding whitespace is stripped).
    * **No "does it look like an id" heuristic -- in particular no
      ``"." in token``.**  CCS registers two legal ids that contain no dot,
      ``undo`` and ``redo``; any dot test silently drops them, which is exactly
      how one caller returned 805 against the bridge's ``returned=807``.  GS32
      puts a dot in every id, so running both targets still missed it.
    * **The tail line's settlement row must not become an id.**  The tail is
      ``definedCommandIds total=... matched(prefix=)=... returned=...
      truncated=...`` -- a summary; the framing excludes it and the fallback
      excludes it by shape.
    * **``+ <id>`` lines are ``handler_only``, never ids.**  They have a handler
      but no ``<command>`` declaration, so ``getDefinedCommandIds`` cannot see
      them and the bridge lists them in their own section; ``cmd.query`` answers
      ``notfound`` for them, so folding them into ``ids`` would corrupt the
      command table.
    * **``caveat=...`` lines belong to neither list.**

    If the signature lines are missing or out of order, the fallback is
    deliberately conservative -- it prefers returning too few ids to returning a
    summary row as one -- but it still accepts dot-less single tokens, for the
    same reason the main path does.
    """
    lines = list(payload)

    ids: List[str] = []
    head = _first(lines, _HEAD_MARKER)
    tail = _first(lines, _TAIL_MARKER)
    if head is not None and tail is not None and tail > head:
        ids = [line.strip() for line in lines[head + 1:tail] if line.strip()]
    if not ids:
        ids = _fallback_ids(lines)

    handler_only: List[str] = []
    for line in lines:
        match = _HANDLER.match(line)
        if match:
            handler_only.append(match.group(1))
    return ids, handler_only


def _first(lines: Sequence[str], marker: str) -> Optional[int]:
    """Index of the first line containing ``marker``, or ``None``."""
    return next((index for index, line in enumerate(lines) if marker in line), None)


def _fallback_ids(lines: Sequence[str]) -> List[str]:
    """Ids when the signature lines are absent: labelled rows, else bare tokens.

    A settlement / ``handlerOnly`` / ``caveat`` row always carries a space or an
    ``=`` (or both), so the bare-token branch cannot mistake one for an id --
    while ``undo`` / ``redo`` pass, because nothing here looks at dots.
    """
    labelled = [match.group(1) for match in (_LABELLED.match(line) for line in lines) if match]
    if labelled:
        return labelled
    return [token for token in (line.strip() for line in lines)
            if token and " " not in token and "=" not in token]
