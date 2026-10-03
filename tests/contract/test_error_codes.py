"""契约层：冻结的 8 个错误码 —— 代码、异常映射、文档三者不得走样。

这张表是**对外承诺**（`protocol.md` §3 的闭集），所以它同时要对三处成立：
客户端常量、`CtlError` 的构造行为、以及文档里真的写了这 8 个码。
任何一处漂移都意味着调用方按错误码写的分支会静默失效。
"""

import os
import unittest

from ctl.client import parse_status
from ctl.errors import (
    ERROR_CODES,
    ERROR_CODE_SET,
    FALLBACK_CODE,
    CtlError,
    NotFoundError,
    PrereqNotReady,
    UsageError,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROTOCOL_DOC = os.path.join(REPO_ROOT, "protocol.md")

#: The set `design.md` §3 fixes.  Written out longhand on purpose: this is the
#: assertion, so it must not be derived from the thing it is checking.
EXPECTED = (
    "badrequest",
    "notfound",
    "disabled",
    "unhandled",
    "timeout",
    "noWorkbench",
    "internal",
    "busy",
)


class ErrorCodeContract(unittest.TestCase):
    def test_closed_set_is_exactly_the_frozen_eight(self) -> None:
        self.assertEqual(ERROR_CODES, EXPECTED)
        self.assertEqual(ERROR_CODE_SET, frozenset(EXPECTED))

    def test_unknown_code_folds_to_internal_never_leaks(self) -> None:
        """A raw exception string must never reach a caller in the code slot.

        The *preservation* half of that promise is not here -- it lives one layer
        up, in `parse_status`, which is where a foreign code is actually seen.
        Asserting preservation against `CtlError` would be asserting a rule the
        code never claimed (measured: this exact assertion failed first).
        """
        err = CtlError("definitely-not-a-code", "boom")
        self.assertEqual(err.code, FALLBACK_CODE)
        self.assertEqual(err.message, "boom")  # passed through, not rewritten

    def test_parse_status_preserves_a_foreign_code_verbatim(self) -> None:
        kind, code, message = parse_status("ERR weirdcode the whole line stays")
        self.assertEqual((kind, code), ("err", FALLBACK_CODE))
        self.assertEqual(message, "weirdcode the whole line stays")

    def test_parse_status_folds_a_bare_exception_string(self) -> None:
        """The legacy-bridge shape: no code token at all, just exception text."""
        old = "java.lang.IllegalStateException: Workbench has not been created yet"
        kind, code, message = parse_status(old)
        self.assertEqual((kind, code), ("err", FALLBACK_CODE))
        self.assertEqual(message, old)

    def test_line_is_the_greppable_stderr_form(self) -> None:
        self.assertEqual(CtlError("notfound", "no such view").line(),
                         "ERR notfound no such view")

    def test_subclasses_map_to_their_documented_codes(self) -> None:
        self.assertEqual(UsageError("bad usage").code, "badrequest")
        self.assertEqual(NotFoundError("missing").code, "notfound")
        self.assertEqual(PrereqNotReady("not ready").code, FALLBACK_CODE)
        self.assertEqual(PrereqNotReady("not ready", code="timeout").code, "timeout")

    def test_every_code_is_documented_in_protocol_md(self) -> None:
        """Code and doc are two halves of one promise; drift is a silent break."""
        with open(PROTOCOL_DOC, encoding="utf-8") as handle:
            text = handle.read()
        missing = [code for code in EXPECTED if code not in text]
        self.assertEqual(missing, [], "protocol.md is missing: %s" % missing)


if __name__ == "__main__":
    unittest.main()
