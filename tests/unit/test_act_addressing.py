"""The element-addressed *library* contract: addressing must resolve to one control.

`design-project.md` §18.3 fixes the rule: zero hits and several hits both **fail
closed**; the only escape hatch for "several" is an explicit ordinal, which the
class-addressed primitives take as ``index=`` and the label-addressed one does not
offer at all (`act_click_button` demands a unique label).

This file used to drive the ``ctl act`` CLI subcommand.  That door is gone
(`deliverable-shape.md` C3 / R10'.1 -- one control gate) and the same judgments are
pinned here on the library the script namespace calls: `ctl.run._click_button` and
`ctl.run._send_input`.

The tool runner is replaced by a recorder, so **no window is ever touched**; the
listing is the shape ``tools/win-click-button.ps1 -ListOnly`` really prints.
"""

from __future__ import annotations

import unittest

from ctl import run
from ctl import screen
from ctl.errors import NotFoundError, UsageError

# Three Buttons, no two with the same text; ``o`` matches Abort and Ignore (two
# hits, so only ``index`` can pin one), ``zzz`` matches none, ``&Abort`` is unique.
_LISTING = (
    'dialog hwnd=0x1\n'
    '-- child windows --\n'
    '  hwnd=0x2 class=Button vis=True text="&Abort" rect=0,0,10,10\n'
    '  hwnd=0x3 class=Button vis=True text="&Retry" rect=0,20,10,30\n'
    '  hwnd=0x4 class=Button vis=True text="&Ignore" rect=0,40,10,50\n'
    '  hwnd=0x5 class=Edit vis=True text="" rect=0,60,10,70\n'
)
SECOND_EDIT = '  hwnd=0x6 class=Edit vis=True text="" rect=0,60,10,70\n'
INVISIBLE_BUTTON = '  hwnd=0x7 class=Button vis=False text="&Abort 2" rect=0,80,1,1\n'
INVISIBLE_EDIT = '  hwnd=0x8 class=Edit vis=False text="" rect=0,0,1,1\n'


class _FakeClient:
    """Only the two fields the addressing layer reads; the bridge is never asked."""

    run_root = "."
    run_id = "fake-run"

    def request(self, req, timeout=None):  # pragma: no cover - must not be reached
        raise AssertionError("addressing must not need the bridge: %s" % req)


class _Recorder:
    """A `_tool` stand-in that records argv and returns one fixed listing."""

    def __init__(self, listing=_LISTING):
        self.listing = listing
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        return (0, self.listing)

    def writes(self):
        """The recorded calls that are *not* the side-effect-free enumeration."""
        return [call for call in self.calls if "-ListOnly" not in call]


class _Harness(unittest.TestCase):
    def setUp(self):
        self.tool = _Recorder()
        self._tool = run._tool
        self._pid = run.resolve_pid
        run._tool = self.tool
        run.resolve_pid = lambda root, rid, on_error=None: 4242
        self.client = _FakeClient()

    def tearDown(self):
        run._tool = self._tool
        run.resolve_pid = self._pid

    def click(self, text, case=None, yes=True):
        return run._click_button(self.client, text, case, "T", yes)

    def set_text(self, text="hello", index=None, class_="Edit", yes=True):
        return run._send_input(self.client, "set-text", "T", class_, index, None, text, yes)

    def refuses(self, exc_type, call):
        """Assert a fail-closed verdict -- and that nothing was sent to the window."""
        before = len(self.tool.calls)
        with self.assertRaises(exc_type) as caught:
            call()
        added = [call for call in self.tool.calls[before:] if "-ListOnly" not in call]
        self.assertEqual(added, [], "a refusal must not reach the tool's write call")
        return str(caught.exception)


