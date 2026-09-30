"""Shared error types plus the frozen bridge error-code set.

`design.md` §3 fixes the closed set of codes a bridge or client may surface::

    badrequest | notfound | disabled | unhandled | timeout | noWorkbench | internal | busy

`busy` is retryable (connection cap reached).  Anything outside the set is
folded into ``internal`` while the original text is preserved verbatim -- a bare
exception string must never reach a caller as if it were a code.
"""

from __future__ import annotations

#: The frozen closed set.  Order matches `design.md` §3 for readability.
ERROR_CODES = (
    "badrequest",
    "notfound",
    "disabled",
    "unhandled",
    "timeout",
    "noWorkbench",
    "internal",
    "busy",
)
ERROR_CODE_SET = frozenset(ERROR_CODES)
FALLBACK_CODE = "internal"

#: Console (Gogo) commands that are refused unless ``--allow-dangerous`` is set
#: (`design-project.md` §15.4 item 3).
DANGEROUS_COMMANDS = ("init", "close", "shutdown", "exit", "gc")
DANGEROUS_FLAG_TOKENS = ("threads -t",)


class CtlError(Exception):
    """Base for CLI-level failures carrying a frozen error ``code``."""

    def __init__(self, code: str, message: str):
        if code not in ERROR_CODE_SET:
            code = FALLBACK_CODE
        self.code = code
        self.message = message
        super().__init__(message)

    def line(self) -> str:
        """The one-line, greppable form used on stderr."""
        return "ERR %s %s" % (self.code, self.message)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.line()


class UsageError(CtlError):
    """Bad CLI usage -> exit code 1."""

    def __init__(self, message: str):
        super().__init__("badrequest", message)


class NotFoundError(CtlError):
    """Unknown case / target / command / file -> exit code 1."""

    def __init__(self, message: str):
        super().__init__("notfound", message)


class EndpointNotFound(NotFoundError):
    """No ``endpoint.json`` for the requested run -> never guess the port."""

    def __init__(self, message: str):
        super().__init__(message)


class PrereqNotReady(CtlError):
    """Environment is not ready -> exit code 2 ("never even started")."""

    def __init__(self, message: str, code: str = FALLBACK_CODE):
        super().__init__(code, message)


class BridgeError(CtlError):
    """An ``ERR`` line returned by the bridge, already normalised to the set."""

    def __init__(self, code: str, message: str, raw: str = ""):
        super().__init__(code, message)
        self.raw = raw
