"""Regression: the console blacklist must not be defeated by whitespace.

`command_is_dangerous()` matched the five bare commands via `text.split()[0]`
(a word match) but matched the flag entry `threads -t` via a raw substring test.
Two different strengths inside one control, so a whitespace variant slipped
through: `threads  -t` (double space) and `threads<TAB>-t` both returned False
(measurement-hygiene 13.7 -- one contract, two call sites, only one of them
actually held).

failing-before: `command_is_dangerous("threads  -t") is False`.
passing-after:  every whitespace variant is refused.
"""

import unittest

from ctl.console import command_is_dangerous


class DangerousCommandWhitespaceTest(unittest.TestCase):
    def test_bare_commands_are_refused(self):
        for name in ("init", "close", "shutdown", "exit", "gc"):
            with self.subTest(name=name):
                self.assertTrue(command_is_dangerous(name))

    def test_flag_survives_whitespace_variants(self):
        for raw in ("threads -t", "threads  -t", "threads\t-t", "  threads   -t  "):
            with self.subTest(raw=raw):
                self.assertTrue(command_is_dangerous(raw))

    def test_ordinary_lines_are_allowed(self):
        for raw in ("", "   ", "threads", "help", "ss", "bundle 1"):
            with self.subTest(raw=raw):
                self.assertFalse(command_is_dangerous(raw))


if __name__ == "__main__":
    unittest.main()
