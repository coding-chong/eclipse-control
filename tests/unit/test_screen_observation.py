"""`ctl/screen.py` -- the three observation primitives no suite had ever run.

`appeared_titles`, `describe` and `shoot` are the "what did the IDE just do"
channel: the bridge payload parser, the evidence renderer, and the screenshot
wrapper.  A regression here is silent -- the guard keeps running and simply
reports the wrong thing -- so each one gets a judge of its own.

Shape contract (`deliverable-shape.md` C10): every expectation below is this
test's **own literal**.  Nothing is read from `_QUOTED`, `IGNORE_CLASSES` or any
other constant of the code under test -- otherwise weakening the fixture would
silently weaken its judge too.

Falsify (measured 2026-10-06, one mutation at a time, `git checkout --` between).
The numbered **M** entries below reddened exactly one test each (C12); the other
entries are measured too and are listed with their own count.
- **M2** `sorted(windows.items())` -> `list(windows.items())` in `describe` ->
  `test_describe_sorts_by_hwnd_and_renders_title_before_class` red, 1 test
  (`Ran 9 tests ... FAILED (failures=1)`).  The fixture is deliberately out of
  insertion order, so an unsorted render cannot pass by luck.
- `appeared_titles` regex: `_QUOTED` -> `r"'([^']*)'"` -> **1 test** red
  (`test_titles_come_out_of_the_payload_in_order`).  The two empty-input tests stay
  green: `findall` still answers `[]` for `""` / `None` under either pattern.
- `appeared_titles` guard: drop the `or ""` in `findall(line or "")` -> **1 test**
  red (`test_none_input_yields_an_empty_list`), the title test stays green.  The two
  mutations are deliberately separate because neither one alone covers both halves.
- `describe` unpack: `(pid, cls, title)` -> `(cls, pid, title)` -> the render test
  red (title-before-class is asserted).
- `shoot`: return the whole `shoot_verbose` tuple instead of its first element ->
  **2 tests** red (`test_shoot_returns_only_the_boolean` +
  `test_a_failed_shot_is_false_not_truthy`, `Ran 9 tests ... FAILED (failures=2)`).
  Both are in `ShootTest` and both judge the same return type, so this is not
  cross-group contamination -- it is just a mutation two tests are entitled to see.
"""

from __future__ import annotations

import unittest
from unittest import mock

from ctl import screen


class AppearedTitlesTest(unittest.TestCase):
    def test_titles_come_out_of_the_payload_in_order(self) -> None:
        """The bridge quotes each dialog title; order is the appearance order."""
        line = 'dialog=appeared "Problem Occurred", "Reset Perspective"'
        self.assertEqual(["Problem Occurred", "Reset Perspective"],
                         screen.appeared_titles(line))

    def test_a_line_without_quoted_titles_yields_nothing(self) -> None:
        """`dialog=appeared` with no list is not one dialog titled by the rest."""
        self.assertEqual([], screen.appeared_titles("dialog=appeared"))

    def test_empty_input_yields_an_empty_list(self) -> None:
        self.assertEqual([], screen.appeared_titles(""))

    def test_none_input_yields_an_empty_list(self) -> None:
        """A missing payload must not raise `TypeError` into the action path."""
        self.assertEqual([], screen.appeared_titles(None))


class DescribeTest(unittest.TestCase):
    def test_an_empty_map_is_not_an_empty_string(self) -> None:
        """The caller prints this straight; `""` would read as "no output"."""
        self.assertEqual("0 window(s)", screen.describe({}))

    def test_describe_sorts_by_hwnd_and_renders_title_before_class(self) -> None:
        """Insertion order is irrelevant; the render is `hwnd "title" (class, pid=N)`.

        hwnds chosen so string order (`0x10` < `0x20`) differs from the order the
        mapping was built in -- an unsorted render cannot accidentally pass.
        """
        windows = {
            "0x20": (101, "#32770", "Second"),
            "0x10": (55, "SWT_Window0", "First"),
        }
        self.assertEqual(
            '2 window(s): 0x10 "First" (SWT_Window0, pid=55), '
            '0x20 "Second" (#32770, pid=101)',
            screen.describe(windows))


class ShootTest(unittest.TestCase):
    def test_shoot_returns_only_the_boolean(self) -> None:
        """`shoot` is `shoot_verbose`'s first element, not the tuple.

        Leaking the note would turn a truthiness check into a constant `True`.
        """
        with mock.patch.object(screen, "shoot_verbose",
                               return_value=(True, "note")) as verbose:
            result = screen.shoot("Title", "out.png")
        self.assertIs(True, result)
        self.assertNotIsInstance(result, tuple)
        self.assertEqual(("Title", "out.png", 60.0), verbose.call_args.args)

    def test_shoot_forwards_flags_and_pids_unchanged(self) -> None:
        """The scope knobs must reach the tool call verbatim, not be re-invented."""
        with mock.patch.object(screen, "shoot_verbose",
                               return_value=(True, "note")) as verbose:
            screen.shoot("Title", "out.png", flags=3, pids=[7])
        self.assertEqual({"flags": 3, "pids": [7]}, verbose.call_args.kwargs)

    def test_a_failed_shot_is_false_not_truthy(self) -> None:
        """The boolean is the tool's verdict, not `shoot_verbose` having returned."""
        with mock.patch.object(screen, "shoot_verbose",
                               return_value=(False, "boom")):
            self.assertIs(False, screen.shoot("Title", "out.png"))


if __name__ == "__main__":
    unittest.main()