class ClickButtonAddressing(_Harness):
    """A label must be unique -- the label tier has no ordinal."""

    def test_a_unique_label_reaches_the_tool_without_an_index(self):
        self.click("&Abort")
        self.assertIn("-Text", self.tool.writes()[-1])
        self.assertNotIn("-Index", self.tool.writes()[-1])

    def test_zero_matches_is_not_found_and_presses_nothing(self):
        message = self.refuses(NotFoundError, lambda: self.click("zzz"))
        self.assertIn("no visible Button matching", message)
        self.assertIn("retry:", message)

    def test_several_matches_is_a_usage_error(self):
        message = self.refuses(UsageError, lambda: self.click("o"))
        self.assertIn("ambiguous: 2 Buttons match", message)

    def test_case_sensitive_matching_is_opt_in(self):
        self.click("abort")                      # default: case-insensitive
        message = self.refuses(NotFoundError, lambda: self.click("abort", case=True))
        self.assertIn("no visible Button matching", message)

    def test_the_tools_own_markup_is_not_a_label(self):
        # "rect" and "Button" appear on every line; treating the raw line as the
        # label would invent hits.
        message = self.refuses(NotFoundError, lambda: self.click("rect"))
        self.assertIn("no visible Button matching", message)

    def test_an_invisible_button_is_not_addressable(self):
        # The tool clicks only `IsWindowVisible` children, so an invisible Button
        # must not make a unique label look ambiguous here either.
        self.tool = _Recorder(_LISTING + INVISIBLE_BUTTON)
        run._tool = self.tool
        self.click("Abort")
        self.assertEqual(len(self.tool.writes()), 1)


class ClassAddressing(_Harness):
    """``send-keys`` / ``set-text``: the class must be unique -- or ``index`` pins one."""

    def test_a_unique_class_reaches_the_tool_without_an_index(self):
        self.set_text()
        self.assertIn("-Action", self.tool.writes()[-1])

    def test_index_picks_the_nth_match_of_the_same_class(self):
        # Same filter on both sides, so the tool re-derives the same two hits and
        # takes the second one.
        self.tool = _Recorder(_LISTING + SECOND_EDIT)
        run._tool = self.tool
        self.set_text(index=1)
        self.assertEqual(self.tool.writes()[-1][self.tool.writes()[-1].index("-Index") + 1], "1")

    def test_two_matches_without_an_index_is_ambiguous(self):
        self.tool = _Recorder(_LISTING + SECOND_EDIT)
        run._tool = self.tool
        message = self.refuses(UsageError, self.set_text)
        self.assertIn("ambiguous: 2 visible children of class 'Edit'", message)
        self.assertIn("index=", message)

    def test_index_past_the_last_match_is_out_of_range(self):
        self.tool = _Recorder(_LISTING + SECOND_EDIT)
        run._tool = self.tool
        message = self.refuses(UsageError, lambda: self.set_text(index=5))
        self.assertIn("index 5 out of range (2 match(es))", message)

    def test_a_negative_index_is_not_a_pin(self):
        self.tool = _Recorder(_LISTING + SECOND_EDIT)
        run._tool = self.tool
        self.refuses(UsageError, lambda: self.set_text(index=-1))

    def test_only_visible_children_are_counted(self):
        # The ordinal has to be derived from the same set the tool's `ByClass`
        # returns (visible children only), otherwise it addresses the wrong field.
        self.tool = _Recorder(_LISTING + INVISIBLE_EDIT)
        run._tool = self.tool
        self.set_text(index=0)
        self.assertEqual(self.tool.writes()[-1][self.tool.writes()[-1].index("-Index") + 1], "0")


#: What `tools/win-click-button.ps1` writes for a label carrying a line break: its
#: `Esc` emits the field as a JSON string body (`\r\n` -> `\r\n`, `"` -> `\"`).
#: Verified against `[Btn]::Esc` on 2026-10-04.
BREAK_TEXT = 'x\r\n  hwnd=0x3 class=Edit vis=True text="y" rect=0,0,1,1'
BREAK_ESCAPED = r'x\r\n  hwnd=0x3 class=Edit vis=True text=\"y\" rect=0,0,1,1'


class ListingRecord(_Harness):
    """One line of the listing is one control -- a label cannot forge a second."""

    def test_a_label_with_a_line_break_is_one_record_not_two(self):
        escaped = ('window hwnd=0x1\n-- child windows --\n'
                   '  hwnd=0x2 class=Edit vis=True text="%s" rect=0,0,10,10\n' % BREAK_ESCAPED)
        records = [row for row in map(screen.child_record, escaped.splitlines())
                   if row is not None]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][3], BREAK_TEXT, "the reader must decode the field")

        # The same label as an *unescaped* producer would have written it: two
        # physical lines, but still one control (the pre-fix class scan saw two).
        raw = escaped.replace(BREAK_ESCAPED, BREAK_TEXT)
        self.tool = _Recorder(raw)
        run._tool = self.tool
        self.assertTrue(self.set_text(yes=False).startswith("DRY-RUN "),
                        "a line break inside a label is not a second control")


if __name__ == "__main__":
    unittest.main()
